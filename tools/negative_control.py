"""Negative control for the kernel tests of `moonbit_fft/kernel_wbtest.mbt`.

It breaks the kernel on purpose and checks that the test suite turns red, so
that a green suite is known to mean something.  Afterwards the files are
restored byte by byte and their checksums are verified.

There are seven negative controls:

* the constants of the small transform of the radix 13,
* the structure of the small transform of the radix 13,
* the twist of the stages, which is the exponent of the roots of unity of
  the small transform,
* the number of butterflies of a stage,
* the plan cache itself: without it every call builds its plan again, which
  is correct but slow, so the tests have to notice,
* the positions of the butterflies of the radix 13,
* the dispatch of the stages, which picks the kernel of a radix and a twist.

and one **stress** control, which is the other way round: with a tiny plan
cache budget the cache drops and rebuilds its plans over and over again, and
the suite has to stay green, because that is not a defect but a different
memory budget.

The order of the factors of the length is *not* one of them, and it cannot be
one: the stages of the Good-Thomas transform act on different coordinates of
the transform, so they commute and the result does not depend on their order.
A control that reorders them therefore breaks nothing, and a green suite would
say nothing about the tests.  The invariance is checked by
`tools/verify_goodthomas.py` instead, where it is a fact and not a hole in
the tests.

Usage:
    python tools/negative_control.py
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODULE = ROOT / "moonbit_fft"
TARGET = MODULE / "mixed_radix.mbt"
KERNELS = MODULE / "kernels.mbt"
BACKUP = ROOT / "build" / "mixed_radix.mbt.negative_control_backup"
BACKUP_KERNELS = ROOT / "build" / "kernels.mbt.negative_control_backup"

# The header of the butterfly of the radix 13 with the twist 1.  The
# butterflies are generated per radix and per twist, so the anchors have to
# name the one they break.
HEADER_13 = (
    "fn stage_r13_mu1(\n"
    "  m : Int32,\n"
    "  kfac : Int32,\n"
    "  re : Array[Double],\n"
    "  im : Array[Double],\n"
    ") -> Unit {\n"
)

# The constants of the small transform of the radix 13.  They are solved in
# double precision, see `tools/solve_constants.py`.
CONSTANT = re.compile(
    r"(fn stage_r13_mu1\((?:.|\n)*?\n  let c1 = )(-?\d+\.\d+)\n"
)

# The pairing of the inputs of the small transform of the radix 13.  The
# butterflies are generated, so the anchor is a pattern: the first pair of
# the round is the sum of the two values of the first pair.
PAIRING = re.compile(r"(fn stage_r13_mu1\((?:.|\n)*?let t1r = re\[p1\] )\+ re\[p12\]")
PAIRING_BROKEN = r"\g<1>- re[p12]"

# The positions of the butterflies of the radix 13.  Every stage starts its
# first butterfly at a different place.
POSITION = re.compile(r"(fn stage_r13_mu1\((?:.|\n)*?let mut p0 = m \* \()0 \* kfac % 13\)")
POSITION_BROKEN = r"\g<1>1 * kfac % 13)"

# The dispatch of the stages, which picks the kernel of a radix and a twist.
DISPATCH = "      stage_r13_mu1(m, kfac, re, im)\n"
DISPATCH_BROKEN = "      stage_r13_mu2(m, kfac, re, im)\n"

# The twist of a stage.  Without the right twist the transform is wrong.
TWIST = "    let mu = r - kk\n"
TWIST_BROKEN = "    let mu = kk\n"

# The number of butterflies of a stage.  The stage has to visit every group
# of the transform, and one group too few leaves the result wrong.
BUTTERFLIES = "    let mi = counts[stage]\n"
BUTTERFLIES_BROKEN = "    let mi = counts[stage] - 1\n"

# The budget of the plan cache.  A tiny budget makes the cache drop its
# plans over and over again, which has to leave the results of the suite
# unchanged.
BUDGET = "let plan_cache_budget : Int32 = 2000000\n"
BUDGET_TINY = "let plan_cache_budget : Int32 = 1000\n"

# The line that puts a plan into the cache.  Without it every call builds its
# plan again, which is correct but slow, so the tests have to notice.
CACHE = "      plan_cache[index] = Some(plan)\n"
CACHE_BROKEN = "      plan_cache[index] = None\n"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_tests() -> tuple[int, str]:
    proc = subprocess.run(
        ["moon", "-C", str(MODULE), "test"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def report(name: str, code: int, output: str) -> bool:
    """Prints the outcome of a control and says whether it was as expected."""
    failed = [line for line in output.splitlines() if "failed:" in line]
    summary = [line for line in output.splitlines() if "Total tests:" in line]
    red = code != 0
    print(f"[{name}] suite is {'RED' if red else 'GREEN'} (exit {code})")
    for line in summary:
        print(f"[{name}]   {line.strip()}")
    # How many failures each test file contributed, so that it is visible
    # which part of the suite caught the break.
    per_file: dict[str, int] = {}
    for line in failed:
        match = re.search(r"test (\S+\.mbt):", line)
        source = match.group(1) if match else line.split("]")[0].strip("[")
        per_file[source] = per_file.get(source, 0) + 1
    for source, count in sorted(per_file.items()):
        print(f"[{name}]   {count} failures in {source}")
    for line in failed[:3]:
        print(f"[{name}]   {line.strip()}")
    return red


def control(
    name: str,
    old: str,
    new: str,
    target: Path = TARGET,
    backup: Path = BACKUP,
) -> bool:
    """Breaks the kernel, checks that the suite turns red, restores it."""
    original = target.read_text(encoding="utf-8")
    if original.count(old) != 1:
        print(f"[{name}] SKIPPED: the anchor was not found exactly once")
        return False
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(target, backup)
    before = sha256(backup)
    try:
        target.write_text(original.replace(old, new), encoding="utf-8", newline="")
        code, output = run_tests()
        return report(name, code, output)
    finally:
        shutil.copy2(backup, target)
        after = sha256(target)
        if after != before:
            raise SystemExit(f"[{name}] FAILED to restore {target}")
        backup.unlink(missing_ok=True)
        print(f"[{name}] restored, sha256 {after[:16]}")


def control_regex(
    name: str,
    pattern: re.Pattern,
    replacement: str,
    target: Path = KERNELS,
    backup: Path = BACKUP_KERNELS,
) -> bool:
    """Breaks the kernel with a pattern, checks that the suite turns red."""
    original = target.read_text(encoding="utf-8")
    matches = pattern.findall(original)
    if len(matches) != 1:
        print(f"[{name}] SKIPPED: the pattern matched {len(matches)} times")
        return False
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(target, backup)
    before = sha256(backup)
    try:
        broken = pattern.sub(replacement, original, count=1)
        if broken == original:
            print(f"[{name}] SKIPPED: the pattern changed nothing")
            return False
        target.write_text(broken, encoding="utf-8", newline="")
        code, output = run_tests()
        return report(name, code, output)
    finally:
        shutil.copy2(backup, target)
        after = sha256(target)
        if after != before:
            raise SystemExit(f"[{name}] FAILED to restore {target}")
        backup.unlink(missing_ok=True)
        print(f"[{name}] restored, sha256 {after[:16]}")


def stress(name: str, old: str, new: str) -> bool:
    """Changes the kernel in a way that must not change the results.

    It is the counterpart of the negative controls: the suite has to stay
    green, because the change is not a defect.
    """
    original = TARGET.read_text(encoding="utf-8")
    if original.count(old) != 1:
        print(f"[{name}] SKIPPED: the anchor was not found exactly once")
        return False
    BACKUP.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(TARGET, BACKUP)
    before = sha256(BACKUP)
    try:
        TARGET.write_text(original.replace(old, new), encoding="utf-8", newline="")
        code, output = run_tests()
        green = code == 0
        report(name, code, output)
        return green
    finally:
        shutil.copy2(BACKUP, TARGET)
        after = sha256(TARGET)
        if after != before:
            raise SystemExit(f"[{name}] FAILED to restore {TARGET}")
        BACKUP.unlink(missing_ok=True)
        print(f"[{name}] restored, sha256 {after[:16]}")


def main() -> int:
    results = [
        control_regex("the constants of the stages", CONSTANT, r"\g<1>-0.000001\n"),
        control_regex("the structure of the stages", PAIRING, PAIRING_BROKEN),
        control("the twist of the stages", TWIST, TWIST_BROKEN),
        control("the number of butterflies", BUTTERFLIES, BUTTERFLIES_BROKEN),
        control("the plan cache", CACHE, CACHE_BROKEN),
        control_regex("the positions of the butterflies", POSITION, POSITION_BROKEN),
        control("the dispatch of the stages", DISPATCH, DISPATCH_BROKEN, KERNELS, BACKUP_KERNELS),
    ]
    stress_ok = stress("a tiny plan cache budget", BUDGET, BUDGET_TINY)
    if not all(results) or not stress_ok:
        print("NEGATIVE CONTROL FAILED")
        return 1
    print(
        f"OK: all {len(results)} negative controls turned the suite red "
        "and the stress control kept it green"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
