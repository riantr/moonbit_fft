#!/usr/bin/env python3
"""Writes the rows of the ecosystem table of `BENCHMARK.md` from the JSON.

The numbers of the document are the numbers of `bench/bench_ecosystem.json`, and
copying them by hand is how a table drifts away from its measurement - this table
has twenty numbers per measurement and was transcribed by hand once already.
The rows are therefore written from the JSON, and `--check` proves that the
document holds the rows of the measurement it claims.

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

# The order of the rows, which is the order of the table of the document.
ORDER = ["port", "hkdsp", "hx/radix4", "hx/bluestein", "lc/radix4",
         "lc/bluestein", "moonnum", "mspec", "mdsp"]
WINDOWS = ["4096", "1024"]

# The first and the last row of the table, so that the block that is replaced
# can be found without knowing its numbers.
FIRST = "| 4 096 | port |"
LAST = "| 1 024 | mdsp |"


def thousands(n: float) -> str:
    """The number with thin spaces between the groups, as the document writes
    the long ones."""
    return "{:,}".format(int(round(n))).replace(",", " ")


def rows(data: dict) -> str:
    out = []
    for window in WINDOWS:
        for side in ORDER:
            out.append("| %s | %s | %s | %s ns | %.3f | %.3fx |" % (
                thousands(int(window)), side,
                thousands(data["lengths"][window][side]),
                thousands(data["median"][window][side]),
                data["per_unit"][window][side],
                data["ratios"][window][side + "/port"],
            ))
    return "\n".join(out) + "\n"


def current(text: str) -> str:
    first = text.index(FIRST)
    end = text.index("\n", text.index(LAST)) + 1
    return text[first:end]


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
    want = rows(data)
    have = current(text)
    if args.check:
        if have != want:
            print("the table of the ecosystem of BENCHMARK.md is not the table "
                  "of %s" % DATA)
            print("the document holds:")
            print(have)
            print("the measurement gives:")
            print(want)
            return 1
        print("OK: the table of the ecosystem of BENCHMARK.md is the table of "
              "the measurement")
        return 0
    DOC.write_text(text.replace(have, want, 1), encoding="utf-8")
    print("wrote %d rows" % (len(ORDER) * len(WINDOWS)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
