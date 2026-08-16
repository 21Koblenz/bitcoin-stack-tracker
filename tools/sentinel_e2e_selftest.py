#!/usr/bin/env python3
"""Runtime-style Sats Sentinel self-test without a Home Assistant installation.

Exercises real wallet_watch.py code for:
- XPUB/ZPUB classification + derivation
- exact Fulcrum TCP server.version probe
- saved monitor transaction overview lookup
- monitor deletion + encrypted-journal purge path
- Fulcrum source preservation after monitor deletion
"""
from __future__ import annotations
import asyncio, importlib.util, json, sys, types, ssl, tempfile
from copy import deepcopy
from pathlib import Path
from datetime import datetime, timedelta, timezone
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

ROOT = Path(__file__).resolve().parents[1]
COMP = ROOT / "custom_components" / "bitcoin_stack_tracker"
RPC_METHODS = []
USED_SCRIPTHASHES = set()


def install_stubs():
    # minimal package shells
    for name in ["custom_components", "custom_components.bitcoin_stack_tracker"]:
        if name not in sys.modules:
            mod = types.ModuleType(name); mod.__path__ = []
            sys.modules[name] = mod
    ha = types.ModuleType("homeassistant"); sys.modules["homeassistant"] = ha
    ce = types.ModuleType("homeassistant.config_entries"); ce.ConfigEntry = object; sys.modules[ce.__name__] = ce
    core = types.ModuleType("homeassistant.core"); core.HomeAssistant = object; sys.modules[core.__name__] = core
    helpers = types.ModuleType("homeassistant.helpers"); helpers.__path__=[]; sys.modules[helpers.__name__]=helpers
    event = types.ModuleType("homeassistant.helpers.event"); event.async_track_time_interval=lambda *a,**k: (lambda: None); sys.modules[event.__name__]=event
    storage = types.ModuleType("homeassistant.helpers.storage")
    class Store:
        # Home Assistant Store persists by storage key across integration object
        # recreation. Model that explicitly so the self-test can simulate a real
        # Home Assistant restart instead of accidentally testing one Python object.
        _values = {}
        def __init__(self,*a,**k): self.key=str(a[-1]) if a else str(k.get("key") or "default")
        @classmethod
        def __class_getitem__(cls, item): return cls
        async def async_load(self): return deepcopy(self._values.get(self.key))
        async def async_save(self, value): self._values[self.key]=deepcopy(value)
        async def async_remove(self): self._values.pop(self.key,None)
    storage.Store=Store; sys.modules[storage.__name__]=storage

    const=types.ModuleType("custom_components.bitcoin_stack_tracker.const")
    for k,v in {
        "CONF_BASE_URL":"base_url", "CONF_MEMPOOL_OWN_INSTANCE":"own_instance", "CONF_MEMPOOL_ROUTE":"mempool_route",
        "CONF_SOURCE_TYPE":"source_type", "CONF_SOURCES":"sources", "CONF_VERIFY_SSL":"verify_ssl",
        "MEMPOOL_ROUTE_DIRECT":"direct", "MEMPOOL_ROUTE_TOR":"tor", "SOURCE_MEMPOOL":"mempool"
    }.items(): setattr(const,k,v)
    sys.modules[const.__name__]=const
    hp=types.ModuleType("custom_components.bitcoin_stack_tracker.helpers"); hp.effective_settings=lambda entry: getattr(entry,"data",{}) or {}; sys.modules[hp.__name__]=hp
    hl=types.ModuleType("custom_components.bitcoin_stack_tracker.http_limits")
    async def async_json_limited(*a,**k): raise RuntimeError("not used in selftest")
    hl.async_json_limited=async_json_limited; sys.modules[hl.__name__]=hl
    net=types.ModuleType("custom_components.bitcoin_stack_tracker.network")
    net.is_private_or_local_url=lambda url: any(x in str(url) for x in ("127.0.0.1","localhost","192.168.","10.","172.16."))
    net.is_onion_url=lambda url: ".onion" in str(url)
    net.automatic_mempool_route=lambda **kw: "direct"
    net.mempool_source_uses_tor=lambda src: False
    net.tor_proxy_from_settings=lambda settings: None
    async def async_tor_socks_connection_info(*a,**k): raise RuntimeError("Tor not used in selftest")
    net.async_tor_socks_connection_info=async_tor_socks_connection_info
    async def async_routed_session(*a,**k): raise RuntimeError("mempool HTTP not used in selftest")
    net.async_routed_session=async_routed_session
    sys.modules[net.__name__]=net


def load_wallet_watch():
    name="custom_components.bitcoin_stack_tracker.wallet_watch"
    spec=importlib.util.spec_from_file_location(name, COMP/"wallet_watch.py")
    mod=importlib.util.module_from_spec(spec); sys.modules[name]=mod
    assert spec.loader; spec.loader.exec_module(mod)
    return mod


class FakeHass:
    def __init__(self): self.data={}
    def async_create_task(self,*a,**k): return None

class FakeEntry:
    def __init__(self): self.data={}; self.options={}; self.entry_id="e2e"

class FakeLedger:
    def __init__(self, cfg): self._cfg=deepcopy(cfg); self.saves=0
    @property
    def wallet_watch_config(self): return deepcopy(self._cfg)
    async def async_set_wallet_watch_config(self,cfg): self._cfg=deepcopy(cfg); self.saves += 1
    async def async_device_binding_secret(self, *, create=True): return b"S"*32

class FakeRuntime:
    def __init__(self,data): self.data=deepcopy(data); self.saves=0
    async def async_save(self): self.saves += 1
    async def async_replace_from_full_config(self, config):
        # replaced after module load in test via bound implementation helper
        raise AssertionError("patched below")


def make_zpub(w):
    version=(0x04B24746).to_bytes(4,"big")
    depth=b"\x03"; parent=b"\xde\xad\xbe\xef"; child=(0x80000000).to_bytes(4,"big")
    chain=bytes(range(1,33)); pub=b"\x02" + w._G[0].to_bytes(32,"big")
    raw=version+depth+parent+child+chain+pub
    return w._b58encode(raw + w._sha256(w._sha256(raw))[:4])


async def electrum_server(reader, writer):
    try:
        while not reader.at_eof():
            line=await reader.readline()
            if not line: break
            req=json.loads(line)
            calls=req if isinstance(req,list) else [req]
            out=[]
            for call in calls:
                method=call.get("method"); RPC_METHODS.append(method)
                if method=="server.version": result=["Fulcrum 2.1.1","1.4"]
                elif method=="blockchain.scripthash.get_balance": result={"confirmed":123456,"unconfirmed":0}
                elif method=="blockchain.scripthash.get_history":
                    sh=str((call.get("params") or [""])[0])
                    result=[{"tx_hash":"a"*64,"height":1}] if sh in USED_SCRIPTHASHES else []
                elif method=="blockchain.scripthash.listunspent": result=[]
                else: result=None
                out.append({"jsonrpc":"2.0","id":call.get("id"),"result":result})
            payload=out if isinstance(req,list) else out[0]
            writer.write((json.dumps(payload)+"\n").encode()); await writer.drain()
    finally:
        writer.close(); await writer.wait_closed()


def make_self_signed_cert(tmp: Path):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Fulcrum selftest")])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=1))
            .not_valid_after(now+timedelta(days=1)).sign(key, hashes.SHA256()))
    cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode("ascii")
    cert_path=tmp/"cert.pem"; key_path=tmp/"key.pem"
    cert_path.write_text(cert_pem)
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()))
    return cert_pem, cert_path, key_path

async def main():
    install_stubs(); w=load_wallet_watch()
    server=await asyncio.start_server(electrum_server,"127.0.0.1",0)
    port=server.sockets[0].getsockname()[1]
    tmp_obj=tempfile.TemporaryDirectory(); tmp=Path(tmp_obj.name)
    cert_pem, cert_path, key_path=make_self_signed_cert(tmp)
    tls_ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); tls_ctx.load_cert_chain(str(cert_path),str(key_path))
    tls_server=await asyncio.start_server(electrum_server,"127.0.0.1",0,ssl=tls_ctx)
    tls_port=tls_server.sockets[0].getsockname()[1]
    try:
        zpub=make_zpub(w)
        wrapped=f"[deadbeef/84h/0h/0h]{zpub[:55]}\n {zpub[55:]}"
        config=w.normalize_watch_config({
            "enabled":True,"query_source":"fulcrum","electrum_kind":"fulcrum","electrum_host":"127.0.0.1","electrum_port":port,
            "electrum_tls":False,"monitors":[{"id":"watch_z","label":"ZPUB","kind":"address","value":wrapped,"receive_count":1,"change_count":1,"history_limit":0}]
        })
        assert config["monitors"][0]["kind"]=="xpub"
        assert config["monitors"][0]["value"]==zpub
        assert config["monitors"][0]["history_limit"]==0
        cache=w.runtime_cache_from_config(config)
        assert len(cache["addresses"])==2

        # Real restart persistence: save the device-bound encrypted runtime cache,
        # construct a completely new store object, then load it again. Fulcrum
        # source settings and concrete derived addresses must survive; the raw
        # XPUB deliberately does not live in this cache.
        restart_ledger=FakeLedger(config)
        restart_store=w.WalletWatchRuntimeStore(FakeHass(),"restart-e2e",restart_ledger.async_device_binding_secret)
        restart_store.data=deepcopy(cache)
        restart_store.data["addresses"][0]["balance_sats"]=777
        await restart_store.async_save()
        restart_store_after=w.WalletWatchRuntimeStore(FakeHass(),"restart-e2e",restart_ledger.async_device_binding_secret)
        await restart_store_after.async_load()
        assert restart_store_after.data["enabled"] is True
        assert restart_store_after.data["query_source"]=="fulcrum"
        assert restart_store_after.data["electrum_host"]=="127.0.0.1"
        assert restart_store_after.data["electrum_port"]==port
        assert len(restart_store_after.data["addresses"])==2
        assert restart_store_after.data["addresses"][0]["balance_sats"]==777
        assert all("xpub" not in row and "descriptor" not in row for row in restart_store_after.data["addresses"])

        ledger=FakeLedger(config); mgr=w.WalletWatchManager(FakeHass(),FakeEntry(),ledger)
        class Runtime:
            def __init__(self,data): self.data=deepcopy(data); self.saves=0
            async def async_save(self): self.saves+=1
            async def async_replace_from_full_config(self,cfg):
                # call the real implementation against this fake runtime object
                return await w.WalletWatchRuntimeStore.async_replace_from_full_config(self,cfg)
        mgr.runtime_store=Runtime(cache)

        # Gap-limit semantics: counts are consecutive-unused reserves, not total
        # derived addresses. Receive and change branches are scanned independently.
        gap_config=deepcopy(config)
        gap_config["monitors"][0]["receive_count"]=2
        gap_config["monitors"][0]["change_count"]=2
        for idx in range(5):
            row=w.derive_extpub_branch_address(zpub,0,idx)
            USED_SCRIPTHASHES.add(w._electrum_scripthash(row["address"]))
        for idx in range(3):
            row=w.derive_extpub_branch_address(zpub,1,idx)
            USED_SCRIPTHASHES.add(w._electrum_scripthash(row["address"]))
        mgr.runtime_store.data=w.runtime_cache_from_config(gap_config)
        # Exercise the real full-settings activation path. Prior to v0.21.0.12
        # this path silently collapsed HD monitoring back to Receive N + Change N
        # total addresses instead of restoring used + gap coverage.
        await mgr.async_apply_full_config(gap_config, poll=False)
        active=[row for row in mgr.runtime_store.data["addresses"] if row.get("active",True)]
        receive=[row for row in active if row.get("branch")=="receive"]
        change=[row for row in active if row.get("branch")=="change"]
        assert [row["index"] for row in receive]==list(range(7))
        assert [row["index"] for row in change]==list(range(5))
        assert sum(1 for row in receive if row.get("used") is False)==2
        assert sum(1 for row in change if row.get("used") is False)==2
        assert all(row.get("used") is True for row in receive[:5])
        assert all(row.get("used") is True for row in change[:3])
        USED_SCRIPTHASHES.clear()
        mgr.runtime_store.data=w.runtime_cache_from_config(config)

        probe=await mgr.async_test_source(config)
        assert probe["ok"] and probe["server_version"][0]=="Fulcrum 2.1.1"
        tls_config=deepcopy(config); tls_config.update({"electrum_port":tls_port,"electrum_tls":True,"electrum_verify_ssl":True,"electrum_pinned_cert_pem":cert_pem})
        tls_config=w.normalize_watch_config(tls_config)
        tls_probe=await mgr.async_test_source(tls_config)
        assert tls_probe["ok"] and tls_probe["certificate_pinned"] is True and tls_probe["server_version"][0]=="Fulcrum 2.1.1"
        overview=await mgr.async_monitor_transactions(config,monitor_id="watch_z",limit=0,page=1)
        assert overview["monitor_id"]=="watch_z" and overview["history_unlimited"] is True
        assert overview["balance_sats"]==246912 and overview["loaded_transaction_count"]==0

        # Real polling behavior: initial baseline may fetch balance/UTXO/history,
        # but an unchanged immediate second poll must use only server.version +
        # one scripthash.subscribe per concrete address.
        mgr.runtime_store.data=w.runtime_cache_from_config(config)
        RPC_METHODS.clear(); await mgr.async_poll(force=True)
        assert "blockchain.scripthash.get_balance" in RPC_METHODS
        assert "blockchain.scripthash.listunspent" in RPC_METHODS
        assert "blockchain.scripthash.get_history" in RPC_METHODS
        status_after_poll=mgr.public_status(include_addresses=False)
        watch_summary=status_after_poll["monitor_summaries"]["watch_z"]
        assert watch_summary["address_count"]==2
        assert watch_summary["receive_address_count"]==1 and watch_summary["change_address_count"]==1
        assert watch_summary["balance_sats"]==246912
        assert "addresses" not in status_after_poll
        RPC_METHODS.clear(); await mgr.async_poll(force=True)
        assert RPC_METHODS.count("blockchain.scripthash.subscribe")==2
        assert "blockchain.scripthash.get_balance" not in RPC_METHODS
        assert "blockchain.scripthash.listunspent" not in RPC_METHODS
        assert "blockchain.scripthash.get_history" not in RPC_METHODS
        # A stale balance cache reconciles balance/UTXOs without reloading history.
        for row in mgr.runtime_store.data["addresses"]: row["last_balance_refresh_unix"]=0
        RPC_METHODS.clear(); await mgr.async_poll(force=True)
        assert "blockchain.scripthash.get_balance" in RPC_METHODS
        assert "blockchain.scripthash.listunspent" in RPC_METHODS
        assert "blockchain.scripthash.get_history" not in RPC_METHODS

        # Add a second target through the real upsert path. This must preserve
        # Fulcrum/TLS/source settings and make the monitor immediately available
        # to backend TX/history calls without a second global save.
        address=w._bech32_address(b"\x11"*20,0)
        ledger._cfg=deepcopy(tls_config); mgr.runtime_store.data=w.runtime_cache_from_config(tls_config)
        upsert=await mgr.async_upsert_monitor({
            "id":"watch_delete","label":"Delete me","kind":"address","value":address,"enabled":True,
            "receive_count":0,"change_count":0,"history_limit":10,"created_at":"2026-08-16T12:00:00+00:00","category":"own","note":"","min_notify_sats":0,
            "notify_incoming":True,"notify_outgoing":True,"notify_ha_event":True,"notify_persistent":True,"notify_services":True,"notify_external":True,
        })
        assert any(m["id"]=="watch_delete" for m in upsert["config"]["monitors"])
        assert upsert["config"]["electrum_port"]==tls_port and upsert["config"]["electrum_tls"] is True
        await mgr.async_monitor_transactions(upsert["config"], monitor_id="watch_delete", limit=10, page=1)
        mgr.runtime_store.data["activity_log"]=[{"monitor_id":"watch_delete","txid":"a"*64,"detected_at":"2026-08-16T12:30:00+00:00"}]
        result=await mgr.async_remove_monitor("watch_delete")
        assert result["removed"] is True
        assert not any(m["id"]=="watch_delete" for m in result["config"]["monitors"])
        assert result["config"]["electrum_host"]=="127.0.0.1" and result["config"]["electrum_port"]==tls_port
        assert result["config"]["electrum_tls"] is True and result["config"]["electrum_pinned_cert_sha256"]
        assert result["status"]["purged_activity_count"]==1
        assert not mgr.runtime_store.data["activity_log"]
        probe2=await mgr.async_test_source(result["config"])
        assert probe2["ok"] and probe2["server_version"][0]=="Fulcrum 2.1.1"
        print("PASS: ZPUB save/derive")
        print("PASS: restart cache persists Fulcrum + derived addresses")
        print("PASS: Receive/Change gap-limit discovery through full config activation")
        print("PASS: Fulcrum server.version before delete")
        print("PASS: Fulcrum self-signed TLS certificate pin")
        print("PASS: saved-monitor TX overview")
        print("PASS: monitor delete + journal purge")
        print("PASS: Fulcrum source unchanged/reachable after delete")
        print("PASS: unlimited history uses page mode")
        print("PASS: watch target upsert is immediately backend-visible")
        print("PASS: unchanged Fulcrum poll uses subscribe-only fast path")
        print("PASS: stale balance reconciliation avoids history reload")
        print("PASS: lightweight status keeps per-monitor balance/count aggregates without addresses")
    finally:
        server.close(); await server.wait_closed()
        tls_server.close(); await tls_server.wait_closed()
        tmp_obj.cleanup()

if __name__=="__main__": asyncio.run(main())
