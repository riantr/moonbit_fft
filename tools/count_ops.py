#!/usr/bin/env python3
"""Counts the operations of the Good-Thomas transform.

The script counts the work of one butterfly of every radix on both sides of
the port: the generated MoonBit kernels of `moonbit_fft2/kernels.mbt` and the
kernels of the Java original, `edu.mines.jtk.dsp.Pfacc`.  From those numbers it
derives the work of a whole transform of a given length.

Both sides run the same algorithm, the prime factor algorithm of the original:
the length is split into pairwise coprime factors and every factor selects a
small kernel.  Because the factors are coprime, no stage needs a twiddle
factor, and the twist of the original is in the roots of unity of the small
transforms.

The counting rules are these.

* A multiplication is a `*` in the body of the butterfly.  The index
  arithmetic is not counted: the Java kernels rotate their indices instead of
  multiplying them, and the MoonBit kernels keep the positions in variables.
* An addition is a `+` or a `-` on the values of the transform.  The additions
  of the addresses are not counted.
* An access is a read or a write of an element of the transform.  The roots of
  unity of the MoonBit kernels are read once per stage and not once per
  butterfly, so they are counted separately.
* A butterfly of the radix `r` works on `r` elements, so the work of a stage is
  the work of one butterfly divided by `r` per element.

The additions are counted as well as the multiplications, because the two
kernels trade one against the other: the symmetry of the roots of unity saves
multiplications and costs additions.  The transform is bound by the number of
floating point operations, not by the number of multiplications alone.

Usage::

    python tools/count_ops.py
    python tools/count_ops.py --lengths 240,32760,720720
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_KERNELS = ROOT / "moonbit_fft2" / "kernels.mbt"
DEFAULT_JAVA = ROOT / "build" / "jtsrc" / "src" / "edu" / "mines" / "jtk" / "dsp" / "Pfacc.java"

# The factors of the original, the order is the one of `Pfacc._kfac`.
KFAC = [16, 13, 11, 9, 8, 7, 5, 4, 3, 2]

# The radices the valid lengths are built from.
RADICES = [2, 3, 4, 5, 7, 8, 9, 11, 13, 16]

# The valid lengths of the original, they are the ones of `Pfacc._ntable`.
VALID_LENGTHS = [
    1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 18, 20, 21, 22, 24, 26, 28,
    30, 33, 35, 36, 39, 40, 42, 44, 45, 48, 52, 55, 56, 60, 63, 65, 66, 70, 72, 77,
    78, 80, 84, 88, 90, 91, 99, 104, 105, 110, 112, 117, 120, 126, 130, 132, 140,
    143, 144, 154, 156, 165, 168, 176, 180, 182, 195, 198, 208, 210, 220, 231,
    234, 240, 252, 260, 264, 273, 280, 286, 308, 312, 315, 330, 336, 360, 364, 385,
    390, 396, 420, 429, 440, 455, 462, 468, 495, 504, 520, 528, 546, 560, 572, 585,
    616, 624, 630, 660, 693, 715, 720, 728, 770, 780, 792, 819, 840, 858, 880, 910,
    924, 936, 990, 1001, 1008, 1040, 1092, 1144, 1155, 1170, 1232, 1260, 1287,
    1320, 1365, 1386, 1430, 1456, 1540, 1560, 1584, 1638, 1680, 1716, 1820, 1848,
    1872, 1980, 2002, 2145, 2184, 2288, 2310, 2340, 2520, 2574, 2640, 2730, 2772,
    2860, 3003, 3080, 3120, 3276, 3432, 3465, 3640, 3696, 3960, 4004, 4095, 4290,
    4368, 4620, 4680, 5005, 5040, 5148, 5460, 5544, 5720, 6006, 6160, 6435, 6552,
    6864, 6930, 7280, 7920, 8008, 8190, 8580, 9009, 9240, 9360, 10010, 10296,
    10920, 11088, 11440, 12012, 12870, 13104, 13860, 15015, 16016, 16380, 17160,
    18018, 18480, 20020, 20592, 21840, 24024, 25740, 27720, 30030, 32760, 34320,
    36036, 40040, 45045, 48048, 51480, 55440, 60060, 65520, 72072, 80080, 90090,
    102960, 120120, 144144, 180180, 240240, 360360, 720720,
]


def coprime_factors(n: int) -> list[int]:
    """The factors of a length, the way the original splits it.

    The factors are taken from `Pfacc._kfac` in its order and they are
    pairwise coprime, because a factor is a prime power and the order takes
    every prime power of the length only once.
    """
    factors: list[int] = []
    left = n
    for f in KFAC:
        if left % f == 0:
            left //= f
            factors.append(f)
    if left != 1:
        raise ValueError("%d is not a valid length" % n)
    return factors


def strip_comments(text: str) -> str:
    """Removes the comments of a piece of source, they hold no operation."""
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    text = re.sub(r"//[^\n]*", " ", text)
    return text


def moonbit_kernel(text: str, r: int) -> tuple[int, int, int, int]:
    """The work of one butterfly of the radix `r` of the MoonBit kernels.

    It returns the number of multiplications, the number of additions, the
    number of accesses of the transform and the number of reads of the roots
    of unity.  The roots of unity are read once per stage, before the rounds
    of the butterflies.

    The kernels are generated per radix *and* per twist, and the structure of
    the butterfly is the same for every twist of a radix, so the first
    variant of the radix is counted.
    """
    start = text.index("fn stage_r%d_mu" % r)
    end = text.find("\nfn ", start + 1)
    body = text[start : end if end > 0 else len(text)]
    body = strip_comments(body)
    # The signature of the function is not part of its work: the two brackets
    # of `Array[Double]` are the type of the two arguments, not a read of a
    # table.  The body starts at the opening brace of the function.
    opening = body.index("{")
    body = body[opening:]
    # The roots of unity are loaded before the loop of the rounds.
    loop = body.index("while i < m {")
    head = body[:loop]
    rounds = body[loop:]
    # The values of the transform are the ones the butterfly computes; the
    # lines that move the positions of the rounds are the address arithmetic.
    values = [
        ln
        for ln in rounds.splitlines()
        if not re.match(r"\s*(if p\d+ < limit|p\d+ = p\d+ \+|limit = limit|i = i)", ln)
    ]
    text_of_values = "\n".join(values)
    mults = len(re.findall(r"\*", text_of_values))
    adds = len(re.findall(r"[+-]", text_of_values))
    accesses = len(re.findall(r"\[", rounds))
    # The reads of the table of the roots of unity, which the port does not
    # have any more: the constants of the small transform are literals in
    # the code.
    tables = len(re.findall(r"consts\[", head))
    return mults, adds, accesses, tables


def java_kernel(text: str, r: int) -> tuple[int, int, int]:
    """The work of one butterfly of the radix `r` of the Java original.

    It returns the number of multiplications, the number of additions and the
    number of accesses of the transform.  The constants of the original are
    literals in the code, so they cost nothing.
    """
    match = re.search(r"private static void pfa%d\(float\[\] z," % r, text)
    if match is None:
        raise ValueError("the Java original has no kernel of the radix %d" % r)
    start = match.start()
    # The body of the function ends at its closing brace, which is found by
    # matching the braces.  The next function of the class is not a boundary:
    # `pfa16` is followed by `transform2a` and `transform2b`, which are not
    # kernels, and counting them would charge the radix 16 for the work of
    # another algorithm.
    opening = text.index("{", match.end())
    depth = 0
    closing = opening
    for index in range(opening, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                closing = index
                break
    body = text[start : closing + 1]
    body = strip_comments(body)
    loop = body.index("for (int i = 0; i < m; ++i) {")
    rounds = body[loop:]
    # The lines that declare an integer hold the addresses, the other ones
    # hold the arithmetic of the values.  The addresses inside the brackets
    # are removed, they are not arithmetic of the values.
    #
    # The rotation of the positions at the end of the round is address
    # arithmetic as well, and it is not caught by the rule above: the line
    # `int jt = j12 + 2;` declares an integer, but the lines that follow it,
    # `j12 = j11 + 2;` and the like, do not.  They are caught here, so that
    # the additions of the addresses are not counted, as the rule says.
    values = [
        ln
        for ln in rounds.splitlines()
        if "int " not in ln and not (re.match(r"\s*j\d+\s*=", ln) and "z[" not in ln)
    ]
    text_of_values = "\n".join(values)
    text_of_values = re.sub(r"\[[^\]]*\]", "[]", text_of_values)
    mults = len(re.findall(r"\*", text_of_values))
    adds = len(re.findall(r"[+-]", text_of_values))
    accesses = len(re.findall(r"z\[", rounds))
    return mults, adds, accesses


def per_element(
    n: int,
    mults: dict[int, int],
    accesses: dict[int, int],
    adds: dict[int, int] | None = None,
) -> tuple[float, float, float]:
    """The work of a transform of the length `n` per element."""
    total_mult = 0.0
    total_access = 0.0
    total_add = 0.0
    for r in coprime_factors(n):
        total_mult += mults[r] / r
        total_access += accesses[r] / r
        if adds is not None:
            total_add += adds[r] / r
    return total_mult, total_access, total_add


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--kernels",
        type=pathlib.Path,
        default=DEFAULT_KERNELS,
        help="the generated MoonBit kernels to count",
    )
    parser.add_argument(
        "--java",
        type=pathlib.Path,
        default=DEFAULT_JAVA,
        help="the decompiled Java original to count",
    )
    parser.add_argument(
        "--lengths",
        default="240,10920,32760,720720",
        help="the lengths to report, separated by commas",
    )
    args = parser.parse_args()

    kernels = args.kernels.read_text(encoding="utf-8")
    java = args.java.read_text(encoding="utf-8")

    mb_mult: dict[int, int] = {}
    mb_add: dict[int, int] = {}
    mb_access: dict[int, int] = {}
    mb_table: dict[int, int] = {}
    ja_mult: dict[int, int] = {}
    ja_add: dict[int, int] = {}
    ja_access: dict[int, int] = {}
    for r in RADICES:
        mb_mult[r], mb_add[r], mb_access[r], mb_table[r] = moonbit_kernel(kernels, r)
        ja_mult[r], ja_add[r], ja_access[r] = java_kernel(java, r)

    print("one butterfly of each radix:")
    print(
        "%6s %9s %9s %9s %10s %9s %9s %9s"
        % (
            "radix",
            "mults mb",
            "adds mb",
            "access mb",
            "table mb",
            "mults java",
            "adds java",
            "access java",
        )
    )
    for r in RADICES:
        print(
            "%6d %9d %9d %9d %10d %9d %9d %9d"
            % (
                r,
                mb_mult[r],
                mb_add[r],
                mb_access[r],
                mb_table[r],
                ja_mult[r],
                ja_add[r],
                ja_access[r],
            )
        )

    print()
    print("the work of a transform per element:")
    print(
        "%9s %7s %11s %11s %11s %11s %11s %11s %8s %8s"
        % (
            "length",
            "stages",
            "mults mb",
            "adds mb",
            "fp mb",
            "mults java",
            "adds java",
            "fp java",
            "fp x",
            "acc x",
        )
    )
    lengths = [int(x) for x in args.lengths.split(",") if x.strip()]
    for n in lengths:
        mb_m, mb_a, mb_s = per_element(n, mb_mult, mb_access, mb_add)
        ja_m, ja_a, ja_s = per_element(n, ja_mult, ja_access, ja_add)
        print(
            "%9d %7d %11.1f %11.1f %11.1f %11.1f %11.1f %11.1f %8.2f %8.2f"
            % (
                n,
                len(coprime_factors(n)),
                mb_m,
                mb_s,
                mb_m + mb_s,
                ja_m,
                ja_s,
                ja_m + ja_s,
                (mb_m + mb_s) / (ja_m + ja_s) if ja_m + ja_s else 0.0,
                mb_a / ja_a if ja_a else 0.0,
            )
        )

    # The mean over every valid length, weighted by the length itself.
    print()
    print("the mean over the %d valid lengths, weighted by the length:" % len(VALID_LENGTHS))
    weight = 0
    mb_m = mb_s = mb_a = 0.0
    ja_m = ja_s = ja_a = 0.0
    for n in VALID_LENGTHS:
        m, a, s = per_element(n, mb_mult, mb_access, mb_add)
        jm, ja, js = per_element(n, ja_mult, ja_access, ja_add)
        mb_m += m * n
        mb_s += s * n
        mb_a += a * n
        ja_m += jm * n
        ja_s += js * n
        ja_a += ja * n
        weight += n
    print(
        "  multiplications : moonbit %5.1f, java %5.1f"
        % (mb_m / weight, ja_m / weight)
    )
    print("  additions       : moonbit %5.1f, java %5.1f" % (mb_s / weight, ja_s / weight))
    print(
        "  floating point  : moonbit %5.1f, java %5.1f"
        % ((mb_m + mb_s) / weight, (ja_m + ja_s) / weight)
    )
    print("  accesses        : moonbit %5.1f, java %5.1f" % (mb_a / weight, ja_a / weight))
    return 0


if __name__ == "__main__":
    sys.exit(main())
