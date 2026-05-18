import subprocess
import os
import sys
from typing import Any, IO


# ===== CONFIG =====
EXECUTABLE = "./codexion"

VAL_LOG = "log_val.txt"
HEL_LOG = "log_hel.txt"


def get_tests() -> list[list[str]]:
    tests = []
    current_dir = os.path.dirname(os.path.abspath(__file__))
    tests_file = os.path.join(current_dir, "tests.txt")

    if os.path.exists(tests_file):
        with open(tests_file, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split("|")
                if len(parts) >= 3:
                    args_str = parts[2].strip()
                    if args_str:
                        if "invalid_args" not in parts[0] and "makefile" not\
                                in parts[0]:
                            tests.append(args_str.split())

    if not tests:
        print("⚠️ tests.txt introuvable ou vide. Fallback sur tests de base.")
        tests = [
            ["5", "1800", "200", "200", "200", "5", "10", "edf"],
            ["4", "1000", "200", "100", "100", "5", "0", "fifo"],
        ]
    return tests


TESTS = get_tests()


# ===================
def run(
    cmd: list[str],
    stdout: int | IO[Any] | None = None,
    stderr: int | IO[Any] | None = None,
) -> bool:
    try:
        res = subprocess.run(cmd, stdout=stdout, stderr=stderr)
        return res.returncode == 0
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


# 🔨 Compilation
def compile_project() -> bool:
    print("🔨 Compiling...")
    res = run(["make", "--no-print-directory", "-s"],
              stdout=subprocess.DEVNULL)
    if res:
        print("✅ Compilation OK")
    else:
        print("❌ Compilation Failed")
    return res


# ⏱️ Vérification des durées strictes
def check_durations(args: list[str]) -> bool:
    print(f"\n⏱️ Checking Chronology, Durations & Cooldown for "
          f"{args[-1:]} mode")
    print(f"Running control test : ./codexion {' '.join(args)}")
    try:
        res = subprocess.run([EXECUTABLE] + args, capture_output=True,
                             text=True)
        lines = res.stdout.strip().split('\n')

        t_compile = 100
        t_debug = 100
        t_refactor = 100
        t_cd = 1000

        last_ts = -1
        chrono_ok = True

        coder_last: dict[int, tuple[int, str]] = {}
        last_release_ts = -1000

        ok = True

        for line in lines:
            if not line.strip():
                continue
            parts = line.split()
            if len(parts) >= 3:
                try:
                    ts = int(parts[0])
                    cid = int(parts[1])
                    state = " ".join(parts[2:])

                    if ts < last_ts:
                        if chrono_ok:
                            print(f"❌ Timestamp moving backwards from "
                                  f"{last_ts} à {ts} !")
                            chrono_ok = False
                        ok = False
                    last_ts = ts

                    if cid in coder_last:
                        lts, lstate = coder_last[cid]
                        needed = 0
                        if "is compiling" in lstate:
                            needed = t_compile
                        elif "is debugging" in lstate:
                            needed = t_debug
                        elif "is refactoring" in lstate:
                            needed = t_refactor

                        if ts - lts < needed and "burned out" not in state:
                            print(f"❌ Invalid duration : Coder {cid} starts"
                                  f"'{state}' at {ts}ms, but previous step "
                                  f"'{lstate}' ({lts}ms) required "
                                  f"{needed}ms (diff = {ts-lts})")
                            ok = False

                    if "has taken a dongle" in state:
                        if ts < last_release_ts + t_cd:
                            print(f"❌ Cooldown not respected : Coder "
                                  f"{cid} takes a dongle at {ts}ms, while the "
                                  f"last compilation finished at "
                                  f"{last_release_ts}ms and the cooldown ("
                                  f"{t_cd}ms) lasts until "
                                  f"{last_release_ts + t_cd}ms !")
                            ok = False

                    if "is debugging" in state:
                        last_release_ts = ts

                    coder_last[cid] = (ts, state)

                    if "burned out" in state:
                        break

                except ValueError:
                    pass
        if ok:
            print("✅ Timings (compile, debug, refactor) and Cooldowns "
                  "are perfectly respected!")
        return ok
    except Exception as e:
        print(f"❌ Error check durations: {e}")
        return False


# 🧠 Valgrind (uniquement les erreurs)
def valgrind_tests() -> None:
    print(f"\n🧠 Valgrind on {len(TESTS)} tests (std output ignored, logs in "
          f"{VAL_LOG})")
    with open(VAL_LOG, "w") as log:
        for args in TESTS:
            log.write(f"\n===== {' '.join(args)} =====\n")
            subprocess.run([
                "valgrind",
                "--leak-check=full",
                "--track-origins=yes",
                EXECUTABLE
            ] + args, stdout=subprocess.DEVNULL, stderr=log)


# 🧵 Helgrind (uniquement les erreurs)
def helgrind_tests() -> None:
    print(f"\n🧵 Helgrind on {len(TESTS)} tests (std output ignored, logs in "
          f"{HEL_LOG})")
    with open(HEL_LOG, "w") as log:
        for args in TESTS:
            log.write(f"\n===== {' '.join(args)} =====\n")
            subprocess.run([
                "valgrind",
                "--tool=helgrind",
                EXECUTABLE
            ] + args, stdout=subprocess.DEVNULL, stderr=log)


# 🔍 Analyse logs
def check_logs() -> bool:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    verif_script = os.path.join(current_dir, "verif.py")
    print("\n🔍 Valgrind / Helgrind Analysis")
    return run(["python3", verif_script, "."])


def basic_tests() -> bool:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    tester_script = os.path.join(current_dir, "tester.py")
    print("\n🚀 Base tests via tester.py")
    return run(["python3", tester_script, "."])


# ===== MAIN =====
def main() -> None:
    print("=== CHECKER ===")
    results = {}

    results["Compilation"] = compile_project()
    results["Chronology, Durations & Cooldown for edf"] = check_durations(
        ["2", "5000", "100", "100", "100", "10", "1000", "edf"])
    results["Chronology, Durations & Cooldown for fifo"] = check_durations(
        ["2", "5000", "100", "100", "100", "10", "1000", "fifo"])
    results["Base tests"] = basic_tests()

    valgrind_tests()
    helgrind_tests()

    results["Memory/Thread Tests"] = check_logs()

    print("\n" + "="*30)
    print("         CHECKER DASHBOARD")
    print("="*30)
    all_ok = True
    for name, success in results.items():
        status_icon = "✅ (OK)" if success else "❌ (FAIL)"
        print(f"{status_icon} : {name}")
        if not success:
            all_ok = False

    print("="*30)

    if all_ok:
        print("🎉 All done and everything is perfect! Congratulations! 🎉\n")
        sys.exit(0)
    else:
        print("⚠️ There are errors to fix, check the logs above. ⚠️\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
