# Bitcoin Stack Tracker v0.21.0.9

## Highlights

- **Revolut X CSV import** for `Symbol, Type, Quantity, Price, Value, Fees, Date`
- Manual **Einnahme**, **Ausgabe** and **Transaktionsgebühr** bookings
- On-Chain/Lightning fees in sats or BTC reduce the tracked stack and are valued at the historical BTC price
- Booking type can be corrected later; FIFO is fully revalidated
- Non-blocking historical price warning from **10% deviation**
- Separate sales/expense/income/network-fee summaries and total realized P/L
- **Kaufkraft in Sicherheit gebracht** replaces “Fiat in Sicherheit gebracht”
- New ranges: **seit Wochenbeginn**, **1 Woche**, **seit Monatsbeginn**
- XIRR remains annualized for the selected range; TWR stays cash-flow neutral; CAGR description clarified

## Revolut X

Expected columns:

`Symbol, Type, Quantity, Price, Value, Fees, Date`

- `BTC`/`XBT` only
- `Buy` → Kauf, `Sell` → Verkauf
- `Quantity` = BTC
- `Value` = Fiat-Handelswert vor Gebühr
- `Fees` = separate Fiatgebühr
- Kauf = `Value + Fees`; Verkauf = `Value - Fees`
- Dates such as `21 Jan 2026, 21:21:21` and month-first AM/PM are supported

## Quality assurance

- Final local suite: **373 tests + 8 subtests passed**
- JavaScript syntax, Python compile, JSON/YAML and version consistency checked

## Versions

- Custom Integration: **v0.21.0.9**
- Tor Gateway: **v0.21.0.3** (unchanged)

See [`CHANGELOG.md`](CHANGELOG.md) and [`RELEASE-NOTES.md`](RELEASE-NOTES.md) for details.
