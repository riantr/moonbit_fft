"""Negative control for the table of the ecosystem in `BENCHMARK.md`.

`tools/check_benchmark.py` holds the numbers of the document against the
measurements of `bench/`, and a check that has never been seen to fail is not
known to check anything.  This script breaks one number at a time and asks
whether the gate turns red for the reason that number is about:

* the time of the port and the time of the package,
* the ratio of the two of them,
* the cost of an element of each side,
* the length of the port, which is the length of its own table of valid lengths,
* the number of rounds of the measurement,
* the version of the package that was measured,
* a row the gate does not understand, which must not pass silently,
* a row that is missing, which must not pass silently either.

A row of this table is easier to break than a kernel is: the numbers of the
document are the numbers of a JSON file, so a check that compares them is the
only thing that stands between the document and a table that has drifted away
from what was measured.  The control is therefore part of the measurement and
not an extra.

Every mutation is undone from the bytes that were read at the beginning, and
the SHA-256 of the document is verified at the end, so a mutation cannot be
left behind.

There is one mutation that is **not** here: the numbers of the table of the
workloads are checked the same way, and they were controlled the same way when
they were written.  This script controls the table that was added last, which is
the one whose check is the newest.

Usage:
    python tools/negative_control_benchmark.py
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOC = ROOT / "BENCHMARK.md"
GATE = ROOT / "tools" / "check_benchmark.py"

# (what the mutation is about, the text to replace, the replacement, the phrase
# the gate has to print when it turns red)
MUTATIONS = [
    (
        "the time of the port",
        "| 4 096 | 4 095 | 41 953 ns",
        "| 4 096 | 4 095 | 41 000 ns",
        "the document says the port takes",
    ),
    (
        "the time of the package",
        "| 41 815 ns |",
        "| 41 000 ns |",
        "the document says the package takes",
    ),
    (
        "the ratio of the two of them",
        "| 0.997x |",
        "| 0.900x |",
        "the document says the ratio is",
    ),
    (
        "the cost of an element of the port",
        "| 0.997x | 0.854 |",
        "| 0.997x | 0.800 |",
        "the cost of an element of the port",
    ),
    (
        "the cost of an element of the package",
        "| 0.854 | 0.851 |",
        "| 0.854 | 0.800 |",
        "the cost of an element of the package",
    ),
    (
        "the length of the port",
        "| 4 096 | 4 095 |",
        "| 4 096 | 4 096 |",
        "the document says the port is measured at",
    ),
    (
        "the number of rounds",
        "The measurement has 16 rounds.",
        "The measurement has 12 rounds.",
        "does not say that the measurement has",
    ),
    (
        "the version of the package",
        "measured at version\n0.1.4.",
        "measured at version\n0.1.5.",
        "does not name the version",
    ),
    (
        "a row that does not parse",
        "| 1 024 | 1 008 | 8 054 ns",
        "| 1 024 | 1 008 | 8 054 us",
        "is not understood",
    ),
    (
        "a missing row",
        "| 1 024 | 1 008 | 8 054 ns | 7 479 ns | 0.939x | 0.801 | 0.730 |\n",
        "",
        "has no row for the window",
    ),
]


def gate() -> tuple[int, str]:
    """Runs the gate of the document and returns its exit code and output."""
    proc = subprocess.run(
        [sys.executable, str(GATE)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=str(ROOT),
    )
    return proc.returncode, proc.stdout.decode("utf-8", "replace")


def main() -> int:
    original = DOC.read_bytes()
    digest = hashlib.sha256(original).hexdigest()
    text = original.decode("utf-8")
    problems = 0
    try:
        code, out = gate()
        if code != 0:
            print("the gate is red before any mutation, it has to be green:")
            print(out)
            return 1
        print("the gate is green before the mutations")
        print()
        for what, before, after, expected in MUTATIONS:
            if text.count(before) != 1:
                print("SKIP %-42s the text appears %d times" % (
                    what, text.count(before)))
                problems += 1
                continue
            DOC.write_bytes(text.replace(before, after, 1).encode("utf-8"))
            code, out = gate()
            good = code != 0 and expected in out
            print("%-4s %-42s the gate exits %d" % (
                "OK" if good else "FAIL", what, code))
            if not good:
                problems += 1
                print("     the gate had to print %r" % expected)
                print("     " + out.strip().replace("\n", "\n     "))
            DOC.write_bytes(original)
    finally:
        DOC.write_bytes(original)
    if hashlib.sha256(DOC.read_bytes()).hexdigest() != digest:
        print("the document was not restored")
        return 1
    print()
    print("the document is restored, sha256 %s" % digest)
    print("%d problems" % problems)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
