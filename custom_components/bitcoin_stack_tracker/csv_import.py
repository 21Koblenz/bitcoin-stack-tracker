"""RAM-only CSV import parser used directly by Home Assistant Core.

This module intentionally contains no network code and never persists uploaded
CSV bytes. It is copied into the custom integration so the Tor/network add-on
does not receive portfolio import data.
"""

from __future__ import annotations

from collections import defaultdict, deque
import asyncio
import csv
import hashlib
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from ipaddress import ip_address
import json
from io import BytesIO, StringIO
import logging
import os
import re
import signal
import time
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse
from zipfile import BadZipFile, ZipFile


MAX_IMPORT_BYTES = 10 * 1024 * 1024
MAX_IMPORT_ROWS = 5_000
MAX_IMPORT_COLUMNS = 128
MAX_IMPORT_CELL_CHARS = 16_384
MAX_IMPORT_PREAMBLE_ROWS = 30
FIAT_AND_QUOTES = {
    "EUR", "USD", "CHF", "GBP", "CAD", "AUD", "NZD", "JPY", "SEK", "NOK",
    "DKK", "PLN", "CZK", "HUF", "RON", "BGN", "TRY", "BRL", "MXN", "ZAR",
    "SGD", "HKD", "AED", "USDT", "USDC", "FDUSD", "BUSD", "DAI", "TUSD",
}
BTC_CODES = {"BTC", "XBT", "XXBT", "XBTC"}


def _clean_header(value: Any) -> str:
    text = str(value or "").replace("\ufeff", "").strip().lower()
    text = text.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _asset(value: Any) -> str:
    code = re.sub(r"[^A-Za-z0-9]", "", str(value or "")).upper()
    if code in BTC_CODES or code.endswith("XBT"):
        return "BTC"
    # Kraken prefixes fiat assets with Z and crypto assets with X.
    if len(code) == 4 and code[0] in {"X", "Z"} and code[1:] in FIAT_AND_QUOTES:
        return code[1:]
    return code


def _number(value: Any) -> Decimal | None:
    if value is None:
        return None
    text = str(value).strip().replace("\u00a0", " ")
    if not text or text.lower() in {"nan", "none", "null", "-", "--", "n/a"}:
        return None
    text = re.sub(r"(?i)btc|xbt|sats?|eur|usd|chf|gbp|usdt|usdc|dai|busd|fdusd", "", text)
    text = text.replace("€", "").replace("$", "").replace("£", "").replace("'", "").replace(" ", "")
    # European decimal comma and common thousands separators.
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        # A single comma after a leading zero is necessarily a decimal separator
        # for portfolio values (for example 0,001 BTC), not a thousands marker.
        # Multiple comma groups remain valid thousands separators.
        comma_count = text.count(",")
        head, tail = text.rsplit(",", 1)
        normalized_head = head.lstrip("+-")
        if comma_count == 1 and (normalized_head == "0" or len(tail) != 3):
            text = head + "." + tail
        elif comma_count > 1 and all(len(group) == 3 for group in text.split(",")[1:]):
            text = text.replace(",", "")
        else:
            text = text.replace(",", "")
    text = re.sub(r"[^0-9eE+\-.]", "", text)
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def _iso_timestamp(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    numeric = _number(text)
    if numeric is not None and re.fullmatch(r"\d{10,13}(?:\.\d+)?", text):
        seconds = float(numeric / 1000 if numeric >= Decimal("100000000000") else numeric)
        return datetime.fromtimestamp(seconds, tz=timezone.utc).isoformat()
    normalized = text.replace(" UTC", "+00:00").replace(" GMT", "+00:00")
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    candidates = [normalized]
    # Common export formats. Naive timestamps are treated as UTC because most
    # exchange exports label their report time zone as UTC.
    formats = (
        "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
        "%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M", "%d.%m.%Y",
        "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y",
        "%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M", "%m/%d/%Y",
        "%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y %I:%M %p",
        "%d/%m/%Y %I:%M:%S %p", "%d/%m/%Y %I:%M %p",
        "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M", "%Y/%m/%d",
    )
    try:
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    except ValueError:
        pass
    for candidate in candidates:
        for fmt in formats:
            try:
                parsed = datetime.strptime(candidate, fmt).replace(tzinfo=timezone.utc)
                return parsed.isoformat()
            except ValueError:
                continue
    return None


def _extract_code(value: Any) -> str:
    text = str(value or "").upper()
    matches = re.findall(r"\b(?:BTC|XBT|EUR|USD|CHF|GBP|CAD|AUD|JPY|USDT|USDC|FDUSD|BUSD|DAI|TUSD)\b", text)
    return _asset(matches[-1]) if matches else ""


def _row_dict(headers: list[str], values: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    seen: dict[str, int] = defaultdict(int)
    for index, raw_header in enumerate(headers):
        key = _clean_header(raw_header) or f"column {index + 1}"
        seen[key] += 1
        if seen[key] > 1:
            key = f"{key} {seen[key]}"
        result[key] = values[index].strip() if index < len(values) else ""
    return result


def _get(row: dict[str, str], *aliases: str) -> str:
    for alias in aliases:
        key = _clean_header(alias)
        if key in row and str(row[key]).strip():
            return row[key]
    return ""


def _stable_reference(row: dict[str, str], *aliases: str) -> str:
    """Return a stable composite source reference from every available ID field.

    Multiple executions can have identical timestamp, BTC amount, price and fee.
    If an exchange exports transaction/order/trade IDs, every differing ID must
    therefore keep the row distinct. The raw identifiers remain RAM-only; only a
    SHA-256 digest is carried into the reviewed import and persisted.
    """
    parts: list[str] = []
    seen_values: set[str] = set()
    for alias in aliases:
        key = _clean_header(alias)
        value = str(row.get(key) or "").strip()
        if not value or value in seen_values:
            continue
        seen_values.add(value)
        parts.append(f"{key}={value}")
    return "|".join(parts)


def _import_reference_hash(source: str, reference: str) -> str:
    """Return a privacy-preserving import identity hash for one source row."""
    clean_reference = str(reference or "").strip()
    if not clean_reference:
        return ""
    clean_source = re.sub(r"\s+", " ", str(source or "").strip().lower())
    return hashlib.sha256(f"{clean_source}\0{clean_reference}".encode("utf-8")).hexdigest()


def _get_contains(row: dict[str, str], required: Iterable[str], forbidden: Iterable[str] = ()) -> str:
    req = tuple(_clean_header(item) for item in required)
    ban = tuple(_clean_header(item) for item in forbidden)
    for key, value in row.items():
        if all(item in key for item in req) and not any(item in key for item in ban) and str(value).strip():
            return value
    return ""


def _transaction(
    *, source: str, row_number: int, kind: str | None, timestamp: str | None,
    amount_btc: Decimal | None, currency: str, price: Decimal | None,
    fee: Decimal | None = None, note: str = "", warnings: list[str] | None = None,
    reference: str = "", optional_note_fields: dict[str, Any] | None = None,
    import_hints: dict[str, Any] | None = None, fiat_amount: Decimal | None = None,
) -> dict[str, Any]:
    issues = list(warnings or [])
    if kind not in {"purchase", "sale", "expense"}:
        issues.append("Kauf, Verkauf oder Ausgabe konnte nicht bestimmt werden")
    if timestamp is None:
        issues.append("Datum konnte nicht gelesen werden")
    if amount_btc is None or amount_btc <= 0:
        issues.append("BTC-Menge fehlt oder ist ungültig")
    expense_has_currency = kind == "expense" and bool(str(currency or "").strip())
    expense_has_price = kind == "expense" and price is not None and price > 0
    expense_has_fiat_value = expense_has_currency and expense_has_price
    if kind != "expense" and not currency:
        issues.append("Handelswährung fehlt")
    if kind != "expense" and (price is None or price <= 0):
        issues.append("Preis pro BTC fehlt oder ist ungültig")
    if kind == "expense" and expense_has_currency != expense_has_price:
        issues.append("Bei einer bewerteten Ausgabe müssen Währung und Preis gemeinsam vorhanden sein")
    clean_fee = abs(fee or Decimal("0"))
    clean_fiat_amount: Decimal | None = None
    if fiat_amount is not None:
        clean_fiat_amount = abs(fiat_amount)
    elif amount_btc is not None and amount_btc > 0 and price is not None and price > 0 and kind in {"purchase", "sale", "expense"}:
        gross = abs(amount_btc) * abs(price)
        if kind == "purchase":
            clean_fiat_amount = gross + clean_fee
        elif kind in {"sale", "expense"}:
            # A priced BTC expense is a disposal just like a sale for the fiat
            # control calculation: the BTC fee reduces the merchant/fiat value.
            clean_fiat_amount = max(Decimal("0"), gross - clean_fee)
    clean_optional_fields: dict[str, str] = {}
    for key, value in (optional_note_fields or {}).items():
        clean_key = re.sub(r"[^a-z0-9_]+", "_", str(key or "").strip().lower()).strip("_")
        clean_value = str(value or "").strip()
        if clean_key and clean_value:
            # Values are returned only for the editable in-memory preview. They
            # are not persisted unless the user explicitly selects the field.
            clean_optional_fields[clean_key] = clean_value[:2000]
    clean_import_hints: dict[str, Any] = {}
    for key, value in (import_hints or {}).items():
        clean_key = re.sub(r"[^a-z0-9_]+", "_", str(key or "").strip().lower()).strip("_")
        if not clean_key or value is None:
            continue
        if isinstance(value, bool):
            clean_import_hints[clean_key] = value
        elif isinstance(value, (int, float, Decimal)):
            clean_import_hints[clean_key] = str(value)[:120]
        else:
            clean_value = str(value).strip()
            if clean_value:
                clean_import_hints[clean_key] = clean_value[:1000]
    return {
        "selected": not issues,
        "source": source,
        "source_row": row_number,
        "type": kind or "purchase",
        "timestamp": timestamp or "",
        "amount_btc": format(abs(amount_btc or Decimal("0")), "f"),
        "currency": _asset(currency) if kind != "expense" or expense_has_fiat_value else "",
        "price": format(abs(price or Decimal("0")), "f") if kind != "expense" or expense_has_fiat_value else "0",
        "fiat_amount": format(clean_fiat_amount, "f") if clean_fiat_amount is not None and clean_fiat_amount > 0 else "",
        "fee": format(clean_fee, "f") if kind != "expense" or expense_has_fiat_value else "0",
        "note": str(note or "")[:2000],
        # The raw exchange/broker reference is intentionally not returned or
        # persisted. A one-way hash is enough for duplicate detection.
        "import_ref_hash": _import_reference_hash(source, reference),
        "optional_note_fields": clean_optional_fields,
        "import_hints": clean_import_hints,
        "warnings": issues,
        "valid": not issues,
    }


def _detect_source(filename: str, headers: list[str], rows: list[list[str]]) -> str:
    name = filename.lower()
    header_set = {_clean_header(item) for item in headers}
    if {"txid", "refid", "time", "type", "asset", "amount"}.issubset(header_set):
        return "kraken_ledger"
    if {"txid", "ordertxid", "pair", "time", "type", "price", "cost", "vol"}.issubset(header_set):
        return "kraken_trades"
    if {"timestamp", "transaction type", "asset", "quantity transacted"}.issubset(header_set):
        return "coinbase"
    if "utc time" in header_set and "operation" in header_set and "coin" in header_set and "change" in header_set:
        return "binance_statement"
    if "pair" in header_set and ("side" in header_set or "type" in header_set) and ("executed" in header_set or "filled" in header_set):
        return "binance_trade"
    joined = "|".join(_clean_header(item) for item in headers)
    if "buy" in header_set and any(key.startswith("cur") for key in header_set) and "sell" in header_set and "date" in header_set:
        return "cointracking"
    # Current Coinfinity activity exports use this stable field group. Detect
    # the format from the data itself because Android downloads may rename the
    # file and remove the broker name.
    coinfinity_columns = {
        "order id", "type", "date", "amount eur", "amount crypto",
        "crypto", "rate eur",
    }
    if coinfinity_columns.issubset(header_set):
        return "coinfinity"
    wavespace_columns = {
        "type category", "executes at", "transaction id", "transaction type",
        "from currency", "from amount", "to currency", "to amount", "memo",
    }
    if wavespace_columns.issubset(header_set):
        return "wavespace"
    # Pocket exports use a CoinTracking-like layout, but with explicit
    # "Buy Amount" / "Sell Amount" columns and several "(optional)" fields.
    # Detect it from the header so the filename does not need to contain Pocket.
    pocket_columns = {
        "type", "buy amount", "buy cur", "sell amount", "sell cur", "date",
    }
    if pocket_columns.issubset(header_set) and any(
        key in header_set
        for key in (
            "fee amount optional", "fee cur optional", "exchange optional",
            "trade group optional", "comment optional",
        )
    ):
        return "pocket"
    # Pocket also offers its native dashboard export. It is structurally
    # different from the CoinTracking export and uses dotted column names.
    # Header detection keeps working even when Android or a browser renames
    # the downloaded file.
    pocket_native_columns = {
        "type", "date", "price currency", "price amount",
        "cost currency", "cost amount", "fee currency", "fee amount",
        "value currency", "value amount",
    }
    if pocket_native_columns.issubset(header_set):
        return "pocket"
    for brand in ("coinfinity", "relai", "pocket", "bittr", "getbittr", "wavespace", "wave space"):
        if brand.replace(" ", "") in name.replace(" ", ""):
            return brand.replace(" ", "_").replace("getbittr", "bittr")
    if "coinbase" in name:
        return "coinbase"
    if "kraken" in name or "ledger" in name:
        return "kraken_ledger"
    if "binance" in name:
        return "binance_trade"
    if "cointracking" in name:
        return "cointracking"
    return "generic"


def _parse_coinbase(headers: list[str], rows: list[list[str]]) -> tuple[list[dict[str, Any]], int]:
    output: list[dict[str, Any]] = []
    skipped = 0
    for row_no, values in enumerate(rows, start=2):
        row = _row_dict(headers, values)
        asset = _asset(_get(row, "asset"))
        tx_type = _get(row, "transaction type", "type").lower()
        if asset != "BTC" or not any(word in tx_type for word in ("buy", "sell")):
            skipped += 1
            continue
        kind = "sale" if "sell" in tx_type else "purchase"
        amount = _number(_get(row, "quantity transacted", "quantity", "amount"))
        currency = _asset(_get(row, "spot price currency", "price currency", "currency"))
        price = _number(_get(row, "spot price at transaction", "price at transaction", "usd spot price at transaction"))
        subtotal = _number(_get(row, "subtotal", "usd subtotal"))
        total = _number(_get(row, "total inclusive of fees and or spread", "total inclusive of fees", "total"))
        fee = _number(_get(row, "fees and or spread", "fees", "usd fees"))
        if price is None and amount and (subtotal or total):
            price = abs((subtotal or total) / amount)
        if fee is None and subtotal is not None and total is not None:
            fee = abs(total - subtotal)
        output.append(_transaction(
            source="Coinbase", row_number=row_no, kind=kind,
            timestamp=_iso_timestamp(_get(row, "timestamp", "date")), amount_btc=amount,
            currency=currency, price=price, fee=fee,
            note=_get(row, "notes", "note", "description"),
            reference=_stable_reference(row, "transaction id", "id", "txid", "trade id", "order id"),
        ))
    return output, skipped


def _parse_kraken_trades(headers: list[str], rows: list[list[str]]) -> tuple[list[dict[str, Any]], int]:
    output: list[dict[str, Any]] = []
    skipped = 0
    for row_no, values in enumerate(rows, start=2):
        row = _row_dict(headers, values)
        pair = _get(row, "pair", "symbol").upper().replace("/", "").replace("-", "")
        if not any(code in pair for code in BTC_CODES):
            skipped += 1
            continue
        quote = ""
        for code in sorted(FIAT_AND_QUOTES, key=len, reverse=True):
            if pair.endswith(code) or pair.endswith("Z" + code):
                quote = code
                break
        side = _get(row, "type", "side").lower()
        if side not in {"buy", "sell"}:
            skipped += 1
            continue
        output.append(_transaction(
            source="Kraken Trades", row_number=row_no,
            kind="purchase" if side == "buy" else "sale",
            timestamp=_iso_timestamp(_get(row, "time", "date", "timestamp")),
            amount_btc=_number(_get(row, "vol", "volume", "amount")),
            currency=quote,
            price=_number(_get(row, "price")),
            fee=_number(_get(row, "fee")),
            note=f"Kraken {side} {pair}",
            reference=_stable_reference(row, "txid", "ordertxid", "trade id", "tradeid"),
        ))
    return output, skipped


def _parse_kraken_ledger(headers: list[str], rows: list[list[str]]) -> tuple[list[dict[str, Any]], int]:
    grouped: dict[str, list[tuple[int, dict[str, str]]]] = defaultdict(list)
    skipped = 0
    for row_no, values in enumerate(rows, start=2):
        row = _row_dict(headers, values)
        tx_type = _get(row, "type").lower()
        if tx_type not in {"trade", "spend", "receive"}:
            skipped += 1
            continue
        key = _get(row, "refid") or f"{_get(row, 'time')}|{tx_type}"
        grouped[key].append((row_no, row))
    output: list[dict[str, Any]] = []
    for reference, group in grouped.items():
        btc_rows = [(n, r) for n, r in group if _asset(_get(r, "asset")) == "BTC"]
        quote_rows = [(n, r) for n, r in group if _asset(_get(r, "asset")) in FIAT_AND_QUOTES]
        if not btc_rows or not quote_rows:
            skipped += len(group)
            continue
        row_no, btc_row = btc_rows[0]
        _, quote_row = quote_rows[0]
        btc_amount = _number(_get(btc_row, "amount"))
        quote_amount = _number(_get(quote_row, "amount"))
        if btc_amount is None or quote_amount is None or btc_amount == 0:
            output.append(_transaction(
                source="Kraken Ledger", row_number=row_no, kind=None,
                timestamp=_iso_timestamp(_get(btc_row, "time")), amount_btc=btc_amount,
                currency=_asset(_get(quote_row, "asset")), price=None,
                reference=reference,
            ))
            continue
        kind = "purchase" if btc_amount > 0 and quote_amount < 0 else "sale" if btc_amount < 0 and quote_amount > 0 else None
        warnings: list[str] = []
        btc_fee = abs(_number(_get(btc_row, "fee")) or Decimal("0"))
        quote_fee = abs(_number(_get(quote_row, "fee")) or Decimal("0"))
        execution_price = abs(quote_amount / btc_amount)
        disposed_btc = abs(btc_amount)
        fee_fiat = quote_fee
        if btc_fee:
            if kind == "sale":
                # Kraken ledger rows keep the BTC trade amount and BTC fee
                # separate.  On a sale both are debited from the wallet.
                disposed_btc += btc_fee
                fee_fiat += btc_fee * execution_price
            else:
                warnings.append("Kraken-Gebühr in BTC erkannt; erhaltene BTC-Menge bitte prüfen")
        output.append(_transaction(
            source="Kraken Ledger", row_number=row_no, kind=kind,
            timestamp=_iso_timestamp(_get(btc_row, "time")), amount_btc=disposed_btc,
            currency=_asset(_get(quote_row, "asset")),
            price=execution_price,
            fee=fee_fiat, warnings=warnings,
            note="Kraken Ledger-Import", reference=reference,
        ))
    return output, skipped


def _split_amount_asset(value: Any) -> tuple[Decimal | None, str]:
    return _number(value), _extract_code(value)


def _parse_binance_trade(headers: list[str], rows: list[list[str]]) -> tuple[list[dict[str, Any]], int]:
    output: list[dict[str, Any]] = []
    skipped = 0
    for row_no, values in enumerate(rows, start=2):
        row = _row_dict(headers, values)
        pair = _get(row, "pair", "symbol", "market").upper().replace("/", "").replace("-", "").replace("_", "")
        side = _get(row, "side", "type", "direction").lower()
        if "buy" in side or "kauf" in side:
            kind = "purchase"
        elif "sell" in side or "verkauf" in side:
            kind = "sale"
        else:
            skipped += 1
            continue
        executed_value = _get(row, "executed", "filled", "amount", "quantity")
        amount, executed_asset = _split_amount_asset(executed_value)
        if executed_asset and executed_asset != "BTC":
            # Some exports put quote amount under Amount and BTC under Executed.
            btc_value = _get_contains(row, ("executed",)) or _get_contains(row, ("btc",))
            amount, executed_asset = _split_amount_asset(btc_value)
        if executed_asset and executed_asset != "BTC" and "BTC" not in pair:
            skipped += 1
            continue
        if not executed_asset and "BTC" not in pair and _asset(_get(row, "asset", "coin")) != "BTC":
            skipped += 1
            continue
        quote = ""
        for code in sorted(FIAT_AND_QUOTES, key=len, reverse=True):
            if pair.endswith(code):
                quote = code
                break
        price = _number(_get(row, "price", "average price", "avg price"))
        total_value = _number(_get(row, "total", "quote quantity", "amount", "value"))
        if price is None and amount and total_value:
            price = abs(total_value / amount)
        fee_value = _get(row, "fee", "commission")
        fee, fee_asset = _split_amount_asset(fee_value)
        warnings: list[str] = []
        if fee and fee_asset and fee_asset not in {quote, ""}:
            if kind == "sale" and fee_asset == "BTC" and price is not None and amount is not None:
                # A BTC-denominated commission on a BTC sale is an additional
                # wallet debit, not a reduction of the already exported BTC trade
                # amount.  Account for both the extra sats and their fiat value.
                amount = abs(amount) + abs(fee)
                fee = abs(fee) * abs(price)
            else:
                warnings.append(f"Gebühr in {fee_asset} erkannt; Fiat-Gebühr bitte prüfen")
                fee = Decimal("0")
        output.append(_transaction(
            source="Binance Trade", row_number=row_no, kind=kind,
            timestamp=_iso_timestamp(_get(row, "date utc", "utc time", "date", "time", "timestamp")),
            amount_btc=amount, currency=quote or _asset(_get(row, "currency", "quote asset")),
            price=price, fee=fee, warnings=warnings,
            note=f"Binance {side} {pair}".strip(), reference=_stable_reference(row, "trade id", "tradeid", "order id", "orderid", "transaction id", "txid"),
        ))
    return output, skipped


def _parse_binance_statement(headers: list[str], rows: list[list[str]]) -> tuple[list[dict[str, Any]], int]:
    grouped: dict[str, list[tuple[int, dict[str, str]]]] = defaultdict(list)
    skipped = 0
    for row_no, values in enumerate(rows, start=2):
        row = _row_dict(headers, values)
        operation = _get(row, "operation").lower()
        if not any(word in operation for word in ("buy", "sell", "transaction buy", "transaction sold", "large otc")):
            skipped += 1
            continue
        key = "|".join((_get(row, "utc time"), operation, _get(row, "account"), _get(row, "remark")))
        grouped[key].append((row_no, row))
    output: list[dict[str, Any]] = []
    for reference, group in grouped.items():
        btc = [(n, r) for n, r in group if _asset(_get(r, "coin")) == "BTC"]
        quotes = [(n, r) for n, r in group if _asset(_get(r, "coin")) in FIAT_AND_QUOTES]
        if not btc or not quotes:
            skipped += len(group)
            continue
        row_no, btc_row = btc[0]
        _, quote_row = quotes[0]
        btc_change = _number(_get(btc_row, "change"))
        quote_change = _number(_get(quote_row, "change"))
        if not btc_change or quote_change is None:
            skipped += len(group)
            continue
        kind = "purchase" if btc_change > 0 else "sale"
        output.append(_transaction(
            source="Binance Statement", row_number=row_no, kind=kind,
            timestamp=_iso_timestamp(_get(btc_row, "utc time")), amount_btc=abs(btc_change),
            currency=_asset(_get(quote_row, "coin")), price=abs(quote_change / btc_change),
            fee=Decimal("0"), note=_get(btc_row, "remark") or "Binance Transaction Record",
            reference=reference,
        ))
    return output, skipped


def _header_index(headers: list[str], aliases: Iterable[str], occurrence: int = 1) -> int | None:
    wanted = {_clean_header(item) for item in aliases}
    seen = 0
    for index, header in enumerate(headers):
        if _clean_header(header) in wanted:
            seen += 1
            if seen == occurrence:
                return index
    return None


def _parse_cointracking(headers: list[str], rows: list[list[str]]) -> tuple[list[dict[str, Any]], int]:
    # CoinTracking intentionally uses repeated "Cur." columns, so use positions.
    type_i = _header_index(headers, ("Type", "Transaction Type"))
    buy_i = _header_index(headers, ("Buy", "Buy Amount", "Received Quantity"))
    sell_i = _header_index(headers, ("Sell", "Sell Amount", "Sent Quantity"))
    date_i = _header_index(headers, ("Date", "Date and Time", "Timestamp"))
    fee_i = _header_index(headers, ("Fee", "Fee Amount"))
    fee_cur_i = _header_index(headers, ("Fee Cur.", "Fee Currency"))
    comment_i = _header_index(headers, ("Comment", "Notes", "Note"))
    buy_cur_i = _header_index(headers, ("Buy Cur.", "Buy Currency", "Received Currency"))
    sell_cur_i = _header_index(headers, ("Sell Cur.", "Sell Currency", "Sent Currency"))
    if buy_cur_i is None:
        buy_cur_i = _header_index(headers, ("Cur.", "Currency"), occurrence=1)
    if sell_cur_i is None:
        sell_cur_i = _header_index(headers, ("Cur.", "Currency"), occurrence=2)
    if fee_cur_i is None:
        fee_cur_i = _header_index(headers, ("Cur.", "Currency"), occurrence=3)
    output: list[dict[str, Any]] = []
    skipped = 0
    for row_no, values in enumerate(rows, start=2):
        def cell(index: int | None) -> str:
            return values[index].strip() if index is not None and index < len(values) else ""
        buy_cur, sell_cur = _asset(cell(buy_cur_i)), _asset(cell(sell_cur_i))
        buy_amount, sell_amount = _number(cell(buy_i)), _number(cell(sell_i))
        tx_type = cell(type_i).lower()
        if buy_cur == "BTC" and sell_cur:
            kind, amount, currency, fiat_amount = "purchase", buy_amount, sell_cur, sell_amount
        elif sell_cur == "BTC" and buy_cur:
            kind, amount, currency, fiat_amount = "sale", sell_amount, buy_cur, buy_amount
        else:
            skipped += 1
            continue
        price = abs(fiat_amount / amount) if amount and fiat_amount is not None else None
        fee = _number(cell(fee_i))
        fee_currency = _asset(cell(fee_cur_i))
        warnings: list[str] = []
        if fee and fee_currency and fee_currency != currency:
            if kind == "sale" and fee_currency == "BTC" and price is not None and amount is not None:
                # CoinTracking reports the traded BTC amount and a BTC fee in
                # separate columns.  For a sale, both leave the wallet.  Keep the
                # execution price, add the fee-BTC to the disposed quantity and
                # retain its fiat equivalent in the fee field.  Then
                # amount*price-fee equals the actual fiat proceeds.
                amount = abs(amount) + abs(fee)
                fee = abs(fee) * abs(price)
            else:
                warnings.append(
                    f"Gebühr in {fee_currency} erkannt; Fiat-Gebühr in {currency} bitte prüfen"
                )
                fee = Decimal("0")
        output.append(_transaction(
            source="CoinTracking", row_number=row_no, kind=kind,
            timestamp=_iso_timestamp(cell(date_i)), amount_btc=amount,
            currency=currency, price=price, fee=fee, warnings=warnings,
            note=cell(comment_i) or tx_type,
            reference=_stable_reference(
                _row_dict(headers, values),
                "tx id", "txid", "transaction id", "trade id",
                "exchange transaction id", "order id", "ordertxid",
                "reference", "id",
            ),
        ))
    return output, skipped


SATOSHIS_PER_BTC = Decimal("100000000")


def _pocket_btc_amount(value: Any, currency: Any) -> Decimal | None:
    """Return a Pocket amount normalized to BTC for BTC/XBT or sat units."""
    amount = _number(value)
    if amount is None:
        return None
    raw_code = re.sub(r"[^A-Za-z0-9]", "", str(currency or "")).upper()
    if _asset(raw_code) == "BTC":
        return abs(amount)
    if raw_code in {"SAT", "SATS", "SATOSHI", "SATOSHIS"}:
        return abs(amount) / SATOSHIS_PER_BTC
    return None


def _parse_pocket(headers: list[str], rows: list[list[str]]) -> tuple[list[dict[str, Any]], int]:
    """Parse Pocket's CoinTracking-style CSV export.

    Pocket exports a Trade plus Deposit/Withdrawal transfer rows. Only Trade is
    a booking. Lightning and on-chain Withdrawals are not reliably labelled, so
    a Withdrawal is assigned only when its BTC amount uniquely matches a group
    of still-pending purchase trades. Its net BTC amount is then used so the
    tracker reflects what actually arrived in the wallet.
    """
    type_i = _header_index(headers, ("Type",))
    buy_i = _header_index(headers, ("Buy Amount", "Buy"))
    buy_cur_i = _header_index(headers, ("Buy Cur.", "Buy Currency"))
    sell_i = _header_index(headers, ("Sell Amount", "Sell"))
    sell_cur_i = _header_index(headers, ("Sell Cur.", "Sell Currency"))
    fee_i = _header_index(headers, ("Fee Amount (optional)", "Fee Amount", "Fee"))
    fee_cur_i = _header_index(headers, ("Fee Cur. (optional)", "Fee Cur.", "Fee Currency"))
    exchange_i = _header_index(headers, ("Exchange (optional)", "Exchange"))
    trade_group_i = _header_index(headers, ("Trade Group (optional)", "Trade Group", "Trade-Group"))
    comment_i = _header_index(headers, ("Comment (optional)", "Comment", "Note", "Notes"))
    date_i = _header_index(headers, ("Date", "Timestamp", "Date and Time"))

    def cell(values: list[str], index: int | None) -> str:
        return values[index].strip() if index is not None and index < len(values) else ""

    withdrawals: list[dict[str, Any]] = []
    for row_no, values in enumerate(rows, start=2):
        tx_type = cell(values, type_i).strip().lower()
        if "withdraw" not in tx_type and "auszahlung" not in tx_type:
            continue
        buy_btc = _pocket_btc_amount(cell(values, buy_i), cell(values, buy_cur_i))
        sell_btc = _pocket_btc_amount(cell(values, sell_i), cell(values, sell_cur_i))
        fee_btc = _pocket_btc_amount(cell(values, fee_i), cell(values, fee_cur_i)) or Decimal("0")

        # Pocket CoinTracking withdrawal rows describe the BTC leaving Pocket in
        # Sell Amount and list the withdrawal fee separately. The amount that
        # actually reaches the user's wallet is therefore:
        #     Sell Amount - Fee Amount
        # Do NOT apply this rule to Pocket's native dashboard CSV: there,
        # value.amount is already the net wallet amount.
        if sell_btc is not None:
            gross_btc = abs(sell_btc)
            net_btc = gross_btc - abs(fee_btc)
            if net_btc < 0:
                net_btc = Decimal("0")
        elif buy_btc is not None:
            # Defensive fallback for unusual CoinTracking exports that place the
            # BTC transfer on the Buy side.
            gross_btc = abs(buy_btc)
            net_btc = gross_btc
        else:
            gross_btc = None
            net_btc = None

        if net_btc is not None and net_btc > 0:
            timestamp = _iso_timestamp(cell(values, date_i))
            withdrawals.append({
                "row_no": row_no,
                "gross_btc": gross_btc,
                "amount_btc": net_btc,
                "fee_btc": abs(fee_btc),
                "trade_group": cell(values, trade_group_i).strip(),
                "timestamp": timestamp,
            })

    # Pocket can batch several purchases into one on-chain withdrawal to save
    # network fees.  A withdrawal therefore closes the batch of all purchase
    # trades that happened after the previous withdrawal and before this one.
    # This event-order rule intentionally crosses midnight: a withdrawal at
    # 01:55 or 02:24 still belongs to the purchases since the preceding payout,
    # while a new purchase later that morning starts the next batch.
    #
    # CoinTracking exports may be newest-first, so we sort by parsed timestamps
    # instead of trusting CSV row order.  The withdrawal's net wallet amount is
    # distributed proportionally to the gross BTC bought in that batch.  This
    # splits the network fee fairly across all purchases and guarantees that the
    # sum of imported BTC equals the amount that actually reached the wallet.
    purchase_events: list[dict[str, Any]] = []
    for row_no, values in enumerate(rows, start=2):
        if cell(values, type_i).strip().lower() != "trade":
            continue
        buy_cur_raw = cell(values, buy_cur_i)
        sell_cur_raw = cell(values, sell_cur_i)
        buy_asset = _asset(buy_cur_raw)
        sell_asset = _asset(sell_cur_raw)
        buy_btc = _pocket_btc_amount(cell(values, buy_i), buy_cur_raw)
        if buy_btc is None or not sell_asset or sell_asset == "BTC":
            continue
        purchase_events.append({
            "row_no": row_no,
            "gross_btc": buy_btc,
            "timestamp": _iso_timestamp(cell(values, date_i)),
        })

    def _pocket_event_sort_key(item: dict[str, Any], event_priority: int) -> tuple[float, int, int]:
        timestamp = item.get("timestamp")
        if timestamp:
            try:
                return (
                    datetime.fromisoformat(str(timestamp).replace("Z", "+00:00")).timestamp(),
                    event_priority,
                    int(item["row_no"]),
                )
            except (TypeError, ValueError, OverflowError):
                pass
        # If a report contains an invalid/missing timestamp, preserve its source
        # order rather than inventing a date.
        return (float(item["row_no"]), event_priority, int(item["row_no"]))

    timeline: list[tuple[tuple[float, int, int], str, dict[str, Any]]] = []
    timeline.extend((_pocket_event_sort_key(item, 0), "trade", item) for item in purchase_events)
    timeline.extend((_pocket_event_sort_key(item, 1), "withdrawal", item) for item in withdrawals)
    timeline.sort(key=lambda item: item[0])

    withdrawal_allocations: dict[int, Decimal] = {}
    withdrawal_transport: dict[int, str] = {}
    # Keep this map for the common output path, but deliberately do not flag an
    # unmatched transfer. Pocket CoinTracking does not identify Lightning vs.
    # on-chain either, so an unrelated Withdrawal is not an inconsistency by
    # itself and must not poison the pending purchase rows with warnings.
    withdrawal_allocation_warnings: dict[int, str] = {}
    pending_purchases: list[dict[str, Any]] = []
    sat_tolerance = Decimal("0.00000002")

    def _matching_pending_window(
        exported_gross: Decimal, explicit_network_fee: Decimal
    ) -> tuple[int, int, Decimal] | None:
        """Find one unambiguous contiguous purchase group for a Withdrawal.

        Pocket's CoinTracking export can contain both Lightning and on-chain
        withdrawals without a reliable marker that distinguishes them. Therefore
        a Withdrawal is NOT a hard boundary. Reconcile its gross BTC amount
        against a unique contiguous group of still-pending purchase trades.

        A group can sit in the middle of the pending list: an older on-chain
        purchase may keep waiting while a newer purchase is paid via Lightning.
        Only the matched purchases are removed, so a later batched on-chain
        payout can still reconcile the remaining trades.
        """
        if exported_gross <= 0 or not pending_purchases:
            return None

        from bisect import bisect_left

        candidates: list[tuple[Decimal, int, int, Decimal]] = []
        count = len(pending_purchases)
        prefix: list[Decimal] = [Decimal("0")]
        for trade in pending_purchases:
            prefix.append(prefix[-1] + Decimal(trade["gross_btc"]))

        seen_windows: set[tuple[int, int]] = set()
        for start in range(count):
            desired_prefix = prefix[start] + exported_gross
            position = bisect_left(prefix, desired_prefix, lo=start + 1)
            for end in (position - 1, position, position + 1):
                if end <= start or end > count:
                    continue
                window = (start, end)
                if window in seen_windows:
                    continue
                seen_windows.add(window)
                total = prefix[end] - prefix[start]
                allowed_delta = max(
                    sat_tolerance,
                    explicit_network_fee + sat_tolerance,
                    total * Decimal("0.001"),
                )
                delta = abs(total - exported_gross)
                if delta <= allowed_delta:
                    candidates.append((delta, start, end, total))

        if not candidates:
            return None

        candidates.sort(key=lambda item: (item[0], item[1], item[2]))
        best = candidates[0]
        equally_good = [item for item in candidates if abs(item[0] - best[0]) <= sat_tolerance]
        unique_windows = {(item[1], item[2]) for item in equally_good}
        if len(unique_windows) != 1:
            return None
        return best[1], best[2], best[3]

    for _sort_key, event_kind, event in timeline:
        if event_kind == "trade":
            pending_purchases.append(event)
            continue

        if not pending_purchases:
            continue

        withdrawal_gross = Decimal(event.get("gross_btc") or "0")
        withdrawal_net = Decimal(event.get("amount_btc") or "0")
        withdrawal_fee = Decimal(event.get("fee_btc") or "0")
        matched = _matching_pending_window(withdrawal_gross, withdrawal_fee)

        if matched is None or withdrawal_net <= 0:
            # It may be an unrelated Lightning transfer, a manual transfer, or an
            # ambiguous amount. Do not consume or reset any purchases; a later
            # Withdrawal may still match them exactly.
            continue

        start, end, total_gross = matched
        matched_purchases = pending_purchases[start:end]
        # Pocket does not export a transport label. Classify only when the CSV
        # evidence is strong enough: a BTC withdrawal fee or a multi-trade batch
        # is treated as on-chain; an exact one-to-one payout without a BTC fee is
        # treated as Lightning. Ambiguous cases keep the neutral Pocket note.
        transport: str | None = None
        if withdrawal_fee > sat_tolerance or len(matched_purchases) > 1:
            transport = "onchain"
        elif len(matched_purchases) == 1:
            only_gross = Decimal(matched_purchases[0]["gross_btc"])
            if abs(withdrawal_net - only_gross) <= sat_tolerance:
                transport = "lightning"

        remaining_net = withdrawal_net
        for position, trade in enumerate(matched_purchases):
            gross = Decimal(trade["gross_btc"])
            if position == len(matched_purchases) - 1:
                net_share = remaining_net
            else:
                net_share = withdrawal_net * gross / total_gross
                remaining_net -= net_share
            if net_share > 0:
                trade_row_no = int(trade["row_no"])
                withdrawal_allocations[trade_row_no] = net_share
                if transport:
                    withdrawal_transport[trade_row_no] = transport

        # Only the purchases actually reconciled by this Withdrawal are closed.
        # All other pending purchases remain available for later payouts.
        del pending_purchases[start:end]

    output: list[dict[str, Any]] = []
    skipped = 0
    for row_no, values in enumerate(rows, start=2):
        tx_type = cell(values, type_i).strip().lower()
        if tx_type != "trade":
            skipped += 1
            continue

        buy_cur_raw, sell_cur_raw = cell(values, buy_cur_i), cell(values, sell_cur_i)
        buy_asset, sell_asset = _asset(buy_cur_raw), _asset(sell_cur_raw)
        buy_btc = _pocket_btc_amount(cell(values, buy_i), buy_cur_raw)
        sell_btc = _pocket_btc_amount(cell(values, sell_i), sell_cur_raw)
        buy_amount, sell_amount = _number(cell(values, buy_i)), _number(cell(values, sell_i))

        if buy_btc is not None and sell_asset and sell_asset != "BTC":
            kind = "purchase"
            amount_btc = buy_btc
            currency = sell_asset
            fiat_amount = sell_amount
        elif sell_btc is not None and buy_asset and buy_asset != "BTC":
            kind = "sale"
            amount_btc = sell_btc
            currency = buy_asset
            fiat_amount = buy_amount
        else:
            skipped += 1
            continue

        raw_fee = _number(cell(values, fee_i))
        fee_currency_raw = cell(values, fee_cur_i)
        fee_asset = _asset(fee_currency_raw)
        fee = Decimal("0")
        warnings: list[str] = []

        # Pocket's CoinTracking-compatible BUY export reports Sell Amount as the
        # total fiat amount paid by the customer. A fiat Fee Amount is already
        # contained in that total and must not be added on top of it. Therefore
        # the execution value used for the BTC price is Sell Amount - Fee Amount;
        # the fee itself stays in the fee field. This keeps the complete cost
        # basis equal to the actual fiat payment.
        pricing_fiat_amount = fiat_amount
        if raw_fee is not None and raw_fee != 0 and fee_asset == currency and kind == "purchase":
            included_fee = abs(raw_fee)
            if fiat_amount is not None and abs(fiat_amount) > included_fee:
                pricing_fiat_amount = abs(fiat_amount) - included_fee
            else:
                warnings.append("Pocket-Gebühr ist größer als oder gleich dem eingezahlten Fiatbetrag; Preis bitte prüfen")

        price = (
            abs(pricing_fiat_amount / amount_btc)
            if amount_btc and pricing_fiat_amount is not None
            else None
        )

        if raw_fee is not None and raw_fee != 0:
            if not fee_asset:
                warnings.append("Pocket-Gebühr erkannt, aber Gebührenwährung fehlt; Gebühr bitte prüfen")
            elif fee_asset == currency:
                fee = abs(raw_fee)
            else:
                fee_btc = _pocket_btc_amount(raw_fee, fee_currency_raw)
                if fee_btc is not None and price is not None:
                    if kind == "sale" and amount_btc is not None:
                        # CoinTracking-style Pocket exports separate a BTC fee
                        # from the BTC sold.  Both quantities leave the wallet.
                        amount_btc = abs(amount_btc) + abs(fee_btc)
                    fee = abs(fee_btc * price)
                else:
                    warnings.append(
                        f"Pocket-Gebühr in {fee_asset or fee_currency_raw} erkannt; Fiat-Gebühr in {currency} bitte prüfen"
                    )

        # Pocket may combine several purchases into a single payout.  The
        # precomputed allocation is based on all purchases since the previous
        # withdrawal, so it also works across midnight and cannot accidentally
        # consume a purchase made after the payout.
        if kind == "purchase" and price is not None:
            warning = withdrawal_allocation_warnings.get(row_no)
            if warning:
                warnings.append(warning)
            net = withdrawal_allocations.get(row_no)
            if net is not None:
                original_trade_btc = amount_btc
                amount_btc = net

                # Keep each purchase's complete fiat cost basis equal to its own
                # Sell Amount.  Its proportional share of the batched network fee
                # appears only as the resulting fee remainder; it is never added
                # a second time on top of the customer's payment.
                if fiat_amount is not None:
                    total_paid = abs(fiat_amount)
                    effective_fee = total_paid - (amount_btc * price)
                    if effective_fee >= 0:
                        fee = effective_fee
                    else:
                        warnings.append("Pocket-Auszahlungsbetrag ergibt einen negativen Gebührenrest; Werte bitte prüfen")
                elif original_trade_btc > net:
                    fee += (original_trade_btc - net) * price

        optional: dict[str, str] = {}
        comment = cell(values, comment_i).strip()
        if comment:
            optional["memo"] = comment
        exchange = cell(values, exchange_i).strip()
        trade_group = cell(values, trade_group_i).strip()
        if exchange:
            optional["exchange"] = exchange
        if trade_group:
            optional["trade_group"] = trade_group

        note = "Pocket Bitcoin CSV-Import"
        if kind == "purchase":
            transport = withdrawal_transport.get(row_no)
            if transport == "lightning":
                note = "Lightning Pocket Bitcoin CSV-Import."
            elif transport == "onchain":
                note = "Onchain Pocket Bitcoin CSV-Import."

        output.append(_transaction(
            source="Pocket Bitcoin", row_number=row_no, kind=kind,
            timestamp=_iso_timestamp(cell(values, date_i)), amount_btc=amount_btc,
            currency=currency, price=price, fee=fee, warnings=warnings,
            note=note,
            reference=_stable_reference(
                _row_dict(headers, values),
                "tx id", "txid", "transaction id", "trade id",
                "exchange transaction id", "order id", "ordertxid",
                "reference", "id",
            ),
            optional_note_fields=optional,
        ))
    return output, skipped

def _parse_pocket_native(headers: list[str], rows: list[list[str]]) -> tuple[list[dict[str, Any]], int]:
    """Parse Pocket Bitcoin's native dashboard CSV export.

    The native export can batch several purchase rows into one later Withdrawal,
    while Lightning payouts may appear as indistinguishable Withdrawal rows too.
    ``value.amount`` on a Withdrawal is already the net BTC amount that reached
    the wallet.  Because the CSV does not label Lightning vs. on-chain, a
    Withdrawal is matched by amount to a unique contiguous group of still-pending
    purchases.  Unrelated or ambiguous Withdrawals are ignored as transfer rows
    and, crucially, do not reset the pending purchase group.  Deposit and
    Withdrawal rows themselves are never imported as additional trades.
    """
    type_i = _header_index(headers, ("type",))
    date_i = _header_index(headers, ("date",))
    reference_i = _header_index(headers, ("reference",))
    price_cur_i = _header_index(headers, ("price.currency", "price currency"))
    price_i = _header_index(headers, ("price.amount", "price amount", "price"))
    cost_cur_i = _header_index(headers, ("cost.currency", "cost currency"))
    cost_i = _header_index(headers, ("cost.amount", "cost amount", "cost"))
    fee_cur_i = _header_index(headers, ("fee.currency", "fee currency"))
    fee_i = _header_index(headers, ("fee.amount", "fee amount", "fee"))
    value_cur_i = _header_index(headers, ("value.currency", "value currency"))
    value_i = _header_index(headers, ("value.amount", "value amount", "value"))

    def cell(values: list[str], index: int | None) -> str:
        return values[index].strip() if index is not None and index < len(values) else ""

    withdrawals: list[dict[str, Any]] = []
    purchase_events: list[dict[str, Any]] = []

    for row_no, values in enumerate(rows, start=2):
        tx_type = cell(values, type_i).strip().lower()
        timestamp = _iso_timestamp(cell(values, date_i))
        value_currency = _asset(cell(values, value_cur_i))
        fee_currency = _asset(cell(values, fee_cur_i))
        cost_currency = _asset(cell(values, cost_cur_i))
        raw_value = _number(cell(values, value_i))
        raw_fee = _number(cell(values, fee_i))
        raw_cost = _number(cell(values, cost_i))

        if "withdraw" in tx_type or "auszahlung" in tx_type:
            # Native Pocket semantics differ from CoinTracking: value.amount is
            # already the BTC amount that actually arrived in the user's wallet.
            if value_currency == "BTC" and raw_value is not None and abs(raw_value) > 0:
                withdrawals.append({
                    "row_no": row_no,
                    "amount_btc": abs(raw_value),
                    "fee_btc": abs(raw_fee) if fee_currency == "BTC" and raw_fee is not None else Decimal("0"),
                    "timestamp": timestamp,
                })
            continue

        # Purchases are the BTC-valued rows funded by a non-BTC cost currency.
        # They are collected separately so one later Withdrawal can close a whole
        # group of purchases rather than being matched to only one row.
        if (
            value_currency == "BTC"
            and raw_value is not None
            and abs(raw_value) > 0
            and cost_currency
            and cost_currency != "BTC"
            and raw_cost is not None
        ):
            purchase_events.append({
                "row_no": row_no,
                "gross_btc": abs(raw_value),
                "timestamp": timestamp,
            })

    def _native_event_sort_key(item: dict[str, Any], event_priority: int) -> tuple[float, int, int]:
        timestamp = item.get("timestamp")
        if timestamp:
            try:
                return (
                    datetime.fromisoformat(str(timestamp).replace("Z", "+00:00")).timestamp(),
                    event_priority,
                    int(item["row_no"]),
                )
            except (TypeError, ValueError, OverflowError):
                pass
        return (float(item["row_no"]), event_priority, int(item["row_no"]))

    timeline: list[tuple[tuple[float, int, int], str, dict[str, Any]]] = []
    timeline.extend((_native_event_sort_key(item, 0), "trade", item) for item in purchase_events)
    timeline.extend((_native_event_sort_key(item, 1), "withdrawal", item) for item in withdrawals)
    timeline.sort(key=lambda item: item[0])

    withdrawal_allocations: dict[int, Decimal] = {}
    withdrawal_transport: dict[int, str] = {}
    withdrawal_allocation_warnings: dict[int, str] = {}
    pending_purchases: list[dict[str, Any]] = []
    sat_tolerance = Decimal("0.00000002")

    def _matching_pending_window(exported_gross: Decimal) -> tuple[int, int, Decimal] | None:
        """Find one unambiguous contiguous purchase group for a Withdrawal.

        Pocket does not expose whether a native Withdrawal used Lightning or
        on-chain.  Treating every Withdrawal as a hard batch boundary therefore
        shifts all later purchases as soon as an unrelated Lightning payout is
        encountered.  Instead, reconcile the Withdrawal gross amount
        (``value.amount + fee.amount``) against still-pending purchases.

        A matching group may be in the middle of the pending list: an older
        on-chain purchase can remain pending while a newer Lightning purchase is
        paid immediately.  After that match is removed, the remaining purchases
        can still be batched by a later on-chain Withdrawal.
        """
        if exported_gross <= 0 or not pending_purchases:
            return None

        from bisect import bisect_left

        candidates: list[tuple[Decimal, int, int, Decimal]] = []
        count = len(pending_purchases)
        prefix: list[Decimal] = [Decimal("0")]
        for trade in pending_purchases:
            prefix.append(prefix[-1] + Decimal(trade["gross_btc"]))

        # Prefix sums are strictly increasing because purchase BTC amounts are
        # positive. For every possible start position, only the prefix values
        # immediately around the target can be the closest matching end. This
        # keeps reconciliation fast even for large exports.
        seen_windows: set[tuple[int, int]] = set()
        for start in range(count):
            desired_prefix = prefix[start] + exported_gross
            position = bisect_left(prefix, desired_prefix, lo=start + 1)
            for end in (position - 1, position, position + 1):
                if end <= start or end > count:
                    continue
                window = (start, end)
                if window in seen_windows:
                    continue
                seen_windows.add(window)
                total = prefix[end] - prefix[start]
                allowed_delta = max(sat_tolerance, total * Decimal("0.001"))
                delta = abs(total - exported_gross)
                if delta <= allowed_delta:
                    candidates.append((delta, start, end, total))

        if not candidates:
            return None

        candidates.sort(key=lambda item: (item[0], item[1], item[2]))
        best = candidates[0]
        # If two different purchase groups fit equally well (within two sats), the
        # CSV lacks enough information to decide safely. Ignore this Withdrawal
        # instead of assigning it to the wrong purchases and shifting the rest.
        equally_good = [item for item in candidates if abs(item[0] - best[0]) <= sat_tolerance]
        unique_windows = {(item[1], item[2]) for item in equally_good}
        if len(unique_windows) != 1:
            return None
        return best[1], best[2], best[3]

    for _sort_key, event_kind, event in timeline:
        if event_kind == "trade":
            pending_purchases.append(event)
            continue

        if not pending_purchases:
            continue

        withdrawal_net = Decimal(event.get("amount_btc") or "0")
        explicit_network_fee = Decimal(event.get("fee_btc") or "0")
        exported_gross = withdrawal_net + explicit_network_fee
        matched = _matching_pending_window(exported_gross)

        if matched is None:
            # Native Pocket does not label Lightning vs. on-chain. An unrelated or
            # ambiguous Withdrawal must therefore NOT clear pending purchases. A
            # later payout can still reconcile them correctly.
            continue

        start, end, total_gross = matched
        matched_purchases = pending_purchases[start:end]
        transport: str | None = None
        if explicit_network_fee > sat_tolerance or len(matched_purchases) > 1:
            transport = "onchain"
        elif len(matched_purchases) == 1:
            only_gross = Decimal(matched_purchases[0]["gross_btc"])
            if abs(withdrawal_net - only_gross) <= sat_tolerance:
                transport = "lightning"

        remaining_net = withdrawal_net
        for position, trade in enumerate(matched_purchases):
            gross = Decimal(trade["gross_btc"])
            if position == len(matched_purchases) - 1:
                net_share = remaining_net
            else:
                net_share = withdrawal_net * gross / total_gross
                remaining_net -= net_share
            if net_share > 0:
                trade_row_no = int(trade["row_no"])
                withdrawal_allocations[trade_row_no] = net_share
                if transport:
                    withdrawal_transport[trade_row_no] = transport

        # Remove only the purchases actually reconciled by this Withdrawal. Older
        # or newer pending purchases remain available for later payouts.
        del pending_purchases[start:end]

    output: list[dict[str, Any]] = []
    skipped = 0
    for row_no, values in enumerate(rows, start=2):
        tx_type = cell(values, type_i).strip().lower()
        if any(word in tx_type for word in ("deposit", "withdraw", "einzahlung", "auszahlung")):
            skipped += 1
            continue

        price_currency = _asset(cell(values, price_cur_i))
        cost_currency = _asset(cell(values, cost_cur_i))
        fee_currency = _asset(cell(values, fee_cur_i))
        value_currency = _asset(cell(values, value_cur_i))
        raw_price = _number(cell(values, price_i))
        raw_cost = _number(cell(values, cost_i))
        raw_fee = _number(cell(values, fee_i))
        raw_value = _number(cell(values, value_i))

        kind: str | None = None
        amount_btc: Decimal | None = None
        currency = ""
        fiat_amount: Decimal | None = None

        if value_currency == "BTC" and raw_value is not None and cost_currency and cost_currency != "BTC" and raw_cost is not None:
            kind = "purchase"
            amount_btc = abs(raw_value)
            currency = cost_currency
            fiat_amount = abs(raw_cost)
        elif cost_currency == "BTC" and raw_cost is not None and value_currency and value_currency != "BTC" and raw_value is not None:
            kind = "sale"
            amount_btc = abs(raw_cost)
            currency = value_currency
            fiat_amount = abs(raw_value)
        else:
            skipped += 1
            continue

        price = abs(raw_price) if raw_price is not None and raw_price != 0 and (not price_currency or price_currency == currency) else None
        if price is None and amount_btc and fiat_amount is not None:
            price = abs(fiat_amount / amount_btc)

        fee = Decimal("0")
        warnings: list[str] = []
        if raw_fee is not None and raw_fee != 0:
            if fee_currency == currency:
                fee = abs(raw_fee)
            elif fee_currency == "BTC" and price is not None:
                fee = abs(raw_fee) * price
            elif fee_currency:
                warnings.append(
                    f"Pocket-Gebühr in {fee_currency} erkannt; Fiat-Gebühr in {currency} bitte prüfen"
                )
            else:
                warnings.append("Pocket-Gebühr erkannt, aber Gebührenwährung fehlt; Gebühr bitte prüfen")

        if kind == "purchase" and price is not None and amount_btc is not None:
            warning = withdrawal_allocation_warnings.get(row_no)
            if warning:
                warnings.append(warning)
            net = withdrawal_allocations.get(row_no)
            if net is not None:
                original_trade_btc = amount_btc
                amount_btc = net

                # value.amount on the Withdrawal is already net.  The difference
                # between this trade's gross BTC and its proportional net share is
                # its share of the common network fee.  Convert that share using
                # the trade's own execution price so each purchase keeps its own
                # correct fiat cost basis.
                network_fee_share_btc = original_trade_btc - net
                if network_fee_share_btc > 0:
                    fee += network_fee_share_btc * price

        optional: dict[str, str] = {}
        reference = cell(values, reference_i).strip()
        if reference:
            # References may contain payment identifiers. Keep them opt-in and
            # never append them to the default note.
            optional["memo"] = reference

        note = "Pocket Bitcoin CSV-Import"
        if kind == "purchase":
            transport = withdrawal_transport.get(row_no)
            if transport == "lightning":
                note = "Lightning Pocket Bitcoin CSV-Import."
            elif transport == "onchain":
                note = "Onchain Pocket Bitcoin CSV-Import."

        output.append(_transaction(
            source="Pocket Bitcoin", row_number=row_no, kind=kind,
            timestamp=_iso_timestamp(cell(values, date_i)), amount_btc=amount_btc,
            currency=currency, price=price, fee=fee, warnings=warnings,
            note=note, reference=reference, optional_note_fields=optional,
        ))
    return output, skipped

def _coinfinity_satoshi_number(value: Any) -> Decimal | None:
    """Parse a Coinfinity satoshi field without stripping significant zeros.

    Coinfinity's ``Mining Fee Crypto`` is a satoshi amount. Locale-style
    thousands separators such as ``20.000`` or ``20,000`` therefore mean
    20,000 sats, not 20 sats. The result remains an integer-valued Decimal;
    trailing zeros are part of the value and must never be removed from a sats
    integer by string trimming.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None

    unitless = re.sub(r"(?i)\b(?:sats?|satoshis?)\b", "", text)
    unitless = unitless.replace("\u00a0", "").replace(" ", "").replace("'", "")
    if re.fullmatch(r"[+-]?\d{1,3}(?:[.,]\d{3})+", unitless):
        negative = unitless.startswith("-")
        digits = re.sub(r"\D", "", unitless)
        try:
            return Decimal(("-" if negative else "") + digits)
        except InvalidOperation:
            return None
    value_decimal = _number(value)
    if value_decimal is None:
        return None
    return value_decimal


def _coinfinity_amount_crypto_to_btc(value: Any) -> Decimal | None:
    """Parse Coinfinity ``Amount Crypto`` as BTC.

    In the Coinfinity activity report the ``Amount Crypto`` column is a BTC
    decimal (for example ``0.00020000``). Parsing it as Decimal may normalize
    the textual representation to ``0.0002``; that is mathematically identical
    and still converts to exactly 20,000 sats. Never interpret a bare
    ``Amount Crypto`` value as a satoshi integer.
    """
    text = str(value or "").strip()
    if not text:
        return None
    # Explicit sats are accepted only as a defensive compatibility fallback.
    if re.search(r"(?i)\b(?:sats?|satoshis?)\b", text):
        sats = _coinfinity_satoshi_number(text)
        return sats / SATOSHIS_PER_BTC if sats is not None else None
    return _number(text)


def _coinfinity_mining_fee_to_btc(value: Any) -> Decimal | None:
    """Parse Coinfinity ``Mining Fee Crypto`` as satoshis and return BTC."""
    sats = _coinfinity_satoshi_number(value)
    if sats is None:
        return None
    return sats / SATOSHIS_PER_BTC


def _coinfinity_purchase_total_eur(*, amount_eur: Decimal | None) -> Decimal | None:
    """Return Coinfinity's exact transferred fiat amount.

    ``Amount EUR`` is the amount the customer transferred. Service fee and,
    for on-chain purchases, mining fee are deductions from that amount rather
    than amounts added on top of it.
    """
    return abs(amount_eur) if amount_eur is not None else None

def _format_decimal(value: Decimal | None) -> str:
    if value is None:
        return ""
    return format(abs(value).normalize(), "f")


def _parse_coinfinity(headers: list[str], rows: list[list[str]]) -> tuple[list[dict[str, Any]], int]:
    """Parse Coinfinity's My Activities CSV, including on-chain and Lightning."""
    output: list[dict[str, Any]] = []
    skipped = 0
    for row_no, values in enumerate(rows, start=2):
        row = _row_dict(headers, values)
        crypto = _asset(_get(row, "crypto", "cryptocurrency", "asset", "coin"))
        if crypto != "BTC":
            skipped += 1
            continue

        kind = _generic_kind(row)
        raw_crypto = _get(row, "amount crypto", "crypto amount")
        amount_btc = _coinfinity_amount_crypto_to_btc(raw_crypto)
        amount_eur = _number(_get(row, "amount eur", "eur amount"))
        price = _number(_get(row, "rate eur", "eur rate", "price eur"))

        type_text = " ".join((
            _get(row, "type"),
            _get(row, "transaction type"),
        )).strip().lower()
        # Do not turn deposits, withdrawals or plain wallet movements into a
        # trade merely because the row also contains a crypto amount.
        movement_only = any(word in type_text for word in (
            "deposit", "withdraw", "transfer", "einzahlung", "auszahlung",
            "wallet transfer", "receive", "send",
        )) and not any(word in type_text for word in (
            "buy", "purchase", "kauf", "sell", "sale", "verkauf",
        ))
        if movement_only:
            skipped += 1
            continue

        if kind is None and amount_btc is not None and amount_eur is not None and price:
            if amount_btc > 0 and amount_eur >= 0:
                kind = "purchase"
            elif amount_btc < 0 and amount_eur >= 0:
                kind = "sale"
        if kind is None:
            skipped += 1
            continue

        amount_btc = abs(amount_btc) if amount_btc is not None else None
        amount_eur = abs(amount_eur) if amount_eur is not None else None
        price = abs(price) if price is not None else None

        mining_fee_crypto_raw = _get(row, "mining fee crypto", "network fee crypto")
        mining_fee_btc = _coinfinity_mining_fee_to_btc(mining_fee_crypto_raw)
        mining_fee_btc = abs(mining_fee_btc) if mining_fee_btc is not None else None
        mining_fee_eur = _number(_get(row, "mining fee eur", "network fee eur"))
        service_fee_eur = _number(_get(row, "service fee eur", "purchase fee eur", "buy fee eur"))
        total_fee_eur = _number(_get(row, "total fee eur", "fee eur"))
        # If an on-chain export omits the EUR network fee, reconstruct it from
        # the satoshi fee and the exported BTC/EUR rate.
        if mining_fee_eur is None and mining_fee_btc is not None and price is not None:
            mining_fee_eur = abs(mining_fee_btc) * abs(price)
        fee = abs(total_fee_eur) if total_fee_eur is not None else (
            abs(mining_fee_eur or Decimal("0")) + abs(service_fee_eur or Decimal("0"))
        )

        # Coinfinity purchase accounting:
        #   paid fiat -> service fee -> BTC purchase -> mining fee -> received BTC
        # ``Amount Crypto`` is therefore the final BTC amount that reached the
        # wallet and must never be increased/decreased by the importer. For the
        # cost basis we keep the exported fees, infer the exact customer payment
        # and derive an effective rate so amount_btc * price + fee equals that
        # payment exactly. This prevents a rounded bank transfer from becoming a
        # crooked cent amount in the preview/database.
        coinfinity_fiat_total: Decimal | None = None
        if kind == "purchase":
            coinfinity_fiat_total = _coinfinity_purchase_total_eur(amount_eur=amount_eur)
            if amount_btc and coinfinity_fiat_total is not None and coinfinity_fiat_total > fee:
                price = (coinfinity_fiat_total - fee) / amount_btc
            elif price is None and amount_btc and amount_eur is not None:
                price = amount_eur / amount_btc
        elif price is None and amount_btc and amount_eur is not None:
            price = amount_eur / amount_btc

        # Sensitive source columns are kept only as optional preview metadata.
        # They are not part of the default note and are persisted only when the
        # user explicitly enables the corresponding checkbox in the preview.
        optional_note_fields = {
            "order_id": _get(row, "order id", "orderid", "id"),
            "address": _get(row, "address", "wallet address"),
            "transaction_id": _get(row, "transaction", "transaction id", "txid", "tx id"),
            "ln_invoice": _get(row, "ln invoice", "lightning invoice", "invoice"),
        }
        # Coinfinity encodes the delivery path through Mining Fee Crypto:
        # empty/zero = Lightning, positive value = on-chain fee in satoshis.
        raw_mining_sats = _coinfinity_satoshi_number(mining_fee_crypto_raw)
        is_onchain = raw_mining_sats is not None and abs(raw_mining_sats) > 0
        is_lightning = not is_onchain

        details: list[str] = ["Coinfinity"]
        if is_lightning:
            details.append("Lightning")
        elif is_onchain:
            details.append("On-Chain")

        if raw_mining_sats:
            details.append(f"Mining Fee: {_format_decimal(raw_mining_sats)} sats")
        if mining_fee_eur:
            details.append(f"Mining Fee: {_format_decimal(mining_fee_eur)} EUR")
        if service_fee_eur:
            details.append(f"Service Fee: {_format_decimal(service_fee_eur)} EUR")
        if total_fee_eur:
            details.append(f"Gesamtgebühr: {_format_decimal(total_fee_eur)} EUR")
        output.append(_transaction(
            source="Coinfinity", row_number=row_no, kind=kind,
            timestamp=_iso_timestamp(_get(row, "date", "timestamp")),
            amount_btc=amount_btc, currency="EUR", price=price, fee=fee,
            fiat_amount=coinfinity_fiat_total if kind == "purchase" else None,
            note=" · ".join(details),
            reference=_stable_reference(
                row, "transaction", "transaction id", "txid", "tx id",
                "order id", "orderid", "id",
            ),
            optional_note_fields=optional_note_fields,
        ))
    return output, skipped


def _wavespace_asset_and_amount(raw_currency: Any, raw_amount: Any) -> tuple[str, Decimal | None]:
    """Normalize Wavespace currencies and convert explicit satoshi units to BTC."""
    raw_code = re.sub(r"[^A-Za-z0-9]", "", str(raw_currency or "")).upper()
    amount = _number(raw_amount)
    if raw_code in {"SAT", "SATS", "SATOSHI", "SATOSHIS"}:
        return "BTC", (amount / SATOSHIS_PER_BTC if amount is not None else None)
    return _asset(raw_code), amount


def _wavespace_row_assets(row: dict[str, str]) -> tuple[str, Decimal | None, str, Decimal | None]:
    """Return normalized From/To assets without reading private ID or memo fields."""
    from_currency, from_amount = _wavespace_asset_and_amount(
        _get(row, "from currency"), _get(row, "from amount")
    )
    to_currency, to_amount = _wavespace_asset_and_amount(
        _get(row, "to currency"), _get(row, "to amount")
    )
    return from_currency, from_amount, to_currency, to_amount


def _wavespace_amount_for_asset(row: dict[str, str], asset: str) -> Decimal | None:
    """Read an amount for one asset, preferring the From side used by withdrawals/fees."""
    from_currency, from_amount, to_currency, to_amount = _wavespace_row_assets(row)
    if from_currency == asset and from_amount is not None:
        return abs(from_amount)
    if to_currency == asset and to_amount is not None:
        return abs(to_amount)
    return None


def _wavespace_fiat_amount(row: dict[str, str], preferred: str = "") -> tuple[str, Decimal | None]:
    """Return the fiat side of a Wavespace row."""
    from_currency, from_amount, to_currency, to_amount = _wavespace_row_assets(row)
    if preferred:
        if from_currency == preferred and from_amount is not None:
            return preferred, abs(from_amount)
        if to_currency == preferred and to_amount is not None:
            return preferred, abs(to_amount)
    if from_currency in FIAT_AND_QUOTES and from_amount is not None:
        return from_currency, abs(from_amount)
    if to_currency in FIAT_AND_QUOTES and to_amount is not None:
        return to_currency, abs(to_amount)
    return "", None


_WAVESPACE_MEMO_AMOUNT_RE = re.compile(
    r"(?<![A-Za-z0-9])([-+]?\d[\d\s.,'’]*?)\s*"
    r"(SATOSHIS?|SATS?|XXBT|XBTC|XBT|BTC|EUR|USD|CHF|GBP|CAD|AUD|NZD|JPY|SEK|NOK|DKK|PLN|CZK|HUF|RON|BGN|TRY|BRL|MXN|ZAR|SGD|HKD|AED|USDT|USDC|FDUSD|BUSD|DAI|TUSD)\b",
    re.IGNORECASE,
)


def _wavespace_fee_from_memo(
    row: dict[str, str], preferred_assets: Iterable[str] = ()
) -> tuple[str, Decimal | None]:
    """Read the actual fee from a Wavespace memo.

    Wavespace memo text can contain the traded amount before the fee, for example
    ``Trading Fee for 1 EUR to BTC 0.1 EUR``.  The final amount/currency pair is
    the fee.  Preferred assets only break ties; the last matching pair wins.
    """
    memo = _get(row, "memo", "note", "notes", "comment").strip()
    if not memo:
        return "", None

    matches: list[tuple[str, Decimal]] = []
    for raw_amount, raw_asset in _WAVESPACE_MEMO_AMOUNT_RE.findall(memo):
        asset, amount = _wavespace_asset_and_amount(raw_asset, raw_amount)
        if asset and amount is not None:
            matches.append((asset, abs(amount)))
    if not matches:
        return "", None

    normalized_preferences = [_asset(item) for item in preferred_assets if item]
    for preferred in normalized_preferences:
        for asset, amount in reversed(matches):
            if asset == preferred:
                return asset, amount
    return matches[-1]


def _wavespace_direct_trade(row: dict[str, str]) -> tuple[str | None, Decimal | None, str, Decimal | None, Decimal | None]:
    """Parse the BUY/SELL conversion row itself."""
    from_currency, from_amount, to_currency, to_amount = _wavespace_row_assets(row)
    if to_currency == "BTC" and from_currency in FIAT_AND_QUOTES:
        btc = abs(to_amount) if to_amount is not None else None
        fiat = abs(from_amount) if from_amount is not None else None
        price = fiat / btc if btc and fiat is not None else None
        return "purchase", btc, from_currency, fiat, price
    if from_currency == "BTC" and to_currency in FIAT_AND_QUOTES:
        btc = abs(from_amount) if from_amount is not None else None
        fiat = abs(to_amount) if to_amount is not None else None
        price = fiat / btc if btc and fiat is not None else None
        return "sale", btc, to_currency, fiat, price
    return None, None, "", None, None


def _wavespace_optional_note_fields(
    entries: list[dict[str, Any]], indices: Iterable[int]
) -> dict[str, str]:
    """Collect optional Wavespace metadata without putting it in the default note."""
    transaction_ids: list[str] = []
    memos: list[str] = []
    transaction_types: list[str] = []
    seen_ids: set[str] = set()
    seen_memos: set[str] = set()
    seen_types: set[str] = set()

    for index in sorted(set(indices)):
        if index < 0 or index >= len(entries):
            continue
        item = entries[index]
        row = item["row"]
        category = item.get("category", "").strip()
        prefix = f"{category}: " if category else ""

        transaction_id = _get(row, "transaction id", "txid", "tx id").strip()
        if transaction_id and transaction_id not in seen_ids:
            seen_ids.add(transaction_id)
            transaction_ids.append(f"{prefix}{transaction_id}")

        memo = _get(row, "memo", "note", "notes", "comment").strip()
        if memo and memo not in seen_memos:
            seen_memos.add(memo)
            memos.append(f"{prefix}{memo}")

        transaction_type = _get(row, "transaction type", "type").strip()
        if transaction_type and transaction_type not in seen_types:
            seen_types.add(transaction_type)
            transaction_types.append(transaction_type)

    return {
        "transaction_id": " | ".join(transaction_ids)[:2000],
        "memo": " | ".join(memos)[:2000],
        "transaction_type": " → ".join(transaction_types)[:1000],
    }


def _wavespace_time_value(row: dict[str, str]) -> tuple[str | None, float | None]:
    """Return a normalized UTC timestamp and a sortable epoch value."""
    timestamp = _iso_timestamp(_get(row, "executes at", "date", "timestamp", "time"))
    if not timestamp:
        return None, None
    try:
        return timestamp, datetime.fromisoformat(timestamp).timestamp()
    except ValueError:
        return timestamp, None


def _wavespace_transaction_id(row: dict[str, str]) -> str:
    return _get(row, "transaction id", "txid", "tx id").strip()


def _wavespace_distance_score(
    left: dict[str, Any], right: dict[str, Any], *, max_seconds: float,
    prefer_right_after_left: bool = False,
) -> float | None:
    """Measure whether two Wavespace rows plausibly belong together.

    Repeated transaction IDs are treated as a strong internal link but are still
    exposed to the user only through the opt-in note fields. If timestamps are
    unavailable, a small row-distance window is used as a conservative fallback.
    """
    left_id = _wavespace_transaction_id(left["row"])
    right_id = _wavespace_transaction_id(right["row"])
    same_id = bool(left_id and right_id and left_id == right_id)
    left_time = left.get("time_value")
    right_time = right.get("time_value")

    if left_time is not None and right_time is not None:
        delta = abs(right_time - left_time)
        if delta > max_seconds and not same_id:
            return None
        score = delta
        if prefer_right_after_left and right_time + 5 < left_time:
            score += min(max_seconds, 1800.0)
    else:
        row_distance = abs(int(right["index"]) - int(left["index"]))
        if row_distance > 12 and not same_id:
            return None
        score = float(row_distance * 60)

    if same_id:
        score -= 100000.0
    return score


def _wavespace_fee_value(
    item: dict[str, Any], preferred_assets: Iterable[str]
) -> tuple[str, Decimal | None, bool]:
    """Read one fee, preferring the last amount in Memo over amount columns."""
    row = item["row"]
    fee_asset, fee_amount = _wavespace_fee_from_memo(row, preferred_assets)
    if fee_amount is not None:
        return fee_asset, fee_amount, True

    preferred = [_asset(value) for value in preferred_assets if value]
    for asset in preferred:
        if asset == "BTC":
            amount = _wavespace_amount_for_asset(row, "BTC")
            if amount is not None:
                return "BTC", amount, False
        elif asset in FIAT_AND_QUOTES:
            currency, amount = _wavespace_fiat_amount(row, asset)
            if currency == asset and amount is not None:
                return currency, amount, False

    currency, fiat_amount = _wavespace_fiat_amount(row)
    if currency and fiat_amount is not None:
        return currency, fiat_amount, False
    btc_amount = _wavespace_amount_for_asset(row, "BTC")
    if btc_amount is not None:
        return "BTC", btc_amount, False
    return "", None, False


def _wavespace_btc_transfer_amount(item: dict[str, Any]) -> Decimal | None:
    """Read the BTC amount that a deposit or withdrawal row actually moves."""
    from_currency, from_amount, to_currency, to_amount = _wavespace_row_assets(item["row"])
    if from_currency == "BTC" and from_amount is not None:
        return abs(from_amount)
    if to_currency == "BTC" and to_amount is not None:
        return abs(to_amount)
    return None


def _wavespace_is_primary_event(item: dict[str, Any]) -> bool:
    category = item["category"]
    transaction_type = item["transaction_type"]
    if transaction_type in {"CURRENCY_SWAP", "CARD_AUTHORIZATION"}:
        return True
    if category in {"BUY", "SELL", "TRADE"}:
        return True
    return category == "TRANSACTION" and transaction_type in {"BUY", "SELL"}


def _wavespace_event_label(event: dict[str, Any]) -> str:
    if event["event_type"] == "card":
        return "Kartenumsatz (Bitcoin-Verkauf)"
    return "Bitcoin-Kauf" if event["kind"] == "purchase" else "Bitcoin-Verkauf"


def _wavespace_is_card_creation_fee(item: dict[str, Any]) -> bool:
    """Identify standalone card-creation charges hidden under APPLICATION_FEE."""
    if item.get("category") != "FEE" or item.get("transaction_type") != "APPLICATION_FEE":
        return False
    memo = _get(item["row"], "memo", "note", "notes", "comment").strip().lower()
    normalized = re.sub(r"[^a-z0-9]+", " ", memo)
    return (
        "application fee for card creation" in normalized
        or "card creation fee" in normalized
        or "fee for card creation" in normalized
        or "kartenerstellungsgebuehr" in normalized
        or "kartenerstellung gebuehr" in normalized
    )


def _wavespace_memo(item: dict[str, Any]) -> str:
    """Return the Wavespace memo for semantic classification only."""
    return _get(item["row"], "memo", "note", "notes", "comment").strip()


def _wavespace_is_wavecard_topup(item: dict[str, Any]) -> bool:
    """Ignore internal Wavecard account funding so it is not counted twice."""
    normalized = re.sub(r"[^a-z0-9]+", " ", _wavespace_memo(item).lower()).strip()
    return "wavecard topup" in normalized or "wave card topup" in normalized


def _wavespace_card_usage(item: dict[str, Any]) -> tuple[str, str]:
    """Classify a card authorization and extract the merchant or ATM label.

    Wavespace prefixes card purchases with labels such as
    ``payWaveLowValuePurchase`` and encloses merchants in parentheses in some
    exports. Only the text between ``Authorization at`` and
    ``application fee of`` is used for the readable note.
    """
    memo = _wavespace_memo(item)
    lowered = memo.lower()
    usage = (
        "atm"
        if "atmwithdrawal" in lowered or "atm withdrawal" in lowered
        else "card"
    )
    location = ""
    patterns = (
        r"card\s+authorization\s+at\s+(.+?)\s+application\s+fee\s+of\b",
        r"authorization\s+at\s+(.+?)\s+application\s+fee\s+of\b",
        r"\bat\s+(.+?)(?=\s+application\s+fee\b|\s+fee\s+of\b|$)",
    )
    for pattern in patterns:
        match = re.search(pattern, memo, re.IGNORECASE)
        if not match:
            continue
        location = re.sub(r"\s+", " ", match.group(1)).strip()
        # Remove cosmetic wrappers such as ``(REWE )``.
        location = location.strip(" ()[]{}.,:;-_")[:160]
        break
    return usage, location


def _wavespace_is_card_purchase_expense(item: dict[str, Any]) -> bool:
    """Return True for Wavespace card purchases that are spending, not a sale order.

    The CSV still represents the BTC->fiat leg numerically like a sale, but labels
    such as ``payWaveLowValuePurchase`` / ``POSPurchase`` identify an actual card
    purchase.  Those rows should therefore be stored as ``expense`` while keeping
    sale-style fiat arithmetic.
    """
    memo = _wavespace_memo(item)
    compact = re.sub(r"[^a-z0-9]+", "", memo.lower())
    normalized = re.sub(r"[^a-z0-9]+", " ", memo.lower()).strip()
    return (
        "paywavelowvaluepurchase" in compact
        or "pospurchase" in compact
        or "card purchase" in normalized
        or "card payment" in normalized
    )


def _wavespace_localized_card_label(usage: str, location: str) -> tuple[str, str]:
    """Return compact German and English card-disposal labels."""
    if usage == "atm":
        return (
            f"Bargeldabhebung {location}" if location else "Bargeldabhebung",
            f"Cash withdrawal {location}" if location else "Cash withdrawal",
        )
    return (
        f"Kartentransaktion {location}" if location else "Kartentransaktion",
        f"Card transaction {location}" if location else "Card transaction",
    )

def _parse_wavespace(headers: list[str], rows: list[list[str]]) -> tuple[list[dict[str, Any]], int]:
    """Parse Wavespace by semantic transaction types instead of fixed row blocks.

    Wavespace can export two, three, four or more rows for one logical action and
    unrelated deposits can appear between them. ``CURRENCY_SWAP`` is therefore the
    anchor for a Bitcoin purchase/sale. ``CARD_AUTHORIZATION`` rows that identify a
    real card purchase (for example ``payWaveLowValuePurchase``) are imported as an
    expense, while their fiat control math remains sale-like. Nearby compatible
    fee/withdrawal rows are associated by timestamp,
    currency, amount and (when repeated) the internal transaction ID.
    """
    entries: list[dict[str, Any]] = []
    for index, (row_no, values) in enumerate(enumerate(rows, start=2)):
        row = _row_dict(headers, values)
        timestamp, time_value = _wavespace_time_value(row)
        entries.append({
            "index": index,
            "row_no": row_no,
            "row": row,
            "category": _get(row, "type category", "category").strip().upper(),
            "transaction_type": _get(row, "transaction type", "type").strip().upper(),
            "timestamp": timestamp,
            "time_value": time_value,
        })

    events: list[dict[str, Any]] = []
    for item in entries:
        if not _wavespace_is_primary_event(item):
            continue
        kind, gross_btc, fiat_currency, fiat_amount, price = _wavespace_direct_trade(item["row"])
        if kind not in {"purchase", "sale"}:
            continue
        event_type = "card" if item["transaction_type"] == "CARD_AUTHORIZATION" else "swap"
        # Wavecard top-ups only move value into the card account. Importing the
        # later CARD_AUTHORIZATION as well would otherwise count the same sats twice.
        if _wavespace_is_wavecard_topup(item):
            continue
        # A card authorization is a disposal of BTC for the card's fiat amount.
        if event_type == "card" and kind != "sale":
            continue
        card_usage, card_location = _wavespace_card_usage(item) if event_type == "card" else ("", "")
        book_kind = (
            "expense"
            if event_type == "card" and _wavespace_is_card_purchase_expense(item)
            else kind
        )
        embedded_fee = None
        memo_lower = _wavespace_memo(item).lower()
        if event_type == "card" and "application fee" in memo_lower:
            fee_asset, fee_amount = _wavespace_fee_from_memo(
                item["row"], ("BTC", fiat_currency)
            )
            if fee_amount is not None and fee_amount >= 0 and fee_asset in {"BTC", fiat_currency}:
                embedded_fee = {
                    "item": item,
                    "asset": fee_asset,
                    "amount": fee_amount,
                    "from_memo": True,
                }
        events.append({
            "entry": item,
            "index": item["index"],
            "kind": kind,
            "book_kind": book_kind,
            "event_type": event_type,
            "card_usage": card_usage,
            "card_location": card_location,
            "gross_btc": gross_btc,
            "fiat_currency": fiat_currency,
            "fiat_amount": fiat_amount,
            "price": price,
            "application_fee": embedded_fee,
            "withdrawal": None,
            "network_fee": None,
            "deposit": None,
            "transaction_meta": None,
        })

    card_creation_fees = [item for item in entries if _wavespace_is_card_creation_fee(item)]

    if not events and not card_creation_fees:
        return [], len(entries)

    application_fees = [
        item for item in entries
        if item["category"] == "FEE"
        and item["transaction_type"] not in {"NETWORK_FEE"}
        and not _wavespace_is_card_creation_fee(item)
    ]
    network_fees = [
        item for item in entries
        if item["category"] == "FEE"
        and (
            item["transaction_type"] == "NETWORK_FEE"
            or any(word in (
                item["transaction_type"] + " "
                + _get(item["row"], "memo", "note", "notes", "comment")
            ).lower() for word in ("network", "mining", "miner", "on-chain", "onchain"))
        )
    ]
    withdrawals = [
        item for item in entries
        if item["category"] in {"WITHDRAWAL", "WITHDRAW"}
        and item["transaction_type"] not in {"SEPA_PAYOUT"}
        and _wavespace_btc_transfer_amount(item) is not None
    ]
    deposits = [
        item for item in entries
        if item["category"] == "DEPOSIT"
        and _wavespace_fiat_amount(item["row"])[1] is not None
    ]
    generic_transactions = [
        item for item in entries
        if item["category"] == "TRANSACTION"
        and item["transaction_type"] not in {
            "CARD_AUTHORIZATION", "REFERRAL_REWARD", "CURRENCY_SWAP",
        }
    ]

    # Match at most one application fee to each event. Currency compatibility is
    # deliberately strict so a BTC card fee is not attached to an EUR->BTC buy.
    fee_pairs: list[tuple[float, int, int, str, Decimal, bool]] = []
    for event_index, event in enumerate(events):
        if event.get("application_fee") is not None:
            continue
        fiat = event["fiat_currency"]
        if event["kind"] == "purchase":
            preferred_assets = (fiat,)
            accepted_assets = {fiat}
        elif event["event_type"] == "card":
            preferred_assets = ("BTC", fiat)
            accepted_assets = {"BTC", fiat}
        else:
            preferred_assets = ("BTC", fiat)
            accepted_assets = {"BTC", fiat}
        for fee_index, fee_item in enumerate(application_fees):
            fee_asset, fee_amount, from_memo = _wavespace_fee_value(fee_item, preferred_assets)
            if fee_amount is None or fee_amount < 0 or fee_asset not in accepted_assets:
                continue
            score = _wavespace_distance_score(
                event["entry"], fee_item, max_seconds=30 * 60,
            )
            if score is None:
                continue
            # Exact preferred currency wins when two fee rows are equally close.
            if fee_asset != preferred_assets[0]:
                score += 120.0
            fee_pairs.append((score, event_index, fee_index, fee_asset, fee_amount, from_memo))

    assigned_events: set[int] = set()
    assigned_fee_rows: set[int] = set()
    for score, event_index, fee_index, fee_asset, fee_amount, from_memo in sorted(fee_pairs):
        if event_index in assigned_events or fee_index in assigned_fee_rows:
            continue
        events[event_index]["application_fee"] = {
            "item": application_fees[fee_index],
            "asset": fee_asset,
            "amount": fee_amount,
            "from_memo": from_memo,
        }
        assigned_events.add(event_index)
        assigned_fee_rows.add(fee_index)

    # A purchase may have an immediate Lightning/on-chain payout. Only a payout
    # close in time and not larger than the gross swap amount can replace the swap
    # quantity. This avoids attaching independent wallet withdrawals.
    withdrawal_pairs: list[tuple[float, int, int]] = []
    for event_index, event in enumerate(events):
        if event["kind"] != "purchase" or event["event_type"] == "card":
            continue
        gross_btc = event["gross_btc"]
        if gross_btc is None or gross_btc <= 0:
            continue
        for withdrawal_index, withdrawal_item in enumerate(withdrawals):
            wallet_btc = _wavespace_btc_transfer_amount(withdrawal_item)
            if wallet_btc is None or wallet_btc <= 0:
                continue
            event_id = _wavespace_transaction_id(event["entry"]["row"])
            withdrawal_id = _wavespace_transaction_id(withdrawal_item["row"])
            same_id = bool(event_id and withdrawal_id and event_id == withdrawal_id)
            ratio = wallet_btc / gross_btc
            if not same_id and (ratio < Decimal("0.50") or ratio > Decimal("1.01")):
                continue
            score = _wavespace_distance_score(
                event["entry"], withdrawal_item,
                max_seconds=2 * 60 * 60,
                prefer_right_after_left=True,
            )
            if score is None:
                continue
            score += float(abs(gross_btc - wallet_btc) / gross_btc) * 3600.0
            if withdrawal_item["transaction_type"] == "LIGHTNING_WITHDRAW":
                score -= 5.0
            withdrawal_pairs.append((score, event_index, withdrawal_index))

    used_events: set[int] = set()
    used_withdrawals: set[int] = set()
    for score, event_index, withdrawal_index in sorted(withdrawal_pairs):
        if event_index in used_events or withdrawal_index in used_withdrawals:
            continue
        events[event_index]["withdrawal"] = withdrawals[withdrawal_index]
        used_events.add(event_index)
        used_withdrawals.add(withdrawal_index)

    # Network fees belong to a concrete on-chain withdrawal, not merely to the
    # nearest currency swap. Standalone withdrawals therefore cannot pollute a buy.
    network_pairs: list[tuple[float, int, int, str, Decimal, bool]] = []
    for event_index, event in enumerate(events):
        withdrawal_item = event.get("withdrawal")
        if not withdrawal_item or withdrawal_item["transaction_type"] == "LIGHTNING_WITHDRAW":
            continue
        for network_index, network_item in enumerate(network_fees):
            fee_asset, fee_amount, from_memo = _wavespace_fee_value(
                network_item, ("BTC", event["fiat_currency"])
            )
            if fee_amount is None or fee_amount < 0 or fee_asset not in {"BTC", event["fiat_currency"]}:
                continue
            score = _wavespace_distance_score(
                withdrawal_item, network_item, max_seconds=30 * 60,
            )
            if score is None:
                continue
            if fee_asset != "BTC":
                score += 120.0
            network_pairs.append((score, event_index, network_index, fee_asset, fee_amount, from_memo))

    used_network_events: set[int] = set()
    used_network_rows: set[int] = set()
    for score, event_index, network_index, fee_asset, fee_amount, from_memo in sorted(network_pairs):
        if event_index in used_network_events or network_index in used_network_rows:
            continue
        events[event_index]["network_fee"] = {
            "item": network_fees[network_index],
            "asset": fee_asset,
            "amount": fee_amount,
            "from_memo": from_memo,
        }
        used_network_events.add(event_index)
        used_network_rows.add(network_index)

    # A matching SEPA deposit is metadata only. It never determines the purchase
    # amount or fee and is selected conservatively by time plus amount similarity.
    deposit_pairs: list[tuple[float, int, int]] = []
    for event_index, event in enumerate(events):
        if event["kind"] != "purchase" or event["fiat_amount"] is None:
            continue
        buy_fiat = event["fiat_amount"]
        for deposit_index, deposit_item in enumerate(deposits):
            currency, amount = _wavespace_fiat_amount(deposit_item["row"], event["fiat_currency"])
            if currency != event["fiat_currency"] or amount is None:
                continue
            tolerance = max(Decimal("10"), buy_fiat * Decimal("0.05"))
            if abs(amount - buy_fiat) > tolerance:
                continue
            score = _wavespace_distance_score(
                deposit_item, event["entry"], max_seconds=2 * 60 * 60,
                prefer_right_after_left=True,
            )
            if score is None:
                continue
            score += float(abs(amount - buy_fiat))
            deposit_pairs.append((score, event_index, deposit_index))

    used_deposit_events: set[int] = set()
    used_deposit_rows: set[int] = set()
    for score, event_index, deposit_index in sorted(deposit_pairs):
        if event_index in used_deposit_events or deposit_index in used_deposit_rows:
            continue
        events[event_index]["deposit"] = deposits[deposit_index]
        used_deposit_events.add(event_index)
        used_deposit_rows.add(deposit_index)

    # Optional blockchain metadata may follow a withdrawal as a TRANSACTION row.
    meta_pairs: list[tuple[float, int, int]] = []
    for event_index, event in enumerate(events):
        anchor = event.get("withdrawal") or event["entry"]
        for meta_index, meta_item in enumerate(generic_transactions):
            score = _wavespace_distance_score(anchor, meta_item, max_seconds=30 * 60)
            if score is not None:
                meta_pairs.append((score, event_index, meta_index))
    used_meta_events: set[int] = set()
    used_meta_rows: set[int] = set()
    for score, event_index, meta_index in sorted(meta_pairs):
        if event_index in used_meta_events or meta_index in used_meta_rows:
            continue
        events[event_index]["transaction_meta"] = generic_transactions[meta_index]
        used_meta_events.add(event_index)
        used_meta_rows.add(meta_index)

    output: list[dict[str, Any]] = []
    consumed: set[int] = set()

    # Wavespace labels the one-time card issue charge as APPLICATION_FEE as well.
    # It is not a trading/card-payment fee. Import it as an explicit BTC expense.
    # The browser preview later compares the BTC amount with locally cached EUR
    # prices and assigns the known 2.99 EUR virtual or 29.99 EUR physical card cost.
    card_creation_amounts: list[tuple[dict[str, Any], Decimal]] = []
    for item in card_creation_fees:
        amount_btc = _wavespace_amount_for_asset(item["row"], "BTC")
        memo_asset, memo_amount = _wavespace_fee_from_memo(item["row"], ("BTC",))
        if memo_asset == "BTC" and memo_amount is not None:
            amount_btc = memo_amount
        if amount_btc is not None and amount_btc > 0:
            card_creation_amounts.append((item, amount_btc))

    ordered_card_fees = sorted(card_creation_amounts, key=lambda pair: pair[1])
    for position, (item, amount_btc) in enumerate(ordered_card_fees):
        if len(ordered_card_fees) >= 2:
            card_value_eur = Decimal("2.99") if position == 0 else Decimal("29.99")
            card_kind = "virtual" if position == 0 else "physical"
        else:
            memo_text = _wavespace_memo(item).lower()
            card_kind = "physical" if "physical" in memo_text or "physisch" in memo_text else "virtual"
            card_value_eur = Decimal("29.99") if card_kind == "physical" else Decimal("2.99")
        effective_price = card_value_eur / amount_btc
        note_de = (
            "Wavespace · Physische Karte · Kartenerstellungsgebühr: 29,99 EUR"
            if card_kind == "physical"
            else "Wavespace · Virtuelle Karte · Kartenerstellungsgebühr: 2,99 EUR"
        )
        note_en = (
            "Wavespace · Physical card · Card creation fee: 29.99 EUR"
            if card_kind == "physical"
            else "Wavespace · Virtual card · Card creation fee: 2.99 EUR"
        )
        output.append(_transaction(
            source="Wavespace",
            row_number=item["row_no"],
            kind="sale",
            timestamp=item["timestamp"],
            amount_btc=amount_btc,
            currency="EUR",
            price=effective_price,
            fee=Decimal("0"),
            note=note_de,
            reference=_wavespace_transaction_id(item["row"]),
            optional_note_fields=_wavespace_optional_note_fields(entries, {item["index"]}),
            import_hints={
                "wavespace_kind": "card_creation",
                "card_kind": card_kind,
                "card_price_eur": card_value_eur,
                "localized_note_de": note_de,
                "localized_note_en": note_en,
            },
        ))
        consumed.add(item["index"])

    for event in events:
        primary = event["entry"]

        # In real Wavespace exports the useful POS/ATM description is often on
        # the nearby APPLICATION_FEE row instead of the CARD_AUTHORIZATION row.
        # Prefer an explicit POS/ATM memo from any row already matched to the
        # card event, while keeping the primary row as the first choice.
        if event["event_type"] == "card":
            card_sources: list[dict[str, Any]] = [primary]
            application_fee = event.get("application_fee")
            if application_fee is not None and application_fee.get("item") is not None:
                card_sources.append(application_fee["item"])
            transaction_meta = event.get("transaction_meta")
            if transaction_meta is not None:
                card_sources.append(transaction_meta)

            if any(_wavespace_is_card_purchase_expense(source_item) for source_item in card_sources):
                event["book_kind"] = "expense"

            chosen_usage = event.get("card_usage", "card")
            chosen_location = event.get("card_location", "")
            for source_item in card_sources:
                usage, location = _wavespace_card_usage(source_item)
                if usage in {"atm", "pos"}:
                    chosen_usage = usage
                    if location:
                        chosen_location = location
                    break
                if not chosen_location and location:
                    chosen_location = location
            event["card_usage"] = chosen_usage
            event["card_location"] = chosen_location

        price = event["price"]
        amount_btc = event["gross_btc"]
        metadata_indices: set[int] = {primary["index"]}
        if event["event_type"] == "card":
            label_de, label_en = _wavespace_localized_card_label(
                event.get("card_usage", "card"), event.get("card_location", "")
            )
        else:
            label_de = "Bitcoin-Kauf" if event["kind"] == "purchase" else "Bitcoin-Verkauf"
            label_en = "Bitcoin purchase" if event["kind"] == "purchase" else "Bitcoin sale"
        details_de = ["Wavespace", label_de]
        details_en = ["Wavespace", label_en]

        withdrawal_item = event.get("withdrawal")
        if withdrawal_item is not None:
            wallet_btc = _wavespace_btc_transfer_amount(withdrawal_item)
            if wallet_btc is not None and wallet_btc > 0:
                amount_btc = wallet_btc
                details_de.append("Wallet-Menge aus Withdrawal")
                details_en.append("Wallet amount from withdrawal")
                if event["gross_btc"] is not None and event["gross_btc"] != wallet_btc:
                    gross_text = f"{_format_decimal(event['gross_btc'])} BTC"
                    details_de.append(f"Bruttokauf: {gross_text}")
                    details_en.append(f"Gross purchase: {gross_text}")
                wallet_text = f"{_format_decimal(wallet_btc)} BTC"
                details_de.append(f"Wallet-Eingang: {wallet_text}")
                details_en.append(f"Wallet receipt: {wallet_text}")
            metadata_indices.add(withdrawal_item["index"])
        elif event["kind"] == "purchase":
            details_de.append("BTC-Menge aus Currency Swap")
            details_en.append("BTC amount from currency swap")

        total_fee_fiat = Decimal("0")
        sale_fee_btc = Decimal("0")
        application_fee = event.get("application_fee")
        if application_fee is not None:
            fee_asset = application_fee["asset"]
            fee_amount = application_fee["amount"]
            fee_fiat = fee_amount if fee_asset == event["fiat_currency"] else (
                fee_amount * price if fee_asset == "BTC" and price is not None else Decimal("0")
            )
            total_fee_fiat += fee_fiat
            if event["kind"] == "sale" and fee_asset == "BTC":
                # Wavespace exports card/sale BTC fees separately from the BTC
                # amount used for the merchant conversion.  The fee sats are an
                # additional disposal and must reduce the tracked stack as well.
                sale_fee_btc += abs(fee_amount)
            label_de_fee = "Kartengebühr" if event["event_type"] == "card" else "Wechselgebühr"
            label_en_fee = "Card fee" if event["event_type"] == "card" else "Trading fee"
            origin_de = " aus Memo" if application_fee["from_memo"] else ""
            origin_en = " from memo" if application_fee["from_memo"] else ""
            fee_text = f"{_format_decimal(fee_amount)} {fee_asset}"
            if fee_asset == "BTC" and fee_fiat:
                fee_text += f" (~{_format_decimal(fee_fiat)} {event['fiat_currency']})"
            details_de.append(f"{label_de_fee}{origin_de}: {fee_text}")
            details_en.append(f"{label_en_fee}{origin_en}: {fee_text}")
            metadata_indices.add(application_fee["item"]["index"])

        network_fee = event.get("network_fee")
        if network_fee is not None:
            fee_asset = network_fee["asset"]
            fee_amount = network_fee["amount"]
            fee_fiat = fee_amount if fee_asset == event["fiat_currency"] else (
                fee_amount * price if fee_asset == "BTC" and price is not None else Decimal("0")
            )
            total_fee_fiat += fee_fiat
            if event["kind"] == "sale" and fee_asset == "BTC":
                sale_fee_btc += abs(fee_amount)
            origin_de = " aus Memo" if network_fee["from_memo"] else ""
            origin_en = " from memo" if network_fee["from_memo"] else ""
            fee_text = f"{_format_decimal(fee_amount)} {fee_asset}"
            if fee_asset == "BTC" and fee_fiat:
                fee_text += f" (~{_format_decimal(fee_fiat)} {event['fiat_currency']})"
            details_de.append(f"Netzwerkgebühr{origin_de}: {fee_text}")
            details_en.append(f"Network fee{origin_en}: {fee_text}")
            metadata_indices.add(network_fee["item"]["index"])

        if event["kind"] == "sale" and sale_fee_btc > 0 and amount_btc is not None:
            amount_btc = abs(amount_btc) + sale_fee_btc

        for related in (event.get("deposit"), event.get("transaction_meta")):
            if related is not None:
                metadata_indices.add(related["index"])

        simple_swap = (
            event["event_type"] == "swap"
            and withdrawal_item is None
            and application_fee is None
            and network_fee is None
            and event.get("deposit") is None
            and event.get("transaction_meta") is None
        )
        # Card notes stay intentionally compact.  The fee remains in the
        # dedicated fee field and the raw memo can still be enabled explicitly
        # through the optional CSV fields above the preview table.
        if event["event_type"] == "card":
            note_de = f"Wavespace · {label_de}"
            note_en = f"Wavespace · {label_en}"
        else:
            note_de = "Wavespace CSV-Import" if simple_swap else " · ".join(details_de)
            note_en = "Wavespace CSV import" if simple_swap else " · ".join(details_en)
        hints: dict[str, Any] = {
            "localized_note_de": note_de,
            "localized_note_en": note_en,
        }
        if event["event_type"] == "card":
            hints.update({
                "wavespace_kind": (
                    "atm_withdrawal" if event.get("card_usage") == "atm"
                    else "card_transaction"
                ),
                "merchant": event.get("card_location", ""),
                "calculation_kind": "sale",
            })
        output.append(_transaction(
            source="Wavespace",
            row_number=primary["row_no"],
            kind=event.get("book_kind", event["kind"]),
            timestamp=primary["timestamp"],
            amount_btc=amount_btc,
            currency=event["fiat_currency"],
            price=price,
            fee=total_fee_fiat,
            note=note_de,
            reference=_wavespace_transaction_id(primary["row"]),
            optional_note_fields=_wavespace_optional_note_fields(entries, metadata_indices),
            import_hints=hints,
        ))
        consumed.update(metadata_indices)

    skipped = max(0, len(entries) - len(consumed))
    return output, skipped


def _generic_kind(row: dict[str, str]) -> str | None:
    # Broker exports use many different labels, including localized activity
    # names. Keep this deliberately broader than the exchange-specific parsers.
    text = " ".join((
        _get(
            row, "transaction type", "type", "side", "action", "operation",
            "direction", "activity", "activity type", "booking type",
            "category", "title", "vorgang", "aktivitaet",
        ),
        _get(row, "description", "details", "note", "comment"),
    )).lower()
    if any(word in text for word in (
        "sell", "sold", "sale", "verkauf", "verkauft", "bitcoin verkaufen",
        "crypto verkaufen", "withdraw fiat", "fiat withdrawal",
    )):
        return "sale"
    if any(word in text for word in (
        "buy", "bought", "purchase", "purchased", "kauf", "gekauft",
        "bitcoin kaufen", "crypto kaufen", "sparplan", "saving plan",
    )):
        return "purchase"
    return None


def _bitcoin_value_from_row(row: dict[str, str], asset_code: str) -> str:
    # Some brokers, especially Coinfinity, put the amount directly in a column
    # named BTC. Kraken may use XBT. Treat all Bitcoin ticker variants equally.
    direct = _get(
        row, "btc", "xbt", "xxbt", "xbtc", "bitcoin",
        "btc amount", "amount btc", "xbt amount", "amount xbt",
        "bitcoin amount", "btc quantity", "quantity btc",
        "xbt quantity", "quantity xbt", "crypto amount",
        "cryptocurrency amount", "base amount",
    )
    if direct:
        return direct
    for ticker in ("btc", "xbt", "bitcoin"):
        value = _get_contains(
            row, (ticker,),
            ("price", "rate", "kurs", "address", "adresse", "fee", "gebuehr", "unit", "currency"),
        )
        if value:
            return value
    if asset_code == "BTC":
        return _get(
            row, "quantity", "amount", "crypto amount", "cryptocurrency amount",
            "volume", "received amount", "sent amount", "menge", "betrag",
        )
    unit_code = _asset(_get(row, "unit", "asset unit", "crypto unit", "currency unit", "einheit", "symbol"))
    if unit_code == "BTC":
        return _get(row, "quantity", "amount", "value", "volume", "menge", "betrag")
    return ""


def _direct_fiat_value(row: dict[str, str]) -> tuple[str, str]:
    # Exports may use a literal EUR/USD/CHF column instead of separate amount
    # and currency fields. Return both the raw value and its currency code.
    for key, value in row.items():
        normalized = _clean_header(key)
        tokens = normalized.split()
        for code in FIAT_AND_QUOTES:
            lower = code.lower()
            if normalized == lower or lower in tokens:
                if any(blocked in normalized for blocked in ("price", "rate", "kurs", "fee", "gebuehr")):
                    continue
                if str(value).strip():
                    return value, code
    return "", ""


def _parse_generic(source: str, headers: list[str], rows: list[list[str]]) -> tuple[list[dict[str, Any]], int]:
    output: list[dict[str, Any]] = []
    skipped = 0
    source_label = {
        "coinfinity": "Coinfinity", "relai": "Relai", "pocket": "Pocket Bitcoin",
        "bittr": "Bittr", "wavespace": "Wavespace", "generic": "Generischer CSV-Import",
    }.get(source, source.replace("_", " ").title())
    for row_no, values in enumerate(rows, start=2):
        row = _row_dict(headers, values)
        kind = _generic_kind(row)
        asset_code = _asset(_get(
            row, "asset", "coin", "crypto currency", "cryptocurrency",
            "base asset", "asset code", "crypto asset", "waehrung", "kryptowaehrung",
        ))
        btc_value = _bitcoin_value_from_row(row, asset_code)
        amount = _number(btc_value)
        if asset_code and asset_code != "BTC" and not btc_value:
            skipped += 1
            continue
        if kind is None and amount is None:
            skipped += 1
            continue

        currency = _asset(_get(
            row, "fiat currency", "quote currency", "price currency",
            "local currency", "fiat waehrung", "handelswaehrung",
        ))
        # A generic column named Currency is ambiguous. Use it as fiat only when
        # it is not BTC/XBT; otherwise it identifies the Bitcoin amount column.
        ambiguous_currency = _asset(_get(row, "currency", "waehrung"))
        if not currency and ambiguous_currency in FIAT_AND_QUOTES:
            currency = ambiguous_currency

        price = _number(_get(
            row, "price per btc", "price per xbt", "btc price", "xbt price",
            "bitcoin price", "spot price", "exchange rate", "rate", "price",
            "btc kurs", "xbt kurs", "bitcoin kurs", "wechselkurs", "kurs",
        ))
        fiat_total_value = (
            _get(
                row, "fiat amount", "total amount", "total", "subtotal", "value",
                "cost", "proceeds", "paid amount", "payment amount", "fiat value",
                "fiat betrag", "gesamtbetrag", "gegenwert", "bezahlt", "erloes",
            )
            or _get_contains(row, ("eur", "amount"))
            or _get_contains(row, ("usd", "amount"))
            or _get_contains(row, ("chf", "amount"))
        )
        direct_fiat_value, direct_fiat_currency = _direct_fiat_value(row)
        if not fiat_total_value:
            fiat_total_value = direct_fiat_value
        fiat_total = _number(fiat_total_value)
        if not currency:
            currency = (
                direct_fiat_currency
                or _extract_code(fiat_total_value)
                or _extract_code(_get(row, "price", "total", "subtotal", "value"))
            )

        # Signed exports can identify the direction without a type column.
        if kind is None and amount is not None and fiat_total is not None:
            if amount > 0 and fiat_total < 0:
                kind = "purchase"
            elif amount < 0 and fiat_total > 0:
                kind = "sale"
        if price is None and amount and fiat_total is not None:
            price = abs(fiat_total / amount)

        fee = _number(_get(
            row, "fee", "fees", "service fee", "commission", "network fee",
            "gebuehr", "gebuehren", "servicegebuehr", "provision",
        ))
        timestamp = _iso_timestamp(_get(
            row, "timestamp", "date time", "datetime", "date", "time",
            "created at", "completed at", "execution date", "booking date",
            "datum", "zeitpunkt", "erstellt am", "ausgefuehrt am", "buchungsdatum",
        ))
        note = _get(
            row, "note", "notes", "comment", "description", "details",
            "notiz", "kommentar", "beschreibung",
        ) or f"{source_label} CSV-Import"
        reference = _stable_reference(
            row, "transaction id", "txid", "tx id", "trade id", "tradeid",
            "order id", "orderid", "id", "reference",
            "transaktions id", "auftrags id", "referenz",
        )
        output.append(_transaction(
            source=source_label, row_number=row_no, kind=kind,
            timestamp=timestamp, amount_btc=amount, currency=currency,
            price=price, fee=fee, note=note, reference=reference, fiat_amount=fiat_total,
        ))
    return output, skipped


def _decode_csv(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-16", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("CSV-Zeichencodierung wird nicht unterstützt")


def _read_csv(raw: bytes) -> tuple[list[str], list[list[str]], str]:
    text = _decode_csv(raw).replace("\x00", "")
    sample = text[:16_384]
    delimiter = ";"
    try:
        delimiter = csv.Sniffer().sniff(sample, delimiters=";,\t|").delimiter
    except csv.Error:
        counts = {item: sample.count(item) for item in (";", ",", "\t", "|")}
        delimiter = max(counts, key=counts.get)
    records: list[list[str]] = []
    reader = csv.reader(StringIO(text), delimiter=delimiter)
    max_records = MAX_IMPORT_ROWS + MAX_IMPORT_PREAMBLE_ROWS + 1
    for row in reader:
        if len(row) > MAX_IMPORT_COLUMNS:
            raise ValueError(f"CSV enthält mehr als {MAX_IMPORT_COLUMNS} Spalten")
        cleaned = [cell.strip() for cell in row]
        if any(len(cell) > MAX_IMPORT_CELL_CHARS for cell in cleaned):
            raise ValueError("CSV enthält eine ungewöhnlich große Zelle")
        if not any(cleaned):
            continue
        records.append(cleaned)
        if len(records) > max_records:
            raise ValueError(f"CSV enthält mehr als {MAX_IMPORT_ROWS} Datenzeilen")
    if not records:
        raise ValueError("Die CSV-Datei ist leer")
    # Coinbase and some tax reports prepend metadata lines. Find the most likely
    # header in the first 30 rows by column count and known field words.
    best_index, best_score = 0, -1
    hints = {
        "date", "datum", "time", "zeit", "timestamp", "type", "typ",
        "activity", "aktivitaet", "asset", "amount", "betrag", "quantity",
        "menge", "price", "preis", "kurs", "buy", "kauf", "sell",
        "verkauf", "coin", "btc", "xbt", "bitcoin", "pair", "operation",
        "vorgang", "currency", "waehrung",
    }
    for index, row in enumerate(records[:30]):
        normalized = [_clean_header(cell) for cell in row]
        score = len(row) + 5 * sum(1 for cell in normalized if any(hint in cell for hint in hints))
        if len(row) >= 3 and score > best_score:
            best_index, best_score = index, score
    headers = records[best_index]
    rows = [row for row in records[best_index + 1:] if len(row) >= 2]
    if len(headers) < 3:
        raise ValueError("Keine brauchbare CSV-Kopfzeile erkannt")
    return headers, rows, delimiter


def _extract_upload(raw: bytes, filename: str) -> tuple[bytes, str, list[str]]:
    warnings: list[str] = []
    if len(raw) > MAX_IMPORT_BYTES:
        raise ValueError("Datei ist größer als 10 MiB")
    if raw[:4] == b"PK\x03\x04" or filename.lower().endswith(".zip"):
        try:
            with ZipFile(BytesIO(raw)) as archive:
                candidates = [item for item in archive.infolist() if not item.is_dir() and item.filename.lower().endswith(('.csv', '.txt'))]
                if not candidates:
                    raise ValueError("ZIP enthält keine CSV-Datei")
                if len(candidates) > 1:
                    warnings.append(f"ZIP enthält {len(candidates)} CSV-Dateien; verwendet wurde {candidates[0].filename}")
                selected = candidates[0]
                if selected.file_size > MAX_IMPORT_BYTES:
                    raise ValueError("CSV im ZIP ist größer als 10 MiB")
                return archive.read(selected), selected.filename, warnings
        except BadZipFile as err:
            raise ValueError("ZIP-Datei ist beschädigt") from err
    return raw, filename, warnings


def parse_transaction_upload(raw: bytes, filename: str) -> dict[str, Any]:
    """Return normalized preview rows without retaining the raw upload."""
    payload, effective_name, top_warnings = _extract_upload(raw, filename)
    headers, rows, delimiter = _read_csv(payload)
    if len(rows) > MAX_IMPORT_ROWS:
        raise ValueError(f"CSV enthält mehr als {MAX_IMPORT_ROWS} Datenzeilen")
    source = _detect_source(effective_name, headers, rows)
    if source == "coinbase":
        parsed, skipped = _parse_coinbase(headers, rows)
    elif source == "kraken_trades":
        parsed, skipped = _parse_kraken_trades(headers, rows)
    elif source == "kraken_ledger":
        parsed, skipped = _parse_kraken_ledger(headers, rows)
    elif source == "binance_statement":
        parsed, skipped = _parse_binance_statement(headers, rows)
    elif source == "binance_trade":
        parsed, skipped = _parse_binance_trade(headers, rows)
    elif source == "cointracking":
        parsed, skipped = _parse_cointracking(headers, rows)
    elif source == "pocket":
        clean_headers = {_clean_header(item) for item in headers}
        if {
            "type", "buy amount", "buy cur", "sell amount", "sell cur", "date",
        }.issubset(clean_headers):
            parsed, skipped = _parse_pocket(headers, rows)
        elif {
            "type", "date", "price currency", "price amount",
            "cost currency", "cost amount", "fee currency", "fee amount",
            "value currency", "value amount",
        }.issubset(clean_headers):
            parsed, skipped = _parse_pocket_native(headers, rows)
        else:
            parsed, skipped = _parse_generic(source, headers, rows)
    elif source == "coinfinity" and {
        "order id", "type", "date", "amount eur", "amount crypto",
        "crypto", "rate eur",
    }.issubset({_clean_header(item) for item in headers}):
        parsed, skipped = _parse_coinfinity(headers, rows)
    elif source == "wavespace" and {
        "type category", "executes at", "transaction id", "transaction type",
        "from currency", "from amount", "to currency", "to amount", "memo",
    }.issubset({_clean_header(item) for item in headers}):
        parsed, skipped = _parse_wavespace(headers, rows)
    else:
        parsed, skipped = _parse_generic(source, headers, rows)
    if not parsed:
        visible_headers = ", ".join(str(item).strip() for item in headers[:16] if str(item).strip())
        detail = f" Erkannte Spalten: {visible_headers}" if visible_headers else ""
        raise ValueError(f"Keine Bitcoin-Käufe oder -Verkäufe erkannt.{detail}")
    valid = sum(1 for item in parsed if item["valid"])
    return {
        "filename": effective_name,
        "source": source,
        "source_label": parsed[0]["source"] if parsed else source,
        "delimiter": "TAB" if delimiter == "\t" else delimiter,
        "header": headers,
        "rows": parsed,
        "recognized": len(parsed),
        "valid": valid,
        "needs_review": len(parsed) - valid,
        "skipped": skipped,
        "warnings": top_warnings,
        "raw_file_retained": False,
    }


