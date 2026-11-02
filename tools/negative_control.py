"""Negative control for the kernel tests of `moonbit_fft2/kernel_wbtest.mbt`.

It breaks the kernel on purpose and checks that the test suite turns red, so
that a green suite is known to mean something.  Afterwards the files are
restored byte by byte and their checksums are verified.

There are seven negative controls:

* all the twiddle factors of the plan,
* the twiddle factors of the radix 13 alone,
* the size of the table of the small Fourier matrices of the generic path,
* the size of the scratch space of the generic path,
* the plan cache itself: without it every call builds its plan again, which
  is correct but slow, so the tests have to notice,
* the pairing of the inputs of the symmetric small transform,
* a constant of the symmetric small transform of the radix 13.

and one **stress** control, which is the other way round: with a tiny plan
cache budget the cache drops and rebuilds its plans over and over again, and
the suite has to stay green, because that is not a defect but a different
memory budget.

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
MODULE = ROOT / "moonbit_fft2"
TARGET = MODULE / "mixed_radix.mbt"
KERNELS = MODULE / "kernels.mbt"
BACKUP = ROOT / "build" / "mixed_radix.mbt.negative_control_backup"
BACKUP_KERNELS = ROOT / "build" / "kernels.mbt.negative_control_backup"

TWIDDLE = "      let ang = -two_pi * k0.to_double() / l.to_double()\n"
TWIDDLE_BROKEN = (
    "      let ang = -two_pi * 1.0001 * k0.to_double() / l.to_double()\n"
)

PUSH = "      base_re.push(@math.cos(ang))\n      base_im.push(@math.sin(ang))\n"
PUSH_BROKEN = (
    "      let delta = if r == 13 { 0.001 } else { 0.0 }\n"
    "      base_re.push(@math.cos(ang + delta))\n"
    "      base_im.push(@math.sin(ang + delta))\n"
)

# The sizes of the scratch space of the butterfly and of the table of the
# small Fourier matrices.  Before the fix they were the constant 13, the
# largest radix of the valid lengths of the original, and a plan of a larger
# radix ran out of both of them.
SIZES = (
    "  let matrix_off = zeros(max_r + 1)\n"
    "  let used = zeros(max_r + 1)\n"
)
SIZES_BROKEN = (
    "  let matrix_off = zeros(13 + 1)\n"
    "  let used = zeros(13 + 1)\n"
)
SCRATCH = "  let scratch_re = zerosd(max_r)\n  let scratch_im = zerosd(max_r)\n"
SCRATCH_BROKEN = (
    "  let scratch_re = zerosd(13)\n  let scratch_im = zerosd(13)\n"
)

# The budget of the plan cache.  A tiny budget makes the cache drop its
# plans over and over again, which has to leave the results of the suite
# unchanged.
BUDGET = "let plan_cache_budget : Int32 = 2000000\n"
BUDGET_TINY = "let plan_cache_budget : Int32 = 1000\n"

# The line that puts a plan into the cache.  Without it every call builds its
# plan again, which is correct but slow, so the tests have to notice.
CACHE = "      plan_cache[index] = Some(plan)\n"
CACHE_BROKEN = "      plan_cache[index] = None\n"

# The pairing of the inputs of the symmetric small transform.  The line
# belongs to the radix 3, the radices 5, 7, 11 and 13 pair their inputs
# differently.
PAIRING = "      let a1_re = u1_re + u2_re\n"
PAIRING_BROKEN = "      let a1_re = u1_re - u2_re\n"

# A constant of the symmetric small transform of the radix 13.  The variable
# `c6` only exists for the radix 13, the radix 11 stops at `c5`.
CONSTANT = "      let mut c6_re = u0_re\n"
CONSTANT_BROKEN = "      let mut c6_re = u0_re * 2.0\n"


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
        control("all twiddles", TWIDDLE, TWIDDLE_BROKEN),
        control("radix 13 only", PUSH, PUSH_BROKEN),
        control("the size of the table of the generic path", SIZES, SIZES_BROKEN),
        control("the size of the scratch space", SCRATCH, SCRATCH_BROKEN),
        control("the plan cache", CACHE, CACHE_BROKEN),
        control("the pairing of the inputs", PAIRING, PAIRING_BROKEN, KERNELS, BACKUP_KERNELS),
        control("a constant of the radix 13", CONSTANT, CONSTANT_BROKEN, KERNELS, BACKUP_KERNELS),
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
