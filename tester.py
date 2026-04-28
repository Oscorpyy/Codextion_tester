#!/usr/bin/env python3
"""
tester.py — Python tester for the Codexion (42 school) project

Usage:
    python3 tester.py [target] [--name BINARY] [--report FILE]
                      [--timeout SECS] [--tolerance MS]

Arguments:
    target         Path to the repo directory or directly to the binary
                   (default: '.')
    --name BINARY  Name of the binary to look for in a repo (default: 'codexion')
    --report FILE  Write a JSON report to this file after all tests
    --timeout SECS Per-test timeout in seconds (default: 15)
    --tolerance MS Acceptable timing error in ms (default: 15)


Binary interface (8 positional args):
    number_of_coders  time_to_burnout  time_to_compile  time_to_debug
    time_to_refactor  number_of_compiles_required  dongle_cooldown  scheduler

Expected log format per line:
    <timestamp_ms> <coder_id> <state>
where <state> is one of:
    has taken a dongle | is compiling | is debugging | is refactoring | burned out
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ─── Default configuration ────────────────────────────────────────────────────
DEFAULT_TIMEOUT_SEC = 15
DEFAULT_TIMING_TOL  = 15   # ms

# ─── ANSI colours (auto-disabled when not a TTY) ──────────────────────────────
def _c(code: str) -> str:
    return code if sys.stdout.isatty() else ""

RED    = _c('\033[0;31m')
GREEN  = _c('\033[0;32m')
YELLOW = _c('\033[1;33m')
CYAN   = _c('\033[0;36m')
BOLD   = _c('\033[1m')
RESET  = _c('\033[0m')

# ─── Data model ───────────────────────────────────────────────────────────────
@dataclass
class TestResult:
    label:      str
    status:     str   # "PASS" | "FAIL" | "SKIP"
    input_args: str = ""
    detail:     str = ""

LogEntry = Tuple[int, int, str]   # (timestamp_ms, coder_id, state)

# ─── Tester ───────────────────────────────────────────────────────────────────
class Tester:
    LOG_PAT = re.compile(
        r'^(\d+) (\d+) '
        r'(has taken a dongle|is compiling|is debugging|is refactoring|burned out)$'
    )

    def __init__(self, binary: str, repo: Optional[str], timeout: int, tolerance: int) -> None:
        self.binary    = binary
        self.repo      = repo
        self.timeout   = timeout
        self.tolerance = tolerance
        self.results:  List[TestResult] = []
        self.pass_n  = 0
        self.fail_n  = 0
        self.skip_n  = 0

    # ── output helpers ────────────────────────────────────────────────────────

    @staticmethod
    def section(title: str) -> None:
        print(f"\n{CYAN}{BOLD}═══ {title} ═══{RESET}")

    def _record(self, label: str, status: str,
                args: str = "", detail: str = "") -> None:
        self.results.append(TestResult(label, status, args, detail))
        if status == "PASS":
            self.pass_n += 1
            print(f"{GREEN}✅ PASS{RESET} — {label}")
        elif status == "FAIL":
            self.fail_n += 1
            suffix = f" ({detail})" if detail else ""
            print(f"{RED}❌ FAIL{RESET} — {label}{suffix}")
        elif status == "SKIP":
            self.skip_n += 1
            suffix = f" ({detail})" if detail else ""
            print(f"{YELLOW}⏭  SKIP{RESET} — {label}{suffix}")

    def ok(self, label: str, args: str = "") -> None:
        self._record(label, "PASS", args)

    def fail(self, label: str, args: str = "", detail: str = "") -> None:
        self._record(label, "FAIL", args, detail)

    def skip(self, label: str, reason: str = "") -> None:
        self._record(label, "SKIP", detail=reason)

    # ── binary runner ─────────────────────────────────────────────────────────

    def run(self, *args) -> Tuple[int, str]:
        """Run binary with timeout. Returns (exit_code, combined_output).
        exit_code == 124 means timeout."""
        cmd = [self.binary] + [str(a) for a in args]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True,
                               timeout=self.timeout)
            return r.returncode, r.stdout + r.stderr
        except subprocess.TimeoutExpired:
            return 124, ""

    def fmt(self, *args) -> str:
        """Format binary arguments as a human-readable string."""
        binary_name = os.path.basename(self.binary)
        return f"./{binary_name} " + " ".join(str(a) for a in args)

    # ── log parsing ───────────────────────────────────────────────────────────

    def parse_log(self, output: str) -> Tuple[bool, List[LogEntry]]:
        """Parse log output. Returns (all_valid, entries).
        all_valid is False if any non-empty line fails to match the pattern."""
        entries: List[LogEntry] = []
        all_valid = True
        for raw in output.splitlines():
            line = raw.rstrip()
            if not line:
                continue
            m = self.LOG_PAT.match(line)
            if m:
                entries.append((int(m.group(1)), int(m.group(2)), m.group(3)))
            else:
                all_valid = False
        return all_valid, entries

    def check_monotonic(self, entries: List[LogEntry]) -> Optional[str]:
        prev = 0
        for ts, _cid, _state in entries:
            if ts < prev:
                return f"timestamp went backwards: {prev} → {ts}"
            prev = ts
        return None

    def check_dongle_before_compile(self, entries: List[LogEntry]) -> Optional[str]:
        dongle_count: Dict[int, int] = {}
        for _ts, cid, state in entries:
            if state == "has taken a dongle":
                dongle_count[cid] = dongle_count.get(cid, 0) + 1
            elif state == "is compiling":
                cnt = dongle_count.get(cid, 0)
                if cnt != 2:
                    return (f"coder {cid} compiled with {cnt} dongle(s) "
                            f"(expected 2)")
                dongle_count[cid] = 0
        return None

    # ── assert helpers ────────────────────────────────────────────────────────

    def assert_non_zero(self, label: str, *args) -> None:
        rc, _ = self.run(*args)
        astr  = self.fmt(*args)
        if rc != 0:
            self.ok(label, astr)
        else:
            self.fail(label, astr, "expected non-zero exit, got 0")

    def assert_zero(self, label: str, *args) -> None:
        rc, _ = self.run(*args)
        astr  = self.fmt(*args)
        if rc == 0:
            self.ok(label, astr)
        else:
            self.fail(label, astr, f"expected exit 0, got {rc}")

    # ══════════════════════════════════════════════════════════════════════════
    # Category 0: Makefile checks
    # ══════════════════════════════════════════════════════════════════════════
    def cat0_makefile(self) -> None:
        self.section("Category 0: Makefile checks")

        if not self.repo:
            for label in (
                "Makefile exists",
                "Makefile: rule 'all' present",
                "Makefile: rule 'clean' present",
                "Makefile: rule 'fclean' present",
                "Makefile: rule 're' present",
                "Makefile: binary name 'codexion' referenced",
                "Makefile: compilation flags -Wall -Wextra -Werror present",
                "Makefile: no relink on repeated 'make'",
            ):
                self.skip(label, "Target is a binary file; no repository provided")
            return

        mk_path: Optional[Path] = None
        for name in ("Makefile", "makefile"):
            candidate = Path(self.repo) / name
            if candidate.exists():
                mk_path = candidate
                break

        if mk_path is None:
            for label in (
                "Makefile exists",
                "Makefile: rule 'all' present",
                "Makefile: rule 'clean' present",
                "Makefile: rule 'fclean' present",
                "Makefile: rule 're' present",
                "Makefile: binary name 'codexion' referenced",
                "Makefile: compilation flags -Wall -Wextra -Werror present",
                "Makefile: no relink on repeated 'make'",
            ):
                self.skip(label, "No Makefile found in repo path")
            return

        self.ok("Makefile exists")
        content = mk_path.read_text(errors="replace")

        # Required rules
        for rule in ("all", "clean", "fclean", "re"):
            if re.search(rf'^{re.escape(rule)}\s*:', content, re.MULTILINE):
                self.ok(f"Makefile: rule '{rule}' present")
            else:
                self.fail(f"Makefile: rule '{rule}' missing",
                          detail=f"'{rule}:' not found in Makefile")

        # Binary name
        if re.search(r'\bcodexion\b', content):
            self.ok("Makefile: binary name 'codexion' referenced")
        else:
            self.fail("Makefile: binary name 'codexion' not found",
                      detail="'codexion' not referenced in Makefile")

        # Compilation flags
        has_wall   = re.search(r'-Wall\b',   content) is not None
        has_wextra = re.search(r'-Wextra\b', content) is not None
        has_werror = re.search(r'-Werror\b', content) is not None
        if has_wall and has_wextra and has_werror:
            self.ok("Makefile: compilation flags -Wall -Wextra -Werror present")
        else:
            missing = [f for f, ok in (("-Wall",   has_wall),
                                        ("-Wextra", has_wextra),
                                        ("-Werror", has_werror)) if not ok]
            self.fail("Makefile: compilation flags incomplete",
                      detail=f"missing: {' '.join(missing)}")

        # No-relink: run make a second time; it should not recompile anything.
        # A relink is detected when make output contains a compiler invocation
        # (cc/gcc/clang/g++) or an explicit link command, regardless of whether
        # make exits 0.
        r2 = subprocess.run(
            ["make", "-C", self.repo],
            capture_output=True, text=True
        )
        combined = r2.stdout + r2.stderr
        relink_pat = re.compile(r'\b(cc|gcc|g\+\+|clang\+\+|clang)\b', re.IGNORECASE)
        if r2.returncode == 0 and not relink_pat.search(combined):
            self.ok("Makefile: no relink on repeated 'make'")
        else:
            self.fail("Makefile: relink detected on second 'make'",
                      detail="second 'make' produced compiler invocations or failed")

    # ══════════════════════════════════════════════════════════════════════════
    # Category 1: Invalid arguments
    # ══════════════════════════════════════════════════════════════════════════
    def cat1_invalid_args(self) -> None:
        self.section("Category 1: Invalid arguments")

        # Too few arguments
        self.assert_non_zero("Too few args (0 args)")
        self.assert_non_zero("Too few args (3 args)", 3, 800, 200)
        self.assert_non_zero("Too few args (7 args)", 4, 800, 200, 100, 50, 3, 0)

        # Negative / zero values
        self.assert_non_zero("Negative number_of_coders",   -1, 800, 200, 100, 50, 3,  0,  "fifo")
        self.assert_non_zero("Negative time_to_burnout",     2,  -1, 200, 100, 50, 3,  0,  "fifo")
        self.assert_non_zero("Negative time_to_compile",     2, 800,  -1, 100, 50, 3,  0,  "fifo")
        self.assert_non_zero("Negative time_to_debug",       2, 800, 200,  -1, 50, 3,  0,  "fifo")
        self.assert_non_zero("Negative time_to_refactor",    2, 800, 200, 100, -1, 3,  0,  "fifo")
        self.assert_non_zero("Negative number_of_compiles",  2, 800, 200, 100, 50, -1, 0,  "fifo")
        self.assert_non_zero("Negative dongle_cooldown",     2, 800, 200, 100, 50, 3,  -1, "fifo")
        self.assert_non_zero("Zero number_of_coders",        0, 800, 200, 100, 50, 3,  0,  "fifo")

        # Invalid scheduler string
        self.assert_non_zero("Invalid scheduler 'round_robin'",
                             4, 800, 200, 100, 50, 3, 0, "round_robin")
        self.assert_non_zero("Invalid scheduler 'FIFO' (case)",
                             4, 800, 200, 100, 50, 3, 0, "FIFO")
        self.assert_non_zero("Invalid scheduler 'random'",
                             4, 800, 200, 100, 50, 3, 0, "random")

        # Non-integer arguments
        self.assert_non_zero("Non-integer coders 'abc'",  "abc", 800, 200, 100, 50, 3, 0, "fifo")
        self.assert_non_zero("Non-integer burnout '1.5'",  2, "1.5", 200, 100, 50, 3, 0, "fifo")
        self.assert_non_zero("Non-integer compile 'two'",  2,  800, "two", 100, 50, 3, 0, "fifo")

    # ══════════════════════════════════════════════════════════════════════════
    # Category 2: Single coder
    # ══════════════════════════════════════════════════════════════════════════
    def cat2_single_coder(self) -> None:
        self.section("Category 2: Single coder")
        args = (1, 400, 200, 100, 50, 3, 0, "fifo")
        astr = self.fmt(*args)
        _, out = self.run(*args)
        if "burned out" in out:
            self.ok("1 coder burns out (only 1 dongle available, needs 2)", astr)
        else:
            self.fail("1 coder did NOT burn out — expected burnout (1 dongle, needs 2)", astr)

    # ══════════════════════════════════════════════════════════════════════════
    # Category 3: Basic cases without burnout
    # ══════════════════════════════════════════════════════════════════════════
    def cat3_basic(self) -> None:
        self.section("Category 3: Basic cases without burnout")
        for n_coders, sched in ((2, "fifo"), (4, "edf")):
            args = (n_coders, 2000, 200, 100, 50, 2, 0, sched)
            astr = self.fmt(*args)
            _, out  = self.run(*args)
            _, ents = self.parse_log(out)
            lbl = f"{n_coders} coders {sched}"

            if "burned out" not in out:
                self.ok(f"{lbl}: no burnout", astr)
            else:
                self.fail(f"{lbl}: unexpected burnout", astr)

            all_compiled = all(
                sum(1 for _, c, s in ents if c == cid and s == "is compiling") >= 2
                for cid in range(1, n_coders + 1)
            )
            if all_compiled:
                self.ok(f"{lbl}: all coders compiled >= 2 times", astr)
            else:
                self.fail(f"{lbl}: not all coders compiled enough times", astr)

    # ══════════════════════════════════════════════════════════════════════════
    # Category 4: Expected burnout
    # ══════════════════════════════════════════════════════════════════════════
    def cat4_burnout(self) -> None:
        self.section("Category 4: Expected burnout")
        args = (4, 150, 300, 150, 100, 5, 0, "fifo")
        astr = self.fmt(*args)
        _, out = self.run(*args)
        if "burned out" in out:
            self.ok("Expected burnout occurs (burnout=150 ms, compile=300 ms)", astr)
        else:
            self.fail("Expected burnout did NOT occur (burnout=150 ms, compile=300 ms)", astr)

    # ══════════════════════════════════════════════════════════════════════════
    # Category 5: Log format verification
    # ══════════════════════════════════════════════════════════════════════════
    def cat5_log_format(self) -> None:
        self.section("Category 5: Log format verification")
        args = (3, 2000, 300, 150, 100, 2, 0, "fifo")
        astr = self.fmt(*args)
        _, out       = self.run(*args)
        all_valid, ents = self.parse_log(out)

        # 5a — line format
        if all_valid:
            self.ok("Log format: all lines match expected pattern", astr)
        else:
            self.fail("Log format: some lines have an invalid format", astr)

        # 5b — monotonic timestamps
        err = self.check_monotonic(ents)
        if err is None:
            self.ok("Log format: timestamps are non-decreasing", astr)
        else:
            self.fail("Log format: timestamps are NOT monotonic", astr, err)

        # 5c — exactly 2 dongles before each compile
        err = self.check_dongle_before_compile(ents)
        if err is None:
            self.ok("Log format: every 'is compiling' preceded by exactly 2 'has taken a dongle'",
                    astr)
        else:
            self.fail("Log format: dongle-count before compile is not exactly 2", astr, err)

        # 5d — no garbage lines
        bad = sum(
            1 for raw in out.splitlines()
            if raw.strip() and not self.LOG_PAT.match(raw.rstrip())
        )
        if bad == 0:
            self.ok("Log format: no mixed or garbage lines", astr)
        else:
            self.fail("Log format: mixed/garbage lines detected", astr, f"{bad} invalid line(s)")

    # ══════════════════════════════════════════════════════════════════════════
    # Category 6: Burnout timing precision
    # ══════════════════════════════════════════════════════════════════════════
    def cat6_burnout_precision(self) -> None:
        burnout_ms = 400
        self.section(f"Category 6: Burnout timing precision (±{self.tolerance} ms)")
        args = (1, burnout_ms, 200, 100, 50, 3, 0, "fifo")
        astr = self.fmt(*args)
        _, out  = self.run(*args)
        _, ents = self.parse_log(out)

        burnout_ts_list = [ts for ts, _, state in ents if state == "burned out"]
        if not burnout_ts_list:
            self.fail("Burnout precision: no 'burned out' in log — cannot measure precision", astr)
            return
        if not ents:
            self.fail("Burnout precision: log is empty", astr)
            return

        first_ts   = ents[0][0]
        burnout_ts = burnout_ts_list[-1]
        delta      = burnout_ts - first_ts
        diff       = abs(delta - burnout_ms)
        if diff <= self.tolerance:
            self.ok(
                f"Burnout precision: delta={delta} ms, expected={burnout_ms} ms "
                f"(diff={diff} ms ≤ {self.tolerance} ms)",
                astr,
            )
        else:
            self.fail(
                f"Burnout precision: delta={delta} ms, expected={burnout_ms} ms "
                f"(diff={diff} ms > {self.tolerance} ms)",
                astr,
            )

    # ══════════════════════════════════════════════════════════════════════════
    # Category 7: Dongle cooldown
    # ══════════════════════════════════════════════════════════════════════════
    def cat7_cooldown(self) -> None:
        cooldown_ms = 200
        self.section(f"Category 7: Dongle cooldown (cooldown={cooldown_ms} ms)")
        args = (2, 5000, 300, 150, 100, 3, cooldown_ms, "fifo")
        astr = self.fmt(*args)
        _, out  = self.run(*args)
        _, ents = self.parse_log(out)

        violation: Optional[str] = None
        last_compile: Dict[int, int] = {}
        threshold = cooldown_ms - self.tolerance

        for ts, cid, state in ents:
            if state == "is compiling":
                last_compile[cid] = ts
            elif state == "has taken a dongle" and cid in last_compile:
                gap = ts - last_compile[cid]
                if gap < threshold:
                    violation = (
                        f"coder {cid} took dongle at {ts} ms, "
                        f"last compiled at {last_compile[cid]} ms "
                        f"(gap={gap} ms < threshold={threshold} ms)"
                    )
                    break

        if violation is None:
            self.ok(
                f"Dongle cooldown: no premature re-acquisition detected "
                f"(cooldown={cooldown_ms} ms, tolerance={self.tolerance} ms)",
                astr,
            )
        else:
            self.fail("Dongle cooldown: premature dongle re-acquisition detected",
                      astr, violation)

    # ══════════════════════════════════════════════════════════════════════════
    # Category 8: fifo vs edf schedulers
    # ══════════════════════════════════════════════════════════════════════════
    def cat8_schedulers(self) -> None:
        self.section("Category 8: fifo vs edf schedulers")
        for sched in ("fifo", "edf"):
            args = (3, 2000, 300, 150, 100, 2, 0, sched)
            astr = self.fmt(*args)
            rc, out = self.run(*args)
            all_valid, _ = self.parse_log(out)

            if out.strip():
                self.ok(f"Scheduler {sched}: binary produced output", astr)
            else:
                self.fail(f"Scheduler {sched}: no output produced", astr)

            if all_valid:
                self.ok(f"Scheduler {sched}: log format is valid", astr)
            else:
                self.fail(f"Scheduler {sched}: log format is invalid", astr)

            if rc != 124:
                self.ok(f"Scheduler {sched}: simulation finishes within {self.timeout}s", astr)
            else:
                self.fail(f"Scheduler {sched}: simulation timed out after {self.timeout}s", astr)

    # ══════════════════════════════════════════════════════════════════════════
    # Category 9: Memory leaks (valgrind)
    # ══════════════════════════════════════════════════════════════════════════
    def cat9_valgrind(self) -> None:
        self.section("Category 9: Memory leaks (valgrind)")

        if not shutil.which("valgrind"):
            self.skip("Valgrind: no memory errors",  "valgrind not installed")
            self.skip("Valgrind: no heap leaks",      "valgrind not installed")
            return

        args = [2, 1500, 300, 150, 100, 2, 0, "fifo"]
        astr = "valgrind " + self.fmt(*args)

        with tempfile.NamedTemporaryFile(suffix=".vg", delete=False) as vf:
            vg_log = vf.name

        try:
            subprocess.run(
                ["valgrind", "--leak-check=full", "--error-exitcode=42",
                 f"--log-file={vg_log}", self.binary] + [str(a) for a in args],
                capture_output=True, text=True,
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired:
            pass

        try:
            vg_content = Path(vg_log).read_text(errors="replace")
        except OSError:
            vg_content = ""
        finally:
            try:
                os.unlink(vg_log)
            except OSError:
                pass

        if "ERROR SUMMARY: 0 errors" in vg_content:
            self.ok("Valgrind: no memory errors", astr)
        else:
            self.fail("Valgrind: memory errors detected", astr)

        if "All heap blocks were freed" in vg_content:
            self.ok("Valgrind: no heap leaks (All blocks freed)", astr)
            return

        def _lost_bytes(pattern: str) -> int:
            m = re.search(pattern, vg_content)
            return int(m.group(1).replace(",", "")) if m else -1

        def_lost = _lost_bytes(r'definitely lost:\s+([\d,]+) bytes')
        ind_lost = _lost_bytes(r'indirectly lost:\s+([\d,]+) bytes')

        if def_lost == 0 and ind_lost == 0:
            self.ok("Valgrind: no heap leaks (definitely/indirectly lost = 0)", astr)
        else:
            detail = f"definitely lost={def_lost} B, indirectly lost={ind_lost} B"
            self.fail("Valgrind: heap leaks detected", astr, detail)

    # ══════════════════════════════════════════════════════════════════════════
    # Category 10: Stop condition
    # ══════════════════════════════════════════════════════════════════════════
    def cat10_stop_condition(self) -> None:
        self.section("Category 10: Stop condition (number_of_compiles_required)")
        required = 3
        n_coders = 2
        args = (n_coders, 5000, 200, 100, 50, required, 0, "fifo")
        astr = self.fmt(*args)
        _, out  = self.run(*args)
        _, ents = self.parse_log(out)

        # 10a — no burnout
        if "burned out" not in out:
            self.ok("Stop condition: simulation stopped without burnout", astr)
        else:
            self.fail("Stop condition: unexpected burnout with generous timings", astr)

        # 10b — all coders reached their compile goal
        all_met = all(
            sum(1 for _, c, s in ents if c == cid and s == "is compiling") >= required
            for cid in range(1, n_coders + 1)
        )
        if all_met:
            self.ok(f"Stop condition: all coders compiled >= {required} times", astr)
        else:
            self.fail(f"Stop condition: some coders did not reach {required} compiles", astr)

        # 10c — simulation did not overshoot (at most required+1 compiles per coder)
        max_expected = required + 1
        overflow = any(
            sum(1 for _, c, s in ents if c == cid and s == "is compiling") > max_expected
            for cid in range(1, n_coders + 1)
        )
        if not overflow:
            self.ok("Stop condition: simulation terminated promptly after goal was reached", astr)
        else:
            self.fail(
                "Stop condition: coders compiled far too many times "
                "(stop condition may be broken)",
                astr,
            )

    # ══════════════════════════════════════════════════════════════════════════
    # Category 11: Phase timing precision
    # ══════════════════════════════════════════════════════════════════════════
    def cat11_timing_precision(self) -> None:
        self.section(f"Category 11: Phase timing precision (±{self.tolerance} ms)")
        compile_ms  = 300
        debug_ms    = 150
        refactor_ms = 100
        args = (2, 5000, compile_ms, debug_ms, refactor_ms, 2, 0, "fifo")
        astr = self.fmt(*args)
        _, out  = self.run(*args)
        _, ents = self.parse_log(out)

        # Group entries by coder
        by_coder: Dict[int, List[Tuple[int, str]]] = {}
        for ts, cid, state in ents:
            by_coder.setdefault(cid, []).append((ts, state))

        compile_diffs:  List[int] = []
        debug_diffs:    List[int] = []
        refactor_diffs: List[int] = []

        for seq in by_coder.values():
            for i in range(len(seq) - 1):
                ts0, s0 = seq[i]
                ts1, s1 = seq[i + 1]
                dur = ts1 - ts0
                if s0 == "is compiling":
                    compile_diffs.append(abs(dur - compile_ms))
                elif s0 == "is debugging":
                    debug_diffs.append(abs(dur - debug_ms))
                elif s0 == "is refactoring":
                    # Refactoring is usually followed by taking a dongle, which might wait for available dongles.
                    # Thus, the duration from "refactoring" to the next action could be longer than refactor_ms.
                    # We will only record it if the next state is not "has taken a dongle" to be safe,
                    # or we record (dur - refactor_ms) maxing at 0 if dur >= refactor_ms.
                    if s1 != "has taken a dongle":
                        refactor_diffs.append(abs(dur - refactor_ms))
                    else:
                        if dur < refactor_ms:
                            refactor_diffs.append(refactor_ms - dur)
                        else:
                            refactor_diffs.append(0)

        for phase, diffs, expected in (
            ("compile",  compile_diffs,  compile_ms),
            ("debug",    debug_diffs,    debug_ms),
            ("refactor", refactor_diffs, refactor_ms),
        ):
            if not diffs:
                self.skip(
                    f"Phase timing: {phase} phase (no data to measure)",
                    "could not collect phase intervals",
                )
                continue
            max_diff = max(diffs)
            avg_diff = sum(diffs) / len(diffs)
            label = (
                f"Phase timing: {phase} duration ≈ {expected} ms "
                f"(max diff={max_diff} ms, avg={avg_diff:.1f} ms, samples={len(diffs)})"
            )
            if max_diff <= self.tolerance:
                self.ok(label, astr)
            else:
                self.fail(
                    label,
                    astr,
                    f"max diff {max_diff} ms > tolerance {self.tolerance} ms",
                )

    # ══════════════════════════════════════════════════════════════════════════
    # Run all categories
    # ══════════════════════════════════════════════════════════════════════════
    def run_all(self) -> None:
        # ── Step 0: build ────────────────────────────────────────────────────
        if self.repo:
            self.section("Step 0: Build")
            try:
                mk_found = any(
                    (Path(self.repo) / n).exists() for n in ("Makefile", "makefile")
                )
                if mk_found:
                    print(f"Running make in {self.repo} …")
                    r = subprocess.run(["make", "-C", self.repo])
                    if r.returncode == 0:
                        self.ok("make succeeded")
                    else:
                        self.fail("make failed — subsequent tests may not be meaningful")
                else:
                    print(f"{YELLOW}No Makefile found in {self.repo} — skipping build step{RESET}")
            except Exception as e:
                self.fail("Build step failed with an error", detail=str(e))
        else:
            self.section("Step 0: Build")
            print(f"{YELLOW}Target is a binary file — skipping build step{RESET}")

        if not os.path.exists(self.binary):
            print(f"{RED}Binary '{self.binary}' not found.{RESET}")
            sys.exit(1)
            
        if not os.access(self.binary, os.X_OK):
            print(f"{RED}Binary '{self.binary}' is not executable.{RESET}")
            sys.exit(1)

        try:
            self.cat0_makefile()
            self.cat1_invalid_args()
            self.cat2_single_coder()
            self.cat3_basic()
            self.cat4_burnout()
            self.cat5_log_format()
            self.cat6_burnout_precision()
            self.cat7_cooldown()
            self.cat8_schedulers()
            self.cat9_valgrind()
            self.cat10_stop_condition()
            self.cat11_timing_precision()
        except Exception as e:
            print(f"\n{RED}An error occurred during tests execution: {e}{RESET}")

    # ══════════════════════════════════════════════════════════════════════════
    # Final summary
    # ══════════════════════════════════════════════════════════════════════════
    def print_summary(self) -> None:
        total = self.pass_n + self.fail_n + self.skip_n
        bar   = "═" * 45
        print(f"\n{BOLD}{bar}{RESET}")
        print(f"{BOLD}  RESULTS: {self.pass_n}/{total} tests passed{RESET}")
        if self.skip_n:
            print(f"  {YELLOW}Skipped: {self.skip_n}{RESET}")
        if self.fail_n:
            print(f"  {RED}Failed:  {self.fail_n}{RESET}")
            print(f"{BOLD}{bar}{RESET}")
            print(f"\n{BOLD}{RED}Failed tests (with input):{RESET}")
            for r in self.results:
                if r.status != "FAIL":
                    continue
                print(f"  {RED}✗{RESET} {r.label}")
                if r.input_args:
                    print(f"    input : {r.input_args}")
                if r.detail:
                    print(f"    detail: {r.detail}")
            print()
        else:
            print(f"{GREEN}  All tests passed! 🎉{RESET}")
        print(f"{BOLD}{bar}{RESET}")

    # ══════════════════════════════════════════════════════════════════════════
    # JSON report
    # ══════════════════════════════════════════════════════════════════════════
    def write_report(self, path: str) -> None:
        data = {
            "summary": {
                "pass":  self.pass_n,
                "fail":  self.fail_n,
                "skip":  self.skip_n,
                "total": self.pass_n + self.fail_n + self.skip_n,
            },
            "tests": [
                {
                    "label":  r.label,
                    "status": r.status,
                    "input":  r.input_args,
                    "detail": r.detail,
                }
                for r in self.results
            ],
        }
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
        print(f"\nReport written to: {path}")


# ─── Entry point ──────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Codexion project tester (Python)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "target", nargs="?", default=".",
        help="Path to the repository directory or directly to the binary file (default: '.')",
    )
    parser.add_argument(
        "--name", default="codexion",
        help="Name of the binary to test if a directory is given (default: 'codexion')",
    )
    parser.add_argument(
        "--report", default=None, metavar="FILE",
        help="Write a JSON report to FILE after all tests",
    )
    parser.add_argument(
        "--timeout", type=int, default=DEFAULT_TIMEOUT_SEC, metavar="SECS",
        help=f"Per-test timeout in seconds (default: {DEFAULT_TIMEOUT_SEC})",
    )
    parser.add_argument(
        "--tolerance", type=int, default=DEFAULT_TIMING_TOL, metavar="MS",
        help=f"Acceptable timing error in ms (default: {DEFAULT_TIMING_TOL})",
    )
    args = parser.parse_args()

    target_path = os.path.abspath(args.target)
    
    if os.path.isfile(target_path):
        repo_path = None
        binary_path = target_path
    elif os.path.isdir(target_path):
        repo_path = target_path
        binary_path = os.path.join(repo_path, args.name)
    else:
        print(f"{RED}Error: Target path '{target_path}' is not a valid file or directory.{RESET}")
        sys.exit(1)

    try:
        t = Tester(binary_path, repo_path, args.timeout, args.tolerance)
        t.run_all()
        t.print_summary()

        if args.report:
            t.write_report(args.report)

        sys.exit(0 if t.fail_n == 0 else 1)
    except KeyboardInterrupt:
        print(f"\n{YELLOW}Testing interrupted by user.{RESET}")
        sys.exit(130)
    except Exception as e:
        print(f"\n{RED}An unexpected error occurred: {e}{RESET}")
        sys.exit(1)

if __name__ == "__main__":
    main()
