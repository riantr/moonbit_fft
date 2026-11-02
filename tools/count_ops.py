#!/usr/bin/env python3
"""Counts the operations of the specialised butterflies.

For every radix it reports the number of real multiplications and of array
accesses of one butterfly.  The numbers say how much of a transform is spent
in the arithmetic of the small discrete Fourier transforms and how much in
the accesses of the arrays, which is what decides whether it is worth
replacing the small transform by a cheaper formula.

Usage::

    python tools/count_ops.py
    python tools/count_ops.py --kernels build/kernels_direct.mbt
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_KERNELS = ROOT / "moonbit_fft2" / "kernels.mbt"
TABLES = ROOT / "moonbit_fft2" / "tables.mbt"

RADICES = [2, 3, 5, 7, 11, 13]


def factorize(n: int) -> list[int]:
    factors = []
    p = 2
    while p * p <= n:
        while n % p == 0:
            factors.append(p)
            n //= p
        p += 1
    if n > 1:
        factors.append(n)
    return factors


def read_table() -> list[int]:
    text = TABLES.read_text(encoding="utf-8")
    body = re.search(r"let ntable : Array\[Int32\] = \[(.*?)\]", text, re.S).group(1)
    return [int(x) for x in re.findall(r"\d+", body)]


def butterfly(text: str, r: int) -> str:
    start = text.index(f"fn stage_r{r}(")
    rest = text[start + 1 :]
    end = rest.index("\nfn ") if "\nfn " in rest else len(rest)
    return text[start : start + 1 + end]


def counts(text: str, r: int) -> tuple[int, int, int]:
    """The multiplications of the small transform, the accesses, the twiddles."""
    body = butterfly(text, r)
    marker = "let mut c1_re" if "let mut c1_re" in body else "let mut v0_re"
    transform = body[body.index(marker) : body.index("k0 = k0 + 1")]
    gather = body[: body.index(marker)]
    # The write back of the results holds a `* m`, which is not a
    # multiplication.
    mults = len(re.findall(r"\*", transform)) - len(re.findall(r"\* m", transform))
    accesses = len(re.findall(r"\[", body))
    twiddle = len(re.findall(r"\*", gather))
    return mults, accesses, twiddle


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--kernels",
        type=pathlib.Path,
        default=DEFAULT_KERNELS,
        help="the generated butterflies to count",
    )
    args = parser.parse_args()

    text = args.kernels.read_text(encoding="utf-8")
    table = read_table()
    print("one butterfly of each radix:")
    print("%5s %10s %10s %10s" % ("radix", "mults", "accesses", "twiddle"))
    for r in RADICES:
        m, a, t = counts(text, r)
        print("%5d %10d %10d %10d" % (r, m, a, t))

    print()
    print("a transform of n = 32760 (2^3 * 3^2 * 5 * 7 * 13):")
    n = 32760
    stages = []
    block = 1
    for r in reversed(factorize(n)):
        block *= r
        stages.append((r, block))
    total_mult = 0
    total_access = 0
    total_twiddle = 0
    print(
        "%5s %11s %12s %14s %14s"
        % ("radix", "butterflies", "mults/bfly", "mults total", "access total")
    )
    for r, l in stages:
        butterflies = n // r
        m, a, t = counts(text, r)
        total_mult += butterflies * (m + t)
        total_access += butterflies * a
        total_twiddle += butterflies * t
        print(
            "%5d %11d %12d %14d %14d"
            % (r, butterflies, m + t, butterflies * (m + t), butterflies * a)
        )
    print()
    print("per element of the transform:")
    print(
        "  multiplications of the small transform : %6.1f"
        % ((total_mult - total_twiddle) / n)
    )
    print(
        "  multiplications of the twiddle factors: %6.1f" % (total_twiddle / n)
    )
    print("  array accesses                       : %6.1f" % (total_access / n))
    print("  total multiplications                : %6.1f" % (total_mult / n))
    print()
    print("the valid lengths of the original: %d, the largest is %d" % (len(table), max(table)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
