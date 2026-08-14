"""CSV and ZIP export helpers for Bitcoin Stack Tracker."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

from .fifo import currency_summary_from_result, fifo_result
from .models import decimal_value, money_string, slugify


def _value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return money_string(value)
    return str(value)


def _safe_csv_text(value: Any) -> str:
    """Neutralize spreadsheet formulas in user-controlled text cells."""
    text = str(value or "")
    if text.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def write_csv_export(
    *,
    output_dir: Path,
    portfolio_name: str,
    entries: list[dict[str, Any]],
    depots: list[dict[str, Any]],
    delimiter: str = ";",
    long_term_days: int = 365,
    tax_note: str = "",
) -> dict[str, str]:
    """Write transaction, FIFO-match, and holding-period overview CSV files."""
    output_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%dT%H%M%S%fZ")
    prefix = f"{slugify(portfolio_name, 'bitcoin_stack')}_{stamp}"
    transactions_path = output_dir / f"{prefix}_transactions.csv"
    matches_path = output_dir / f"{prefix}_fifo_matches.csv"
    tax_path = output_dir / f"{prefix}_holding_period_overview.csv"
    zip_path = output_dir / f"{prefix}.zip"
    depot_names = {str(item.get("id")): _safe_csv_text(item.get("name")) for item in depots}
    result = fifo_result(entries, long_term_days=long_term_days, as_of=now)
    sale_summaries = result["sales"]
    expense_summaries = result.get("expenses", {})
    transaction_fee_summaries = result.get("transaction_fees", {})
    open_lots = {str(lot.get("entry_id")): lot for lot in result["open_lots"]}
    purchase_match_details: dict[str, list[dict[str, Any]]] = {}
    for match in result["matches"]:
        if match.get("purchase_id"):
            purchase_match_details.setdefault(str(match["purchase_id"]), []).append(match)

    transaction_fields = [
        "id", "timestamp", "depot_id", "depot_name", "type", "amount_btc",
        "currency", "price_per_btc", "gross_amount", "fee", "network", "network_fee_fiat_value", "included_fee",
        "included_fee_estimated", "fee_btc", "fee_btc_affects_stack", "fee_btc_fiat_equivalent", "fiat_total", "net_amount",
        "fifo_cost_basis", "fifo_realized_gain", "fifo_status",
        "fifo_resolved_btc", "fifo_unresolved_btc", "fifo_oversold_btc",
        "holding_period_days_setting", "holding_status", "holding_days",
        "long_term_date", "remaining_open_btc", "long_term_sale_btc",
        "short_term_sale_btc", "long_term_realized_gain",
        "short_term_realized_gain", "tax_overview_note", "note",
    ]
    with transactions_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=transaction_fields, delimiter=delimiter)
        writer.writeheader()
        for item in sorted(
            entries,
            key=lambda row: (
                row.get("timestamp", ""),
                1 if row.get("type") in {"sale", "expense", "network_fee"} else 0,
                row.get("id", ""),
            ),
        ):
            kind = str(item.get("type", ""))
            amount = decimal_value(item.get("amount_btc"))
            price = decimal_value(item.get("price"))
            fee = decimal_value(item.get("fee"))
            gross = (
                amount * price
                if kind in {"purchase", "income", "sale", "expense"} and price > 0
                else None
            )
            net = (
                gross + fee if kind in {"purchase", "income"} and gross is not None
                else gross - fee if kind in {"sale", "expense"} and gross is not None
                else None
            )
            sale = sale_summaries.get(str(item.get("id")), {})
            expense = expense_summaries.get(str(item.get("id")), {})
            transaction_fee = transaction_fee_summaries.get(str(item.get("id")), {})
            item_id = str(item.get("id"))
            lot = open_lots.get(item_id, {})
            purchase_matches = purchase_match_details.get(item_id, [])
            purchase_statuses = {
                str(match.get("holding_status", "unknown"))
                for match in purchase_matches
                if match.get("holding_status")
            }
            if lot.get("holding_status"):
                purchase_statuses.add(str(lot["holding_status"]))
            purchase_holding_status = (
                next(iter(purchase_statuses))
                if len(purchase_statuses) == 1
                else "mixed"
                if len(purchase_statuses) > 1
                else "unknown"
            )
            holding_status = (
                sale.get("holding_status")
                if kind == "sale"
                else expense.get("holding_status")
                if kind == "expense"
                else transaction_fee.get("holding_status")
                if kind == "network_fee"
                else purchase_holding_status
                if kind in {"purchase", "income", "stack"}
                else ""
            )
            historical_detail = purchase_matches[-1] if purchase_matches else {}
            writer.writerow({
                "id": item.get("id", ""),
                "timestamp": item.get("timestamp", ""),
                "depot_id": item.get("depot_id", "main"),
                "depot_name": depot_names.get(str(item.get("depot_id", "main")), ""),
                "type": kind,
                "amount_btc": _value(amount),
                "currency": item.get("currency", ""),
                "price_per_btc": _value(price) if kind in {"purchase", "income", "sale", "expense", "network_fee"} and price > 0 else "",
                "gross_amount": _value(gross),
                "fee": _value(fee) if kind in {"purchase", "income", "sale", "expense"} and (fee > 0 or price > 0) else "",
                "network": item.get("network", "") if kind == "network_fee" else "",
                "network_fee_fiat_value": _value(amount * price) if kind == "network_fee" and price > 0 else "",
                "included_fee": _value(decimal_value(item.get("included_fee"))) if decimal_value(item.get("included_fee")) > 0 else "",
                "included_fee_estimated": "true" if bool(item.get("included_fee_estimated")) else "",
                "fee_btc": _value(decimal_value(item.get("fee_btc"))) if decimal_value(item.get("fee_btc")) > 0 else "",
                "fee_btc_affects_stack": "true" if bool(item.get("fee_btc_affects_stack")) else "false",
                "fee_btc_fiat_equivalent": _value(decimal_value(item.get("fee_btc")) * price) if decimal_value(item.get("fee_btc")) > 0 and price > 0 else "",
                "fiat_total": _value(net),
                "net_amount": _value(net),
                "fifo_cost_basis": _value(transaction_fee.get("cost_basis") if kind == "network_fee" else expense.get("cost_basis") if kind == "expense" else sale.get("cost_basis")),
                "fifo_realized_gain": _value(transaction_fee.get("realized_gain") if kind == "network_fee" else expense.get("realized_gain") if kind == "expense" else sale.get("realized_gain")),
                "fifo_status": (transaction_fee.get("status", "") if kind == "network_fee" else expense.get("status", "") if kind == "expense" else sale.get("status", "") if kind == "sale" else ""),
                "fifo_resolved_btc": _value(transaction_fee.get("resolved_btc") if kind == "network_fee" else expense.get("resolved_btc") if kind == "expense" else sale.get("resolved_btc")),
                "fifo_unresolved_btc": _value(transaction_fee.get("unknown_cost_basis_btc") if kind == "network_fee" else expense.get("unknown_cost_basis_btc") if kind == "expense" else sale.get("unresolved_btc")),
                "fifo_oversold_btc": _value(transaction_fee.get("oversold_btc") if kind == "network_fee" else expense.get("oversold_btc") if kind == "expense" else sale.get("oversold_btc")),
                "holding_period_days_setting": long_term_days,
                "holding_status": holding_status,
                "holding_days": lot.get("holding_days", historical_detail.get("holding_days", "")),
                "long_term_date": lot.get("long_term_date", historical_detail.get("long_term_date", "")),
                "remaining_open_btc": _value(lot.get("remaining_btc")),
                "long_term_sale_btc": _value(sale.get("long_term_btc")),
                "short_term_sale_btc": _value(sale.get("short_term_btc")),
                "long_term_realized_gain": _value(sale.get("long_term_realized_gain")),
                "short_term_realized_gain": _value(sale.get("short_term_realized_gain")),
                "tax_overview_note": _safe_csv_text(tax_note),
                "note": _safe_csv_text(item.get("note", "")),
            })

    match_fields = [
        "sale_id", "sale_timestamp", "disposition_type", "purchase_id", "purchase_timestamp",
        "depot_id", "depot_name", "amount_btc", "purchase_currency",
        "sale_currency", "fifo_cost_basis", "net_sale_proceeds",
        "realized_gain", "status", "holding_period_days_setting",
        "holding_days", "holding_status", "long_term_date", "tax_overview_note",
    ]
    with matches_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=match_fields, delimiter=delimiter)
        writer.writeheader()
        for match in result["matches"]:
            writer.writerow({
                "sale_id": match.get("sale_id", ""),
                "sale_timestamp": match.get("sale_timestamp", ""),
                "disposition_type": match.get("disposition_type", "sale"),
                "purchase_id": match.get("purchase_id", ""),
                "purchase_timestamp": match.get("purchase_timestamp", ""),
                "depot_id": match.get("depot_id", ""),
                "depot_name": depot_names.get(str(match.get("depot_id", "")), ""),
                "amount_btc": _value(match.get("amount_btc")),
                "purchase_currency": match.get("purchase_currency", ""),
                "sale_currency": match.get("sale_currency", ""),
                "fifo_cost_basis": _value(match.get("cost_basis")),
                "net_sale_proceeds": _value(match.get("net_proceeds")),
                "realized_gain": _value(match.get("realized_gain")),
                "status": match.get("status", ""),
                "holding_period_days_setting": long_term_days,
                "holding_days": match.get("holding_days", ""),
                "holding_status": match.get("holding_status", ""),
                "long_term_date": match.get("long_term_date", ""),
                "tax_overview_note": _safe_csv_text(tax_note),
            })

    currencies = sorted(
        {
            str(item.get("currency", "")).upper()
            for item in entries
            if item.get("currency")
        }
    )
    overview_fields = [
        "generated_at", "portfolio", "scope", "depot_id", "depot_name",
        "currency", "holding_period_days_setting", "long_term_open_btc",
        "short_term_open_btc", "unknown_holding_open_btc", "next_long_term_date",
        "next_long_term_btc", "realized_long_term_gain",
        "realized_short_term_gain", "total_realized_gain", "purchase_fees",
        "income_fees", "sale_fees", "unresolved_fifo_btc", "tax_overview_note",
        "disclaimer",
    ]
    with tax_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=overview_fields, delimiter=delimiter)
        writer.writeheader()
        scopes: list[tuple[str, str, str | None]] = [("all", "", None)] + [
            ("depot", str(depot.get("name", "")), str(depot.get("id")))
            for depot in depots
        ]
        for scope, depot_name, current_depot in scopes:
            scoped = fifo_result(
                entries,
                current_depot,
                long_term_days=long_term_days,
                as_of=now,
            )
            for currency in currencies or [""]:
                summary = currency_summary_from_result(scoped, currency) if currency else None
                writer.writerow({
                    "generated_at": now.isoformat(),
                    "portfolio": _safe_csv_text(portfolio_name),
                    "scope": scope,
                    "depot_id": current_depot or "all",
                    "depot_name": depot_name,
                    "currency": currency,
                    "holding_period_days_setting": long_term_days,
                    "long_term_open_btc": _value(scoped["long_term_btc"]),
                    "short_term_open_btc": _value(scoped["short_term_btc"]),
                    "unknown_holding_open_btc": _value(scoped["unknown_holding_btc"]),
                    "next_long_term_date": scoped.get("next_long_term_date") or "",
                    "next_long_term_btc": _value(scoped.get("next_long_term_btc")),
                    "realized_long_term_gain": _value(summary["realized_long_term_gain"] if summary else None),
                    "realized_short_term_gain": _value(summary["realized_short_term_gain"] if summary else None),
                    "total_realized_gain": _value(summary["realized_gain"] if summary else None),
                    "purchase_fees": _value(summary["purchase_fees"] if summary else None),
                    "income_fees": _value(summary.get("income_fees") if summary else None),
                    "sale_fees": _value(summary["sale_fees"] if summary else None),
                    "unresolved_fifo_btc": _value(scoped["unresolved_btc"]),
                    "tax_overview_note": _safe_csv_text(tax_note),
                    "disclaimer": "Holding-period overview only; not tax advice and not a tax return.",
                })

    with ZipFile(zip_path, "w", compression=ZIP_DEFLATED) as archive:
        archive.write(transactions_path, transactions_path.name)
        archive.write(matches_path, matches_path.name)
        archive.write(tax_path, tax_path.name)

    # CSV is necessarily plaintext. Restrict host permissions and prefer the
    # dashboard's ephemeral download endpoint over persistent manual exports.
    for path in (transactions_path, matches_path, tax_path, zip_path):
        try:
            path.chmod(0o600)
        except OSError:
            pass

    return {
        "transactions": str(transactions_path),
        "fifo_matches": str(matches_path),
        "holding_period_overview": str(tax_path),
        "zip": str(zip_path),
    }
