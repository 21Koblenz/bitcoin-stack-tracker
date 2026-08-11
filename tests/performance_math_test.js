"use strict";

const assert = require("assert");
const math = require("../custom_components/bitcoin_stack_tracker/frontend/static/performance-math.js");
const ts = value => Date.parse(value);
const close = (actual, expected, tolerance = 1e-9) => {
  assert(Number.isFinite(actual), `expected finite number, got ${actual}`);
  assert(Math.abs(actual - expected) <= tolerance, `${actual} != ${expected}`);
};

// Exact TWR split around a mid-period contribution:
// 1 BTC: 100 -> 200 (+100%), then add 0.5 BTC at 200, then 200 -> 300 (+50%).
// TWR = 2.0 * 1.5 - 1 = +200%, not +250%.
{
  const prices = [
    {time:ts("2026-01-01T00:00:00Z"),value:100,key:"2026-01-01T00:00:00Z"},
    {time:ts("2026-01-02T00:00:00Z"),value:200,key:"2026-01-02T00:00:00Z"},
    {time:ts("2026-01-03T00:00:00Z"),value:300,key:"2026-01-03T00:00:00Z"},
  ];
  const events = [
    {time:ts("2025-12-31T12:00:00Z"),btcDelta:1,externalFlow:100,valuationPrice:100,sequence:0},
    {time:ts("2026-01-02T12:00:00Z"),btcDelta:0.5,externalFlow:100,valuationPrice:200,sequence:1},
  ];
  const result = math.timeWeightedReturn(prices,events);
  close(result.percent,200,1e-10);
}

// Trading fees are portfolio performance, not external cash flow. A 10 fiat fee
// on a 100 fiat contribution into an existing 100 fiat portfolio yields a
// 200 / 210 transaction factor at an unchanged BTC price.
{
  const prices = [
    {time:ts("2026-02-01T00:00:00Z"),value:100,key:"2026-02-01T00:00:00Z"},
    {time:ts("2026-02-03T00:00:00Z"),value:100,key:"2026-02-03T00:00:00Z"},
  ];
  const events = [
    {time:ts("2026-01-31T12:00:00Z"),btcDelta:1,externalFlow:100,valuationPrice:100,sequence:0},
    {time:ts("2026-02-02T00:00:00Z"),btcDelta:1,externalFlow:110,valuationPrice:100,sequence:1},
  ];
  const result = math.timeWeightedReturn(prices,events);
  close(result.percent,(200/210-1)*100,1e-10);
}

// A complete sale and withdrawal leaves the tracked portfolio empty, but that
// is not a -100% investment return. With a 1 fiat sale fee at a flat 100
// valuation, only the 1% transaction cost belongs in TWR.
{
  const prices = [
    {time:ts("2026-03-01T00:00:00Z"),value:100,key:"2026-03-01T00:00:00Z"},
    {time:ts("2026-03-02T00:00:00Z"),value:100,key:"2026-03-02T00:00:00Z"},
  ];
  const events = [
    {time:ts("2026-02-28T12:00:00Z"),btcDelta:1,externalFlow:100,valuationPrice:100,sequence:0},
    {time:ts("2026-03-01T12:00:00Z"),btcDelta:-1,externalFlow:-99,valuationPrice:100,sequence:1},
  ];
  const result = math.timeWeightedReturn(prices,events);
  close(result.percent,-1,1e-10);
}

// Multiple cash-flow events at the exact same timestamp must remain separate
// TWR index observations; fractional-millisecond Date offsets are truncated.
{
  const start = ts("2026-01-01T00:00:00Z");
  const flow = ts("2026-01-02T12:00:00Z");
  const end = ts("2026-01-03T00:00:00Z");
  const result = math.timeWeightedReturn(
    [
      {time:start,value:100,key:"2026-01-01T00:00:00.000Z"},
      {time:end,value:100,key:"2026-01-03T00:00:00.000Z"},
    ],
    [
      {time:start-1,btcDelta:1,externalFlow:100,valuationPrice:100,sequence:0},
      {time:flow,btcDelta:0.1,externalFlow:10,valuationPrice:100,sequence:0},
      {time:flow,btcDelta:0.2,externalFlow:20,valuationPrice:100,sequence:1},
    ],
  );
  const flowKeys = Object.keys(result.index).filter(key => key.startsWith("2026-01-02T12:00:00."));
  assert.strictEqual(flowKeys.length,2);
  close(result.percent,0,1e-9);
}

// Conventional XIRR day-count basis: 365 days even across a leap-year span.
{
  const flows = [
    {time:ts("2024-01-01T00:00:00Z"),amount:-1000},
    {time:ts("2025-01-01T00:00:00Z"),amount:1100},
  ];
  const solved = math.xirrSolveDetailed(flows);
  const expected = Math.pow(1.1,365/366)-1;
  assert.strictEqual(solved.ambiguous,false);
  close(solved.rate,expected,2e-10);
  assert.strictEqual(math.XIRR_YEAR_MS,365*86400000);
}

// XIRR uses payment dates, not intraday time fractions. Cash flows on the same
// UTC date have the same discount exponent.
{
  const sameDay = [
    {time:ts("2026-04-01T00:00:01Z"),amount:-100},
    {time:ts("2026-04-01T23:59:59Z"),amount:110},
  ];
  close(math.xnpv(0.10,sameDay),10,1e-12);
}

// A 10% gain over one calendar day annualizes far above the old 5,000%/
// low-log search ceilings and must still have a valid XIRR root.
{
  const start = ts("2026-05-01T00:00:00Z");
  const solved = math.xirrSolveDetailed([
    {time:start,amount:-100},
    {time:start+86400000,amount:110},
  ]);
  const expected = Math.pow(1.1,365)-1;
  assert.strictEqual(solved.ambiguous,false);
  close(solved.rate,expected,Math.max(1,expected)*2e-9);
}

// Multiple valid IRRs must not be silently reduced to whichever root happens to
// be found first. This classic cash-flow series has 10% and 20% roots.
{
  const year = 365*86400000;
  const start = ts("2020-01-01T00:00:00Z");
  const solved = math.xirrSolveDetailed([
    {time:start,amount:-100},
    {time:start+year,amount:230},
    {time:start+2*year,amount:-132},
  ]);
  assert.strictEqual(solved.ambiguous,true);
  assert.strictEqual(solved.rate,null);
  assert.strictEqual(solved.roots.length,2);
  close(solved.roots[0],0.1,1e-8);
  close(solved.roots[1],0.2,1e-8);
}

// Max drawdown must see the real peak/trough pair, independent of visual chart downsampling.
{
  const result = math.maximumDrawdown([
    {time:1,value:100,key:"a"},
    {time:2,value:110,key:"b"},
    {time:3,value:70,key:"c"},
    {time:4,value:105,key:"d"},
  ]);
  close(result.maximum,(70/110-1)*100,1e-12);
  close(result.current,(105/110-1)*100,1e-12);
  assert.strictEqual(result.peakTime,2);
  assert.strictEqual(result.troughTime,3);
}

console.log("performance math numeric tests: ok");

// Recovery duration and days since the latest period high are reported without extra scans in the UI.
{
  const result = math.maximumDrawdown([
    {time:0*math.DAY_MS,value:100,key:"a"},
    {time:1*math.DAY_MS,value:80,key:"b"},
    {time:5*math.DAY_MS,value:101,key:"c"},
    {time:6*math.DAY_MS,value:90,key:"d"},
    {time:9*math.DAY_MS,value:102,key:"e"},
    {time:11*math.DAY_MS,value:95,key:"f"},
  ]);
  close(result.longestRecoveryDays,5,1e-12);
  close(result.daysSincePeriodPeak,2,1e-12);
}

// Retesting the exact same ATH resets "days since ATH" to the latest occurrence.
{
  const result = math.maximumDrawdown([
    {time:0*math.DAY_MS,value:100,key:"a"},
    {time:3*math.DAY_MS,value:100,key:"b"},
    {time:5*math.DAY_MS,value:90,key:"c"},
  ]);
  close(result.daysSincePeriodPeak,2,1e-12);
  assert.strictEqual(result.periodPeakTime,3*math.DAY_MS);
}

// A real fall from a positive peak to zero is a complete (-100%) drawdown,
// not an invalid data point that may be filtered away.
{
  const result = math.maximumDrawdown([
    {time:0*math.DAY_MS,value:100,key:"a"},
    {time:1*math.DAY_MS,value:0,key:"b"},
    {time:2*math.DAY_MS,value:25,key:"c"},
  ]);
  close(result.maximum,-100,1e-12);
  close(result.current,-75,1e-12);
  assert.strictEqual(result.troughTime,1*math.DAY_MS);
}
