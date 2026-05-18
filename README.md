# README_TESTER.md — Codexion Project Tester

A **comprehensive test suite** for the *Codexion* project (42 school).

The tester covers argument validation, burnout logic, log-format correctness,
timing precision, dongle cooldown, scheduler behaviour, memory leaks, Makefile
compliance, and the simulation stop-condition.

## Prerequisites

| Tool | Required | Notes |
|------|----------|-------|
| Python ≥ 3.8 | ✅ Yes | |
| `make` | ✅ Yes | Used to build the project automatically |
| `valgrind` | ⬜ Optional | For memory-leak tests and data races |

## Quick start

### Global Installation (Recommended)

You can install the tester wrappers to use them globally from anywhere.

```bash
cd /path/to/Codextion_tester
./install.sh

# If ~/.local/bin is not in your PATH, add it to your ~/.zshrc or ~/.bashrc:
# export PATH="$HOME/.local/bin:$PATH"
```

Once installed, you can use the available commands directly from your project folder (`codexion`):

* `checker` — Runs the full test suite (including Valgrind/Helgrind tests, timing tests and Makefile) with a dashboard summary.
* `check_valhell` — Runs memory and thread analysis directly.
* `codetest` — Runs the legacy python tester.

### Uninstallation

To completely remove the global wrappers and permanently delete the tester folder from your machine, run:

```bash
cd /path/to/Codextion_tester
./uninstall.sh
```

### Using Make 

U can also add to your `Makefile` the rule `make test` like this :
```Makefile
test: all
	@echo "$(COLOR_BLUE)Running tests with Python checker...$(COLOR_RESET)"
	@checker . --no-print-directory
```
This will automatically invoke the `checker` to natively run tests over your compilation output.

## Available Modules

- `checker.py`: The master script evaluating the full state machine of the project (argument bounds, dongle cooldown enforcement, strict phase timestamp compliance).
- `verif.py`: Focused entirely on checking Valgrind and Helgrind traces strictly to easily spot data-races and memory leaks.
- `tester.py`: Core tester handling the underlying base constraints and execution logic.

## Failed-test summary

The tester prints a clear minimal dashboard at the end showing exactly what features passed or failed:

```text
=== Dashboard de fin ===
✅ Compilation Makefile: OK
✅ Memory (Valgrind/Helgrind): OK
❌ Chronologie, Durées & Cooldown: FAILED
========================
```

It will specifically output pinpointed debug info on failing chronometric rules allowing you to easily read situations exactly (e.g. `❌ Cooldown non respecté : Coder 1 prend un dongle à 350ms au lieu d'attendre 450ms`).

## License

This tester is provided as-is for educational purposes within the 42 school network. No warranty is expressed or implied.
