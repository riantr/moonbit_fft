"""Negative control for the table of the ecosystem in `BENCHMARK.md`.

`tools/check_benchmark.py` holds the numbers of the document against the
measurements of `bench/`, and a check that has never been seen to fail is not
known to check anything.  This script breaks one number at a time and asks
whether the gate turns red for the reason that number is about:

* the time of a side, the cost of an element of a side and the ratio of a side
  to the port,
* the length a side is measured at, which is the length of the port's own table
  of valid lengths for the port and the window itself for the packages,
* the number of rounds of the measurement,
* the version of a package that was measured,
* a row the gate does not understand, which must not pass silently,
* a row that is missing, and a row that is written twice, which must not pass
  silently either.

The rows of these mutations are built from `bench/bench_ecosystem.json`, which is
also what the rows of the document are built from, so a new measurement needs no
transcription here either.  A row that the document does not hold exactly as the
JSON describes it is reported as a skip, which is a problem of its own.

Every mutation is undone from the bytes that were read at the beginning, and the
SHA-256 of the document is verified at the end, so a mutation cannot be left
behind.

Usage:
    python tools/negative_control_benchmark.py
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOC = ROOT / "BENCHMARK.md"
GATE = ROOT / "tools" / "check_benchmark.py"
DATA = ROOT / "bench" / "bench_ecosystem.json"


def thousands(n) -> str:
    return "{:,}".format(int(round(n))).replace(",", " ")


def visit(node, *path):
    """The value at a path of the JSON, so that this script and the document
    read the numbers the same way."""
    for key in path:
        node = node[key]
    return node


def build_mutations(data: dict) -> list[tuple[str, str, str, str]]:
    """The mutations, each one built out of the measurement itself."""

    def row(window: str, side: str, *, ns=None, unit=None, ratio=None,
            n=None, unit_text="ns") -> str:
        return "| %s | %s | %s | %s %s | %.3f | %.3fx |" % (
            thousands(int(window)), side,
            thousands(n if n is not None
                      else visit(data, "lengths", window, side)),
            thousands(ns if ns is not None
                      else visit(data, "median", window, side)),
            unit_text,
            unit if unit is not None
            else visit(data, "per_unit", window, side),
            ratio if ratio is not None
            else visit(data, "ratios", window, side + "/port"),
        )

    def up(value: float, factor: float = 1.05) -> float:
        # Five percent and not two: the gate accepts a ratio that is within two
        # percent of the measurement, so a mutation of two percent would sit on
        # the boundary of its own tolerance and could pass.
        return value * factor

    port_4096 = visit(data, "median", "4096", "port")
    hkdsp_4096 = visit(data, "median", "4096", "hkdsp")
    ratio_4096 = visit(data, "ratios", "4096", "hx/radix4/port")
    unit_1024 = visit(data, "per_unit", "1024", "moonnum")
    rounds = data["rounds"]
    version = data["ecosystem"][0]["version"]
    bump = "%s" % version
    # The last digit of the version, so that the mutation does not have to know
    # the shape of the number.
    bumped = bump[:-1] + str((int(bump[-1]) + 1) % 10)

    return [
        (
            "the time of the port",
            row("4096", "port"),
            row("4096", "port", ns=up(port_4096)),
            "the document says %d ns" % round(up(port_4096)),
        ),
        (
            "the time of a package",
            row("4096", "hkdsp"),
            row("4096", "hkdsp", ns=up(hkdsp_4096)),
            "the document says %d ns" % round(up(hkdsp_4096)),
        ),
        (
            "the ratio of a side to the port",
            row("4096", "hx/radix4"),
            row("4096", "hx/radix4", ratio=up(ratio_4096)),
            "the ratio to the port is %.3f" % up(ratio_4096),
        ),
        (
            "the cost of an element",
            row("1024", "moonnum"),
            row("1024", "moonnum", unit=up(unit_1024)),
            "the cost of an element is %.3f" % up(unit_1024),
        ),
        (
            "the length the port is measured at",
            row("4096", "port"),
            row("4096", "port", n=4096),
            "the document says it is measured at 4096",
        ),
        (
            "the number of rounds",
            "The measurement has %d rounds." % rounds,
            "The measurement has %d rounds." % (rounds - 4),
            "does not say that the measurement has",
        ),
        (
            "the version of a package",
            "`%s` %s" % (data["ecosystem"][0]["package"], version),
            "`%s` %s" % (data["ecosystem"][0]["package"], bumped),
            "does not name the version",
        ),
        (
            "a row that does not parse",
            row("1024", "mspec"),
            row("1024", "mspec", unit_text="us"),
            "is not understood",
        ),
        (
            "a missing row",
            row("1024", "mdsp") + "{EOL}",
            "",
            "has no row for",
        ),
        (
            "a row written twice",
            row("1024", "mdsp") + "{EOL}",
            row("1024", "mdsp") + "{EOL}" + row("1024", "mdsp") + "{EOL}",
            "is written twice",
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
    data = json.loads(DATA.read_text(encoding="utf-8"))
    original = DOC.read_bytes()
    digest = hashlib.sha256(original).hexdigest()
    text = original.decode("utf-8")
    # The document is written with the line ending of the platform it was edited
    # on, so a mutation that spans a line is written with the ending the file
    # actually has.
    eol = "\r\n" if "\r\n" in text else "\n"
    problems = 0
    try:
        code, out = gate()
        if code != 0:
            print("the gate is red before any mutation, it has to be green:")
            print(out)
            return 1
        print("the gate is green before the mutations")
        print()
        for what, before, after, expected in build_mutations(data):
            before = before.replace("{EOL}", eol)
            after = after.replace("{EOL}", eol)
            if text.count(before) != 1:
                print("SKIP %-42s the text appears %d times: %r" % (
                    what, text.count(before), before))
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
