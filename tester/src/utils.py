"""utils.py — Shared helpers for the Codexion tester."""

import subprocess
import sys
from dataclasses import dataclass
from typing import List, Tuple

# ── Type alias ────────────────────────────────────────────────────────────────
# (timestamp_ms, coder_id, state)
LogEntry = Tuple[int, int, str]

# ── ANSI colours (auto-disabled when not a TTY) ───────────────────────────────
def _c(code: str) -> str:
    return code if sys.stdout.isatty() else ""

RED    = _c('\033[0;31m')
GREEN  = _c('\033[0;32m')
YELLOW = _c('\033[1;33m')
CYAN   = _c('\033[0;36m')
BOLD   = _c('\033[1m')
RESET  = _c('\033[0m')


# ── Result dataclass ──────────────────────────────────────────────────────────
@dataclass
class TestResult:
    label:      str
    status:     str   # "PASS" | "FAIL" | "SKIP"
    input_args: str = ""
    detail:     str = ""


# ── Printing helpers ──────────────────────────────────────────────────────────
def print_pass(label: str) -> None:
    print(f"{GREEN}✅ PASS{RESET} — {label}")


def print_fail(label: str, detail: str = "") -> None:
    suffix = f" ({detail})" if detail else ""
    print(f"{RED}❌ FAIL{RESET} — {label}{suffix}")


def print_skip(label: str, reason: str = "") -> None:
    suffix = f" ({reason})" if reason else ""
    print(f"{YELLOW}⏭  SKIP{RESET} — {label}{suffix}")


def print_section(title: str) -> None:
    print(f"\n{CYAN}{BOLD}═══ {title} ═══{RESET}")


# ── Binary runner with timeout ────────────────────────────────────────────────
def run_binary(binary: str, args: List[str], timeout: int) -> Tuple[int, str]:
    """Run *binary* with *args* subject to *timeout* seconds.

    Returns ``(exit_code, combined_stdout_stderr)``.
    ``exit_code == 124`` means the process was killed by the timeout.
    """
    cmd = [binary] + args
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout + r.stderr
    except subprocess.TimeoutExpired:
        return 124, ""


# ── Final summary printer ─────────────────────────────────────────────────────
def print_summary(results: List[TestResult]) -> None:
    pass_n = sum(1 for r in results if r.status == "PASS")
    fail_n = sum(1 for r in results if r.status == "FAIL")
    skip_n = sum(1 for r in results if r.status == "SKIP")
    total  = pass_n + fail_n + skip_n
    bar    = "═" * 45
    print(f"\n{BOLD}{bar}{RESET}")
    print(f"{BOLD}  RESULTS: {pass_n}/{total} tests passed{RESET}")
    if skip_n:
        print(f"  {YELLOW}Skipped: {skip_n}{RESET}")
    if fail_n:
        print(f"  {RED}Failed:  {fail_n}{RESET}")
        print(f"{BOLD}{bar}{RESET}")
        print(f"\n{BOLD}{RED}Failed tests (with input):{RESET}")
        for r in results:
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
