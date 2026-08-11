"""FIFO accounting and configurable holding-period overview for Bitcoin only."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from .models import decimal_value

ZERO = Decimal("0")


def _sorted_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sort ledger rows by their real UTC instant, never lexicographically.

    ISO-8601 strings with different offsets can compare in the opposite order
    from the instants they represent. FIFO must therefore sort parsed UTC
    datetimes. Incoming BTC rows win ties before outgoing rows.
    """

    def sort_key(row: dict[str, Any]) -> tuple[datetime, int, str]:
        parsed = _parse_timestamp(row.get("timestamp"))
        if parsed is None:
            parsed = datetime.max.replace(tzinfo=timezone.utc)
        return (
            parsed,
            1 if row.get("type") in {"sale", "expense"} else 0,
            str(row.get("id", "")),
        )

    return sorted(entries, key=sort_key)


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


def _holding_details(
    acquired_at: Any, reference_at: Any, long_term_days: int
) -> dict[str, Any]:
    acquired = _parse_timestamp(acquired_at)
    reference = _parse_timestamp(reference_at)
    if acquired is None or reference is None or reference < acquired:
        return {
            "holding_days": None,
            "holding_status": "unknown",
            "long_term_date": None,
            "days_until_long_term": None,
        }
    long_term_at = acquired + timedelta(days=max(1, int(long_term_days)))
    seconds = (reference - acquired).total_seconds()
    holding_days = max(0, int(seconds // 86400))
    remaining_seconds = (long_term_at - reference).total_seconds()
    days_until = max(0, int((remaining_seconds + 86399) // 86400))
    return {
        "holding_days": holding_days,
        "holding_status": "long_term" if reference >= long_term_at else "short_term",
        "long_term_date": long_term_at.isoformat(),
        "days_until_long_term": days_until,
    }


def cumulative_average_entry_price_by_disposition(
    entries: list[dict[str, Any]],
) -> dict[str, Decimal]:
    """Return the portfolio-wide weighted average acquisition price at each disposal.

    The comparison deliberately differs from FIFO. It answers the intuitive
    question "was this sale/expense above or below my average buy-in at that
    moment?" by using every priced purchase in the same fiat currency up to the
    outgoing booking's timestamp, including purchase fees in the effective
    acquisition price. Previously sold purchases remain part of this historical
    average because the metric is a cumulative buy-in comparison, not an open-lot
    cost basis.

    No FX conversion is invented. Stack entries without an acquisition price are
    excluded. Equal-timestamp purchases are included because ``_sorted_entries``
    orders incoming BTC before outgoing BTC.
    """
    totals: dict[str, dict[str, Decimal]] = {}
    result: dict[str, Decimal] = {}

    for item in _sorted_entries(entries):
        kind = str(item.get("type") or "")
        amount = max(decimal_value(item.get("amount_btc")), ZERO)
        if amount <= 0:
            continue

        if kind == "purchase":
            currency = str(item.get("currency") or "").upper()
            price = decimal_value(item.get("price"))
            if not currency or price <= 0:
                continue
            fee = max(decimal_value(item.get("fee")), ZERO)
            bucket = totals.setdefault(
                currency,
                {"btc": ZERO, "basis": ZERO},
            )
            bucket["btc"] += amount
            bucket["basis"] += amount * price + fee
            continue

        if kind not in {"sale", "expense"}:
            continue

        entry_id = str(item.get("id") or "")
        currency = str(item.get("currency") or "").upper()
        if not entry_id or not currency:
            continue
        bucket = totals.get(currency)
        if not bucket or bucket["btc"] <= 0:
            continue
        result[entry_id] = bucket["basis"] / bucket["btc"]

    return result


def fifo_result(
    entries: list[dict[str, Any]],
    depot_id: str | None = None,
    *,
    long_term_days: int = 365,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    """Return open FIFO lots, sale matches, gains, and holding-period classes.

    FIFO is independent inside each depot. Fiat gains are calculated only if a
    purchase lot and its sale use the same fiat currency. The holding-period
    classification is a configurable overview and deliberately does not assert
    any country's tax treatment.
    """
    threshold = max(1, int(long_term_days))
    reference = as_of or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    reference = reference.astimezone(timezone.utc)

    lots_by_depot: dict[str, list[dict[str, Any]]] = {}
    # Index of the first lot that may still contain BTC for each depot. Keeping
    # this cursor makes repeated sales/expenses O(n) overall instead of
    # rescanning every already-consumed lot from the beginning each time.
    lot_cursor_by_depot: dict[str, int] = {}
    matches: list[dict[str, Any]] = []
    sales: dict[str, dict[str, Any]] = {}
    expenses: dict[str, dict[str, Any]] = {}
    purchase_fees: dict[str, Decimal] = {}
    sale_fees: dict[str, Decimal] = {}
    realized: dict[str, Decimal] = {}
    realized_long_term: dict[str, Decimal] = {}
    realized_short_term: dict[str, Decimal] = {}
    unresolved_btc = ZERO
    oversold_btc = ZERO

    filtered = [
        item
        for item in _sorted_entries(entries)
        if depot_id is None or str(item.get("depot_id", "main")) == depot_id
    ]

    for item in filtered:
        kind = item.get("type")
        current_depot = str(item.get("depot_id", "main"))
        amount = max(decimal_value(item.get("amount_btc")), ZERO)
        if amount <= 0:
            continue
        lots = lots_by_depot.setdefault(current_depot, [])

        if kind in {"purchase", "stack"}:
            currency = (
                str(item.get("currency", "")).upper()
                if kind == "purchase" and item.get("currency")
                else None
            )
            price = decimal_value(item.get("price")) if kind == "purchase" else ZERO
            fee = decimal_value(item.get("fee")) if kind == "purchase" else ZERO
            total_basis = amount * price + fee if kind == "purchase" else None
            unit_basis = total_basis / amount if total_basis is not None and amount > 0 else None
            lots.append(
                {
                    "entry_id": item.get("id"),
                    "timestamp": item.get("timestamp"),
                    "depot_id": current_depot,
                    "original_btc": amount,
                    "remaining_btc": amount,
                    "currency": currency,
                    "unit_basis": unit_basis,
                    "known_cost": kind == "purchase",
                    "source_type": kind,
                }
            )
            if currency:
                purchase_fees[currency] = purchase_fees.get(currency, ZERO) + fee
            continue

        if kind == "expense":
            expense_timestamp = item.get("timestamp")
            expense_currency = str(item.get("currency", "")).upper()
            expense_price = decimal_value(item.get("price"))
            expense_fee = decimal_value(item.get("fee"))
            priced_expense = bool(expense_currency and expense_price > 0)
            remaining_expense = amount
            expense_summary: dict[str, Any] = {
                "entry_id": item.get("id"),
                "timestamp": expense_timestamp,
                "depot_id": current_depot,
                "amount_btc": amount,
                "currency": expense_currency if priced_expense else "",
                "gross_proceeds": amount * expense_price if priced_expense else None,
                "fee": expense_fee if priced_expense else ZERO,
                "resolved_btc": ZERO,
                "unresolved_btc": ZERO,
                "oversold_btc": ZERO,
                "cost_basis": ZERO,
                "realized_gain": ZERO,
                "unknown_cost_basis_btc": ZERO,
                "long_term_btc": ZERO,
                "short_term_btc": ZERO,
                "unknown_holding_btc": ZERO,
                "long_term_realized_gain": ZERO,
                "short_term_realized_gain": ZERO,
                "long_term_days": threshold,
            }
            lot_cursor = lot_cursor_by_depot.get(current_depot, 0)
            while lot_cursor < len(lots) and remaining_expense > 0:
                lot = lots[lot_cursor]
                available = decimal_value(lot.get("remaining_btc"))
                if available <= 0:
                    lot_cursor += 1
                    continue
                used = min(available, remaining_expense)
                remaining_in_lot = available - used
                lot["remaining_btc"] = remaining_in_lot
                remaining_expense -= used

                fee_share = (
                    expense_fee * used / amount
                    if priced_expense and amount > 0
                    else ZERO
                )
                proceeds = (
                    used * expense_price - fee_share
                    if priced_expense
                    else None
                )
                lot_currency = lot.get("currency")
                known_cost = bool(lot.get("known_cost"))
                same_currency = bool(
                    priced_expense and lot_currency and lot_currency == expense_currency
                )
                cost_basis = (
                    used * decimal_value(lot.get("unit_basis"))
                    if known_cost and same_currency
                    else None
                )
                gain = (
                    proceeds - cost_basis
                    if proceeds is not None and cost_basis is not None
                    else None
                )
                match_status = (
                    "resolved"
                    if gain is not None
                    else "unknown_proceeds"
                    if not priced_expense
                    else "unknown_cost_basis"
                    if not known_cost
                    else "currency_conversion_required"
                )

                holding = _holding_details(lot.get("timestamp"), expense_timestamp, threshold)
                holding_status = holding["holding_status"]
                if holding_status == "long_term":
                    expense_summary["long_term_btc"] += used
                elif holding_status == "short_term":
                    expense_summary["short_term_btc"] += used
                else:
                    expense_summary["unknown_holding_btc"] += used

                if gain is None:
                    unresolved_btc += used
                    expense_summary["unresolved_btc"] += used
                    if not known_cost:
                        expense_summary["unknown_cost_basis_btc"] += used
                    # Preserve the known acquisition basis for the expense
                    # summary even when no fiat proceeds are available.
                    elif lot.get("unit_basis") is not None:
                        expense_summary["cost_basis"] += used * decimal_value(lot.get("unit_basis"))
                else:
                    expense_summary["resolved_btc"] += used
                    expense_summary["cost_basis"] += cost_basis
                    expense_summary["realized_gain"] += gain
                    realized[expense_currency] = realized.get(expense_currency, ZERO) + gain
                    if holding_status == "long_term":
                        expense_summary["long_term_realized_gain"] += gain
                        realized_long_term[expense_currency] = (
                            realized_long_term.get(expense_currency, ZERO) + gain
                        )
                    elif holding_status == "short_term":
                        expense_summary["short_term_realized_gain"] += gain
                        realized_short_term[expense_currency] = (
                            realized_short_term.get(expense_currency, ZERO) + gain
                        )

                matches.append(
                    {
                        # Keep sale_id for compatibility with older frontend/index
                        # code, while disposition_type makes the actual ledger kind
                        # explicit. Card payments remain expenses in the ledger.
                        "sale_id": item.get("id"),
                        "disposition_id": item.get("id"),
                        "disposition_type": "expense",
                        "sale_timestamp": expense_timestamp,
                        "purchase_id": lot.get("entry_id"),
                        "purchase_timestamp": lot.get("timestamp"),
                        "depot_id": current_depot,
                        "amount_btc": used,
                        "purchase_currency": lot_currency,
                        "sale_currency": expense_currency if priced_expense else "",
                        "cost_basis": cost_basis,
                        "net_proceeds": proceeds,
                        "realized_gain": gain,
                        "status": match_status,
                        **holding,
                    }
                )
                if remaining_in_lot <= 0:
                    lot_cursor += 1

            lot_cursor_by_depot[current_depot] = lot_cursor
            if remaining_expense > 0:
                oversold_btc += remaining_expense
                expense_summary["oversold_btc"] = remaining_expense
                expense_summary["unresolved_btc"] += remaining_expense
                expense_summary["unknown_holding_btc"] += remaining_expense
                unresolved_btc += remaining_expense
                matches.append(
                    {
                        "sale_id": item.get("id"),
                        "disposition_id": item.get("id"),
                        "disposition_type": "expense",
                        "sale_timestamp": expense_timestamp,
                        "purchase_id": None,
                        "purchase_timestamp": None,
                        "depot_id": current_depot,
                        "amount_btc": remaining_expense,
                        "purchase_currency": None,
                        "sale_currency": expense_currency if priced_expense else "",
                        "cost_basis": None,
                        "net_proceeds": (
                            remaining_expense * expense_price
                            - (expense_fee * remaining_expense / amount if amount > 0 else ZERO)
                            if priced_expense
                            else None
                        ),
                        "realized_gain": None,
                        "status": "insufficient_stack",
                        "holding_days": None,
                        "holding_status": "unknown",
                        "long_term_date": None,
                        "days_until_long_term": None,
                    }
                )

            if expense_summary["oversold_btc"] > 0:
                expense_summary["status"] = "insufficient_stack"
            elif expense_summary["unresolved_btc"] > 0 and expense_summary["resolved_btc"] > 0:
                expense_summary["status"] = "partially_resolved"
            elif expense_summary["unresolved_btc"] > 0:
                expense_summary["status"] = "unresolved"
            else:
                expense_summary["status"] = "resolved"

            classes = sum(
                1 for key in ("long_term_btc", "short_term_btc", "unknown_holding_btc")
                if expense_summary[key] > 0
            )
            if classes > 1:
                expense_summary["holding_status"] = "mixed"
            elif expense_summary["long_term_btc"] > 0:
                expense_summary["holding_status"] = "long_term"
            elif expense_summary["short_term_btc"] > 0:
                expense_summary["holding_status"] = "short_term"
            else:
                expense_summary["holding_status"] = "unknown"
            expenses[str(item.get("id"))] = expense_summary
            continue

        if kind != "sale":
            continue

        sale_timestamp = item.get("timestamp")
        sale_currency = str(item.get("currency", "")).upper()
        sale_price = decimal_value(item.get("price"))
        sale_fee = decimal_value(item.get("fee"))
        sale_fees[sale_currency] = sale_fees.get(sale_currency, ZERO) + sale_fee
        remaining_sale = amount
        sale_summary: dict[str, Any] = {
            "entry_id": item.get("id"),
            "timestamp": sale_timestamp,
            "depot_id": current_depot,
            "amount_btc": amount,
            "currency": sale_currency,
            "gross_proceeds": amount * sale_price,
            "fee": sale_fee,
            "resolved_btc": ZERO,
            "unresolved_btc": ZERO,
            "cost_basis": ZERO,
            "realized_gain": ZERO,
            "long_term_btc": ZERO,
            "short_term_btc": ZERO,
            "unknown_holding_btc": ZERO,
            "long_term_realized_gain": ZERO,
            "short_term_realized_gain": ZERO,
            "oversold_btc": ZERO,
            "long_term_days": threshold,
        }

        lot_cursor = lot_cursor_by_depot.get(current_depot, 0)
        while lot_cursor < len(lots) and remaining_sale > 0:
            lot = lots[lot_cursor]
            available = decimal_value(lot.get("remaining_btc"))
            if available <= 0:
                lot_cursor += 1
                continue
            used = min(available, remaining_sale)
            remaining_in_lot = available - used
            lot["remaining_btc"] = remaining_in_lot
            remaining_sale -= used

            fee_share = sale_fee * used / amount if amount > 0 else ZERO
            proceeds = used * sale_price - fee_share
            lot_currency = lot.get("currency")
            known_cost = bool(lot.get("known_cost"))
            same_currency = bool(lot_currency and lot_currency == sale_currency)
            cost_basis = (
                used * decimal_value(lot.get("unit_basis"))
                if known_cost and same_currency
                else None
            )
            gain = proceeds - cost_basis if cost_basis is not None else None
            match_status = (
                "resolved"
                if gain is not None
                else "unknown_cost_basis"
                if not known_cost
                else "currency_conversion_required"
            )
            holding = _holding_details(lot.get("timestamp"), sale_timestamp, threshold)
            holding_status = holding["holding_status"]
            if holding_status == "long_term":
                sale_summary["long_term_btc"] += used
            elif holding_status == "short_term":
                sale_summary["short_term_btc"] += used
            else:
                sale_summary["unknown_holding_btc"] += used

            if gain is None:
                unresolved_btc += used
                sale_summary["unresolved_btc"] += used
            else:
                sale_summary["resolved_btc"] += used
                sale_summary["cost_basis"] += cost_basis
                sale_summary["realized_gain"] += gain
                realized[sale_currency] = realized.get(sale_currency, ZERO) + gain
                if holding_status == "long_term":
                    sale_summary["long_term_realized_gain"] += gain
                    realized_long_term[sale_currency] = (
                        realized_long_term.get(sale_currency, ZERO) + gain
                    )
                elif holding_status == "short_term":
                    sale_summary["short_term_realized_gain"] += gain
                    realized_short_term[sale_currency] = (
                        realized_short_term.get(sale_currency, ZERO) + gain
                    )

            matches.append(
                {
                    "sale_id": item.get("id"),
                    "disposition_id": item.get("id"),
                    "disposition_type": "sale",
                    "sale_timestamp": sale_timestamp,
                    "purchase_id": lot.get("entry_id"),
                    "purchase_timestamp": lot.get("timestamp"),
                    "depot_id": current_depot,
                    "amount_btc": used,
                    "purchase_currency": lot_currency,
                    "sale_currency": sale_currency,
                    "cost_basis": cost_basis,
                    "net_proceeds": proceeds,
                    "realized_gain": gain,
                    "status": match_status,
                    **holding,
                }
            )
            if remaining_in_lot <= 0:
                lot_cursor += 1

        lot_cursor_by_depot[current_depot] = lot_cursor
        if remaining_sale > 0:
            oversold_btc += remaining_sale
            sale_summary["oversold_btc"] = remaining_sale
            sale_summary["unresolved_btc"] += remaining_sale
            sale_summary["unknown_holding_btc"] += remaining_sale
            unresolved_btc += remaining_sale
            matches.append(
                {
                    "sale_id": item.get("id"),
                    "disposition_id": item.get("id"),
                    "disposition_type": "sale",
                    "sale_timestamp": sale_timestamp,
                    "purchase_id": None,
                    "purchase_timestamp": None,
                    "depot_id": current_depot,
                    "amount_btc": remaining_sale,
                    "purchase_currency": None,
                    "sale_currency": sale_currency,
                    "cost_basis": None,
                    "net_proceeds": remaining_sale * sale_price
                    - (sale_fee * remaining_sale / amount if amount > 0 else ZERO),
                    "realized_gain": None,
                    "status": "insufficient_stack",
                    "holding_days": None,
                    "holding_status": "unknown",
                    "long_term_date": None,
                    "days_until_long_term": None,
                }
            )

        if sale_summary["oversold_btc"] > 0:
            sale_summary["status"] = "insufficient_stack"
        elif sale_summary["unresolved_btc"] > 0 and sale_summary["resolved_btc"] > 0:
            sale_summary["status"] = "partially_resolved"
        elif sale_summary["unresolved_btc"] > 0:
            sale_summary["status"] = "unresolved"
        else:
            sale_summary["status"] = "resolved"

        holding_classes = sum(
            1
            for key in ("long_term_btc", "short_term_btc", "unknown_holding_btc")
            if sale_summary[key] > 0
        )
        if holding_classes > 1:
            sale_summary["holding_status"] = "mixed"
        elif sale_summary["long_term_btc"] > 0:
            sale_summary["holding_status"] = "long_term"
        elif sale_summary["short_term_btc"] > 0:
            sale_summary["holding_status"] = "short_term"
        else:
            sale_summary["holding_status"] = "unknown"
        sales[str(item.get("id"))] = sale_summary

    open_lots: list[dict[str, Any]] = []
    for lots in lots_by_depot.values():
        for lot in lots:
            if decimal_value(lot.get("remaining_btc")) <= 0:
                continue
            enriched = deepcopy(lot)
            enriched.update(_holding_details(lot.get("timestamp"), reference, threshold))
            open_lots.append(enriched)

    total_btc = sum((decimal_value(lot["remaining_btc"]) for lot in open_lots), ZERO)
    known_btc = sum(
        (
            decimal_value(lot["remaining_btc"])
            for lot in open_lots
            if lot.get("known_cost")
        ),
        ZERO,
    )
    unknown_btc = total_btc - known_btc
    long_term_btc = sum(
        (
            decimal_value(lot["remaining_btc"])
            for lot in open_lots
            if lot.get("holding_status") == "long_term"
        ),
        ZERO,
    )
    short_term_btc = sum(
        (
            decimal_value(lot["remaining_btc"])
            for lot in open_lots
            if lot.get("holding_status") == "short_term"
        ),
        ZERO,
    )
    unknown_holding_btc = total_btc - long_term_btc - short_term_btc
    upcoming = sorted(
        (
            lot
            for lot in open_lots
            if lot.get("holding_status") == "short_term" and lot.get("long_term_date")
        ),
        key=lambda lot: str(lot.get("long_term_date")),
    )

    return {
        "open_lots": open_lots,
        "matches": matches,
        "sales": sales,
        "expenses": expenses,
        "total_btc": total_btc,
        "known_btc": known_btc,
        "unknown_btc": unknown_btc,
        "long_term_btc": long_term_btc,
        "short_term_btc": short_term_btc,
        "unknown_holding_btc": unknown_holding_btc,
        "next_long_term_date": upcoming[0]["long_term_date"] if upcoming else None,
        "next_long_term_btc": decimal_value(upcoming[0]["remaining_btc"]) if upcoming else ZERO,
        "realized": realized,
        "realized_long_term": realized_long_term,
        "realized_short_term": realized_short_term,
        "purchase_fees": purchase_fees,
        "sale_fees": sale_fees,
        "unresolved_btc": unresolved_btc,
        "oversold_btc": oversold_btc,
        "long_term_days": threshold,
        "as_of": reference.isoformat(),
    }


def currency_summary(
    entries: list[dict[str, Any]],
    currency: str,
    depot_id: str | None = None,
    *,
    long_term_days: int = 365,
    as_of: datetime | None = None,
) -> dict[str, Decimal]:
    """Calculate remaining basis and realized gain for one currency."""
    return currency_summary_from_result(
        fifo_result(
            entries, depot_id, long_term_days=long_term_days, as_of=as_of
        ),
        currency,
    )


def currency_summary_from_result(
    result: dict[str, Any], currency: str
) -> dict[str, Decimal]:
    """Calculate one currency summary from an existing FIFO result."""
    currency = currency.upper()
    lots = result["open_lots"]
    known_btc = sum(
        (
            decimal_value(lot["remaining_btc"])
            for lot in lots
            if lot.get("currency") == currency
        ),
        ZERO,
    )
    invested = sum(
        (
            decimal_value(lot["remaining_btc"]) * decimal_value(lot.get("unit_basis"))
            for lot in lots
            if lot.get("currency") == currency
        ),
        ZERO,
    )
    return {
        "total_btc": result["total_btc"],
        "known_btc": known_btc,
        "invested": invested,
        "realized_gain": result["realized"].get(currency, ZERO),
        "realized_long_term_gain": result["realized_long_term"].get(currency, ZERO),
        "realized_short_term_gain": result["realized_short_term"].get(currency, ZERO),
        "purchase_fees": result["purchase_fees"].get(currency, ZERO),
        "sale_fees": result["sale_fees"].get(currency, ZERO),
        "unresolved_btc": result["unresolved_btc"],
        "long_term_btc": result["long_term_btc"],
        "short_term_btc": result["short_term_btc"],
    }
