(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.BSTPerformanceMath = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const DAY_MS = 86400000;
  const XIRR_YEAR_MS = 365 * DAY_MS;
  const EPSILON = 1e-12;

  function finiteNumber(value) {
    const numeric = Number(value);
    return Number.isFinite(numeric) ? numeric : null;
  }

  function normalizePricePoints(points) {
    return (Array.isArray(points) ? points : [])
      .map((point, index) => ({
        time: finiteNumber(point?.time),
        value: finiteNumber(point?.value),
        key: point?.key == null ? String(point?.time ?? index) : String(point.key),
      }))
      .filter(point => point.time !== null && point.value !== null && point.value > 0)
      .sort((left, right) => left.time - right.time || left.key.localeCompare(right.key));
  }

  function normalizeDrawdownPoints(points) {
    const clean = (Array.isArray(points) ? points : [])
      .map((point, index) => ({
        time: finiteNumber(point?.time),
        value: finiteNumber(point?.value),
        key: point?.key == null ? String(point?.time ?? index) : String(point.key),
      }))
      .filter(point => point.time !== null && point.value !== null && point.value >= 0)
      .sort((left, right) => left.time - right.time || left.key.localeCompare(right.key));
    // A drawdown requires a positive capital/price base. Ignore only leading
    // zero observations; once a positive peak exists, zero is a valid -100% trough.
    const firstPositive = clean.findIndex(point => point.value > 0);
    return firstPositive < 0 ? [] : clean.slice(firstPositive);
  }

  function normalizeLedgerEvents(events) {
    return (Array.isArray(events) ? events : [])
      .map((event, index) => ({
        time: finiteNumber(event?.time),
        btcDelta: finiteNumber(event?.btcDelta),
        externalFlow: finiteNumber(event?.externalFlow),
        valuationPrice: finiteNumber(event?.valuationPrice),
        sequence: Number.isFinite(Number(event?.sequence)) ? Number(event.sequence) : index,
      }))
      .filter(event => event.time !== null && event.btcDelta !== null && event.externalFlow !== null)
      .sort((left, right) => left.time - right.time || left.sequence - right.sequence);
  }

  function uniqueIndexKey(time, sequence) {
    // Keep multiple ledger events that share the exact same timestamp as distinct
    // TWR index observations. JavaScript Date has millisecond precision, so use
    // whole milliseconds (not fractional milliseconds, which are truncated).
    const offset = 1 + Math.max(0, Math.min(998, Number(sequence) || 0));
    return new Date(time + offset).toISOString();
  }

  function timeWeightedReturn(pricePoints, ledgerEvents) {
    const prices = normalizePricePoints(pricePoints);
    const events = normalizeLedgerEvents(ledgerEvents);
    if (prices.length < 2) return null;

    const startTime = prices[0].time;
    const endTime = prices[prices.length - 1].time;
    let balance = 0;
    let eventPosition = 0;

    while (eventPosition < events.length && events[eventPosition].time <= startTime) {
      balance += events[eventPosition].btcDelta;
      eventPosition += 1;
    }
    if (balance < -EPSILON) return { percent: null, index: {}, invalid: true, reason: "negative_balance" };
    if (Math.abs(balance) <= EPSILON) balance = 0;

    let factor = 1;
    let previousValue = balance * prices[0].value;
    let latestMarketPrice = prices[0].value;
    let calculatedPeriods = 0;
    let firstMeaningfulTime = previousValue > EPSILON ? startTime : null;
    const index = {};
    if (previousValue > EPSILON) index[prices[0].key] = 100;

    const timeline = [];
    for (let indexPosition = 1; indexPosition < prices.length; indexPosition += 1) {
      timeline.push({ kind: "price", ...prices[indexPosition], sequence: -1 });
    }
    for (let indexPosition = eventPosition; indexPosition < events.length; indexPosition += 1) {
      const event = events[indexPosition];
      if (event.time > startTime && event.time <= endTime) timeline.push({ kind: "flow", ...event });
    }
    timeline.sort((left, right) => {
      if (left.time !== right.time) return left.time - right.time;
      if (left.kind !== right.kind) return left.kind === "price" ? -1 : 1;
      return (left.sequence || 0) - (right.sequence || 0);
    });

    for (const item of timeline) {
      if (item.kind === "price") {
        latestMarketPrice = item.value;
        const currentValue = balance * item.value;
        if (previousValue > EPSILON) {
          const subFactor = currentValue / previousValue;
          if (!Number.isFinite(subFactor) || subFactor < -EPSILON) {
            return { percent: null, index, invalid: true, reason: "invalid_valuation" };
          }
          factor *= Math.max(0, subFactor);
          calculatedPeriods += 1;
        } else if (currentValue > EPSILON && firstMeaningfulTime === null) {
          firstMeaningfulTime = item.time;
        }
        previousValue = Math.max(0, currentValue);
        if (firstMeaningfulTime !== null) index[item.key] = factor * 100;
        continue;
      }

      const valuationPrice = item.valuationPrice && item.valuationPrice > 0 ? item.valuationPrice : latestMarketPrice;
      if (!(valuationPrice > 0)) continue;
      const before = Math.max(0, balance * valuationPrice);

      // Close the market-return subperiod immediately before the external flow.
      if (previousValue > EPSILON) {
        const marketFactor = before / previousValue;
        if (!Number.isFinite(marketFactor) || marketFactor < -EPSILON) {
          return { percent: null, index, invalid: true, reason: "invalid_market_factor" };
        }
        factor *= Math.max(0, marketFactor);
        calculatedPeriods += 1;
      }

      const nextBalance = balance + item.btcDelta;
      if (nextBalance < -EPSILON) {
        return { percent: null, index, invalid: true, reason: "negative_balance" };
      }
      const cleanNextBalance = Math.abs(nextBalance) <= EPSILON ? 0 : nextBalance;
      const after = Math.max(0, cleanNextBalance * valuationPrice);
      // Cash-flow timing follows the actual transaction direction:
      // - contributions fund a purchase first, so capital at risk is
      //   pre-flow value + contributed cash; transaction costs reduce the
      //   post-trade value and therefore performance.
      // - withdrawals happen after a sale, so the pre-withdrawal portfolio
      //   value is post-trade value + withdrawn cash. This captures sale
      //   transaction costs without turning a full withdrawal into a -100% return.
      let flowFactor = 1;
      if (item.externalFlow >= 0) {
        const fundedBase = before + item.externalFlow;
        if (fundedBase > EPSILON) flowFactor = after / fundedBase;
        else if (after > EPSILON) return { percent: null, index, invalid: true, reason: "invalid_flow_base" };
      } else if (before > EPSILON) {
        flowFactor = (after - item.externalFlow) / before;
      } else if (after - item.externalFlow > EPSILON) {
        return { percent: null, index, invalid: true, reason: "invalid_withdrawal_base" };
      }
      if (!Number.isFinite(flowFactor) || flowFactor < -EPSILON) {
        return { percent: null, index, invalid: true, reason: "invalid_flow_factor" };
      }
      factor *= Math.max(0, flowFactor);
      calculatedPeriods += 1;

      balance = cleanNextBalance;
      previousValue = after;
      if (after > EPSILON && firstMeaningfulTime === null) firstMeaningfulTime = item.time;
      if (firstMeaningfulTime !== null) index[uniqueIndexKey(item.time, item.sequence)] = factor * 100;
    }

    const indexPoints = Object.entries(index)
      .map(([key, value]) => ({ key, time: Date.parse(key), value: Number(value) }))
      .filter(point => Number.isFinite(point.time) && Number.isFinite(point.value))
      .sort((left, right) => left.time - right.time);

    if (indexPoints.length < 2 || calculatedPeriods < 1) {
      return {
        percent: null,
        index,
        invalid: false,
        calculatedPeriods,
        startTime: firstMeaningfulTime,
        endTime,
      };
    }
    return {
      percent: (factor - 1) * 100,
      index,
      invalid: false,
      calculatedPeriods,
      startTime: indexPoints[0].time,
      endTime: indexPoints[indexPoints.length - 1].time,
    };
  }


  function xirrDayTime(value) {
    const numeric = finiteNumber(value);
    if (numeric === null) return null;
    return Math.floor(numeric / DAY_MS) * DAY_MS;
  }

  function xnpvClean(rate, clean) {
    if (!(rate > -1)) return Number.POSITIVE_INFINITY;
    if (!clean.length) return Number.NaN;
    const start = clean[0].time;
    return clean.reduce((sum, item) => {
      const years = (item.time - start) / XIRR_YEAR_MS;
      return sum + item.amount / ((1 + rate) ** years);
    }, 0);
  }

  function xnpv(rate, flows) {
    const clean = (Array.isArray(flows) ? flows : [])
      .map(item => ({ time: xirrDayTime(item?.time), amount: finiteNumber(item?.amount) }))
      .filter(item => item.time !== null && item.amount !== null)
      .sort((left, right) => left.time - right.time);
    return xnpvClean(rate, clean);
  }

  function bisectRoot(clean, left, right, tolerance) {
    let leftValue = xnpvClean(left, clean);
    let rightValue = xnpvClean(right, clean);
    if (!Number.isFinite(leftValue) || !Number.isFinite(rightValue)) return null;
    if (Math.abs(leftValue) <= tolerance) return left;
    if (Math.abs(rightValue) <= tolerance) return right;
    if (Math.sign(leftValue) === Math.sign(rightValue)) return null;
    for (let iteration = 0; iteration < 260; iteration += 1) {
      const middle = (left + right) / 2;
      const value = xnpvClean(middle, clean);
      if (!Number.isFinite(value)) return null;
      if (Math.abs(value) <= tolerance || Math.abs(right - left) <= 1e-13 * Math.max(1, Math.abs(middle))) return middle;
      if (Math.sign(value) === Math.sign(leftValue)) {
        left = middle;
        leftValue = value;
      } else {
        right = middle;
        rightValue = value;
      }
    }
    return (left + right) / 2;
  }

  function xirrSolveDetailed(flows) {
    const clean = (Array.isArray(flows) ? flows : [])
      .map(item => ({ time: xirrDayTime(item?.time), amount: finiteNumber(item?.amount) }))
      .filter(item => item.time !== null && item.amount !== null)
      .sort((left, right) => left.time - right.time);
    if (!clean.some(item => item.amount > 0) || !clean.some(item => item.amount < 0)) {
      return { rate: null, roots: [], ambiguous: false };
    }

    const scale = clean.reduce((sum, item) => sum + Math.abs(item.amount), 0) || 1;
    const tolerance = scale * 1e-11;
    const candidates = [];
    // r = exp(x)-1 keeps every candidate strictly above -100% and covers
    // extremely large annualized rates without an arbitrary 5,000% ceiling.
    for (let exponent = -20; exponent <= 30; exponent += 0.125) candidates.push(Math.exp(exponent) - 1);
    // Short ranges can legitimately annualize to enormous rates. Continue on
    // the log-rate axis with a coarser grid so one-day/two-day XIRR roots are
    // not incorrectly reported as unavailable while keeping browser work bounded.
    for (let exponent = 30.5; exponent <= 300; exponent += 0.5) candidates.push(Math.exp(exponent) - 1);
    candidates.push(-0.999999999999, -0.99, -0.9, -0.5, 0, 0.1, 0.5, 1, 5, 10, 100);
    candidates.sort((left, right) => left - right);

    const roots = [];
    const addRoot = root => {
      if (!Number.isFinite(root) || root <= -1) return;
      if (roots.some(existing => Math.abs(existing - root) <= 1e-8 * Math.max(1, Math.abs(existing), Math.abs(root)))) return;
      roots.push(root);
    };

    let previousRate = null;
    let previousValue = null;
    for (const rate of candidates) {
      const value = xnpvClean(rate, clean);
      if (!Number.isFinite(value)) continue;
      if (Math.abs(value) <= tolerance) addRoot(rate);
      if (previousRate !== null && previousValue !== null && Math.sign(value) !== Math.sign(previousValue)) {
        addRoot(bisectRoot(clean, previousRate, rate, tolerance));
      }
      previousRate = rate;
      previousValue = value;
    }
    roots.sort((left, right) => left - right);
    return {
      rate: roots.length === 1 ? roots[0] : null,
      roots,
      ambiguous: roots.length > 1,
    };
  }

  function maximumDrawdown(points) {
    const clean = normalizeDrawdownPoints(points);
    if (clean.length < 2) return null;
    let peak = clean[0];
    let periodPeak = clean[0];
    let maxDrawdown = 0;
    let maxPeak = clean[0];
    let maxTrough = clean[0];
    let recoveryPeak = clean[0];
    let recoveryActive = false;
    let longestRecoveryMs = 0;
    for (const point of clean) {
      if (point.value < recoveryPeak.value) recoveryActive = true;
      if (point.value >= recoveryPeak.value) {
        if (recoveryActive) longestRecoveryMs = Math.max(longestRecoveryMs, point.time - recoveryPeak.time);
        recoveryPeak = point;
        recoveryActive = false;
      }
      if (point.value > peak.value) peak = point;
      // "Tage seit ATH" means the most recent occurrence of the period high.
      // An equal retest of the ATH resets that clock even though it does not
      // change the peak value used for drawdown math.
      if (point.value >= periodPeak.value) periodPeak = point;
      const drawdown = (point.value / peak.value - 1) * 100;
      if (drawdown < maxDrawdown) {
        maxDrawdown = drawdown;
        maxPeak = peak;
        maxTrough = point;
      }
    }
    const final = clean[clean.length - 1];
    return {
      current: (final.value / periodPeak.value - 1) * 100,
      maximum: maxDrawdown,
      peakTime: maxPeak.time,
      troughTime: maxTrough.time,
      periodPeakTime: periodPeak.time,
      endTime: final.time,
      daysSincePeriodPeak: Math.max(0, (final.time - periodPeak.time) / DAY_MS),
      longestRecoveryDays: Math.max(0, longestRecoveryMs / DAY_MS),
    };
  }

  return {
    DAY_MS,
    XIRR_YEAR_MS,
    timeWeightedReturn,
    xnpv,
    xirrSolveDetailed,
    maximumDrawdown,
  };
});
