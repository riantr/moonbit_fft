"""Checks that the tables of `BENCHMARK.md` agree with the benchmark results.

The document quotes numbers that were produced by `tools/merge_bench.py` and
`tools/compare_bench.py`; this script recomputes them from the raw runs and
compares them with what the document says, so that a table cannot drift away
from the measurements it claims to show.

Usage::

    python tools/check_benchmark.py
"""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
DOC = ROOT / "BENCHMARK.md"

LINE = re.compile(
    r"^CASE\s+(?P<impl>\w+)\s+(?P<workload>\w+)\s+n=(?P<n>\d+)\s+ns_per_op=(?P<ns>[\d.]+)\s*$"
)

# The rows of the three tables of the document, in the order they appear.
ROW = re.compile(
    r"^\|\s*(?P<n>[\d ]+)\s*\|\s*(?P<java>[\d ]+)\s*\|\s*(?P<before>[\d ]+)\s*\|"
    r"\s*\**(?P<after>[\d ]+)\**\s*\|\s*\**(?P<speed>[\d.]+)x\**\s*\|"
    r"\s*\**(?P<ratio>[\d.]+)x\**\s*\|$"
)

# The sections of the document that hold a table.
SECTIONS = {
    "Complex to complex": "c2c",
    "Real to complex": "r2c",
    "Through the image API": "api",
}


def decode(path: pathlib.Path) -> str:
    raw = path.read_bytes()
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return raw.decode("utf-16")
    return raw.decode("utf-8", errors="replace")


def read(path: pathlib.Path) -> dict[tuple[str, int], float]:
    out: dict[tuple[str, int], float] = {}
    for line in decode(path).splitlines():
        m = LINE.match(line.strip())
        if m:
            out[(m.group("workload"), int(m.group("n")))] = float(m.group("ns"))
    return out


def number(text: str) -> int:
    return int(text.replace(" ", ""))


def main() -> int:
    java = read(BUILD / "bench_java_merged.txt")
    before = read(BUILD / "bench_moonbit_before.txt")
    after = read(BUILD / "bench_moonbit_final.txt")

    problems: list[str] = []
    checked = 0
    workload = None
    for line in DOC.read_text(encoding="utf-8").splitlines():
        if line.startswith("### "):
            workload = SECTIONS.get(line[4:].strip())
        if line.startswith("| n |") or line.startswith("| ---"):
            continue
        m = ROW.match(line)
        if not m:
            continue
        n = number(m.group("n"))
        if workload is None:
            problems.append(f"the row for n = {n} is in an unknown section")
            continue
        key = (workload, n)
        if key not in java or key not in before or key not in after:
            problems.append(f"no measurement for {workload} n = {n}")
            continue
        checked += 1
        for label, expected, actual in (
            ("java", number(m.group("java")), java[key]),
            ("before", number(m.group("before")), before[key]),
            ("after", number(m.group("after")), after[key]),
        ):
            if abs(expected - actual) > max(1.0, actual * 0.005):
                problems.append(
                    f"{key[0]} n = {n}: the document says {label} = {expected}, "
                    f"the measurement is {actual:.0f}"
                )
        speed = before[key] / after[key]
        if round(speed, 1) != float(m.group("speed")):
            problems.append(
                f"{key[0]} n = {n}: the document says the speedup is "
                f"{m.group('speed')}x, it is {speed:.1f}x"
            )
        ratio = after[key] / java[key]
        if round(ratio, 1) != float(m.group("ratio")):
            problems.append(
                f"{key[0]} n = {n}: the document says the ratio to the original "
                f"is {m.group('ratio')}x, it is {ratio:.1f}x"
            )

    if checked == 0:
        print("no rows of the document were found")
        return 1
    if problems:
        print(f"{len(problems)} problems in {checked} rows:")
        for problem in problems:
            print("  " + problem)
        return 1
    print(f"OK: the {checked} rows of BENCHMARK.md agree with the measurements")
    return 0


if __name__ == "__main__":
    sys.exit(main())
