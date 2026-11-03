#!/usr/bin/env python3
"""Checks the model of the Good-Thomas transform against the direct transform.

The port of `edu.mines.jtk.dsp.Pfacc` is a prime factor algorithm: the length
is split into pairwise coprime factors and every factor selects a small
kernel.  The model of this script is the reference of that algorithm, in
Python, and it is checked against `numpy.fft` for every length the original
supports.

The structure of one stage is this.  The stage has the radix `r`, the length
is `n`, and `m = n / r` is the number of butterflies of the stage.  The value
`kfac` is the inverse of `m` modulo `r`, it is the twist of the stage.

The butterfly of the round `i` takes its `r` values from the positions

    p[t] = m * ((t * kfac) mod r)      for t = 0 .. r - 1

applies a discrete Fourier transform of the size `r` to them, in which the
roots of unity are raised to the power `kfac`, and writes the result back to
the same positions.  The twist of the original, which rotates the output of
the small transform, is in the roots of unity and not in the indices, so the
small transform needs no permutation at all.

The positions of the round `i + 1` follow from the ones of the round `i`:
every offset loses `kfac` and wraps around, which is one comparison and one
conditional addition per value.

The script checks three things.

* The factors of every valid length are pairwise coprime.  That is the
  property that lets the transform run without twiddle factors.
* The model gives the same transform as `numpy.fft`, for every valid length
  that is small enough to be checked, and for the largest one.
* The twists of the stages, the ones that decide which variant of a small
  kernel a length needs, are listed.

Usage::

    python tools/verify_goodthomas.py
    python tools/verify_goodthomas.py --max-length 4096
"""

from __future__ import annotations

import argparse
import math
import pathlib
import re
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent.parent

# The factors of the original, the order is the one of `Pfacc._kfac`.
KFAC = [16, 13, 11, 9, 8, 7, 5, 4, 3, 2]


def valid_lengths() -> list[int]:
    """The valid lengths of the original, they are the ones of the table."""
    text = (ROOT / "moonbit_fft2" / "tables.mbt").read_text(encoding="utf-8")
    body = re.search(r"let ntable : Array\[Int32\] = \[(.*?)\]", text, re.S).group(1)
    return [int(x) for x in re.findall(r"\d+", body)]


def factors_of(n: int) -> list[int]:
    """The factors of a length, the way the original splits it."""
    out: list[int] = []
    left = n
    for f in KFAC:
        if left % f == 0:
            left //= f
            out.append(f)
    if left != 1:
        raise ValueError("%d is not a valid length" % n)
    return out


def transform(x: np.ndarray, factors: list[int]) -> np.ndarray:
    """The transform of the model, in the natural order of the samples."""
    a = x.astype(complex).copy()
    n = len(a)
    for r in factors:
        m = n // r
        kfac = pow(m, -1, r)
        w = np.exp(-2j * np.pi * np.arange(r) / r)
        p = [m * ((t * kfac) % r) for t in range(r)]
        limit = m * kfac
        delta = 1 - m * kfac
        for _ in range(m):
            v = np.array([a[p[t]] for t in range(r)])
            y = np.array(
                [sum(v[s] * w[(kfac * t * s) % r] for s in range(r)) for t in range(r)]
            )
            for t in range(r):
                a[p[t]] = y[t]
            for t in range(r):
                if p[t] < limit:
                    p[t] += m * r
                p[t] += delta
            limit += 1
    return a


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-length",
        type=int,
        default=4096,
        help="the lengths up to this one are checked one by one",
    )
    args = parser.parse_args()

    lengths = valid_lengths()
    rng = np.random.default_rng(4711)
    failures = 0

    # The factors of every valid length must be pairwise coprime.
    not_coprime = 0
    twists: dict[int, set[int]] = {}
    for n in lengths:
        factors = factors_of(n)
        for i in range(len(factors)):
            for j in range(i + 1, len(factors)):
                if math.gcd(factors[i], factors[j]) != 1:
                    not_coprime += 1
                    print(f"n = {n}: the factors {factors} are not coprime")
        for r in factors:
            m = n // r
            twists.setdefault(r, set()).add(pow(m, -1, r))
    if not_coprime:
        failures += not_coprime
    print(
        "the factors of the %d valid lengths are pairwise coprime" % len(lengths)
        if not_coprime == 0
        else "%d lengths have factors that are not coprime" % not_coprime
    )

    # The model must give the same transform as the direct evaluation.
    worst = 0.0
    checked = 0
    for n in lengths:
        if n > args.max_length:
            continue
        x = rng.normal(size=n) + 1j * rng.normal(size=n)
        got = transform(x, factors_of(n))
        want = np.fft.fft(x)
        error = np.max(np.abs(got - want))
        scale = max(np.max(np.abs(want)), 1.0)
        worst = max(worst, error / scale)
        if not np.allclose(got, want, atol=1e-9):
            failures += 1
            print(f"n = {n}: MISMATCH, error {error:.3e}")
        checked += 1
    print(
        "%d lengths match the direct transform, the worst relative error is %.3e"
        % (checked, worst)
    )

    # The largest length is checked as well, it is the one that has the most
    # stages and the most factors.
    n = max(lengths)
    x = rng.normal(size=n) + 1j * rng.normal(size=n)
    got = transform(x, factors_of(n))
    want = np.fft.fft(x)
    error = np.max(np.abs(got - want)) / np.max(np.abs(want))
    print(
        "the largest length %d has the factors %s and the relative error %.3e"
        % (n, factors_of(n), error)
    )
    if error > 1e-12:
        failures += 1

    # The stages act on different coordinates of the transform, so they
    # commute: the order of the factors does not change the result.  This is
    # why the order of the factors cannot be a negative control of the tests,
    # a broken order would break nothing.
    n = 32760
    factors = factors_of(n)
    x = rng.normal(size=n) + 1j * rng.normal(size=n)
    straight = transform(x, factors)
    reversed_ = transform(x, list(reversed(factors)))
    difference = np.max(np.abs(straight - reversed_))
    print(
        "the order of the factors does not matter: the difference between the "
        "two orders is %.3e" % difference
    )
    if difference > 1e-9:
        failures += 1

    # The twists decide which variant of a small kernel a length needs.
    print()
    print("the twists of the stages:")
    variants = 0
    for r in sorted(twists):
        ks = sorted(twists[r])
        variants += len(ks)
        print("  radix %2d: %2d twists %s" % (r, len(ks), ks))
    print("  %d variants of the small kernels in total" % variants)

    if failures:
        print()
        print("%d failures" % failures)
        return 1
    print()
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
