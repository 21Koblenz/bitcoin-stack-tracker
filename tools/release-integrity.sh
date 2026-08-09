#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "Usage: $0 <release-file> [minisign-secret-key]" >&2
  exit 64
fi

artifact="$1"
secret_key="${2:-${MINISIGN_SECRET_KEY:-}}"

if [[ ! -f "$artifact" ]]; then
  echo "Release file not found: $artifact" >&2
  exit 66
fi

sha256sum "$artifact" > "${artifact}.sha256"
echo "SHA-256: ${artifact}.sha256"

if [[ -z "$secret_key" ]]; then
  echo "No publisher signing key supplied; checksum created, detached signature skipped." >&2
  exit 0
fi

if ! command -v minisign >/dev/null 2>&1; then
  echo "minisign is required to create a detached publisher signature." >&2
  exit 69
fi

if [[ ! -f "$secret_key" ]]; then
  echo "Minisign secret key not found: $secret_key" >&2
  exit 66
fi

minisign -Sm "$artifact" -s "$secret_key" -x "${artifact}.minisig"
echo "Signature: ${artifact}.minisig"
