#!/usr/bin/env bash
# =============================================================================
# tester.sh — Comprehensive tester for the "Codexion" (42 school) project
#
# Usage: ./tester.sh [path/to/codexion_binary]
#   Default binary path: ./codexion
#
# Argument order for the binary:
#   number_of_coders  time_to_burnout  time_to_compile  time_to_debug
#   time_to_refactor  number_of_compiles_required  dongle_cooldown  scheduler
# =============================================================================

set -uo pipefail
# Note: -e (errexit) is intentionally omitted so individual test helpers can
# capture non-zero exit codes from the binary without aborting the script.

# ---------------------------------------------------------------------------
# Configurable paths
# ---------------------------------------------------------------------------
BINARY="${1:-./codexion}"
MAKE_DIR="."          # directory that contains the Makefile
TIMEOUT_SEC=15        # per-test timeout (seconds)
TIMING_TOLERANCE=15   # acceptable timing error in ms

# ---------------------------------------------------------------------------
# Colours
# ---------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

# ---------------------------------------------------------------------------
# Counters
# ---------------------------------------------------------------------------
PASS=0
FAIL=0
SKIP=0

# ---------------------------------------------------------------------------
# Failed-test tracking
# _FAIL_ARGS holds the binary arguments for the current test; set it before
# calling run_binary / assert_* so that fail() can record it automatically.
# It is consumed (reset to "") by fail() after each use.
# ---------------------------------------------------------------------------
declare -a FAILED_TESTS=()
_FAIL_ARGS=""

# ---------------------------------------------------------------------------
# Helper: print pass / fail
# ---------------------------------------------------------------------------
pass() { echo -e "${GREEN}✅ PASS${RESET} — $1"; PASS=$((PASS + 1)); }
fail() {
    echo -e "${RED}❌ FAIL${RESET} — $1"
    FAIL=$((FAIL + 1))
    if [[ -n "${_FAIL_ARGS}" ]]; then
        FAILED_TESTS+=("$1 | input: ${_FAIL_ARGS}")
    else
        FAILED_TESTS+=("$1")
    fi
    _FAIL_ARGS=""
}
skip() { echo -e "${YELLOW}⏭  SKIP${RESET} — $1"; SKIP=$((SKIP + 1)); }
section() { echo -e "\n${CYAN}${BOLD}═══ $1 ═══${RESET}"; }

# ---------------------------------------------------------------------------
# Helper: run binary with timeout, capture stdout+stderr into <outfile>
# Always succeeds from the script's perspective (exit code swallowed).
# ---------------------------------------------------------------------------
run_binary() {
    # run_binary <outfile> <args...>
    local outfile="$1"; shift
    local _rc=0
    timeout "${TIMEOUT_SEC}s" "${BINARY}" "$@" >"${outfile}" 2>&1 || _rc=$?
    return 0
}

# ---------------------------------------------------------------------------
# Helper: assert the binary exits with a non-zero code
# ---------------------------------------------------------------------------
assert_exits_non_zero() {
    local label="$1"; shift
    local args_str="$*"
    local outfile rc=0
    outfile="$(mktemp /tmp/codexion_test_XXXXXX)"
    timeout "${TIMEOUT_SEC}s" "${BINARY}" "$@" >"${outfile}" 2>&1 || rc=$?
    rm -f "${outfile}"
    if [[ ${rc} -ne 0 ]]; then
        pass "${label}"
    else
        _FAIL_ARGS="${args_str}"
        fail "${label} (expected non-zero exit, got 0)"
    fi
}

# ---------------------------------------------------------------------------
# Helper: assert the binary exits with code 0
# ---------------------------------------------------------------------------
assert_exits_zero() {
    local label="$1"; shift
    local args_str="$*"
    local outfile rc=0
    outfile="$(mktemp /tmp/codexion_test_XXXXXX)"
    timeout "${TIMEOUT_SEC}s" "${BINARY}" "$@" >"${outfile}" 2>&1 || rc=$?
    rm -f "${outfile}"
    if [[ ${rc} -eq 0 ]]; then
        pass "${label}"
    else
        _FAIL_ARGS="${args_str}"
        fail "${label} (expected exit 0, got ${rc})"
    fi
}

# ---------------------------------------------------------------------------
# Helper: parse a single log line into ts / id / state
# Sets variables TS, CODER_ID, STATE in the caller's scope.
# ---------------------------------------------------------------------------
parse_log_line() {
    local line="$1"
    TS="${line%% *}"
    local rest="${line#* }"
    CODER_ID="${rest%% *}"
    STATE="${rest#* }"
}

# ---------------------------------------------------------------------------
# Helper: verify log format
# Returns 0 if all lines match; 1 otherwise.
# ---------------------------------------------------------------------------
validate_log_format() {
    local logfile="$1"
    local pattern='^[0-9]+ [0-9]+ (has taken a dongle|is compiling|is debugging|is refactoring|burned out)$'
    local bad
    bad=$(grep -vP "${pattern}" "${logfile}" 2>/dev/null || true)
    if [[ -n "${bad}" ]]; then
        echo "INVALID lines:" >&2
        echo "${bad}" >&2
        return 1
    fi
    return 0
}

# ---------------------------------------------------------------------------
# Helper: verify timestamps are non-decreasing
# ---------------------------------------------------------------------------
check_timestamps_monotonic() {
    local logfile="$1"
    local prev=0
    local ts
    while IFS= read -r line; do
        ts="${line%% *}"
        if [[ "${ts}" =~ ^[0-9]+$ ]]; then
            if [[ "${ts}" -lt "${prev}" ]]; then
                echo "Timestamp went backwards: ${prev} -> ${ts}" >&2
                return 1
            fi
            prev="${ts}"
        fi
    done < "${logfile}"
    return 0
}

# ---------------------------------------------------------------------------
# Helper: verify each "is compiling" is preceded by exactly 2
#         "has taken a dongle" for the same coder (since last compile/start)
# ---------------------------------------------------------------------------
check_dongle_before_compile() {
    local logfile="$1"
    declare -A dongle_count=()
    local ts coder_id state cnt

    while IFS= read -r line; do
        parse_log_line "${line}"
        coder_id="${CODER_ID}"
        state="${STATE}"

        case "${state}" in
            "has taken a dongle")
                dongle_count["${coder_id}"]=$(( ${dongle_count["${coder_id}"]:-0} + 1 ))
                ;;
            "is compiling")
                cnt=${dongle_count["${coder_id}"]:-0}
                if [[ "${cnt}" -ne 2 ]]; then
                    echo "Coder ${coder_id} compiled with ${cnt} dongle(s) (expected 2)" >&2
                    return 1
                fi
                dongle_count["${coder_id}"]=0
                ;;
        esac
    done < "${logfile}"
    return 0
}

# =============================================================================
# Step 0: Build the project
# =============================================================================
section "Step 0: Build"
if [[ -f "${MAKE_DIR}/Makefile" ]] || [[ -f "${MAKE_DIR}/makefile" ]]; then
    echo "Running make in ${MAKE_DIR} …"
    if make -C "${MAKE_DIR}" 2>&1; then
        pass "make succeeded"
    else
        fail "make failed — subsequent tests may not be meaningful"
    fi
else
    echo -e "${YELLOW}No Makefile found in ${MAKE_DIR} — skipping build step${RESET}"
fi

# Check the binary exists and is executable
if [[ ! -x "${BINARY}" ]]; then
    echo -e "${RED}Binary '${BINARY}' not found or not executable.${RESET}"
    echo "Usage: $0 [path/to/codexion_binary]"
    exit 1
fi

# =============================================================================
# Test Category 1: Invalid arguments
# =============================================================================
section "Category 1: Invalid arguments"

# Too few arguments (< 8)
assert_exits_non_zero "Too few args (0 args)"
assert_exits_non_zero "Too few args (3 args)" 3 800 200
assert_exits_non_zero "Too few args (7 args)" 4 800 200 100 50 3 0

# Negative / zero values
assert_exits_non_zero "Negative number_of_coders"    -1 800 200 100 50 3 0 fifo
assert_exits_non_zero "Negative time_to_burnout"     2 -1 200 100 50 3 0 fifo
assert_exits_non_zero "Negative time_to_compile"     2 800 -1 100 50 3 0 fifo
assert_exits_non_zero "Negative time_to_debug"       2 800 200 -1 50 3 0 fifo
assert_exits_non_zero "Negative time_to_refactor"    2 800 200 100 -1 3 0 fifo
assert_exits_non_zero "Negative number_of_compiles"  2 800 200 100 50 -1 0 fifo
assert_exits_non_zero "Negative dongle_cooldown"     2 800 200 100 50 3 -1 fifo
assert_exits_non_zero "Zero number_of_coders"        0 800 200 100 50 3 0 fifo

# Invalid scheduler string
assert_exits_non_zero "Invalid scheduler 'round_robin'" 4 800 200 100 50 3 0 round_robin
assert_exits_non_zero "Invalid scheduler 'FIFO' (case)" 4 800 200 100 50 3 0 FIFO
assert_exits_non_zero "Invalid scheduler 'random'"      4 800 200 100 50 3 0 random

# Non-integer arguments
assert_exits_non_zero "Non-integer coders 'abc'"    abc 800 200 100 50 3 0 fifo
assert_exits_non_zero "Non-integer burnout '1.5'"   2 1.5 200 100 50 3 0 fifo
assert_exits_non_zero "Non-integer compile 'two'"   2 800 two 100 50 3 0 fifo

# =============================================================================
# Test Category 2: Single coder
# =============================================================================
section "Category 2: Single coder"

# 1 coder needs 2 dongles but there is only 1 dongle → cannot compile → burns out
TMP_LOG="$(mktemp /tmp/codexion_test_XXXXXX)"
_FAIL_ARGS="1 400 200 100 50 3 0 fifo"
run_binary "${TMP_LOG}" 1 400 200 100 50 3 0 fifo
if grep -q "burned out" "${TMP_LOG}"; then
    pass "1 coder burns out (only 1 dongle available, needs 2)"
else
    fail "1 coder did NOT burn out — expected burnout (1 dongle, needs 2)"
fi
rm -f "${TMP_LOG}"

# =============================================================================
# Test Category 3: Basic cases without burnout
# =============================================================================
section "Category 3: Basic cases without burnout"

# ---------- 2 coders, fifo ----------
TMP_LOG="$(mktemp /tmp/codexion_test_XXXXXX)"
_FAIL_ARGS="2 2000 200 100 50 2 0 fifo"
run_binary "${TMP_LOG}" 2 2000 200 100 50 2 0 fifo

if ! grep -q "burned out" "${TMP_LOG}"; then
    pass "2 coders fifo: no burnout"
else
    fail "2 coders fifo: unexpected burnout"
fi

ALL_COMPILED=true
for id in 1 2; do
    cnt=$(grep -P "^[0-9]+ ${id} is compiling$" "${TMP_LOG}" 2>/dev/null | wc -l)
    if [[ "${cnt}" -lt 2 ]]; then
        ALL_COMPILED=false
        break
    fi
done
if ${ALL_COMPILED}; then
    pass "2 coders fifo: all coders compiled >= 2 times"
else
    fail "2 coders fifo: not all coders compiled enough times"
fi
rm -f "${TMP_LOG}"

# ---------- 4 coders, edf ----------
TMP_LOG="$(mktemp /tmp/codexion_test_XXXXXX)"
_FAIL_ARGS="4 2000 200 100 50 2 0 edf"
run_binary "${TMP_LOG}" 4 2000 200 100 50 2 0 edf

if ! grep -q "burned out" "${TMP_LOG}"; then
    pass "4 coders edf: no burnout"
else
    fail "4 coders edf: unexpected burnout"
fi

ALL_COMPILED=true
for id in 1 2 3 4; do
    cnt=$(grep -P "^[0-9]+ ${id} is compiling$" "${TMP_LOG}" 2>/dev/null | wc -l)
    if [[ "${cnt}" -lt 2 ]]; then
        ALL_COMPILED=false
        break
    fi
done
if ${ALL_COMPILED}; then
    pass "4 coders edf: all coders compiled >= 2 times"
else
    fail "4 coders edf: not all coders compiled enough times"
fi
rm -f "${TMP_LOG}"

# =============================================================================
# Test Category 4: Expected burnout
# =============================================================================
section "Category 4: Expected burnout"

# time_to_burnout=150 ms, time_to_compile=300 ms → coder starves while waiting
TMP_LOG="$(mktemp /tmp/codexion_test_XXXXXX)"
_FAIL_ARGS="4 150 300 150 100 5 0 fifo"
run_binary "${TMP_LOG}" 4 150 300 150 100 5 0 fifo

if grep -q "burned out" "${TMP_LOG}"; then
    pass "Expected burnout occurs (burnout=150 ms, compile=300 ms)"
else
    fail "Expected burnout did NOT occur (burnout=150 ms, compile=300 ms)"
fi
rm -f "${TMP_LOG}"

# =============================================================================
# Test Category 5: Log format verification
# =============================================================================
section "Category 5: Log format verification"

TMP_LOG="$(mktemp /tmp/codexion_test_XXXXXX)"
_FAIL_ARGS="3 2000 300 150 100 2 0 fifo"
run_binary "${TMP_LOG}" 3 2000 300 150 100 2 0 fifo
if validate_log_format "${TMP_LOG}"; then
    pass "Log format: all lines match expected pattern"
else
    fail "Log format: some lines have an invalid format"
fi

# 5b — Timestamps monotonic
if check_timestamps_monotonic "${TMP_LOG}"; then
    pass "Log format: timestamps are non-decreasing"
else
    fail "Log format: timestamps are NOT monotonic"
fi

# 5c — Exactly 2 dongles taken before each compile
if check_dongle_before_compile "${TMP_LOG}"; then
    pass "Log format: every 'is compiling' preceded by exactly 2 'has taken a dongle'"
else
    fail "Log format: dongle-count before compile is not exactly 2"
fi

# 5d — No mixed/garbage lines (same regex, different error message)
BAD_LINES=$(grep -vP '^[0-9]+ [0-9]+ (has taken a dongle|is compiling|is debugging|is refactoring|burned out)$' \
    "${TMP_LOG}" 2>/dev/null | wc -l)
if [[ "${BAD_LINES}" -eq 0 ]]; then
    pass "Log format: no mixed or garbage lines"
else
    fail "Log format: ${BAD_LINES} mixed/garbage line(s) detected"
fi

rm -f "${TMP_LOG}"

# =============================================================================
# Test Category 6: Burnout timing precision (±TIMING_TOLERANCE ms)
# =============================================================================
section "Category 6: Burnout timing precision (±${TIMING_TOLERANCE} ms)"

BURNOUT_MS=400
TMP_LOG="$(mktemp /tmp/codexion_test_XXXXXX)"
_FAIL_ARGS="1 ${BURNOUT_MS} 200 100 50 3 0 fifo"
run_binary "${TMP_LOG}" 1 "${BURNOUT_MS}" 200 100 50 3 0 fifo

if grep -q "burned out" "${TMP_LOG}"; then
    # Timestamps are relative to program start; first log line gives us t=0.
    BURNOUT_LOG_TS=$(grep "burned out" "${TMP_LOG}" | tail -1 | awk '{print $1}')
    FIRST_TS=$(head -1 "${TMP_LOG}" | awk '{print $1}')
    if [[ -n "${BURNOUT_LOG_TS}" ]] && [[ -n "${FIRST_TS}" ]]; then
        ACTUAL_DELTA=$(( BURNOUT_LOG_TS - FIRST_TS ))
        DIFF=$(( ACTUAL_DELTA - BURNOUT_MS ))
        ABS_DIFF=${DIFF#-}   # absolute value (POSIX parameter expansion)
        if [[ "${ABS_DIFF}" -le "${TIMING_TOLERANCE}" ]]; then
            pass "Burnout precision: delta=${ACTUAL_DELTA} ms, expected=${BURNOUT_MS} ms (diff=${ABS_DIFF} ms ≤ ${TIMING_TOLERANCE} ms)"
        else
            fail "Burnout precision: delta=${ACTUAL_DELTA} ms, expected=${BURNOUT_MS} ms (diff=${ABS_DIFF} ms > ${TIMING_TOLERANCE} ms)"
        fi
    else
        fail "Burnout precision: could not parse timestamps from log"
    fi
else
    fail "Burnout precision: no 'burned out' in log — cannot measure precision"
fi
rm -f "${TMP_LOG}"

# =============================================================================
# Test Category 7: Dongle cooldown
# =============================================================================
COOLDOWN_MS=200
section "Category 7: Dongle cooldown (cooldown=${COOLDOWN_MS} ms)"
TMP_LOG="$(mktemp /tmp/codexion_test_XXXXXX)"
_FAIL_ARGS="2 5000 300 150 100 3 ${COOLDOWN_MS} fifo"
# Generous burnout ensures we collect multiple compile cycles per coder.
run_binary "${TMP_LOG}" 2 5000 300 150 100 3 "${COOLDOWN_MS}" fifo

# Strategy: after each "is compiling" event for coder X, the coder releases
# its dongles.  A dongle must remain unavailable for COOLDOWN_MS.  Since the
# log doesn't carry dongle IDs, we use a conservative lower bound:
# the earliest a coder can take a NEW dongle again is COOLDOWN_MS after
# compile start (when debug+refactor = 0).  We flag gaps shorter than
# COOLDOWN_MS - TIMING_TOLERANCE as violations.
COOLDOWN_VIOLATION=false
declare -A last_compile_ts=()

while IFS= read -r line; do
    parse_log_line "${line}"
    coder_id="${CODER_ID}"
    state="${STATE}"

    case "${state}" in
        "is compiling")
            last_compile_ts["${coder_id}"]="${TS}"
            ;;
        "has taken a dongle")
            if [[ -n "${last_compile_ts["${coder_id}"]:-}" ]]; then
                GAP=$(( TS - last_compile_ts["${coder_id}"] ))
                THRESHOLD=$(( COOLDOWN_MS - TIMING_TOLERANCE ))
                if [[ "${GAP}" -lt "${THRESHOLD}" ]]; then
                    echo "  Cooldown violation: coder ${coder_id} took dongle at ${TS} ms,"\
                         "last compiled at ${last_compile_ts["${coder_id}"]} ms"\
                         "(gap=${GAP} ms < threshold=${THRESHOLD} ms)" >&2
                    COOLDOWN_VIOLATION=true
                fi
            fi
            ;;
    esac
done < "${TMP_LOG}"

if ! ${COOLDOWN_VIOLATION}; then
    pass "Dongle cooldown: no premature re-acquisition detected (cooldown=${COOLDOWN_MS} ms, tolerance=${TIMING_TOLERANCE} ms)"
else
    fail "Dongle cooldown: premature dongle re-acquisition detected"
fi
rm -f "${TMP_LOG}"

# =============================================================================
# Test Category 8: fifo vs edf — both schedulers complete correctly
# =============================================================================
section "Category 8: fifo vs edf schedulers"

for SCHED in fifo edf; do
    TMP_LOG="$(mktemp /tmp/codexion_test_XXXXXX)"
    _FAIL_ARGS="3 2000 300 150 100 2 0 ${SCHED}"
    run_binary "${TMP_LOG}" 3 2000 300 150 100 2 0 "${SCHED}"

    if [[ -s "${TMP_LOG}" ]]; then
        pass "Scheduler ${SCHED}: binary produced output"
    else
        fail "Scheduler ${SCHED}: no output produced"
    fi

    if validate_log_format "${TMP_LOG}"; then
        pass "Scheduler ${SCHED}: log format is valid"
    else
        fail "Scheduler ${SCHED}: log format is invalid"
    fi

    # Verify the run finishes before the timeout (timeout exits with 124).
    local_rc=0
    timeout "${TIMEOUT_SEC}s" "${BINARY}" 3 2000 300 150 100 2 0 "${SCHED}" \
        >/dev/null 2>&1 || local_rc=$?
    if [[ ${local_rc} -ne 124 ]]; then
        pass "Scheduler ${SCHED}: simulation finishes within ${TIMEOUT_SEC}s"
    else
        fail "Scheduler ${SCHED}: simulation timed out after ${TIMEOUT_SEC}s"
    fi

    rm -f "${TMP_LOG}"
done

# =============================================================================
# Test Category 9: Memory leaks with valgrind (optional)
# =============================================================================
section "Category 9: Memory leaks (valgrind)"

if command -v valgrind >/dev/null 2>&1; then
    TMP_LOG="$(mktemp /tmp/codexion_test_XXXXXX)"
    TMP_VALGRIND="$(mktemp /tmp/codexion_valgrind_XXXXXX)"

    timeout "${TIMEOUT_SEC}s" valgrind \
        --leak-check=full \
        --error-exitcode=42 \
        --log-file="${TMP_VALGRIND}" \
        "${BINARY}" 2 1500 300 150 100 2 0 fifo \
        >"${TMP_LOG}" 2>&1 || true

    if grep -q "ERROR SUMMARY: 0 errors" "${TMP_VALGRIND}"; then
        pass "Valgrind: no memory errors"
    else
        fail "Valgrind: memory errors detected — see ${TMP_VALGRIND} for details"
        TMP_VALGRIND=""  # keep for inspection
    fi
    rm -f "${TMP_LOG}" ${TMP_VALGRIND:+"${TMP_VALGRIND}"}

    TMP_VALGRIND2="$(mktemp /tmp/codexion_valgrind_XXXXXX)"
    timeout "${TIMEOUT_SEC}s" valgrind \
        --leak-check=full \
        --error-exitcode=42 \
        --log-file="${TMP_VALGRIND2}" \
        "${BINARY}" 2 1500 300 150 100 2 0 fifo \
        >/dev/null 2>&1 || true

    if grep -q "definitely lost: 0 bytes" "${TMP_VALGRIND2}" && \
       grep -q "indirectly lost: 0 bytes" "${TMP_VALGRIND2}"; then
        pass "Valgrind: no heap leaks (definitely/indirectly lost = 0)"
    else
        fail "Valgrind: heap leaks detected — see ${TMP_VALGRIND2} for details"
        TMP_VALGRIND2=""
    fi
    rm -f ${TMP_VALGRIND2:+"${TMP_VALGRIND2}"}
else
    skip "Valgrind not installed — memory error test skipped"
    skip "Valgrind not installed — memory leak test skipped"
fi

# =============================================================================
# Test Category 10: Stop condition — all coders reach compile goal
# =============================================================================
section "Category 10: Stop condition (number_of_compiles_required)"

REQUIRED_COMPILES=3
TMP_LOG="$(mktemp /tmp/codexion_test_XXXXXX)"
_FAIL_ARGS="2 5000 200 100 50 ${REQUIRED_COMPILES} 0 fifo"
run_binary "${TMP_LOG}" 2 5000 200 100 50 "${REQUIRED_COMPILES}" 0 fifo

# 10a — No burnout expected (generous timings)
if ! grep -q "burned out" "${TMP_LOG}"; then
    pass "Stop condition: simulation stopped without burnout"
else
    fail "Stop condition: unexpected burnout with generous timings"
fi

# 10b — Every coder must have compiled at least REQUIRED_COMPILES times
ALL_MET=true
for id in 1 2; do
    cnt=$(grep -P "^[0-9]+ ${id} is compiling$" "${TMP_LOG}" 2>/dev/null | wc -l)
    if [[ "${cnt}" -lt "${REQUIRED_COMPILES}" ]]; then
        ALL_MET=false
        echo "  Coder ${id} compiled ${cnt}/${REQUIRED_COMPILES} times" >&2
    fi
done
if ${ALL_MET}; then
    pass "Stop condition: all coders compiled >= ${REQUIRED_COMPILES} times"
else
    fail "Stop condition: some coders did not reach ${REQUIRED_COMPILES} compiles"
fi

# 10c — Simulation must not overshoot by much (stop condition sanity check).
# Allow at most REQUIRED + 1 extra per coder (due to in-flight threads when
# stop is signalled).
MAX_EXPECTED=$(( REQUIRED_COMPILES + 1 ))
OVERFLOW=false
for id in 1 2; do
    cnt=$(grep -P "^[0-9]+ ${id} is compiling$" "${TMP_LOG}" 2>/dev/null | wc -l)
    if [[ "${cnt}" -gt "${MAX_EXPECTED}" ]]; then
        OVERFLOW=true
        echo "  Coder ${id} compiled ${cnt} times (max expected ~${MAX_EXPECTED})" >&2
    fi
done
if ! ${OVERFLOW}; then
    pass "Stop condition: simulation terminated promptly after goal was reached"
else
    fail "Stop condition: coders compiled far too many times (stop condition may be broken)"
fi

rm -f "${TMP_LOG}"

# =============================================================================
# Final summary
# =============================================================================
TOTAL=$((PASS + FAIL + SKIP))
echo ""
echo -e "${BOLD}═══════════════════════════════════════${RESET}"
echo -e "${BOLD}  RESULTS: ${PASS}/${TOTAL} tests passed${RESET}"
if [[ ${SKIP} -gt 0 ]]; then
    echo -e "  ${YELLOW}Skipped: ${SKIP}${RESET}"
fi
if [[ ${FAIL} -gt 0 ]]; then
    echo -e "  ${RED}Failed:  ${FAIL}${RESET}"
    echo -e "${BOLD}═══════════════════════════════════════${RESET}"
    echo ""
    echo -e "${BOLD}${RED}Failed tests (with input):${RESET}"
    for entry in "${FAILED_TESTS[@]}"; do
        echo -e "  ${RED}✗${RESET} ${entry}"
    done
    echo ""
    exit 1
fi
echo -e "${GREEN}  All tests passed! 🎉${RESET}"
echo -e "${BOLD}═══════════════════════════════════════${RESET}"
exit 0
