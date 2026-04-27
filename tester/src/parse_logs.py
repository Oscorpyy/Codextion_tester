"""parse_logs.py — Parses and validates Codexion log output."""

import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Make the src/ directory importable when this module is run directly.
_SRC = Path(__file__).resolve().parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from utils import LogEntry

# ── Log-line pattern ──────────────────────────────────────────────────────────
LOG_PAT = re.compile(
    r'^(\d+) (\d+) '
    r'(has taken a dongle|is compiling|is debugging|is refactoring|burned out)$'
)


def parse_log(output: str) -> Tuple[bool, List[LogEntry]]:
    """Parse *output* into a list of log entries.

    Returns ``(all_valid, entries)`` where *all_valid* is ``False`` if any
    non-empty line fails to match :data:`LOG_PAT`.
    """
    entries: List[LogEntry] = []
    all_valid = True
    for raw in output.splitlines():
        line = raw.rstrip()
        if not line:
            continue
        m = LOG_PAT.match(line)
        if m:
            entries.append((int(m.group(1)), int(m.group(2)), m.group(3)))
        else:
            all_valid = False
    return all_valid, entries


def check_monotonic(entries: List[LogEntry]) -> Optional[str]:
    """Return an error string if timestamps are not non-decreasing, else ``None``."""
    prev = 0
    for ts, _cid, _state in entries:
        if ts < prev:
            return f"timestamp went backwards: {prev} → {ts}"
        prev = ts
    return None


def check_dongle_before_compile(entries: List[LogEntry]) -> Optional[str]:
    """Verify each ``is compiling`` event is preceded by exactly 2
    ``has taken a dongle`` events for the same coder (since the last compile).

    Returns an error string on violation, ``None`` on success.
    """
    dongle_count: Dict[int, int] = {}
    for _ts, cid, state in entries:
        if state == "has taken a dongle":
            dongle_count[cid] = dongle_count.get(cid, 0) + 1
        elif state == "is compiling":
            cnt = dongle_count.get(cid, 0)
            if cnt != 2:
                return (
                    f"coder {cid} compiled with {cnt} dongle(s) (expected 2)"
                )
            dongle_count[cid] = 0
    return None
