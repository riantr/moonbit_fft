#!/usr/bin/env python3
"""Holds every side of the ecosystem benchmark to a double precision reference.

A timing table is only worth its rows if the faster side computes the same
transform as the slower one, so every side of `tools/bench_ecosystem.py` is
dumped once at the length it is measured at, and compared with `numpy.fft`.

The comparison has a second purpose.  Two packages of the ecosystem offer a
radix path next to their Bluestein one, and the radix path of `hwlxmm/dsp` does
**not** compute the transform at any length that was tried, while the rest of
the sides do.  The set of the sides that are correct is therefore pinned in
`EXPECTED_CORRECT`: a side that stops being correct, and a side that becomes
correct, both turn this script red, because either one would make the document
of the benchmark say something that is no longer true.

Usage::

    python tools/check_ecospectra.py
    python tools/check_ecospectra.py --skip-build
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import pathlib

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHADOW = ROOT / "build" / "ecomodule"
OUT = SHADOW / "spec9out"

# The window of the packages and the closest valid length of the port.
WINDOWS = [(4096, 4095), (1024, 1008)]

# The sides that compute the transform, as of the versions pinned in
# `tools/bench_ecosystem.py`.  The rest of them are reported with their
# deviation and are expected to be wrong.
EXPECTED_CORRECT = {
    "port", "hkdsp", "hx_bluestein", "lc_radix4", "lc_bluestein", "moonnum",
    "mspec", "mdsp",
}

# The port transforms single precision samples and rounds its result back to
# single precision, so its deviation is that of `float32`.  The other sides work
# in double precision.
LIMITS = {"port": 3e-6}
DEFAULT_LIMIT = 1e-9


def sample(i: int) -> float:
    return ((i * 2654435761) % 1000) / 1000.0 - 0.5


def reference(n: int, real_only: bool) -> np.ndarray:
    if real_only:
        # `mdsp` takes the real parts of the samples of the others.
        return np.fft.fft(np.array([sample(2 * i) for i in range(n)],
                                   dtype=np.float64))
    src = np.array([sample(i) for i in range(2 * n)], dtype=np.float64)
    return np.fft.fft(src[0::2] + 1j * src[1::2])


def read(path: pathlib.Path) -> np.ndarray:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        a, b = line.split()
        out.append(complex(float(a), float(b)))
    return np.array(out, dtype=np.complex128)


def build_and_run(skip_build: bool) -> None:
    subprocess.run(
        [sys.executable, str(ROOT / "tools" / "bench_ecosystem.py"),
         "--assemble-only"],
        check=True, cwd=str(ROOT),
    )
    if not skip_build:
        subprocess.run(
            ["moon", "-C", str(SHADOW), "build", "--release",
             "--target", "native", "./spec9"],
            check=True,
        )
    proc = subprocess.run(
        ["moon", "-C", str(SHADOW), "run", "--release",
         "--target", "native", "./spec9", "--", str(OUT)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=str(ROOT),
    )
    if proc.returncode != 0:
        print(proc.stdout.decode("utf-8", "replace")[-4000:])
        raise SystemExit("the probe exited with %d" % proc.returncode)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-build", action="store_true",
                        help="use the binaries of the last build")
    args = parser.parse_args()

    build_and_run(args.skip_build)

    problems: list[str] = []
    correct: set[str] = set()
    rows = 0
    for window, port_length in WINDOWS:
        print("== window %d, the port at %d ==" % (window, port_length))
        for side in sorted(EXPECTED_CORRECT | {"hx_radix4"}):
            n = port_length if side == "port" else window
            path = OUT / ("%s_%d.txt" % (side, n))
            if not path.exists():
                print("  %-14s MISSING %s" % (side, path.name))
                problems.append("no spectrum of %s at %d" % (side, n))
                continue
            got = read(path)
            ref = reference(n, real_only=(side == "mdsp"))
            if got.shape != ref.shape:
                problems.append("%s at %d holds %d values, the reference has %d"
                                % (side, got.size, ref.size))
                continue
            rows += 1
            scale = max(1.0, float(np.abs(ref).max()))
            deviation = float(np.abs(got - ref).max()) / scale
            limit = LIMITS.get(side, DEFAULT_LIMIT)
            ok = deviation <= limit
            if ok:
                correct.add(side)
            print("  %-14s %s n=%-5d relative deviation %.3e"
                  % (side, "the transform " if ok else "NOT the transform",
                     n, deviation))

    print()
    if correct != EXPECTED_CORRECT:
        gained = correct - EXPECTED_CORRECT
        lost = EXPECTED_CORRECT - correct
        if gained:
            problems.append(
                "these sides now compute the transform and did not: %s"
                % sorted(gained))
        if lost:
            problems.append(
                "these sides no longer compute the transform: %s" % sorted(lost))
    if problems:
        print("%d problems:" % len(problems))
        for problem in problems:
            print("  " + problem)
        return 1
    print("%d spectra were read.  %d of the sides compute the transform: %s."
          % (rows, len(correct), sorted(correct)))
    print("The radix path of `hwlxmm/dsp` does not, at either length, and the")
    print("document of the benchmark says so.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
