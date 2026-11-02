"""Measures the port as it was before the kernel was rewritten.

The benchmark of the port needs the current module, but the "before" column
of `BENCHMARK.md` is the port with the old kernel - the one that transformed
`O(n^2)` for every length that is not a power of two.  That kernel is in the
git history, so it can be checked out and measured again.

The script assembles a shadow module under `build/oldmodule` from the current
module, replaces the files that the kernel rewrite touched with the ones of
the given revision, and runs the benchmark of the port there.

Usage:
    python tools/bench_baseline.py [--rev HEAD] [--out build/bench_moonbit_head.txt]
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODULE = ROOT / "moonbit_fft2"
SHADOW = ROOT / "build" / "oldmodule"

# The files of the module that the kernel rewrite touched.  Everything else
# is taken from the working tree, so that the benchmark harness is the one of
# the current revision.
REPLACED = ("kernel.mbt", "types.mbt")

# The files of the module that the shadow needs.  The test files are left
# out, they belong to the new kernel.
COPIED = ("moon.mod", "moon.pkg", "types.mbt", "nfft.mbt", "tables.mbt", "fft.mbt", "methods.mbt")


def git_show(rev: str, path: str) -> bytes:
    """Reads a file of a revision as bytes.

    The output is written as bytes on purpose: a redirect of `git show` in
    PowerShell writes UTF-16, which the compiler cannot read.
    """
    proc = subprocess.run(
        ["git", "-C", str(ROOT), "show", f"{rev}:{path}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return proc.stdout


def assemble(rev: str) -> None:
    SHADOW.mkdir(parents=True, exist_ok=True)
    (SHADOW / "benchmark").mkdir(parents=True, exist_ok=True)
    for name in COPIED:
        shutil.copy2(MODULE / name, SHADOW / name)
    for name in ("moon.pkg", "main.mbt"):
        shutil.copy2(MODULE / "benchmark" / name, SHADOW / "benchmark" / name)
    for name in REPLACED:
        (SHADOW / name).write_bytes(git_show(rev, f"moonbit_fft2/{name}"))
        print(f"[{rev}] moonbit_fft2/{name} -> build/oldmodule/{name}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rev", default="HEAD", help="the revision to measure")
    parser.add_argument(
        "--out",
        default=str(ROOT / "build" / "bench_moonbit_head.txt"),
        help="the file the benchmark writes to",
    )
    args = parser.parse_args()

    assemble(args.rev)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    print(f"running the benchmark of the port at {args.rev}, this takes a while")
    with out.open("wb") as handle:
        proc = subprocess.run(
            ["moon", "-C", str(SHADOW), "run", "--target", "native", "./benchmark"],
            stdout=handle,
            stderr=subprocess.STDOUT,
        )
    print(f"exit {proc.returncode}, the result is in {out}")
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
