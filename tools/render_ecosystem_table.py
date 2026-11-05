#!/usr/bin/env python3
"""Writes the rows of the ecosystem tables of `BENCHMARK.md` from the JSON.

The numbers of the document are the numbers of `bench/bench_ecosystem.json`, and
copying them by hand is how a table drifts away from its measurement - this table
has twenty numbers per measurement and was transcribed by hand once already.
The rows are therefore written from the JSON, and `--check` proves that the
document holds the rows of the measurement it claims.

Two tables are written: the forward transform, taken over the forward port, and
the inverse transform, taken over the **unnormalised** inverse of the port.  That
base is the same amount of work as a forward transform of the same length, so a
normalised inverse of a package - which is that work plus one pass over the
result - reads as that work plus that pass, and a package that scales its inverse
and one that does not are still comparable.

`tools/check_benchmark.py` does the same comparison with its own parser, and it
is the one that runs before a commit.  This script is the other direction: it
*writes* the rows, so that a new measurement needs no transcription at all.

Usage::

    python tools/render_ecosystem_table.py
    python tools/render_ecosystem_table.py --check
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOC = ROOT / "BENCHMARK.md"
DATA = ROOT / "bench" / "bench_ecosystem.json"

# The order of the rows, which is the order of the tables of the document.
ORDER = ["port", "hkdsp", "hx/radix4", "hx/bluestein", "lc/radix4",
         "lc/bluestein", "moonnum", "mspec", "mdsp"]
INVERSE_ORDER = ["port/bfft", "port/ifft", "hkdsp/ifft", "hx/ifft-bluestein",
                 "hx/ifft-radix2", "lc/ifft", "lc/ifft-radix4", "moonnum/ifft",
                 "mspec/ifft"]
WINDOWS = ["4096", "1024"]

# The first and the last row of a table, so that the block that is replaced can
# be found without knowing its numbers.
TABLES = [
    # the forward table, based on the forward port
    (("| 4 096 | port |", "| 1 024 | mdsp |"), ORDER, "ratios", "/port"),
    # the inverse table, based on the unnormalised inverse of the port
    (("| 4 096 | port/bfft |", "| 1 024 | mspec/ifft |"), INVERSE_ORDER,
     "inverse_ratios", "/port/bfft"),
]


def thousands(n: float) -> str:
    """The number with spaces between the groups, as the document writes the
    long ones."""
    return "{:,}".format(int(round(n))).replace(",", " ")


def rows(data: dict, order: list[str], ratios: str, base: str) -> str:
    out = []
    for window in WINDOWS:
        for side in order:
            out.append("| %s | %s | %s | %s ns | %.3f | %.3fx |" % (
                thousands(int(window)), side,
                thousands(data["lengths"][window][side]),
                thousands(data["median"][window][side]),
                data["per_unit"][window][side],
                data[ratios][window][side + base],
            ))
    return "\n".join(out) + "\n"


def current(text: str, first: str, last: str) -> str:
    """The block of the table, from its first row to its last one."""
    for anchor in (first, last):
        if text.count(anchor) != 1:
            raise SystemExit(
                "the anchor %r appears %d times in %s, it has to appear once"
                % (anchor, text.count(anchor), DOC))
    start = text.index(first)
    end = text.index("\n", text.index(last)) + 1
    return text[start:end]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="do not write, only say whether the document holds the rows of "
        "the measurement",
    )
    args = parser.parse_args()

    data = json.loads(DATA.read_text(encoding="utf-8"))
    text = DOC.read_text(encoding="utf-8")
    problems = 0
    for (first, last), order, ratios, base in TABLES:
        want = rows(data, order, ratios, base)
        have = current(text, first, last)
        if have != want:
            problems += 1
            if args.check:
                print("the table %s ... %s of BENCHMARK.md is not the table of "
                      "%s" % (first, last, DATA))
                print("the document holds:")
                print(have)
                print("the measurement gives:")
                print(want)
            else:
                text = text.replace(have, want, 1)
    if args.check:
        if problems:
            return 1
        print("OK: both tables of the ecosystem of BENCHMARK.md are the tables "
              "of the measurement")
        return 0
    DOC.write_text(text, encoding="utf-8")
    print("wrote %d rows in %d tables"
          % (sum(len(order) for _, order, _, _ in TABLES), len(TABLES)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
