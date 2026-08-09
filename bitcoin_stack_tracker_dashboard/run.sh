#!/usr/bin/with-contenv bashio
set -Eeuo pipefail

export LOG_LEVEL="$(bashio::config 'log_level')"
export TOR_HOST="127.0.0.1"
export TOR_PORT="9050"
export TOR_SHARED_PORT="9051"
export NETWORK_STATUS_FILE="/run/bitcoin-stack-network-status.json"
export NETWORK_STOP_FILE="/run/bitcoin-stack-network-agent-stop"
NETWORK_AGENT_STOP_FILE="${NETWORK_STOP_FILE}"

NFT_FAMILY="inet"
NFT_TABLE="bst_only_tor"
NFT_CHAIN="output"
NFT_INPUT_CHAIN="input"
TOR_PID=""
APP_PID=""
FIREWALL_ACTIVE="false"
FIREWALL_IPV4="false"
FIREWALL_IPV6="false"
IPV6_DISABLED="false"
FIREWALL_ERROR=""
FIREWALL_CHECK_ERROR=""
LAST_FW_STATE=""
SHUTDOWN_REQUESTED="false"
CLEANUP_DONE="false"
FINAL_EXIT_STATUS=1

TOR_UID="$(id -u tor)"
APP_UID="$(id -u bitcointracker)"

pid_is_running() {
  # A zombie still has /proc/<pid>, but it has already exited and only needs to
  # be reaped with wait. Treat Z/X as stopped so shutdown never waits forever.
  local pid="${1:-}"
  local state=""
  [[ "${pid}" =~ ^[0-9]+$ ]] || return 1
  [[ -r "/proc/${pid}/stat" ]] || return 1
  state="$(awk '{print $3}' "/proc/${pid}/stat" 2>/dev/null || true)"
  [[ -n "${state}" && "${state}" != "Z" && "${state}" != "X" ]]
}

shutdown_pending() {
  [[ "${SHUTDOWN_REQUESTED}" == "true" || -e /run/bitcoin-stack-manual-stop ]]
}

signal_pid_checked() {
  # Do not hide signal permission failures. Tor deliberately runs under a
  # different uid, so AppArmor must grant CAP_KILL to this root gateway.
  local pid="${1:-}"
  local signal_name="${2:-TERM}"
  local label="${3:-managed process}"
  [[ "${pid}" =~ ^[0-9]+$ ]] || return 1
  if kill "-${signal_name}" "${pid}" 2>/dev/null; then
    return 0
  fi
  bashio::log.warning "Could not send ${signal_name} to ${label} pid=${pid}"
  return 1
}

child_pids() {
  local parent="${1:-}"
  local status pid ppid
  [[ "${parent}" =~ ^[0-9]+$ ]] || return 0
  for status in /proc/[0-9]*/status; do
    [[ -r "${status}" ]] || continue
    pid="${status#/proc/}"
    pid="${pid%/status}"
    ppid="$(awk '$1 == "PPid:" { print $2; exit }' "${status}" 2>/dev/null || true)"
    if [[ "${ppid}" == "${parent}" ]]; then
      printf '%s\n' "${pid}"
    fi
  done
}

signal_process_tree() {
  # Walk descendants first, then the root. This keeps shutdown bounded
  # even if a managed process has spawned helper children.
  local root="${1:-}"
  local signal_name="${2:-TERM}"
  local child
  [[ "${root}" =~ ^[0-9]+$ ]] || return 0
  while IFS= read -r child; do
    [[ -n "${child}" ]] || continue
    signal_process_tree "${child}" "${signal_name}"
  done < <(child_pids "${root}")
  signal_pid_checked "${root}" "${signal_name}" "managed child" || true
}

terminate_pid_bounded() {
  local pid="${1:-}"
  local term_loops="${2:-40}"
  local kill_loops="${3:-20}"
  local attempts=0
  [[ "${pid}" =~ ^[0-9]+$ ]] || return 0

  if pid_is_running "${pid}"; then
    signal_process_tree "${pid}" TERM
  fi
  while pid_is_running "${pid}" && (( attempts < term_loops )); do
    sleep 0.05 || true
    attempts=$((attempts + 1))
  done
  if pid_is_running "${pid}"; then
    signal_process_tree "${pid}" KILL
    attempts=0
    while pid_is_running "${pid}" && (( attempts < kill_loops )); do
      sleep 0.05 || true
      attempts=$((attempts + 1))
    done
  fi
  if ! pid_is_running "${pid}"; then
    wait "${pid}" 2>/dev/null || true
  fi
}

managed_process_pids() {
  # Report only live managed processes. Zombies are already dead and are reaped
  # by s6/PID 1; treating them as running can keep shutdown loops alive.
  local status pid uid comm state
  for status in /proc/[0-9]*/status; do
    [[ -r "${status}" ]] || continue
    pid="${status#/proc/}"
    pid="${pid%/status}"
    [[ "${pid}" =~ ^[0-9]+$ ]] || continue
    [[ "${pid}" != "1" && "${pid}" != "$$" ]] || continue
    state="$(awk '$1 == "State:" { print $2; exit }' "${status}" 2>/dev/null || true)"
    [[ -n "${state}" && "${state}" != "Z" && "${state}" != "X" ]] || continue
    uid="$(awk '$1 == "Uid:" { print $2; exit }' "${status}" 2>/dev/null || true)"
    comm="$(cat "/proc/${pid}/comm" 2>/dev/null || true)"
    if [[ "${uid}" == "${APP_UID}" || "${uid}" == "${TOR_UID}" ]]; then
      printf '%s\n' "${pid}"
    fi
  done
}

managed_process_details() {
  local pid status state uid ppid comm
  while IFS= read -r pid; do
    [[ "${pid}" =~ ^[0-9]+$ ]] || continue
    status="/proc/${pid}/status"
    [[ -r "${status}" ]] || continue
    state="$(awk '$1 == "State:" { print $2; exit }' "${status}" 2>/dev/null || true)"
    uid="$(awk '$1 == "Uid:" { print $2; exit }' "${status}" 2>/dev/null || true)"
    ppid="$(awk '$1 == "PPid:" { print $2; exit }' "${status}" 2>/dev/null || true)"
    comm="$(cat "/proc/${pid}/comm" 2>/dev/null || true)"
    printf 'pid=%s comm=%s state=%s ppid=%s uid=%s\n' "${pid}" "${comm:-?}" "${state:-?}" "${ppid:-?}" "${uid:-?}"
  done < <(managed_process_pids)
}

terminate_remaining_managed_processes() {
  # s6-overlay gives legacy service shutdown a short stop budget. Keep this
  # final sweep deliberately sub-second so run.sh always returns before
  # s6-svwait's own timeout. The nftables killswitch remains installed unless
  # every managed process is gone, so shortening the wait never opens Clearnet.
  local signal_name pid attempts remaining
  for signal_name in TERM KILL; do
    while IFS= read -r pid; do
      [[ "${pid}" =~ ^[0-9]+$ ]] || continue
      signal_pid_checked "${pid}" "${signal_name}" "managed network process" || true
    done < <(managed_process_pids)

    attempts=0
    while (( attempts < 5 )); do
      remaining="$(managed_process_pids)"
      [[ -z "${remaining}" ]] && break
      sleep 0.04 || true
      attempts=$((attempts + 1))
    done
    [[ -z "$(managed_process_pids)" ]] && break
  done

  remaining="$(managed_process_pids)"
  if [[ -n "${remaining}" ]]; then
    bashio::log.info "Managed process still visible after fast final cleanup; killswitch stays active until namespace exit: $(managed_process_details | tr '\n' ';' | sed 's/;$//')"
  fi
}

stop_health_agent() {
  local app_pid="${APP_PID}"
  local attempts=0
  if [[ ! "${app_pid}" =~ ^[0-9]+$ ]]; then
    APP_PID=""
    return 0
  fi

  : > "${NETWORK_AGENT_STOP_FILE}"
  if pid_is_running "${app_pid}"; then
    signal_process_tree "${app_pid}" TERM
  fi
  # The agent polls the stop marker frequently; give it only ~0.4 s before
  # escalation so the complete legacy-service stop stays below s6's 5 s limit.
  while pid_is_running "${app_pid}" && (( attempts < 8 )); do
    sleep 0.05 || true
    attempts=$((attempts + 1))
  done
  if pid_is_running "${app_pid}"; then
    bashio::log.info "Network health agent did not stop promptly; terminating it inside shutdown budget"
    signal_process_tree "${app_pid}" KILL
    attempts=0
    while pid_is_running "${app_pid}" && (( attempts < 4 )); do
      sleep 0.05 || true
      attempts=$((attempts + 1))
    done
  fi
  if ! pid_is_running "${app_pid}"; then
    wait "${app_pid}" 2>/dev/null || true
  fi
  APP_PID=""
}



nft_counter() {
  local marker="$1"
  nft list chain "${NFT_FAMILY}" "${NFT_TABLE}" "${NFT_CHAIN}" 2>/dev/null \
    | awk -v marker="${marker}" '
      index($0, "comment \"" marker "\"") {
        for (i = 1; i <= NF; i++) {
          if ($i == "packets") { sum += $(i + 1) }
        }
      }
      END { print sum + 0 }
    '
}

tor_process_is_running() {
  # TOR_PID is normally the foreground Tor process. pgrep is a fallback for
  # implementations that re-parent after dropping privileges. The Unix socket
  # is accepted as current evidence too, because it cannot exist before Tor has
  # opened its listener.
  if pid_is_running "${TOR_PID}"; then
    return 0
  fi
  local comm
  for comm in /proc/[0-9]*/comm; do
    if [[ -r "${comm}" ]] && [[ "$(cat "${comm}" 2>/dev/null || true)" == "tor" ]]; then
      return 0
    fi
  done
  return 1
}

tor_process_pids() {
  # Return every live Tor process owned by the dedicated Tor UID. This is used
  # as a recovery fallback only; TOR_PID remains the primary process handle.
  local status pid uid comm state
  for status in /proc/[0-9]*/status; do
    [[ -r "${status}" ]] || continue
    pid="${status#/proc/}"
    pid="${pid%/status}"
    [[ "${pid}" =~ ^[0-9]+$ ]] || continue
    uid="$(awk '$1 == "Uid:" { print $2; exit }' "${status}" 2>/dev/null || true)"
    [[ "${uid}" == "${TOR_UID}" ]] || continue
    state="$(awk '$1 == "State:" { print $2; exit }' "${status}" 2>/dev/null || true)"
    [[ -n "${state}" && "${state}" != "Z" && "${state}" != "X" ]] || continue
    comm="$(cat "/proc/${pid}/comm" 2>/dev/null || true)"
    [[ "${comm}" == "tor" ]] || continue
    printf '%s\n' "${pid}"
  done
}

wait_for_tor_socket() {
  local attempts=0
  while (( attempts < 100 )); do
    shutdown_pending && return 1
    if tcp_socks_listener_ready; then
      return 0
    fi
    if ! tor_process_is_running; then
      return 1
    fi
    sleep 0.1
    attempts=$((attempts + 1))
  done
  return 1
}


write_status() {
  local blocked4 blocked6 tor_running
  blocked4="$(nft_counter BST_BLOCK_IPV4 || printf '0')"
  blocked6="$(nft_counter BST_BLOCK_IPV6 || printf '0')"
  tor_running="false"
  if tor_process_is_running; then
    tor_running="true"
  fi
  BST_FW_ACTIVE="${FIREWALL_ACTIVE}" \
  BST_FW_IPV4="${FIREWALL_IPV4}" \
  BST_FW_IPV6="${FIREWALL_IPV6}" \
  BST_IPV6_DISABLED="${IPV6_DISABLED}" \
  BST_FW_ERROR="${FIREWALL_ERROR}" \
  BST_BLOCKED4="${blocked4:-0}" \
  BST_BLOCKED6="${blocked6:-0}" \
  BST_TOR_RUNNING="${tor_running}" \
  BST_APP_UID="${APP_UID}" \
  BST_TOR_UID="${TOR_UID}" \
  BST_STATUS_FILE="${NETWORK_STATUS_FILE}" \
  python3 - <<'PY'
import ipaddress
import json
import os
from datetime import datetime, timezone
from pathlib import Path

LOCAL_NETWORKS = tuple(
    ipaddress.ip_network(value)
    for value in (
        "10.0.0.0/8", "127.0.0.0/8", "169.254.0.0/16",
        "172.16.0.0/12", "192.168.0.0/16", "::1/128",
        "fc00::/7", "fe80::/10",
    )
)


def decode_address(raw: str, ipv6: bool) -> ipaddress._BaseAddress:
    value = bytes.fromhex(raw)
    if ipv6:
        value = b"".join(value[index:index + 4][::-1] for index in range(0, 16, 4))
        return ipaddress.IPv6Address(value)
    return ipaddress.IPv4Address(value[::-1])


def socket_rows() -> list[tuple[int, ipaddress._BaseAddress, int]]:
    rows: list[tuple[int, ipaddress._BaseAddress, int]] = []
    for filename, ipv6, tcp in (
        ("/proc/net/tcp", False, True),
        ("/proc/net/tcp6", True, True),
        ("/proc/net/udp", False, False),
        ("/proc/net/udp6", True, False),
    ):
        try:
            lines = Path(filename).read_text(encoding="ascii").splitlines()[1:]
        except OSError:
            continue
        for line in lines:
            fields = line.split()
            if len(fields) < 8:
                continue
            remote, state, uid_text = fields[2], fields[3], fields[7]
            try:
                uid = int(uid_text)
                address_hex, port_hex = remote.split(":", 1)
                port = int(port_hex, 16)
                address = decode_address(address_hex, ipv6)
            except (ValueError, IndexError):
                continue
            if port == 0:
                continue
            if tcp and state not in {"01", "02", "03"}:
                continue
            rows.append((uid, address, port))
    return rows


def is_local(address: ipaddress._BaseAddress) -> bool:
    return any(address in network for network in LOCAL_NETWORKS)


def target(address: ipaddress._BaseAddress, port: int) -> str:
    return f"{address.compressed}:{port}"


tor_uid = int(os.environ["BST_TOR_UID"])
app_uid = int(os.environ["BST_APP_UID"])
rows = socket_rows()
public_sockets = sorted({
    target(address, port)
    for uid, address, port in rows
    if uid != tor_uid and not is_local(address)
})
tor_public_sockets = sorted({
    target(address, port)
    for uid, address, port in rows
    if uid == tor_uid and not is_local(address)
})
app_local_sockets = sorted({
    target(address, port)
    for uid, address, port in rows
    if uid == app_uid and is_local(address)
})
path = Path(os.environ["BST_STATUS_FILE"])
payload = {
    "firewall_active": os.environ["BST_FW_ACTIVE"] == "true",
    "firewall_ipv4": os.environ["BST_FW_IPV4"] == "true",
    "firewall_ipv6": os.environ["BST_FW_IPV6"] == "true",
    "ipv6_disabled": os.environ["BST_IPV6_DISABLED"] == "true",
    "firewall_backend": "nftables",
    "firewall_error": os.environ.get("BST_FW_ERROR") or None,
    "blocked_ipv4_packets": int(os.environ.get("BST_BLOCKED4", "0") or 0),
    "blocked_ipv6_packets": int(os.environ.get("BST_BLOCKED6", "0") or 0),
    "tor_process_running": os.environ["BST_TOR_RUNNING"] == "true",
    "non_tor_public_socket_count": len(public_sockets),
    "non_tor_public_socket_targets": public_sockets[:10],
    "tor_public_socket_targets": tor_public_sockets[:12],
    "app_local_socket_targets": app_local_sockets[:12],
    "clearnet_leak_detected": bool(public_sockets),
    "policy": "local direct or Tor only; public direct traffic is dropped by nftables",
    "updated_at": datetime.now(timezone.utc).isoformat(),
}
tmp = path.with_suffix(".tmp")
tmp.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
tmp.replace(path)
PY
}

homeassistant_ipv4() {
  local value=""
  value="$(getent ahostsv4 homeassistant 2>/dev/null | awk '$1 ~ /^[0-9.]+$/ { print $1; exit }')"
  if [[ -z "${value}" ]]; then
    value="$(getent hosts homeassistant 2>/dev/null | awk '$1 ~ /^[0-9.]+$/ { print $1; exit }')"
  fi
  printf '%s' "${value}"
}

apply_firewall() {
  local error_file="/tmp/bitcoin-stack-nft-error.log"
  FIREWALL_ACTIVE="false"
  FIREWALL_IPV4="false"
  FIREWALL_IPV6="false"
  IPV6_DISABLED="false"
  FIREWALL_ERROR=""
  HOMEASSISTANT_IP="$(homeassistant_ipv4)"
  if [[ -z "${HOMEASSISTANT_IP}" ]]; then
    FIREWALL_ERROR="Home Assistant Core IPv4 could not be resolved; refusing to open SOCKS 9050"
    return 1
  fi

  if ! command -v nft >/dev/null 2>&1; then
    FIREWALL_ERROR="nft command is unavailable"
    return 1
  fi

  nft delete table "${NFT_FAMILY}" "${NFT_TABLE}" >/dev/null 2>&1 || true

  if ! nft -f - 2>"${error_file}" <<NFT
 table ${NFT_FAMILY} ${NFT_TABLE} {
   set local_v4 {
     type ipv4_addr
     flags interval
     elements = { 10.0.0.0/8, 127.0.0.0/8, 169.254.0.0/16, 172.16.0.0/12, 192.168.0.0/16 }
   }
   set local_v6 {
     type ipv6_addr
     flags interval
     elements = { ::1/128, fc00::/7, fe80::/10 }
   }
   chain ${NFT_INPUT_CHAIN} {
     type filter hook input priority filter; policy drop;

     iifname "lo" counter accept comment "BST_INPUT_LOOPBACK"
     ct state established,related counter accept comment "BST_INPUT_ESTABLISHED"
     ip saddr ${HOMEASSISTANT_IP} tcp dport ${TOR_PORT} counter accept comment "BST_SOCKS_CORE_ONLY"
     ip saddr 172.30.32.0/23 tcp dport ${TOR_SHARED_PORT} counter accept comment "BST_SOCKS_SHARED_INTERNAL"
     ip saddr 172.30.32.0/23 tcp dport 8099 counter accept comment "BST_HEALTH_INTERNAL"
     tcp dport ${TOR_PORT} counter reject comment "BST_SOCKS_BLOCK_EXTERNAL"
     tcp dport ${TOR_SHARED_PORT} counter reject comment "BST_SHARED_SOCKS_BLOCK_EXTERNAL"
   }
   chain ${NFT_CHAIN} {
     type filter hook output priority filter; policy drop;

     oifname "lo" counter accept comment "BST_LOOPBACK"
     ct state established,related counter accept comment "BST_ESTABLISHED_REPLY"
     # Never let the Tor process or any other container process use the gateway
     # as a path into RFC1918/link-local networks. Shared SOCKS is Internet-only.
     ip daddr @local_v4 counter reject comment "BST_BLOCK_LOCAL_IPV4"
     ip6 daddr @local_v6 counter reject comment "BST_BLOCK_LOCAL_IPV6"

     # Only Tor itself may establish non-local outbound connections.
     meta skuid ${TOR_UID} counter accept comment "BST_TOR_PUBLIC"

     # The network health agent is read-only and may answer inbound health
     # checks, but it may not initiate any network connection at all.
     meta skuid ${APP_UID} counter reject comment "BST_AGENT_NO_EGRESS"

     meta nfproto ipv4 counter reject comment "BST_BLOCK_IPV4"
     meta nfproto ipv6 counter reject comment "BST_BLOCK_IPV6"
     counter reject comment "BST_BLOCK_OTHER"
   }
 }
NFT
  then
    FIREWALL_ERROR="$(tr '\n' ' ' <"${error_file}" | sed 's/[[:space:]]\+/ /g; s/^ //; s/ $//')"
    [[ -n "${FIREWALL_ERROR}" ]] || FIREWALL_ERROR="nftables ruleset could not be installed"
    nft delete table "${NFT_FAMILY}" "${NFT_TABLE}" >/dev/null 2>&1 || true
    return 1
  fi

  if ! nft list table "${NFT_FAMILY}" "${NFT_TABLE}" >/dev/null 2>"${error_file}"; then
    FIREWALL_ERROR="nftables table verification failed: $(tr '\n' ' ' <"${error_file}")"
    return 1
  fi

  FIREWALL_IPV4="true"
  FIREWALL_IPV6="true"
  FIREWALL_ACTIVE="true"
  return 0
}

firewall_still_active() {
  # Do not use `nft | grep -q` while `pipefail` is enabled. grep -q closes the
  # pipe as soon as it finds a match; nft can then exit with SIGPIPE (141),
  # which incorrectly looks like a failed firewall check. That false negative
  # A failed pipeline check must never stop Tor during startup or remove its control socket
  # and forget the real Tor PID even though Tor itself kept running.
  local output_chain=""
  local input_chain=""
  FIREWALL_CHECK_ERROR=""

  if ! nft list table "${NFT_FAMILY}" "${NFT_TABLE}" >/dev/null 2>&1; then
    FIREWALL_CHECK_ERROR="nftables table ${NFT_FAMILY}/${NFT_TABLE} is missing"
    return 1
  fi
  if ! output_chain="$(nft list chain "${NFT_FAMILY}" "${NFT_TABLE}" "${NFT_CHAIN}" 2>/dev/null)"; then
    FIREWALL_CHECK_ERROR="nftables output chain could not be read"
    return 1
  fi
  if ! input_chain="$(nft list chain "${NFT_FAMILY}" "${NFT_TABLE}" "${NFT_INPUT_CHAIN}" 2>/dev/null)"; then
    FIREWALL_CHECK_ERROR="nftables input chain could not be read"
    return 1
  fi

  case "${output_chain}" in *'policy drop'*) ;; *) FIREWALL_CHECK_ERROR="output chain lost policy drop"; return 1 ;; esac
  case "${output_chain}" in *'comment "BST_TOR_PUBLIC"'*) ;; *) FIREWALL_CHECK_ERROR="Tor-only output rule is missing"; return 1 ;; esac
  case "${output_chain}" in *'comment "BST_AGENT_NO_EGRESS"'*) ;; *) FIREWALL_CHECK_ERROR="network-agent no-egress rule is missing"; return 1 ;; esac
  case "${output_chain}" in *'comment "BST_BLOCK_IPV4"'*) ;; *) FIREWALL_CHECK_ERROR="IPv4 public-block rule is missing"; return 1 ;; esac
  case "${output_chain}" in *'comment "BST_BLOCK_IPV6"'*) ;; *) FIREWALL_CHECK_ERROR="IPv6 public-block rule is missing"; return 1 ;; esac
  case "${input_chain}" in *'policy drop'*) ;; *) FIREWALL_CHECK_ERROR="input chain lost policy drop"; return 1 ;; esac
  case "${input_chain}" in *'comment "BST_SOCKS_CORE_ONLY"'*) ;; *) FIREWALL_CHECK_ERROR="Core-only SOCKS allow rule is missing"; return 1 ;; esac
  case "${input_chain}" in *'comment "BST_SOCKS_SHARED_INTERNAL"'*) ;; *) FIREWALL_CHECK_ERROR="shared SOCKS allow rule is missing"; return 1 ;; esac
  case "${input_chain}" in *'comment "BST_HEALTH_INTERNAL"'*) ;; *) FIREWALL_CHECK_ERROR="health endpoint allow rule is missing"; return 1 ;; esac
  case "${input_chain}" in *'comment "BST_SOCKS_BLOCK_EXTERNAL"'*) ;; *) FIREWALL_CHECK_ERROR="external SOCKS block rule is missing"; return 1 ;; esac
  return 0
}

container_ipv4() {
  local value
  value="$(ip -4 -o addr show scope global 2>/dev/null \
    | awk '$2 != "lo" { split($4, parts, "/"); print parts[1]; exit }')"
  if [[ -z "${value}" ]]; then
    value="$(hostname -i 2>/dev/null | awk '{ print $1 }')"
  fi
  printf '%s' "${value}"
}

tcp_socks_listener_ready() {
  python3 - <<'PYTCP' >/dev/null 2>&1
import socket
try:
    for port in (9050, 9051):
        with socket.create_connection(("127.0.0.1", port), timeout=0.25):
            pass
except OSError:
    raise SystemExit(1)
PYTCP
}

render_runtime_torrc() {
  local container_ip
  container_ip="$(container_ipv4)"
  if [[ -z "${container_ip}" ]]; then
    bashio::log.error "Could not determine the internal app IPv4 address for Tor SOCKS5"
    return 1
  fi
  sed "s/__CONTAINER_IP__/${container_ip}/g" /etc/tor/torrc > /run/bitcoin-stack-tor/torrc
  chown tor:tor /run/bitcoin-stack-tor/torrc
  chmod 0640 /run/bitcoin-stack-tor/torrc
}

start_tor() {
  if shutdown_pending; then
    return 1
  fi
  if [[ "${FIREWALL_ACTIVE}" != "true" ]]; then
    return 1
  fi
  rm -f /run/bitcoin-stack-tor/torrc /run/bitcoin-stack-tor/tor.pid
  mkdir -p /data/tor /run/bitcoin-stack-tor
  chown tor:tor /data/tor /run/bitcoin-stack-tor
  chmod 0700 /data/tor
  chmod 0750 /run/bitcoin-stack-tor
  if ! render_runtime_torrc; then
    return 1
  fi
  if ! su-exec tor:tor /usr/bin/tor --verify-config -f /run/bitcoin-stack-tor/torrc; then
    bashio::log.error "Bundled Tor configuration is invalid; app remains local/cache-only"
    return 1
  fi
  bashio::log.info "Starting bundled Tor behind the nftables killswitch"
  su-exec tor:tor /usr/bin/tor -f /run/bitcoin-stack-tor/torrc &
  TOR_PID=$!
  # Tor also writes its authoritative PID. su-exec normally preserves $!, but
  # using the PidFile removes ambiguity on s6/container shutdown.
  pid_wait=0
  while (( pid_wait < 30 )); do
    if [[ -r /run/bitcoin-stack-tor/tor.pid ]]; then
      runtime_tor_pid="$(cat /run/bitcoin-stack-tor/tor.pid 2>/dev/null || true)"
      if [[ "${runtime_tor_pid}" =~ ^[0-9]+$ ]]; then TOR_PID="${runtime_tor_pid}"; break; fi
    fi
    sleep 0.05 || true
    pid_wait=$((pid_wait + 1))
  done
  write_status
  if ! wait_for_tor_socket; then
    bashio::log.error "Bundled Tor did not create its protected TCP SOCKS listeners"
    terminate_pid_bounded "${TOR_PID}" 40 20
    TOR_PID=""
    write_status
    return 1
  fi
  shutdown_pending && return 1
  bashio::log.info "Restricted Tor SOCKS5 listeners ready for Home Assistant Core"
  write_status

  bashio::log.info "Tor SOCKS isolation uses IsolateSOCKSAuth; no Tor ControlSocket is exposed"
  write_status
  return 0
}


signal_all_tor_processes() {
  local signal_name="${1:-TERM}"
  local pid=""
  if [[ "${TOR_PID}" =~ ^[0-9]+$ ]]; then
    signal_pid_checked "${TOR_PID}" "${signal_name}" "Tor" || true
  fi
  while IFS= read -r pid; do
    [[ "${pid}" =~ ^[0-9]+$ ]] || continue
    [[ "${pid}" == "${TOR_PID}" ]] && continue
    signal_pid_checked "${pid}" "${signal_name}" "Tor" || true
  done < <(tor_process_pids)
}

stop_tor() {
  local tor_pid="${TOR_PID}"
  local runtime_pid=""
  local attempts=0
  local pid=""

  if [[ -r /run/bitcoin-stack-tor/tor.pid ]]; then
    runtime_pid="$(cat /run/bitcoin-stack-tor/tor.pid 2>/dev/null || true)"
    if [[ "${runtime_pid}" =~ ^[0-9]+$ ]]; then tor_pid="${runtime_pid}"; fi
  fi

  # Keep the whole Tor stop comfortably inside s6-overlay's legacy-service
  # timeout. TERM is Tor's normal process-termination path; if it does not
  # disappear quickly, KILL is preferable to letting s6-svwait time out.
  if [[ "${tor_pid}" =~ ^[0-9]+$ ]] && pid_is_running "${tor_pid}"; then
    signal_pid_checked "${tor_pid}" CONT "Tor" || true
    signal_pid_checked "${tor_pid}" TERM "Tor" || true
  fi
  signal_all_tor_processes TERM

  while [[ "${tor_pid}" =~ ^[0-9]+$ ]] && pid_is_running "${tor_pid}" && (( attempts < 16 )); do
    sleep 0.05 || true
    attempts=$((attempts + 1))
  done

  if [[ "${tor_pid}" =~ ^[0-9]+$ ]] && pid_is_running "${tor_pid}"; then
    signal_pid_checked "${tor_pid}" KILL "Tor" || true
  fi
  while IFS= read -r pid; do
    [[ "${pid}" =~ ^[0-9]+$ ]] || continue
    signal_pid_checked "${pid}" KILL "Tor" || true
  done < <(tor_process_pids)

  attempts=0
  while (( attempts < 5 )); do
    [[ -z "$(tor_process_pids)" ]] && break
    sleep 0.04 || true
    attempts=$((attempts + 1))
  done

  if [[ "${tor_pid}" =~ ^[0-9]+$ ]] && ! pid_is_running "${tor_pid}"; then
    wait "${tor_pid}" 2>/dev/null || true
  fi

  TOR_PID=""
  rm -f /run/bitcoin-stack-tor/tor.pid /run/bitcoin-stack-tor/torrc

  if [[ -n "$(tor_process_pids)" ]]; then
    return 1
  fi
  bashio::log.info "Bundled Tor stopped"
  return 0
}


request_shutdown() {
  if [[ "${SHUTDOWN_REQUESTED}" == "true" ]]; then
    return 0
  fi
  # Set both guards before logging or doing any work. The Tor watchdog checks
  # these markers and therefore cannot restart Tor once shutdown has begun.
  SHUTDOWN_REQUESTED="true"
  : > /run/bitcoin-stack-manual-stop
  : > "${NETWORK_AGENT_STOP_FILE}"
  bashio::log.info "Shutdown requested; stopping network health agent before Tor and firewall"
  return 0
}

cleanup() {
  local raw_status="${1:-1}"
  local status=1
  if [[ "${CLEANUP_DONE}" == "true" ]]; then
    return 0
  fi
  CLEANUP_DONE="true"

  case "${raw_status}" in
    ''|*[!0-9]*) status=1 ;;
    *) status="${raw_status}" ;;
  esac
  if [[ "${SHUTDOWN_REQUESTED}" == "true" ]]; then
    status=0
  fi

  # Ignore additional stop signals while cleanup is already in progress.
  trap '' INT TERM
  stop_health_agent
  bashio::log.info "Network health agent stopped; stopping bundled Tor"
  set +e
  stop_tor
  tor_stop_status=$?
  # The final bounded process cleanup is part of the normal stop.
  # path, not merely a dormant helper. This catches a Tor/helper process that
  # exits a fraction later than the primary PID without ever opening Clearnet.
  terminate_remaining_managed_processes
  remaining_managed="$(managed_process_pids)"
  set -e
  if [[ -z "${remaining_managed}" ]]; then
    nft delete table "${NFT_FAMILY}" "${NFT_TABLE}" >/dev/null 2>&1 || true
    if [[ "${tor_stop_status}" != "0" ]]; then
      bashio::log.info "Bundled Tor stopped during final bounded cleanup"
    fi
  else
    # Fail closed until the network namespace disappears. Removing the firewall
    # while a process is still visible would create a needless shutdown window.
    bashio::log.warning "Managed network process still visible after final cleanup; killswitch remains active until namespace exit: $(managed_process_details | tr '\n' ';' | sed 's/;$//')"
  fi
  FINAL_EXIT_STATUS="${status}"
  if [[ "${status}" == "0" ]]; then
    bashio::log.info "Bitcoin Stack Tracker Tor Gateway stopped cleanly"
  else
    bashio::log.error "Bitcoin Stack Tracker Tor Gateway stopped with exit code ${status}"
  fi
}

trap request_shutdown INT TERM

rm -f /run/bitcoin-stack-manual-stop "${NETWORK_AGENT_STOP_FILE}"

# A missing firewall is different from a Tor outage: without a kernel
# killswitch, local/cache-only operation cannot be guaranteed safely.
if ! apply_firewall; then
  write_status
  bashio::log.fatal "Only-Tor firewall could not be installed: ${FIREWALL_ERROR}"
  bashio::log.fatal "The Tor gateway is not started because direct Clearnet blocking cannot be guaranteed"
  exit 1
fi

bashio::log.info "Only-Tor nftables firewall active: only local networks and Tor UID ${TOR_UID} may leave the container"
write_status

bashio::log.info "Starting network-only health agent as unprivileged UID ${APP_UID}; no Home Assistant API token is present"
bashio::log.info "Tor outages are fail-closed for public Bitcoin Stack Tracker requests"
su-exec bitcointracker:tor /app/network_agent.py &
APP_PID=$!

start_tor || true
write_status

while pid_is_running "${APP_PID}"; do
  if shutdown_pending; then
    break
  fi

  if ! firewall_still_active; then
    # Require a second independent failure before touching Tor. This prevents a
    # transient nft read error from restarting a healthy Tor process.
    first_firewall_error="${FIREWALL_CHECK_ERROR}"
    sleep 0.2 || true
    if ! firewall_still_active; then
      FIREWALL_ACTIVE="false"
      FIREWALL_ERROR="nftables killswitch verification failed: ${FIREWALL_CHECK_ERROR:-${first_firewall_error}}"
      bashio::log.error "${FIREWALL_ERROR}"
      if ! stop_tor; then
        write_status
        bashio::log.fatal "Tor could not be stopped after a real killswitch failure; refusing unsafe recovery"
        kill -TERM "${APP_PID}" 2>/dev/null || true
        break
      fi
      if apply_firewall; then
        FIREWALL_ERROR=""
        start_tor || true
      else
        write_status
        bashio::log.fatal "Killswitch could not be restored: ${FIREWALL_ERROR}"
        kill -TERM "${APP_PID}" 2>/dev/null || true
        break
      fi
    fi
  fi

  if ! tor_process_is_running || ! tcp_socks_listener_ready; then
    bashio::log.warning "Bundled Tor or its protected SOCKS5 listener is unavailable; restarting it behind the active killswitch"
    stop_tor
    start_tor || true
  fi

  if [[ "${LAST_FW_STATE}" != "${FIREWALL_ACTIVE}" ]]; then
    bashio::log.info "Firewall killswitch verified"
    LAST_FW_STATE="${FIREWALL_ACTIVE}"
  fi
  write_status
  # Stay responsive to Docker/Supervisor TERM instead of sleeping for a full
  # five-second monitor interval.
  monitor_tick=0
  while (( monitor_tick < 50 )); do
    shutdown_pending && break
    sleep 0.1 || true
    monitor_tick=$((monitor_tick + 1))
  done
done

if shutdown_pending; then
  cleanup 0
  exit "${FINAL_EXIT_STATUS}"
fi

set +e
wait "${APP_PID}"
APP_STATUS=$?
set -e
APP_PID=""
# A health agent that disappears while no operator/system shutdown is pending
# is an actual service failure, even if Python happened to return status 0.
# Classify that here so the s6 finish script can trust a zero run.sh exit as a
# deliberate clean stop instead of trying to infer intent from timing races.
if [[ "${APP_STATUS}" == "0" ]]; then
  bashio::log.error "Network health agent exited unexpectedly while the gateway was meant to stay running"
  APP_STATUS=1
fi
cleanup "${APP_STATUS}"
exit "${FINAL_EXIT_STATUS}"
