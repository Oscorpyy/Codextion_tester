#!/usr/bin/env bash
# =============================================================================
# tester/tester.sh — Main entry point for the Codexion modular tester
#
# Usage:
#   ./tester.sh [path/to/codexion_binary] [options]
#
#   All options after the binary path are forwarded verbatim to run_tests.py.
#
# Examples:
#   ./tester.sh
#   ./tester.sh /path/to/codexion
#   ./tester.sh /path/to/codexion --report results.json
#   ./tester.sh /path/to/codexion --timeout 20 --tolerance 25
#   ./tester.sh /path/to/codexion --repo /path/to/codexion_repo
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ---------------------------------------------------------------------------
# Pick up the binary argument (first positional arg, if present).
# Remaining arguments are forwarded to run_tests.py.
# ---------------------------------------------------------------------------
BINARY="${1:-./codexion}"
if [[ $# -gt 0 ]]; then
    shift
fi

# ---------------------------------------------------------------------------
# Locate the Python runner
# ---------------------------------------------------------------------------
RUNNER="${SCRIPT_DIR}/src/run_tests.py"
if [[ ! -f "${RUNNER}" ]]; then
    echo "Error: '${RUNNER}' not found." >&2
    echo "Run 'make' inside the tester/ directory first." >&2
    exit 1
fi

exec python3 "${RUNNER}" "${BINARY}" "$@"
