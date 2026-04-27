#!/usr/bin/env python3
"""run_tests.py — Reads tests.txt, runs each test case, and reports results.

Usage:
    python3 src/run_tests.py [binary] [--repo PATH] [--tests FILE]
                             [--timeout SECS] [--tolerance MS]
                             [--report FILE]

Binary interface (8 positional args):
    number_of_coders  time_to_burnout  time_to_compile  time_to_debug
    time_to_refactor  number_of_compiles_required  dongle_cooldown  scheduler

tests.txt format (one test per line):
    type|label|args

    type is one of:
        invalid_args       binary must exit non-zero
        single_coder       1 coder must produce "burned out"
        no_burnout         no burnout; all coders reach their compile goal
        expect_burnout     at least one "burned out" must appear
        log_format         line format, monotonic timestamps, dongle counts
        burnout_precision  "burned out" timestamp within ±tolerance ms
        cooldown           dongle re-acquisition respects cooldown period
        scheduler          valid output, correct format, finishes in time
        valgrind           no memory errors / heap leaks (skipped if absent)
        stop_condition     simulation stops after all coders reach goal
        phase_timing       compile/debug/refactor durations within ±tolerance
        makefile           Makefile rules, binary name, flags, no-relink

    args is the space-separated list of binary arguments (may be empty).

    Lines starting with '#' and blank lines are ignored.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ── Make src/ importable regardless of the working directory ──────────────────
_SRC = Path(__file__).resolve().parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from utils import (
    LogEntry, TestResult,
    RED, GREEN, YELLOW, CYAN, BOLD, RESET,
    print_pass, print_fail, print_skip, print_section,
    print_summary, run_binary,
)
from parse_logs import (
    LOG_PAT, parse_log, check_monotonic, check_dongle_before_compile,
)
from check_timing import (
    check_burnout_precision, check_dongle_cooldown, check_phase_timing,
)
from check_makefile import check_makefile

DEFAULT_TIMEOUT   = 15   # seconds
DEFAULT_TOLERANCE = 15   # ms


# ── tests.txt loader ──────────────────────────────────────────────────────────
def load_tests(path: str) -> List[Tuple[str, str, str]]:
    """Load test cases from *path*.

    Each non-blank, non-comment line must follow the format::

        type|label|args

    Returns a list of ``(type, label, args_string)`` tuples.
    """
    tests: List[Tuple[str, str, str]] = []
    with open(path, encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("|", 2)
            if len(parts) != 3:
                print(
                    f"{YELLOW}Warning: skipping malformed line {lineno}: "
                    f"{raw.rstrip()}{RESET}",
                    file=sys.stderr,
                )
                continue
            typ, label, args = parts
            tests.append((typ.strip(), label.strip(), args.strip()))
    return tests


# ── Test runner ───────────────────────────────────────────────────────────────
class Runner:
    """Executes individual test cases and accumulates :class:`TestResult` objects."""

    # Section headings shown the first time a test type is encountered.
    _SECTIONS: Dict[str, str] = {
        "makefile":          "Category 0: Makefile checks",
        "invalid_args":      "Category 1: Invalid arguments",
        "single_coder":      "Category 2: Single coder",
        "no_burnout":        "Category 3: Basic cases without burnout",
        "expect_burnout":    "Category 4: Expected burnout",
        "log_format":        "Category 5: Log format verification",
        "burnout_precision": "Category 6: Burnout timing precision",
        "cooldown":          "Category 7: Dongle cooldown",
        "scheduler":         "Category 8: fifo vs edf schedulers",
        "valgrind":          "Category 9: Memory leaks (valgrind)",
        "stop_condition":    "Category 10: Stop condition",
        "phase_timing":      "Category 11: Phase timing precision",
    }

    def __init__(
        self,
        binary: str,
        repo: str,
        timeout: int,
        tolerance: int,
    ) -> None:
        self.binary    = binary
        self.repo      = repo
        self.timeout   = timeout
        self.tolerance = tolerance
        self.results:  List[TestResult] = []
        self._seen_sections: set = set()

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _rec(
        self,
        label:  str,
        status: str,
        args:   str = "",
        detail: str = "",
    ) -> None:
        self.results.append(TestResult(label, status, args, detail))
        if status == "PASS":
            print_pass(label)
        elif status == "FAIL":
            print_fail(label, detail)
        elif status == "SKIP":
            print_skip(label, detail)

    def _run(self, args_str: str) -> Tuple[int, str]:
        args = args_str.split() if args_str else []
        return run_binary(self.binary, args, self.timeout)

    def _maybe_section(self, typ: str) -> None:
        if typ not in self._seen_sections:
            title = self._SECTIONS.get(typ, typ)
            # Append tolerance to timing-sensitive section titles.
            if typ in ("burnout_precision", "phase_timing"):
                title = f"{title} (±{self.tolerance} ms)"
            elif typ == "cooldown":
                pass  # cooldown value embedded in test label
            print_section(title)
            self._seen_sections.add(typ)

    # ── Type handlers ─────────────────────────────────────────────────────────

    def _invalid_args(self, label: str, args_str: str) -> None:
        rc, _ = self._run(args_str)
        if rc != 0:
            self._rec(label, "PASS", args_str)
        else:
            self._rec(label, "FAIL", args_str, "expected non-zero exit, got 0")

    def _single_coder(self, label: str, args_str: str) -> None:
        _, out = self._run(args_str)
        if "burned out" in out:
            self._rec(label, "PASS", args_str)
        else:
            self._rec(label, "FAIL", args_str,
                      "expected 'burned out' in output, not found")

    def _no_burnout(self, label: str, args_str: str) -> None:
        args = args_str.split()
        _, out = self._run(args_str)
        _, ents = parse_log(out)
        n_coders = int(args[0]) if args else 0
        required = int(args[5]) if len(args) > 5 else 1

        if "burned out" not in out:
            self._rec(f"{label}: no burnout", "PASS", args_str)
        else:
            self._rec(f"{label}: unexpected burnout", "FAIL", args_str)

        all_compiled = all(
            sum(1 for _, c, s in ents if c == cid and s == "is compiling") >= required
            for cid in range(1, n_coders + 1)
        )
        if all_compiled:
            self._rec(f"{label}: all coders compiled >= {required} times",
                      "PASS", args_str)
        else:
            self._rec(f"{label}: not all coders compiled enough times",
                      "FAIL", args_str)

    def _expect_burnout(self, label: str, args_str: str) -> None:
        _, out = self._run(args_str)
        if "burned out" in out:
            self._rec(label, "PASS", args_str)
        else:
            self._rec(label, "FAIL", args_str,
                      "expected at least one 'burned out', found none")

    def _log_format(self, label: str, args_str: str) -> None:
        _, out = self._run(args_str)
        all_valid, ents = parse_log(out)

        # 5a — line format
        if all_valid:
            self._rec(f"{label}: all lines match expected pattern", "PASS", args_str)
        else:
            self._rec(f"{label}: some lines have an invalid format", "FAIL", args_str)

        # 5b — monotonic timestamps
        err = check_monotonic(ents)
        if err is None:
            self._rec(f"{label}: timestamps are non-decreasing", "PASS", args_str)
        else:
            self._rec(f"{label}: timestamps are NOT monotonic", "FAIL", args_str, err)

        # 5c — exactly 2 dongles before each compile
        err = check_dongle_before_compile(ents)
        if err is None:
            self._rec(
                f"{label}: every 'is compiling' preceded by exactly 2 'has taken a dongle'",
                "PASS", args_str,
            )
        else:
            self._rec(f"{label}: dongle-count before compile is not exactly 2",
                      "FAIL", args_str, err)

        # 5d — no garbage lines
        bad = sum(
            1 for raw in out.splitlines()
            if raw.strip() and not LOG_PAT.match(raw.rstrip())
        )
        if bad == 0:
            self._rec(f"{label}: no mixed or garbage lines", "PASS", args_str)
        else:
            self._rec(f"{label}: mixed/garbage lines detected", "FAIL", args_str,
                      f"{bad} invalid line(s)")

    def _burnout_precision(self, label: str, args_str: str) -> None:
        args = args_str.split()
        burnout_ms = int(args[1]) if len(args) > 1 else 0
        _, out = self._run(args_str)
        _, ents = parse_log(out)
        ok, msg = check_burnout_precision(ents, burnout_ms, self.tolerance)
        status = "PASS" if ok else "FAIL"
        self._rec(f"{label}: {msg}", status, args_str)

    def _cooldown(self, label: str, args_str: str) -> None:
        args = args_str.split()
        cooldown_ms = int(args[6]) if len(args) > 6 else 0
        _, out = self._run(args_str)
        _, ents = parse_log(out)
        ok, detail = check_dongle_cooldown(ents, cooldown_ms, self.tolerance)
        if ok:
            self._rec(
                f"{label}: no premature re-acquisition "
                f"(cooldown={cooldown_ms} ms, tolerance=±{self.tolerance} ms)",
                "PASS", args_str,
            )
        else:
            self._rec(f"{label}: premature dongle re-acquisition detected",
                      "FAIL", args_str, detail)

    def _scheduler(self, label: str, args_str: str) -> None:
        rc, out = self._run(args_str)
        all_valid, _ = parse_log(out)

        if out.strip():
            self._rec(f"{label}: binary produced output", "PASS", args_str)
        else:
            self._rec(f"{label}: no output produced", "FAIL", args_str)

        if all_valid:
            self._rec(f"{label}: log format is valid", "PASS", args_str)
        else:
            self._rec(f"{label}: log format is invalid", "FAIL", args_str)

        if rc != 124:
            self._rec(f"{label}: simulation finishes within {self.timeout}s",
                      "PASS", args_str)
        else:
            self._rec(f"{label}: simulation timed out after {self.timeout}s",
                      "FAIL", args_str)

    def _valgrind(self, label: str, args_str: str) -> None:
        if not shutil.which("valgrind"):
            self._rec(f"{label}: no memory errors", "SKIP", "",
                      "valgrind not installed")
            self._rec(f"{label}: no heap leaks", "SKIP", "",
                      "valgrind not installed")
            return

        args = args_str.split()
        with tempfile.NamedTemporaryFile(suffix=".vg", delete=False) as vf:
            vg_log = vf.name

        try:
            subprocess.run(
                ["valgrind", "--leak-check=full", "--error-exitcode=42",
                 f"--log-file={vg_log}", self.binary] + args,
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
            self._rec(f"{label}: no memory errors", "PASS", args_str)
        else:
            self._rec(f"{label}: memory errors detected", "FAIL", args_str)

        def _lost(pattern: str) -> int:
            m = re.search(pattern, vg_content)
            return int(m.group(1).replace(",", "")) if m else -1

        def_lost = _lost(r'definitely lost:\s+([\d,]+) bytes')
        ind_lost = _lost(r'indirectly lost:\s+([\d,]+) bytes')

        if def_lost == 0 and ind_lost == 0:
            self._rec(
                f"{label}: no heap leaks (definitely/indirectly lost = 0)",
                "PASS", args_str,
            )
        else:
            detail = (
                f"definitely lost={def_lost} B, indirectly lost={ind_lost} B"
            )
            self._rec(f"{label}: heap leaks detected", "FAIL", args_str, detail)

    def _stop_condition(self, label: str, args_str: str) -> None:
        args = args_str.split()
        n_coders = int(args[0]) if args else 0
        required = int(args[5]) if len(args) > 5 else 1
        _, out = self._run(args_str)
        _, ents = parse_log(out)

        if "burned out" not in out:
            self._rec(f"{label}: simulation stopped without burnout",
                      "PASS", args_str)
        else:
            self._rec(f"{label}: unexpected burnout with generous timings",
                      "FAIL", args_str)

        all_met = all(
            sum(1 for _, c, s in ents if c == cid and s == "is compiling") >= required
            for cid in range(1, n_coders + 1)
        )
        if all_met:
            self._rec(f"{label}: all coders compiled >= {required} times",
                      "PASS", args_str)
        else:
            self._rec(
                f"{label}: some coders did not reach {required} compiles",
                "FAIL", args_str,
            )

        max_expected = required + 1
        overflow = any(
            sum(1 for _, c, s in ents if c == cid and s == "is compiling") > max_expected
            for cid in range(1, n_coders + 1)
        )
        if not overflow:
            self._rec(
                f"{label}: simulation terminated promptly after goal was reached",
                "PASS", args_str,
            )
        else:
            self._rec(
                f"{label}: coders compiled far too many times "
                "(stop condition may be broken)",
                "FAIL", args_str,
            )

    def _phase_timing(self, label: str, args_str: str) -> None:
        args = args_str.split()
        compile_ms  = int(args[2]) if len(args) > 2 else 0
        debug_ms    = int(args[3]) if len(args) > 3 else 0
        refactor_ms = int(args[4]) if len(args) > 4 else 0
        _, out = self._run(args_str)
        _, ents = parse_log(out)

        for phase, ok, msg in check_phase_timing(
            ents, compile_ms, debug_ms, refactor_ms, self.tolerance,
        ):
            full_label = f"{label}: {msg}"
            if ok is None:
                self._rec(full_label, "SKIP", args_str, msg)
            elif ok:
                self._rec(full_label, "PASS", args_str)
            else:
                self._rec(full_label, "FAIL", args_str)

    def _makefile(self, _label: str, _args_str: str) -> None:
        for lbl, ok, detail in check_makefile(self.repo):
            if ok is True:
                self._rec(lbl, "PASS")
            elif ok is False:
                self._rec(lbl, "FAIL", detail=detail)
            else:
                self._rec(lbl, "SKIP", detail=detail)

    # ── Dispatch table ────────────────────────────────────────────────────────
    _HANDLERS = {
        "invalid_args":      _invalid_args,
        "single_coder":      _single_coder,
        "no_burnout":        _no_burnout,
        "expect_burnout":    _expect_burnout,
        "log_format":        _log_format,
        "burnout_precision": _burnout_precision,
        "cooldown":          _cooldown,
        "scheduler":         _scheduler,
        "valgrind":          _valgrind,
        "stop_condition":    _stop_condition,
        "phase_timing":      _phase_timing,
        "makefile":          _makefile,
    }

    def run_test(self, typ: str, label: str, args_str: str) -> None:
        self._maybe_section(typ)
        handler = self._HANDLERS.get(typ)
        if handler is None:
            self._rec(label, "SKIP", detail=f"unknown test type '{typ}'")
        else:
            handler(self, label, args_str)

    def run_all(self, tests: List[Tuple[str, str, str]]) -> None:
        for typ, label, args_str in tests:
            self.run_test(typ, label, args_str)


# ── Entry point ───────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Codexion tester — reads tests.txt and runs all test cases",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "binary", nargs="?", default="./codexion",
        help="Path to the codexion binary (default: ./codexion)",
    )
    parser.add_argument(
        "--repo", default=None,
        help="Path to the repo directory containing the Makefile "
             "(default: directory of the binary, or '.')",
    )
    parser.add_argument(
        "--tests", default=None, metavar="FILE",
        help="Path to tests.txt (default: <tester_dir>/tests.txt)",
    )
    parser.add_argument(
        "--report", default=None, metavar="FILE",
        help="Write a JSON report to FILE after all tests",
    )
    parser.add_argument(
        "--timeout", type=int, default=DEFAULT_TIMEOUT, metavar="SECS",
        help=f"Per-test timeout in seconds (default: {DEFAULT_TIMEOUT})",
    )
    parser.add_argument(
        "--tolerance", type=int, default=DEFAULT_TOLERANCE, metavar="MS",
        help=f"Acceptable timing error in ms (default: {DEFAULT_TOLERANCE})",
    )
    opts = parser.parse_args()

    # Resolve repo path
    if opts.repo is None:
        binary_dir = os.path.dirname(os.path.abspath(opts.binary))
        opts.repo  = binary_dir if binary_dir else "."

    # Resolve tests file (default: <tester_root>/tests.txt)
    if opts.tests is None:
        tester_dir = _SRC.parent
        opts.tests = str(tester_dir / "tests.txt")

    # Build step
    print_section("Step 0: Build")
    mk_found = any(
        (Path(opts.repo) / n).exists() for n in ("Makefile", "makefile")
    )
    if mk_found:
        print(f"Running make in {opts.repo} …")
        r = subprocess.run(["make", "-C", opts.repo])
        if r.returncode == 0:
            print_pass("make succeeded")
        else:
            print_fail("make failed — subsequent tests may not be meaningful")
    else:
        print(f"{YELLOW}No Makefile found in {opts.repo} — skipping build step{RESET}")

    if not os.access(opts.binary, os.X_OK):
        print(f"{RED}Binary '{opts.binary}' not found or not executable.{RESET}")
        sys.exit(1)

    # Load and run all tests
    tests = load_tests(opts.tests)
    runner = Runner(opts.binary, opts.repo, opts.timeout, opts.tolerance)
    runner.run_all(tests)

    # Print summary
    print_summary(runner.results)

    # Optional JSON report
    if opts.report:
        data = {
            "summary": {
                "pass":  sum(1 for r in runner.results if r.status == "PASS"),
                "fail":  sum(1 for r in runner.results if r.status == "FAIL"),
                "skip":  sum(1 for r in runner.results if r.status == "SKIP"),
                "total": len(runner.results),
            },
            "tests": [
                {
                    "label":  r.label,
                    "status": r.status,
                    "input":  r.input_args,
                    "detail": r.detail,
                }
                for r in runner.results
            ],
        }
        with open(opts.report, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
        print(f"\nReport written to: {opts.report}")

    sys.exit(0 if sum(1 for r in runner.results if r.status == "FAIL") == 0 else 1)


if __name__ == "__main__":
    main()
