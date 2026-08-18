"use strict";

(() => {
  if (window.__BITCOIN_STACK_TRACKER_RUNTIME_FIXES_RC15__) return;
  window.__BITCOIN_STACK_TRACKER_RUNTIME_FIXES_RC15__ = true;

  // Dedicated market-history views previously ignored the already persisted
  // intraday tail unless a caller explicitly opted in. Default to the real
  // observed intraday snapshots; callers can still pass includeIntraday:false.
  if (typeof marketAssessmentLiveTailPoints === "function") {
    const originalMarketAssessmentLiveTailPoints = marketAssessmentLiveTailPoints;
    marketAssessmentLiveTailPoints = function marketAssessmentLiveTailPointsWithIntraday(payload, options = {}) {
      const normalized = options && typeof options === "object" ? {...options} : {};
      if (!Object.prototype.hasOwnProperty.call(normalized, "includeIntraday")) {
        normalized.includeIntraday = true;
      }
      return originalMarketAssessmentLiveTailPoints(payload, normalized);
    };
  }

  // A fresh five-minute score does not change the daily-history revision. The
  // previous client cache therefore stayed valid forever and charts could stop
  // advancing. Re-read only the local cached history payload when calculated_at
  // advances; this never triggers another external price request or model run.
  if (typeof refreshMarketAssessment === "function") {
    const originalRefreshMarketAssessment = refreshMarketAssessment;
    refreshMarketAssessment = async function refreshMarketAssessmentWithHistoryRefresh(options = {}) {
      const before = String(state.data?.buy_opportunity_calculated_at || "");
      const ok = await originalRefreshMarketAssessment(options);
      const after = String(state.data?.buy_opportunity_calculated_at || "");
      if (!ok || !after || after === before) return ok;

      if (state.activeTab === "market" && typeof loadMarketAssessmentHistory === "function") {
        void loadMarketAssessmentHistory({force:true});
      }
      if (
        state.activeTab === "overview" &&
        (state.chartMode === "price_market" || document.querySelector("#chartMode")?.value === "price_market") &&
        typeof ensureChartMarketAssessmentHistory === "function"
      ) {
        void ensureChartMarketAssessmentHistory({force:true});
      }
      return ok;
    };
  }

  // The manage endpoint is the authoritative owner check. The locked dashboard
  // intentionally may not expose owner UI metadata, so rejecting on the client
  // before calling this endpoint made the explicitly enabled locked Sentinel
  // invisible. Only mark the local locked view as owner-authorized after the
  // server accepted /wallet-watch/manage.
  if (typeof loadLockedWalletWatchManagement === "function") {
    loadLockedWalletWatchManagement = async function loadLockedWalletWatchManagementAuthorized() {
      if (!state.entryId || !state.data?.locked) return false;
      try {
        const response = await api(
          `api/wallet-watch/manage?entry_id=${encodeURIComponent(state.entryId)}`,
          {timeoutMs:10000},
        );
        const previous = state.walletWatch || {};
        state.walletWatch = {
          ...previous,
          config: response.config || previous.config || {},
          status: response.status || previous.status || {},
          notify_services: previous.notify_services || [],
          activity_log: previous.activity_log || {items:[],page:1,pages:1,total:0,stored_total:0},
          locked_runtime_snapshot: true,
        };
        state.data.security = {...(state.data.security || {}), owner:true};
        return true;
      } catch (_error) {
        return false;
      }
    };
  }

  let lockedSentinelRefreshInFlight = false;
  let nextLockedSentinelAttemptAt = 0;
  async function ensureLockedSentinelVisible() {
    if (!state.data?.locked) {
      nextLockedSentinelAttemptAt = 0;
      return;
    }
    if (typeof walletWatchShowWhenLocked !== "function" || !walletWatchShowWhenLocked()) return;
    if (state.walletWatch?.locked_runtime_snapshot && state.walletWatch?.status) {
      if (typeof renderLockedWalletWatch === "function") renderLockedWalletWatch();
      return;
    }
    if (lockedSentinelRefreshInFlight || Date.now() < nextLockedSentinelAttemptAt) return;
    lockedSentinelRefreshInFlight = true;
    nextLockedSentinelAttemptAt = Date.now() + 15000;
    try {
      const ok = await loadLockedWalletWatchManagement();
      if (ok && typeof renderLockedWalletWatch === "function") renderLockedWalletWatch();
    } finally {
      lockedSentinelRefreshInFlight = false;
    }
  }

  window.setInterval(() => { void ensureLockedSentinelVisible(); }, 1000);
  queueMicrotask(() => { void ensureLockedSentinelVisible(); });
})();
