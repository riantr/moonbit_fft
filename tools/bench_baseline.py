"""Measures the port as it was before the kernel was rewritten.

The benchmark of the port needs the current module, but the "before" column
of `BENCHMARK.md` is the port with the old kernel - the one that transformed
`O(n^2)` for every length that is not a power of two.  That kernel is in the
git history, so the column can be measured again instead of being taken on
trust.

The script assembles a shadow module under `build/oldmodule` from a given
revision: every file of the module is taken from that revision, only the
benchmark harness is taken from the working tree, so that the harness is the
one of the current revision.

Usage:
    python tools/bench_baseline.py --rev cdd5285
    python tools/bench_baseline.py --rev cdd5285 --assemble-only
    python tools/bench_baseline.py --rev HEAD --shadow build/headmodule
"""

from __future__ import annotations

import argparse
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHADOW = ROOT / "build" / "oldmodule"

# The directories the module has had.  The published name was
# `riantr/moonbit_fft2` before it was shortened, and the directory followed
# the name, so a revision of the history holds one of the two.
MODULE_DIRS = ("moonbit_fft", "moonbit_fft2")

# The files of the benchmark harness, they are not part of the module.
HARNESS = ("benchmark/main.mbt", "benchmark/moon.pkg")


def git(*args: str) -> bytes:
    """Runs a git command and returns its output."""
    proc = subprocess.run(
        ["git", "-C", str(ROOT), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return proc.stdout


def module_files(rev: str) -> tuple[str, list[str]]:
    """The directory and the files of the module in a revision.

    The module was published as `riantr/moonbit_fft2` before its name was
    shortened, so its directory is `moonbit_fft2/` in the older revisions and
    `moonbit_fft/` from the rename on.  Both spellings have to be understood,
    because this tool reads the module out of a revision of the history.
    """
    out = git("ls-tree", "-r", "--name-only", rev).decode("utf-8")
    lines = [line.strip() for line in out.splitlines() if line.strip()]
    for directory in MODULE_DIRS:
        prefix = directory + "/"
        names = [
            line[len(prefix) :]
            for line in lines
            if line.startswith(prefix)
            and not line[len(prefix) :].startswith("benchmark/")
        ]
        if names:
            return directory, names
    raise SystemExit("%s holds no module directory" % rev)


def assemble(rev: str, shadow: pathlib.Path) -> None:
    """Builds the shadow module of a revision."""
    if shadow.exists():
        shutil.rmtree(shadow)
    shadow.mkdir(parents=True)
    directory, names = module_files(rev)
    for name in names:
        data = git("show", f"{rev}:{directory}/{name}")
        # The output is written as bytes on purpose: a redirect of `git show`
        # in PowerShell writes UTF-16, which the compiler cannot read.
        target = shadow / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        print(f"[{rev}] {directory}/{name} -> {target}")
    for name in HARNESS:
        source = ROOT / "moonbit_fft" / name
        target = shadow / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        print(f"[harness] moonbit_fft/{name} -> {target}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rev",
        default="HEAD",
        help="the revision to measure",
    )
    parser.add_argument(
        "--out",
        default=str(ROOT / "build" / "bench_moonbit_head.txt"),
        help="the file the benchmark writes to",
    )
    parser.add_argument(
        "--assemble-only",
        action="store_true",
        help="only assemble the shadow module, do not run the benchmark",
    )
    parser.add_argument(
        "--shadow",
        type=pathlib.Path,
        default=SHADOW,
        help="the directory the shadow module is assembled in",
    )
    args = parser.parse_args()

    assemble(args.rev, args.shadow)
    if args.assemble_only:
        print(f"the shadow module is in {args.shadow}")
        return 0
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    print("running the benchmark of the port, this takes a while")
    with out.open("wb") as handle:
        proc = subprocess.run(
            ["moon", "-C", str(args.shadow), "run", "--target", "native", "./benchmark"],
            stdout=handle,
            stderr=subprocess.STDOUT,
        )
    print(f"exit {proc.returncode}, the result is in {out}")
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
