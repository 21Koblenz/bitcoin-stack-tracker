# Immutable Home Assistant base images. BUILD_ARCH is supplied by Supervisor/BuildKit.
# amd64:  ghcr.io/home-assistant/amd64-base:3.22-2026.06.1
# aarch64: ghcr.io/home-assistant/aarch64-base:3.22-2026.06.1
ARG BUILD_ARCH
FROM --platform=linux/amd64 ghcr.io/home-assistant/amd64-base:3.22-2026.06.1@sha256:368b5fcd266d1e5a643bad9bc9e84760760032e911ecfdef2a7fc148d76035d1 AS base-amd64
FROM --platform=linux/arm64 ghcr.io/home-assistant/aarch64-base:3.22-2026.06.1@sha256:03185a346a3e505e0aa102cb1e976a2e7be7421cf4a405abd2cd83e0a6bd0a58 AS base-aarch64
FROM base-${BUILD_ARCH}


ARG BUILD_VERSION
ARG BUILD_ARCH

LABEL \
  io.hass.version="${BUILD_VERSION}" \
  io.hass.type="app" \
  io.hass.arch="${BUILD_ARCH}"

ENV \
  PYTHONUNBUFFERED=1 \
  PYTHONPATH=/app \
  S6_SERVICES_GRACETIME=10000 \
  S6_KILL_GRACETIME=1000 \
  S6_KILL_FINISH_MAXTIME=1000

RUN apk add --no-cache \
      python3 \
      tor \
      nftables \
      su-exec \
    && addgroup -S bitcointracker \
    && adduser -S -D -H -G bitcointracker bitcointracker \
    && addgroup bitcointracker tor

WORKDIR /app
COPY app /app
COPY SBOM.source.cdx.json /app/SBOM.source.cdx.json
COPY generate_runtime_sbom.py /usr/local/bin/generate_runtime_sbom.py
COPY torrc /etc/tor/torrc
COPY run.sh /run.sh
COPY rootfs /
RUN chmod a+x /run.sh /app/network_agent.py \
    /etc/services.d/bitcoin-stack-tracker/run \
    /etc/services.d/bitcoin-stack-tracker/finish \
    && python3 -m py_compile /app/network_agent.py \
    && python3 /usr/local/bin/generate_runtime_sbom.py --version "${BUILD_VERSION}" --output /app/SBOM.runtime.cdx.json \
    && python3 -c "import sys; sys.path.insert(0, '/app'); import network_agent; assert network_agent.APP_VERSION == '0.21.0.3'"
