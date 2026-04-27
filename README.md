# README_TESTER.md — Codexion Project Tester

A **comprehensive bash test suite** for the *Codexion* project (42 school).  
The tester covers argument validation, burnout logic, log-format correctness,
timing precision, dongle cooldown, scheduler behaviour, memory leaks, and the
simulation stop-condition.

---

## Prerequisites

| Tool | Required | Notes |
|------|----------|-------|
| `bash` ≥ 4 | ✅ Yes | Associative arrays (`declare -A`) are used |
| `make` | ✅ Yes | Used to build the project automatically |
| `timeout` | ✅ Yes | Part of GNU coreutils (Linux / macOS via brew) |
| `grep -P` | ✅ Yes | Perl-compatible regex; available on most Linux distros |
| `valgrind` | ⬜ Optional | Only needed for the memory-leak test (Category 9) |

---

## Quick start

```bash
# 1. Clone the tester next to your codexion project
#    (or copy tester.sh into your project directory)

# 2. Make the script executable
chmod +x tester.sh

# 3. Run — assumes `make` is available and `./codexion` is the binary name
./tester.sh

# 4. Specify a custom path to the binary (optional)
./tester.sh /path/to/codexion
```

The script will:

1. Run `make` in the current directory to (re)build the project.  
2. Execute every test category in order.  
3. Print a **coloured summary** (`✅ PASS` / `❌ FAIL` / `⏭  SKIP`) for each test.  
4. Print a final score and exit with code **0** (all pass) or **1** (any fail).

---

## Binary interface

The tester assumes the binary accepts **exactly 8 positional arguments** in
this order:

```
./codexion  <number_of_coders>  <time_to_burnout>  <time_to_compile>
            <time_to_debug>     <time_to_refactor>
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

| # | Name | What is checked |
|---|------|-----------------|
| 1 | **Invalid arguments** | Too few args, negative values, zero coders, bad scheduler string, non-integer values → binary must exit non-zero |
| 2 | **Single coder** | 1 coder + 1 dongle → can never acquire 2 dongles → must burn out |
| 3 | **Basic: no burnout** | 2 coders (fifo) and 4 coders (edf) with generous timings → no burnout, all coders complete their compile goal |
| 4 | **Expected burnout** | `time_to_burnout < time_to_compile` → at least one "burned out" must appear |
| 5 | **Log format** | Every line matches the pattern; timestamps are non-decreasing; each `is compiling` is preceded by exactly 2 `has taken a dongle` for the same coder; no mixed/garbage lines |
| 6 | **Burnout precision** | Log timestamp of "burned out" is within ±15 ms of `time_to_burnout` ms after the first log line |
| 7 | **Dongle cooldown** | Verifies a coder does not re-acquire a dongle sooner than `dongle_cooldown` ms after its last compile |
| 8 | **fifo vs edf** | Both schedulers produce valid output and finish within the timeout |
| 9 | **Memory leaks (valgrind)** | No memory errors and no heap leaks (skipped if valgrind is absent) |
| 10 | **Stop condition** | With `number_of_compiles_required=3`, simulation stops after all coders reach the goal without over-running |

---

## Configuration

Edit the variables at the top of `tester.sh` to adjust defaults:

```bash
BINARY="${1:-./codexion}"   # path to the binary (or pass as first argument)
MAKE_DIR="."                # directory containing the Makefile
TIMEOUT_SEC=15              # per-test timeout in seconds
TIMING_TOLERANCE=15         # acceptable timing error in ms (categories 6 & 7)
```

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

═══════════════════════════════════════
  RESULTS: 42/42 tests passed
  All tests passed! 🎉
═══════════════════════════════════════
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `Binary './codexion' not found` | Build failed or wrong path | Run `make` manually; pass the correct path as `./tester.sh path/to/binary` |
| Many FAIL on timing tests | Machine under heavy load | Increase `TIMING_TOLERANCE` in the script |
| `grep: invalid option -- 'P'` | macOS default grep | Install GNU grep: `brew install grep` and ensure it is first in `PATH` |
| Valgrind tests skipped | valgrind not installed | `apt install valgrind` (Debian/Ubuntu) or `brew install valgrind` |

---

## License

This tester is provided as-is for educational purposes within the 42 school
network. No warranty is expressed or implied.
