"""Resource and data limits for Bitcoin Stack Tracker."""

from __future__ import annotations

MAX_DEPOTS = 10
MAX_GOALS = 20
MAX_LEDGER_ENTRIES = 25_000
MAX_NAME_LENGTH = 80
MAX_NOTE_LENGTH = 2_000

# Recorder protection. The dashboard can still render from locally cached daily
# prices even when some optional external statistics are skipped.
MAX_STATISTIC_SERIES = 80
MAX_STATISTIC_POINTS_PER_SYNC = 1_000_000
# No calendar-time cutoff is applied to the local daily cache. This technical
# ceiling only prevents a malformed source from returning an unbounded payload.
MAX_STATISTIC_POINTS_PER_SERIES = 100_000
MAX_HISTORY_CURRENCIES = 20

# Service/API rate limits: (maximum calls, rolling window in seconds).
RATE_LIMITS: dict[str, tuple[int, int]] = {
    "unlock_vault": (5, 300),
    "set_encryption": (3, 900),
    "change_vault_password": (3, 900),
    "backup": (3, 600),
    "restore": (3, 600),
    "import_preview": (10, 60),
    "export_csv": (5, 600),
    "bulk_import": (5, 600),
    "delete_all_entries": (2, 600),
    "sync_history": (6, 300),
}
