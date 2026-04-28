# README_TESTER.md — Codexion Project Tester

A **comprehensive test suite** for the *Codexion* project (42 school), available
as a Python script (`tester.py`) or installable globally as `codetest`.

The tester covers argument validation, burnout logic, log-format correctness,
timing precision, dongle cooldown, scheduler behaviour, memory leaks, Makefile
compliance, and the simulation stop-condition.

---

## Prerequisites

### Python tester (`tester.py`)

| Tool | Required | Notes |
|------|----------|-------|
| Python ≥ 3.8 | ✅ Yes | Uses `dataclasses`, `subprocess.run(capture_output=...)` |
| `make` | ✅ Yes | Used to build the project automatically |
| `valgrind` | ⬜ Optional | Only needed for the memory-leak test (Category 9) |

---

## Quick start

### Global Installation (Recommended)

You can install the tester to use it globally from anywhere as the `codetest` command.

```bash
# 1. Go to the tester directory
cd /path/to/Codextion_tester

# 2. Run the install script
./install.sh

# If ~/.local/bin is not in your PATH, add it to your ~/.zshrc or ~/.bashrc:
# export PATH="$HOME/.local/bin:$PATH"
```

Once installed, you can use the `codetest` command directly:

```bash
# Test the current directory (auto-detects Makefile and builds codexion)
codetest

# Test a specific project folder
codetest ~/42/codexion

# Test a specific compiled binary directly (skips the build step)
codetest ~/42/codexion/leodexion

```

### Manual Usage (without install)
```bash
# Test the current directory
python3 tester.py .

# Test a specific directory
python3 tester.py /path/to/codexion

# Test a specifically named binary inside a directory
python3 tester.py /path/to/codexion --name my_binary

# Build skipped: Test an already compiled binary directly
python3 tester.py /path/to/codexion/compiled_binary

```

Full option reference:

```
usage: tester.py [target] [--name BINARY] [--report FILE]
                 [--timeout SECS] [--tolerance MS]

  target          Path to the repo directory or directly to the binary (default: .)
  --name BINARY   Name of the binary to test if a directory is given (default: codexion)
  --report FILE   Write a JSON report to FILE after all tests
  --timeout SECS  Per-test timeout in seconds  (default: 15)
  --tolerance MS  Acceptable timing error in ms (default: 15)
```
            <number_of_compiles_required>  <dongle_cooldown>  <scheduler>
```

| Argument | Type | Description |
|---|---|---|
| `number_of_coders` | positive integer | How many coder threads to spawn |
| `time_to_burnout` | ms (positive integer) | Time without compiling before burnout |
| `time_to_compile` | ms (positive integer) | Duration of one compile phase |
| `time_to_debug` | ms (positive integer) | Duration of one debug phase |
| `time_to_refactor` | ms (positive integer) | Duration of one refactor phase |
| `number_of_compiles_required` | positive integer | Goal: each coder must compile this many times |
| `dongle_cooldown` | ms (≥ 0) | How long a dongle is unavailable after release |
| `scheduler` | `fifo` or `edf` | Thread scheduling policy |

### Expected log format

Every output line must match:

```
<timestamp_ms> <coder_id> <state>
```

Where `<state>` is one of:

* `has taken a dongle`
* `is compiling`
* `is debugging`
* `is refactoring`
* `burned out`

---

## Test categories

Both testers run the same core categories. `tester.py` adds categories **0** and **11**.

| # | Name | What is checked |
|---|------|-----------------|
| 0 | **Makefile** *(Python only)* | `all`/`clean`/`fclean`/`re` rules exist; binary name `codexion` is referenced; `-Wall -Wextra -Werror` flags present; no relink on a second `make` call |
| 1 | **Invalid arguments** | Too few args, negative values, zero coders, bad scheduler string, non-integer values → binary must exit non-zero |
| 2 | **Single coder** | 1 coder + 1 dongle → can never acquire 2 dongles → must burn out |
| 3 | **Basic: no burnout** | 2 coders (fifo) and 4 coders (edf) with generous timings → no burnout, all coders complete their compile goal |
| 4 | **Expected burnout** | `time_to_burnout < time_to_compile` → at least one "burned out" must appear |
| 5 | **Log format** | Every line matches the pattern; timestamps are non-decreasing; each `is compiling` is preceded by exactly 2 `has taken a dongle` for the same coder; no mixed/garbage lines |
| 6 | **Burnout precision** | Log timestamp of "burned out" is within ±tolerance ms of `time_to_burnout` ms after the first log line |
| 7 | **Dongle cooldown** | Verifies a coder does not re-acquire a dongle sooner than `dongle_cooldown` ms after its last compile |
| 8 | **fifo vs edf** | Both schedulers produce valid output and finish within the timeout |
| 9 | **Memory leaks (valgrind)** | No memory errors and no heap leaks (skipped if valgrind is absent) |
| 10 | **Stop condition** | With `number_of_compiles_required=3`, simulation stops after all coders reach the goal without over-running |
| 11 | **Phase timing** *(Python only)* | Compile / debug / refactor phase durations are within ±tolerance ms of the configured values |

---

## Failed-test summary

Both testers print a **"Failed tests (with input)"** section at the end of the
run listing every failing test together with the exact binary arguments that
were used, for easy reproduction:

```
Failed tests (with input):
  ✗ Dongle cooldown: premature dongle re-acquisition detected
    input : 2 5000 300 150 100 3 200 fifo
    detail: coder 1 took dongle at 350 ms, last compiled at 300 ms (gap=50 ms < threshold=185 ms)
```

---

## JSON report (Python tester only)

Pass `--report results.json` to save a machine-readable report:

```json
{
  "summary": { "pass": 48, "fail": 2, "skip": 2, "total": 52 },
  "tests": [
    { "label": "Too few args (0 args)", "status": "PASS", "input": "", "detail": "" },
    { "label": "Dongle cooldown: ...", "status": "FAIL",
      "input": "2 5000 300 150 100 3 200 fifo",
      "detail": "coder 1 took dongle at 350 ms ..." }
  ]
}
```

---

## Configuration

### Bash tester (`tester.sh`)

Edit the variables at the top of `tester.sh` to adjust defaults:

```bash
BINARY="${1:-./codexion}"   # path to the binary (or pass as first argument)
MAKE_DIR="."                # directory containing the Makefile
TIMEOUT_SEC=15              # per-test timeout in seconds
TIMING_TOLERANCE=15         # acceptable timing error in ms (categories 6 & 7)
```

### Python tester (`tester.py`)

All options are command-line flags; see `python3 tester.py --help`.

---

## Example output

```
═══ Step 0: Build ═══
Running make in . …
✅ PASS — make succeeded

═══ Category 1: Invalid arguments ═══
✅ PASS — Too few args (0 args)
✅ PASS — Too few args (3 args)
...

═══════════════════════════════════════════════
  RESULTS: 48/50 tests passed
  Failed:  2
═══════════════════════════════════════════════

Failed tests (with input):
  ✗ Burnout precision: delta=450 ms, expected=400 ms (diff=50 ms > 15 ms)
    input : 1 400 200 100 50 3 0 fifo
  ✗ Dongle cooldown: premature dongle re-acquisition detected
    input : 2 5000 300 150 100 3 200 fifo
    detail: coder 2 took dongle at 510 ms, last compiled at 500 ms (gap=10 ms < threshold=185 ms)
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `Binary './codexion' not found` | Build failed or wrong path | Run `make` manually; pass the correct path as `./tester.sh path/to/binary` (or `python3 tester.py path/to/binary`) |
| Many FAIL on timing tests | Machine under heavy load | Increase `TIMING_TOLERANCE` / `--tolerance` |
| `grep: invalid option -- 'P'` | macOS default grep (bash tester) | Install GNU grep: `brew install grep` and ensure it is first in `PATH` |
| Valgrind tests skipped | valgrind not installed | `apt install valgrind` (Debian/Ubuntu) or `brew install valgrind` |
| Category 0 skipped entirely | `--repo` points to wrong dir | Pass `--repo /path/to/your/codexion/repo` |

---

## License

This tester is provided as-is for educational purposes within the 42 school
network. No warranty is expressed or implied.
