#!/usr/bin/env python3
"""Holds every side of the ecosystem comparison to a double precision reference.

A timing table is only worth its rows if the faster side computes the same
transform as the slower one, so the probe `tools/ecomodule/spec9` dumps the
result of every side and this script compares it with `numpy.fft`.

Three groups are checked:

* the forward transform of every side, at the two windows of the benchmark;
* the small lengths of the two radix paths of `hwlxmm/dsp`, because one of them
  is correct at only one of them and the document says which;
* the inverse transform of every side that publishes one, in the scaling that
  the side publishes - a package that divides by `n` and a package that does not
  are both right, but they are not the same transform.

The expected sets are written down here, so a side that stops being correct and
a side that becomes correct both turn this red.

Usage::

    python tools/check_ecospectra.py
    python tools/check_ecospectra.py --skip-build
"""

from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHADOW = ROOT / "build" / "ecomodule"
OUT = SHADOW / "spec9out"

# The window of the packages and the closest valid length of the port.
WINDOWS = [(4096, 4095), (1024, 1008)]

# The lengths at which the two radix paths of `hwlxmm/dsp` are dumped in
# addition, so that the range over which they hold is pinned and not claimed.
SMALL = [4, 8, 16, 64, 256]

# The sides that compute the forward transform, as of the versions pinned in
# `tools/bench_ecosystem.py`.
FORWARD_CORRECT = {
    "port", "hkdsp", "hx_radix2", "hx_bluestein", "lc_radix4", "lc_bluestein",
    "moonnum", "mspec", "mdsp",
}

# The sides that do not, at either window.
FORWARD_WRONG = {"hx_radix4"}

# The radix-4 path of `hwlxmm/dsp` is correct at exactly one of the small
# lengths; its radix-2 path is correct at all of them.
RADIX4_CORRECT = {8}

# The inverse of every side that publishes one, and the scaling it uses.  The
# Java original and `port/bfft` do not scale; everything else does.
INVERSE = {
    "port_bfft": "unnormalised",
    "port_ifft": "normalised",
    "hkdsp_ifft": "normalised",
    "hx_ifft_bluestein": "normalised",
    "hx_ifft_radix2": "normalised",
    "lc_ifft": "normalised",
    "lc_ifft_radix4": "normalised",
    "moonnum_ifft": "normalised",
    "mspec_ifft": "normalised",
}

# The port transforms single precision samples and rounds its result back to
# single precision, so its deviation is that of `float32`.  The other sides work
# in double precision.
LIMITS = {"port": 3e-6, "port_bfft": 3e-6, "port_ifft": 3e-6}
DEFAULT_LIMIT = 1e-9


def sample(i: int) -> float:
    return ((i * 2654435761) % 1000) / 1000.0 - 0.5


def input_of(n: int) -> np.ndarray:
    src = np.array([sample(i) for i in range(2 * n)], dtype=np.float64)
    return src[0::2] + 1j * src[1::2]


def forward_reference(n: int, real_only: bool) -> np.ndarray:
    if real_only:
        # `mdsp` takes the real parts of the samples of the others.
        return np.fft.fft(np.array([sample(2 * i) for i in range(n)],
                                   dtype=np.float64))
    return np.fft.fft(input_of(n))


def inverse_reference(n: int, scaling: str) -> np.ndarray:
    out = np.fft.ifft(input_of(n))
    return out * n if scaling == "unnormalised" else out


def read(side: str, n: int) -> np.ndarray | None:
    path = OUT / ("%s_%d.txt" % (side, n))
    if not path.exists():
        return None
    values = np.array([float(x) for x in path.read_text(encoding="utf-8").split()],
                      dtype=np.float64)
    return values[0::2] + 1j * values[1::2]


def deviation(got: np.ndarray, ref: np.ndarray) -> float:
    """The relative deviation, which does not depend on the magnitude of the
    result - the inverse of a sequence is a hundred times smaller than its
    spectrum, and an absolute tolerance would read that as accuracy."""
    return float(np.linalg.norm(got - ref) / np.linalg.norm(ref))


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
    rows = 0

    forward_ok: set[str] = set()
    for window, port_length in WINDOWS:
        print("== the forward transform, window %d, the port at %d =="
              % (window, port_length))
        for side in sorted(FORWARD_CORRECT | FORWARD_WRONG):
            n = port_length if side == "port" else window
            got = read(side, n)
            if got is None:
                problems.append("no spectrum of %s at %d" % (side, n))
                continue
            ref = forward_reference(n, real_only=(side == "mdsp"))
            if got.shape != ref.shape:
                problems.append("%s at %d holds %d values, the reference has %d"
                                % (side, got.size, ref.size))
                continue
            rows += 1
            dev = deviation(got, ref)
            ok = dev <= LIMITS.get(side, DEFAULT_LIMIT)
            if ok:
                forward_ok.add(side)
            print("  %-18s %s n=%-5d relative deviation %.3e"
                  % (side, "the transform " if ok else "NOT the transform ", n, dev))

    print()
    print("== the small lengths of the two radix paths of `hwlxmm/dsp` ==")
    radix4_ok: set[int] = set()
    radix2_ok: set[int] = set()
    for n in SMALL:
        ref = forward_reference(n, real_only=False)
        for side, sink in (("hx_radix4", radix4_ok), ("hx_radix2", radix2_ok)):
            got = read(side, n)
            if got is None:
                problems.append("no spectrum of %s at %d" % (side, n))
                continue
            rows += 1
            dev = deviation(got, ref)
            ok = dev <= DEFAULT_LIMIT
            if ok:
                sink.add(n)
            print("  %-18s %s n=%-5d relative deviation %.3e"
                  % (side, "the transform " if ok else "NOT the transform ", n, dev))

    print()
    inverse_ok: set[str] = set()
    for window, port_length in WINDOWS:
        print("== the inverse transform, window %d ==" % window)
        for side in sorted(INVERSE):
            n = port_length if side.startswith("port") else window
            got = read(side, n)
            if got is None:
                problems.append("no inverse of %s at %d" % (side, n))
                continue
            rows += 1
            dev = deviation(got, inverse_reference(n, INVERSE[side]))
            ok = dev <= LIMITS.get(side, DEFAULT_LIMIT)
            if ok:
                inverse_ok.add(side)
            print("  %-18s %-13s %s n=%-5d relative deviation %.3e"
                  % (side, INVERSE[side], "the transform " if ok else "NOT the transform ",
                     n, dev))

    if forward_ok != FORWARD_CORRECT:
        problems.append("the forward sides that compute the transform are %s, "
                        "they were %s" % (sorted(forward_ok),
                                          sorted(FORWARD_CORRECT)))
    if (FORWARD_CORRECT | FORWARD_WRONG) - forward_ok != FORWARD_WRONG:
        problems.append("the forward sides that do not compute it are %s, "
                        "they were %s"
                        % (sorted((FORWARD_CORRECT | FORWARD_WRONG) - forward_ok),
                           sorted(FORWARD_WRONG)))
    if radix4_ok != RADIX4_CORRECT:
        problems.append("radix 4 of `hwlxmm/dsp` is correct at %s, it was correct "
                        "at %s" % (sorted(radix4_ok), sorted(RADIX4_CORRECT)))
    if radix2_ok != set(SMALL):
        problems.append("radix 2 of `hwlxmm/dsp` is correct at %s, it was correct "
                        "at every one of %s" % (sorted(radix2_ok), sorted(SMALL)))
    if inverse_ok != set(INVERSE):
        problems.append("the inverse sides that compute the transform are %s, "
                        "they were %s" % (sorted(inverse_ok), sorted(INVERSE)))

    print()
    if problems:
        print("%d problems:" % len(problems))
        for problem in problems:
            print("  " + problem)
        return 1
    print("%d readings.  %d forward sides, %d inverse sides, and the two radix "
          "paths of `hwlxmm/dsp` are held to `numpy.fft`."
          % (rows, len(forward_ok), len(inverse_ok)))
    print("The radix **4** path of `hwlxmm/dsp` does not compute the transform at")
    print("either window, and at 8 of the small lengths it is the only one that")
    print("does; its radix 2 and its Bluestein paths do, and the documents say so.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
