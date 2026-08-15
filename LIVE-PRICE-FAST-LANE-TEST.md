# v0.21.0.9 test overlay – Live price fast lane

This test build separates price refresh cadences without changing the Sats Sentinel trust rule.

## Live price cadence

- Own/local price sources: default **300 seconds**.
- Additional public price sources: default **60 seconds**, configurable from **30 to 300 seconds**.
- Public sources remain Tor-only and fail closed; there is no direct clearnet fallback.
- The dashboard reads the already cached Home Assistant coordinator price every **15 seconds**. This local UI poll does not create an external request.
- When both an own/local source and a public source provide the same currency, the fresh public source acts as the live fast lane between slower local anchor updates. If that public data becomes stale, a healthy local source can take over.

## Sats Sentinel remains separate

Price-source failover does not apply to wallet monitoring. If an own mempool instance is configured for the integration, Sats Sentinel uses that own instance exclusively. If it is unavailable, Sentinel is offline and does not fall back to mempool.space, another public mempool server, Tor or clearnet.
