"""check_timing.py — Timestamp consistency and timing-precision checks."""

import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Make the src/ directory importable when this module is run directly.
_SRC = Path(__file__).resolve().parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from utils import LogEntry


def check_burnout_precision(
    entries: List[LogEntry],
    burnout_ms: int,
    tolerance: int,
) -> Tuple[bool, str]:
    """Check that the ``burned out`` timestamp falls within *±tolerance* ms of
    *burnout_ms* after the first log entry.

    Returns ``(ok, detail_message)``.
    """
    if not entries:
        return False, "log is empty"

    burnout_ts_list = [ts for ts, _, state in entries if state == "burned out"]
    if not burnout_ts_list:
        return False, "no 'burned out' event in log — cannot measure precision"

    first_ts   = entries[0][0]
    burnout_ts = burnout_ts_list[-1]
    delta      = burnout_ts - first_ts
    diff       = abs(delta - burnout_ms)
    msg = (
        f"delta={delta} ms, expected={burnout_ms} ms, "
        f"diff={diff} ms, tolerance=±{tolerance} ms"
    )
    return diff <= tolerance, msg


def check_dongle_cooldown(
    entries: List[LogEntry],
    cooldown_ms: int,
    tolerance: int,
) -> Tuple[bool, str]:
    """Verify no coder re-acquires a dongle sooner than
    ``(cooldown_ms - tolerance)`` ms after its last compile.

    Returns ``(ok, violation_message_or_empty)``.
    """
    last_compile: Dict[int, int] = {}
    threshold = cooldown_ms - tolerance

    for ts, cid, state in entries:
        if state == "is compiling":
            last_compile[cid] = ts
        elif state == "has taken a dongle" and cid in last_compile:
            gap = ts - last_compile[cid]
            if gap < threshold:
                return (
                    False,
                    f"coder {cid} took dongle at {ts} ms, "
                    f"last compiled at {last_compile[cid]} ms "
                    f"(gap={gap} ms < threshold={threshold} ms)",
                )
    return True, ""


def check_phase_timing(
    entries: List[LogEntry],
    compile_ms: int,
    debug_ms: int,
    refactor_ms: int,
    tolerance: int,
) -> List[Tuple[str, Optional[bool], str]]:
    """Measure compile / debug / refactor phase durations per coder and check
    they are within *±tolerance* ms of the configured values.

    Returns a list of ``(phase_name, ok, detail_message)`` where *ok* is
    ``None`` when there is no data to measure.
    """
    by_coder: Dict[int, List[Tuple[int, str]]] = {}
    for ts, cid, state in entries:
        by_coder.setdefault(cid, []).append((ts, state))

    compile_diffs:  List[int] = []
    debug_diffs:    List[int] = []
    refactor_diffs: List[int] = []

    for seq in by_coder.values():
        for i in range(len(seq) - 1):
            ts0, s0 = seq[i]
            ts1, _  = seq[i + 1]
            dur = ts1 - ts0
            if s0 == "is compiling":
                compile_diffs.append(abs(dur - compile_ms))
            elif s0 == "is debugging":
                debug_diffs.append(abs(dur - debug_ms))
            elif s0 == "is refactoring":
                refactor_diffs.append(abs(dur - refactor_ms))

    results: List[Tuple[str, Optional[bool], str]] = []
    for phase, diffs, expected in (
        ("compile",  compile_diffs,  compile_ms),
        ("debug",    debug_diffs,    debug_ms),
        ("refactor", refactor_diffs, refactor_ms),
    ):
        if not diffs:
            results.append((phase, None, "no data to measure"))
            continue
        max_diff = max(diffs)
        avg_diff = sum(diffs) / len(diffs)
        msg = (
            f"{phase} ≈ {expected} ms: "
            f"max diff={max_diff} ms, avg={avg_diff:.1f} ms, "
            f"samples={len(diffs)}, tolerance=±{tolerance} ms"
        )
        results.append((phase, max_diff <= tolerance, msg))
    return results
