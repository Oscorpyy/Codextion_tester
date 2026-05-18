import re
import sys
import os


def analyse_valgrind(file_path):
    errors = 0
    leaks = 0
    others = 0

    with open(file_path, "r") as f:
        for line in f:
            if "ERROR SUMMARY" in line:
                match = re.search(r'(\d+)\s+errors', line)
                if match:
                    errors += int(match.group(1))

            if ("definitely lost" in line or
                "indirectly lost" in line or
                "possibly lost" in line):
                leaks += 1

            if ("invalid read" in line.lower() or
                "invalid write" in line.lower() or
                "uninitialised" in line.lower()):
                others += 1

    return errors, leaks, others


def analyse_helgrind(file_path):
    errors = 0
    others = 0

    with open(file_path, "r") as f:
        for line in f:
            if "ERROR SUMMARY" in line:
                match = re.search(r'(\d+)\s+errors', line)
                if match:
                    errors += int(match.group(1))

            if "data race" in line.lower():
                others += 1

    return errors, others


def main():
    # chemin dossier
    target = sys.argv[1] if len(sys.argv) > 1 else "."

    val_file = os.path.join(target, "log_val.txt")
    hel_file = os.path.join(target, "log_hel.txt")

    if not os.path.exists(val_file):
        print(f"❌ log_val.txt not found in {target}")
        return 1

    if not os.path.exists(hel_file):
        print(f"❌ log_hel.txt not found in {target}")
        return 1

    val_errors, val_leaks, val_others = analyse_valgrind(val_file)
    hel_errors, hel_others = analyse_helgrind(hel_file)

    print("===== VALGRIND =====")
    print(f"Errors : {val_errors}")
    print(f"Leaks   : {val_leaks}")
    print(f"Others  : {val_others}")

    print("\n===== HELGRIND =====")
    print(f"Errors : {hel_errors}")
    print(f"Others  : {hel_others}")

    # code retour propre
    if val_errors == 0 and val_leaks == 0 and hel_errors == 0:
        print("\n✅ OK")
        return 0
    else:
        print("\n❌ FAIL")
        return 1


if __name__ == "__main__":
    exit(main())