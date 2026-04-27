"""check_makefile.py — Verifies the Codexion project Makefile."""

import re
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple


def check_makefile(repo_path: str) -> List[Tuple[str, Optional[bool], str]]:
    """Check the Codexion Makefile for required rules, binary name, compiler
    flags, and no-relink behaviour.

    Returns a list of ``(label, ok, detail)`` tuples where *ok* is:

    * ``True``  → pass
    * ``False`` → fail
    * ``None``  → skip (Makefile not found)
    """
    results: List[Tuple[str, Optional[bool], str]] = []

    mk_path: Optional[Path] = None
    for name in ("Makefile", "makefile"):
        candidate = Path(repo_path) / name
        if candidate.exists():
            mk_path = candidate
            break

    if mk_path is None:
        reason = f"no Makefile found in '{repo_path}'"
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
            results.append((label, None, reason))
        return results

    results.append(("Makefile exists", True, str(mk_path)))
    content = mk_path.read_text(errors="replace")

    # Required phony rules
    for rule in ("all", "clean", "fclean", "re"):
        label = f"Makefile: rule '{rule}' present"
        if re.search(rf'^{re.escape(rule)}\s*:', content, re.MULTILINE):
            results.append((label, True, ""))
        else:
            results.append((label, False, f"'{rule}:' target not found in Makefile"))

    # Binary name referenced
    if re.search(r'\bcodexion\b', content):
        results.append(("Makefile: binary name 'codexion' referenced", True, ""))
    else:
        results.append((
            "Makefile: binary name 'codexion' not found",
            False,
            "'codexion' is not referenced anywhere in the Makefile",
        ))

    # Compiler warning flags
    has_wall   = bool(re.search(r'-Wall\b',   content))
    has_wextra = bool(re.search(r'-Wextra\b', content))
    has_werror = bool(re.search(r'-Werror\b', content))
    if has_wall and has_wextra and has_werror:
        results.append((
            "Makefile: compilation flags -Wall -Wextra -Werror present",
            True, "",
        ))
    else:
        missing = [
            flag for flag, present in (
                ("-Wall",   has_wall),
                ("-Wextra", has_wextra),
                ("-Werror", has_werror),
            ) if not present
        ]
        results.append((
            "Makefile: compilation flags incomplete",
            False,
            f"missing: {' '.join(missing)}",
        ))

    # No-relink: a second `make` must not invoke a compiler.
    r2 = subprocess.run(
        ["make", "-C", str(mk_path.parent)],
        capture_output=True, text=True,
    )
    combined = r2.stdout + r2.stderr
    relink_pat = re.compile(r'\b(cc|gcc|g\+\+|clang\+\+|clang)\b', re.IGNORECASE)
    if r2.returncode == 0 and not relink_pat.search(combined):
        results.append(("Makefile: no relink on repeated 'make'", True, ""))
    else:
        results.append((
            "Makefile: relink detected on second 'make'",
            False,
            "second 'make' produced compiler invocations or exited non-zero",
        ))

    return results
