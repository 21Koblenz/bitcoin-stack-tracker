"""Compact local-only dashboard metrics for Bitcoin Stack Tracker.

The functions in this module deliberately return aggregates only.  Notes,
provider references, import hashes and ledger UUIDs never leave this module.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import re
from typing import Any

from .fifo import currency_summary_from_result
from .models import decimal_value

ZERO = Decimal("0")
SATS_PER_BTC = Decimal("100000000")
DAYS_PER_YEAR = Decimal("365.2425")
DAYS_PER_MONTH = DAYS_PER_YEAR / Decimal("12")


def _parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _signed_stack_amount(entry: dict[str, Any]) -> Decimal:
    amount = max(decimal_value(entry.get("amount_btc")), ZERO)
    fee_btc = max(decimal_value(entry.get("fee_btc")), ZERO)
    stack_fee = fee_btc if bool(entry.get("fee_btc_affects_stack")) else ZERO
    if entry.get("type") in {"purchase", "income", "stack"}:
        return amount - stack_fee
    if entry.get("type") in {"sale", "expense"}:
        return -amount - stack_fee
    if entry.get("type") == "network_fee":
        return -amount
    return -stack_fee


def _stacking_window(
    entries: list[dict[str, Any]], now: datetime, days: int | None
) -> dict[str, Any]:
    cutoff = now - timedelta(days=days) if days is not None else None
    net = ZERO
    first: datetime | None = None
    for entry in entries:
        timestamp = _parse_timestamp(entry.get("timestamp"))
        if timestamp is None or timestamp > now:
            continue
        if first is None or timestamp < first:
            first = timestamp
        if cutoff is not None and timestamp < cutoff:
            continue
        net += _signed_stack_amount(entry)

    if days is None:
        elapsed_days = max(
            Decimal("1"),
            Decimal(str((now - first).total_seconds() / 86400)) if first else Decimal("1"),
        )
    else:
        elapsed_days = Decimal(days)
    sats = net * SATS_PER_BTC
    per_day = sats / elapsed_days if elapsed_days > 0 else ZERO
    per_month = per_day * DAYS_PER_MONTH
    return {
        "net_btc": net,
        "net_sats": sats,
        "avg_sats_per_day": per_day,
        "avg_sats_per_month": per_month,
        "days": float(elapsed_days),
    }


def _holding_metrics(fifo: dict[str, Any], now: datetime) -> dict[str, Any]:
    open_lots = [lot for lot in fifo.get("open_lots", []) if decimal_value(lot.get("remaining_btc")) > 0]
    total = sum((decimal_value(lot.get("remaining_btc")) for lot in open_lots), ZERO)
    long_term = decimal_value(fifo.get("long_term_btc"))
    short_term = decimal_value(fifo.get("short_term_btc"))
    unknown = max(total - long_term - short_term, ZERO)

    next_30 = ZERO
    next_90 = ZERO
    weighted_age_days = ZERO
    oldest_age_days = ZERO
    bucket_amounts = {
        "under_1y": ZERO,
        "1_to_2y": ZERO,
        "2_to_4y": ZERO,
        "over_4y": ZERO,
    }

    for lot in open_lots:
        amount = decimal_value(lot.get("remaining_btc"))
        acquired = _parse_timestamp(lot.get("timestamp"))
        if acquired is None or acquired > now:
            continue
        age_days = Decimal(str((now - acquired).total_seconds() / 86400))
        weighted_age_days += amount * age_days
        oldest_age_days = max(oldest_age_days, age_days)
        # Keep the visual age buckets consistent with the same tropical-year
        # convention used by the weighted/oldest age metrics.  The tax holding
        # rule remains an independent configurable day count (default: 365).
        if age_days < DAYS_PER_YEAR:
            bucket_amounts["under_1y"] += amount
        elif age_days < DAYS_PER_YEAR * Decimal("2"):
            bucket_amounts["1_to_2y"] += amount
        elif age_days < DAYS_PER_YEAR * Decimal("4"):
            bucket_amounts["2_to_4y"] += amount
        else:
            bucket_amounts["over_4y"] += amount

        if lot.get("holding_status") == "short_term":
            long_term_at = _parse_timestamp(lot.get("long_term_date"))
            if long_term_at is not None and long_term_at > now:
                if long_term_at <= now + timedelta(days=30):
                    next_30 += amount
                if long_term_at <= now + timedelta(days=90):
                    next_90 += amount

    def pct(value: Decimal) -> Decimal:
        return value / total * Decimal("100") if total > 0 else ZERO

    weighted_years = (
        (weighted_age_days / total) / DAYS_PER_YEAR if total > 0 else ZERO
    )
    oldest_years = oldest_age_days / DAYS_PER_YEAR if oldest_age_days > 0 else ZERO
    return {
        "total_btc": total,
        "over_rule_btc": long_term,
        "under_rule_btc": short_term,
        "unknown_btc": unknown,
        "over_rule_percent": pct(long_term),
        "under_rule_percent": pct(short_term),
        "unknown_percent": pct(unknown),
        "next_30_btc": next_30,
        "next_90_btc": next_90,
        "weighted_age_years": weighted_years,
        "oldest_open_lot_years": oldest_years,
        "age_distribution": {
            key: {"btc": value, "percent": pct(value)}
            for key, value in bucket_amounts.items()
        },
        "long_term_days": int(fifo.get("long_term_days") or 365),
    }



_LEGACY_MINING_SATS_RE = re.compile(
    r"(?:^|\s[·|]\s)Mining Fee:\s*([0-9]+(?:[.,][0-9]+)?)\s*sats(?:\s[·|]\s|$)",
    re.IGNORECASE,
)
_LEGACY_NETWORK_BTC_RE = re.compile(
    r"(?:Netzwerkgebühr|Network fee)(?:\s+aus Memo|\s+from memo)?\s*:\s*([0-9]+(?:[.,][0-9]+)?)\s*BTC\b",
    re.IGNORECASE,
)


def _legacy_btc_fee_from_generated_note(entry: dict[str, Any]) -> Decimal:
    """Recover only BTC fees that our own older importer wrote explicitly.

    This is deliberately conservative: no fee is inferred from fiat values,
    prices, transaction sizes or generic free-form notes.  That avoids inventing
    satoshi fees for legacy ledgers while still recovering exact on-chain/mining
    fees from the structured note formats used by older tracker releases.
    """
    note = str(entry.get("note") or "")
    if not note:
        return ZERO
    if "Coinfinity" in note and ("On-Chain" in note or "Onchain" in note):
        match = _LEGACY_MINING_SATS_RE.search(note)
        if match:
            raw = match.group(1).replace(",", ".")
            try:
                return abs(Decimal(raw)) / SATS_PER_BTC
            except Exception:
                return ZERO
    match = _LEGACY_NETWORK_BTC_RE.search(note)
    if match:
        raw = match.group(1).replace(",", ".")
        try:
            return abs(Decimal(raw))
        except Exception:
            return ZERO
    return ZERO


def _legacy_onchain_fee_may_be_missing(entry: dict[str, Any]) -> bool:
    """Return True when an older booking signals on-chain use but no exact BTC fee survives."""
    note = str(entry.get("note") or "").lower()
    return any(token in note for token in ("on-chain", "onchain", "mining fee", "netzwerkgebühr", "network fee"))

def _currency_metrics(
    entries: list[dict[str, Any]],
    fifo: dict[str, Any],
    currency: str,
    live_price: Any,
    now: datetime,
) -> dict[str, Any]:
    code = str(currency or "").upper()
    summary = currency_summary_from_result(fifo, code)
    price = decimal_value(live_price)
    known_btc = decimal_value(summary.get("known_btc"))
    invested = decimal_value(summary.get("invested"))
    realized = decimal_value(summary.get("realized_gain"))
    market_value = known_btc * price if price > 0 else None
    unrealized = market_value - invested if market_value is not None else None
    total_profit = realized + unrealized if unrealized is not None else None

    purchase_outlay = ZERO
    sale_net_proceeds = ZERO
    total_fee = ZERO
    purchase_fee = ZERO
    income_fee = ZERO
    sale_fee = ZERO
    expense_fee = ZERO
    disposition_fee = ZERO
    btc_fee_fiat_equivalent = ZERO
    purchase_btc_fee_fiat = ZERO
    income_btc_fee_fiat = ZERO
    sale_btc_fee_fiat = ZERO
    expense_btc_fee_fiat = ZERO
    included_fee_total = ZERO
    included_fee_purchase = ZERO
    included_fee_sale = ZERO
    included_fee_estimated_total = ZERO
    gross_volume = ZERO
    purchase_gross_volume = ZERO
    income_gross_volume = ZERO
    sale_gross_volume = ZERO
    expense_gross_volume = ZERO
    disposition_gross_volume = ZERO
    purchase_btc = ZERO
    income_btc = ZERO
    sale_btc = ZERO
    expense_btc = ZERO
    network_fee_btc = ZERO
    network_fee_fiat = ZERO
    network_fee_onchain_btc = ZERO
    network_fee_lightning_btc = ZERO
    purchase_count = 0
    income_count = 0
    sale_count = 0
    expense_count = 0
    network_fee_count = 0
    known_btc_fee = ZERO
    known_btc_fee_entries = 0
    btc_fee_data_incomplete = False
    priced_entry_count = 0
    all_priced_currencies: set[str] = set()
    first_priced: tuple[datetime, Decimal] | None = None

    ordered: list[tuple[datetime, dict[str, Any]]] = []
    for entry in entries:
        timestamp = _parse_timestamp(entry.get("timestamp"))
        if timestamp is not None and timestamp <= now:
            ordered.append((timestamp, entry))
    # Match the canonical ledger/FIFO tie-breaker: incoming BTC must be
    # processed before outgoing BTC at the exact same instant.  This makes
    # HODL/CAGR/fee metrics independent of the caller's list order.
    ordered.sort(key=lambda item: (
        item[0],
        1 if item[1].get("type") in {"sale", "expense", "network_fee"} else 0,
        str(item[1].get("id", "")),
    ))

    for timestamp, entry in ordered:
        kind = str(entry.get("type") or "")
        entry_currency = str(entry.get("currency") or "").upper()
        amount = max(decimal_value(entry.get("amount_btc")), ZERO)
        entry_price = max(decimal_value(entry.get("price")), ZERO)
        fee = max(decimal_value(entry.get("fee")), ZERO)
        included_fee = max(decimal_value(entry.get("included_fee")), ZERO)
        analytics_fee = fee + included_fee
        fee_btc = max(decimal_value(entry.get("fee_btc")), ZERO)
        if fee_btc <= 0:
            fee_btc = _legacy_btc_fee_from_generated_note(entry)
        if fee_btc > 0:
            known_btc_fee += fee_btc
            known_btc_fee_entries += 1
        elif _legacy_onchain_fee_may_be_missing(entry):
            btc_fee_data_incomplete = True
        if kind == "network_fee":
            if not entry_currency or entry_price <= 0 or amount <= 0:
                continue
            all_priced_currencies.add(entry_currency)
            if entry_currency != code:
                continue
            network_fee_count += 1
            network_fee_btc += amount
            fee_value = amount * entry_price
            network_fee_fiat += fee_value
            btc_fee_fiat_equivalent += fee_value
            known_btc_fee += amount
            known_btc_fee_entries += 1
            network = str(entry.get("network") or "onchain").lower()
            if network == "lightning":
                network_fee_lightning_btc += amount
            else:
                network_fee_onchain_btc += amount
            continue

        if kind not in {"purchase", "income", "sale", "expense"} or not entry_currency or entry_price <= 0:
            continue
        all_priced_currencies.add(entry_currency)
        if entry_currency != code:
            continue
        priced_entry_count += 1
        gross = amount * entry_price
        fee_btc_fiat = fee_btc * entry_price
        gross_volume += gross
        total_fee += analytics_fee
        btc_fee_fiat_equivalent += fee_btc_fiat
        included_fee_total += included_fee
        if bool(entry.get("included_fee_estimated")):
            included_fee_estimated_total += included_fee
        if first_priced is None and kind in {"purchase", "income"}:
            first_priced = (timestamp, entry_price)
        if kind == "purchase":
            purchase_count += 1
            purchase_btc += amount
            purchase_fee += analytics_fee
            purchase_btc_fee_fiat += fee_btc_fiat
            included_fee_purchase += included_fee
            purchase_gross_volume += gross
            # included_fee is already embedded in the execution price and must
            # not be added to FIFO/cash outlay a second time.
            purchase_outlay += gross + fee
        elif kind == "income":
            income_count += 1
            income_btc += amount
            income_fee += analytics_fee
            income_btc_fee_fiat += fee_btc_fiat
            income_gross_volume += gross
        elif kind == "sale":
            sale_count += 1
            sale_btc += amount
            sale_fee += analytics_fee
            sale_btc_fee_fiat += fee_btc_fiat
            disposition_fee += analytics_fee
            included_fee_sale += included_fee
            sale_gross_volume += gross
            disposition_gross_volume += gross
            # Same rule for sales: only an explicit extra fiat fee is subtracted.
            sale_net_proceeds += max(gross - fee, ZERO)
        elif kind == "expense":
            expense_count += 1
            expense_btc += amount
            expense_fee += analytics_fee
            expense_btc_fee_fiat += fee_btc_fiat
            # A priced expense realizes FIFO gain/loss like a sale, but remains
            # a separate semantic category and does not become fiat cash proceeds.
            disposition_fee += analytics_fee
            expense_gross_volume += gross
            disposition_gross_volume += gross

    net_invested = purchase_outlay - sale_net_proceeds
    fee_ratio = total_fee / gross_volume * Decimal("100") if gross_volume > 0 else ZERO
    purchase_fee_ratio = (
        purchase_fee / purchase_gross_volume * Decimal("100")
        if purchase_gross_volume > 0 else ZERO
    )
    sale_fee_ratio = (
        sale_fee / sale_gross_volume * Decimal("100")
        if sale_gross_volume > 0 else ZERO
    )
    disposition_fee_ratio = (
        disposition_fee / disposition_gross_volume * Decimal("100")
        if disposition_gross_volume > 0 else ZERO
    )

    # Cash-flow-neutral HODL benchmark. Unknown-basis stack entries add the same
    # BTC to both paths. Priced purchases and income add their external value to
    # a fee-free HODL path; priced sales/expenses remove the same net value.
    # A multi-fiat ledger is flagged incomplete because no hidden FX conversion
    # is invented.
    benchmark_complete = not all_priced_currencies or all_priced_currencies == {code}
    benchmark_btc = ZERO
    benchmark_valid = benchmark_complete
    for _timestamp, entry in ordered:
        kind = str(entry.get("type") or "")
        amount = max(decimal_value(entry.get("amount_btc")), ZERO)
        if kind == "stack":
            benchmark_btc += amount
            continue
        entry_currency = str(entry.get("currency") or "").upper()
        entry_price = max(decimal_value(entry.get("price")), ZERO)
        fee = max(decimal_value(entry.get("fee")), ZERO)
        if kind not in {"purchase", "income", "sale", "expense"} or entry_currency != code or entry_price <= 0:
            continue
        if kind in {"purchase", "income"}:
            benchmark_btc += (amount * entry_price + fee) / entry_price
        else:
            withdrawal = max(amount * entry_price - fee, ZERO)
            benchmark_btc -= withdrawal / entry_price
            if benchmark_btc < ZERO:
                benchmark_valid = False
    benchmark_btc = max(benchmark_btc, ZERO)
    actual_btc = decimal_value(fifo.get("total_btc"))
    benchmark_value = benchmark_btc * price if price > 0 and benchmark_valid else None
    actual_value = actual_btc * price if price > 0 else None
    benchmark_diff_btc = actual_btc - benchmark_btc if benchmark_valid else None
    strategy_vs_hodl = (
        (actual_btc / benchmark_btc - Decimal("1")) * Decimal("100")
        if benchmark_valid and benchmark_btc > 0
        else None
    )

    # This is deliberately the BTC market CAGR from the first priced booking,
    # not portfolio CAGR. It therefore remains mathematically meaningful even
    # with later cash flows and complements TWR/XIRR instead of pretending to
    # replace them.
    cagr_percent: Decimal | None = None
    cagr_start_at: str | None = None
    if first_priced is not None and price > 0:
        first_time, first_price = first_priced
        years = Decimal(str((now - first_time).total_seconds() / (86400 * float(DAYS_PER_YEAR))))
        if years > Decimal("0.0027") and first_price > 0:
            cagr_percent = (
                Decimal(str((float(price / first_price) ** (1 / float(years)) - 1)))
                * Decimal("100")
            )
            cagr_start_at = first_time.isoformat()

    sale_realized = sum(
        (decimal_value(value.get("realized_gain")) for value in fifo.get("sales", {}).values()
         if str(value.get("currency") or "").upper() == code),
        ZERO,
    )
    expense_realized = sum(
        (decimal_value(value.get("realized_gain")) for value in fifo.get("expenses", {}).values()
         if str(value.get("currency") or "").upper() == code),
        ZERO,
    )
    fee_realized = sum(
        (decimal_value(value.get("realized_gain")) for value in fifo.get("transaction_fees", {}).values()
         if str(value.get("currency") or "").upper() == code),
        ZERO,
    )

    return {
        "profit": {
            "open_cost_basis": invested,
            "known_btc": known_btc,
            "market_value": market_value,
            "realized": realized,
            "unrealized": unrealized,
            "total": total_profit,
        },
        "net_invested_fiat": net_invested,
        "purchase_outlay": purchase_outlay,
        "sale_net_proceeds": sale_net_proceeds,
        "activity": {
            "purchases": {
                "count": purchase_count, "btc": purchase_btc,
                "value": purchase_gross_volume,
                "fees_fiat": purchase_fee, "btc_fee_fiat": purchase_btc_fee_fiat,
            },
            "income": {
                "count": income_count, "btc": income_btc,
                "value": income_gross_volume,
                "fees_fiat": income_fee, "btc_fee_fiat": income_btc_fee_fiat,
            },
            "sales": {
                "count": sale_count, "btc": sale_btc,
                "value": sale_gross_volume, "net_proceeds": sale_net_proceeds,
                "fees_fiat": sale_fee, "btc_fee_fiat": sale_btc_fee_fiat,
                "realized": sale_realized,
            },
            "expenses": {
                "count": expense_count, "btc": expense_btc,
                "value": expense_gross_volume,
                "fees_fiat": expense_fee, "btc_fee_fiat": expense_btc_fee_fiat,
                "realized": expense_realized,
            },
            "network_fees": {
                "count": network_fee_count, "btc": network_fee_btc,
                "value": network_fee_fiat,
                "onchain_btc": network_fee_onchain_btc,
                "lightning_btc": network_fee_lightning_btc,
                "realized": fee_realized,
            },
            "realized_total": realized,
            "transaction_fee_realized": fee_realized,
        },
        "fees": {
            "total_fiat": total_fee,
            "btc_fiat_equivalent": btc_fee_fiat_equivalent,
            "network_fee_fiat": network_fee_fiat,
            "total_fiat_equivalent": total_fee + btc_fee_fiat_equivalent,
            "purchase_fiat": purchase_fee,
            "income_fiat": income_fee,
            "sale_fiat": sale_fee,
            "expense_fiat": expense_fee,
            "disposition_fiat": disposition_fee,
            "included_fiat": included_fee_total,
            "included_purchase_fiat": included_fee_purchase,
            "included_sale_fiat": included_fee_sale,
            "included_estimated_fiat": included_fee_estimated_total,
            "ratio_percent": fee_ratio,
            "purchase_ratio_percent": purchase_fee_ratio,
            # Retained for API/backward compatibility; the UI uses the broader
            # disposition ratio so card expenses are not silently excluded.
            "sale_ratio_percent": sale_fee_ratio,
            "disposition_ratio_percent": disposition_fee_ratio,
            "gross_volume": gross_volume,
            "purchase_gross_volume": purchase_gross_volume,
            "sale_gross_volume": sale_gross_volume,
            "disposition_gross_volume": disposition_gross_volume,
            "btc": known_btc_fee,
            "btc_sats": known_btc_fee * SATS_PER_BTC,
            "btc_known_entry_count": known_btc_fee_entries,
            "btc_data_incomplete": btc_fee_data_incomplete,
            "priced_entry_count": priced_entry_count,
        },
        "hodl_benchmark": {
            "complete": benchmark_complete,
            "valid": benchmark_valid,
            "actual_btc": actual_btc,
            "benchmark_btc": benchmark_btc if benchmark_valid else None,
            "difference_btc": benchmark_diff_btc,
            "actual_value": actual_value,
            "benchmark_value": benchmark_value,
            "strategy_vs_hodl_percent": strategy_vs_hodl,
            "assumption": "same_external_fiat_cashflows_fee_free_hodl",
        },
        "btc_cagr": {
            "percent": cagr_percent,
            "start_at": cagr_start_at,
            "start_price": first_priced[1] if first_priced else None,
            "end_price": price if price > 0 else None,
        },
    }


def build_dashboard_metrics(
    entries: list[dict[str, Any]],
    fifo: dict[str, Any],
    prices: dict[str, Any],
    currencies: list[str],
    *,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    """Return compact aggregate metrics without exposing raw ledger rows."""
    now = as_of or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)
    codes = sorted({str(code or "").upper() for code in currencies if str(code or "").strip()})
    return {
        "generated_at": now.isoformat(),
        "holding": _holding_metrics(fifo, now),
        "stacking_speed": {
            "30d": _stacking_window(entries, now, 30),
            "365d": _stacking_window(entries, now, 365),
            "since_start": _stacking_window(entries, now, None),
        },
        "currencies": {
            code: _currency_metrics(entries, fifo, code, prices.get(code), now)
            for code in codes
        },
    }
