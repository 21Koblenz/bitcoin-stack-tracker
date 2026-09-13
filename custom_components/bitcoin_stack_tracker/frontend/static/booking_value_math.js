(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.BSTBookingValueMath = api;
})(typeof window !== "undefined" ? window : globalThis, function () {
  "use strict";

  function transactionFiatTotal(type, amountBtc, price, fee) {
    const amount = Number(amountBtc);
    const rate = Number(price);
    const charge = Math.max(0, Number(fee) || 0);
    if (!(amount > 0) || !(rate > 0)) return NaN;
    const gross = amount * rate;
    if (type === "purchase" || type === "income") return gross + charge;
    if (type === "sale" || type === "expense") return gross - charge;
    return gross;
  }

  function todayMetrics(entry, prices, fallbackCurrency) {
    const amount = Math.max(0, Number(entry?.amount_btc || 0));
    const currency = String(entry?.currency || fallbackCurrency || "").toUpperCase();
    const live = Number(prices?.[currency]);
    const historical = transactionFiatTotal(
      String(entry?.type || ""),
      amount,
      Number(entry?.price),
      Number(entry?.fee || 0)
    );
    const currentValue =
      amount > 0 && Number.isFinite(live) && live > 0 ? amount * live : null;
    const percent =
      currentValue != null && Number.isFinite(historical) && historical > 0
        ? (currentValue / historical - 1) * 100
        : null;
    return { currency, currentValue, percent, historical };
  }

  return { transactionFiatTotal, todayMetrics };
});
