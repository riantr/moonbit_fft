#!/usr/bin/env python3
"""Checks that the tables of `BENCHMARK.md` agree with the measurements.

The document quotes numbers that were produced by `tools/bench_compare.py`;
this script recomputes them from the machine readable result of that script
and compares them with what the document says, so that a table cannot drift
away from the measurements it claims to show.

Two kinds of tables are checked:

* the tables of the three workloads, one row per transform length, with the
  runtime of the original, the runtime of the port before the rewrite of the
  kernel, the runtime of the port of today, the speedup, the ratio to the
  original and the spread of the measurements,
* the table of the kernels, which compares the port of today with the port as
  it is committed and with the port of today with the direct small transform.

Usage::

    python tools/check_benchmark.py
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
DOC = ROOT / "BENCHMARK.md"
DATA = BUILD / "bench_compare.json"
# The comparison of the kernels is a separate measurement.
KERNEL_DATA = BUILD / "bench_kernels.json"

# A row of the tables of the workloads:
#
#   | n | Java ns/op | before ns/op | after ns/op | speedup | after / Java | spread |
#
# The numbers may be written with thin spaces and they may be put in bold, and
# the last three carry an `x`.
ROW = re.compile(
    r"^\|\s*\**\s*(?P<n>[\d ]+)\s*\**\s*\|\s*\**\s*(?P<java>[\d ]+)\s*\**\s*\|"
    r"\s*\**\s*(?P<before>[\d ]+)\s*\**\s*\|"
    r"\s*\**\s*(?P<after>[\d ]+)\s*\**\s*\|"
    r"\s*\**\s*(?P<speed>[\d.]+)x\s*\**\s*\|"
    r"\s*\**\s*(?P<ratio>[\d.]+)x\s*\**\s*"
    r"(?:\|\s*\**\s*(?P<spread>[\d.]+)x\s*\**\s*)?\|$"
)

# A row of the table of the kernels:
#
#   | workload | n | head ns/op | direct ns/op | today ns/op | head / today | direct / today |
ROW_KERNELS = re.compile(
    r"^\|\s*(?P<workload>\w+)\s*\|\s*\**\s*(?P<n>[\d ]+)\s*\**\s*\|"
    r"\s*\**\s*(?P<head>[\d ]+)\s*\**\s*\|"
    r"\s*\**\s*(?P<direct>[\d ]+)\s*\**\s*\|\s*\**\s*(?P<today>[\d ]+)\s*\**\s*\|"
    r"\s*\**\s*(?P<over_head>[\d.]+)x\s*\**\s*\|"
    r"\s*\**\s*(?P<over_direct>[\d.]+)x\s*\**\s*\|$"
)

# A row of the table of the prime factor rewrite:
#
#   | workload | n | java ns/op | head ns/op | today ns/op | head / today | today / java |
ROW_GOODTHOMAS = re.compile(
    r"^\|\s*(?P<workload>\w+)\s*\|\s*\**\s*(?P<n>[\d ]+)\s*\**\s*\|"
    r"\s*\**\s*(?P<java>[\d ]+)\s*\**\s*\|"
    r"\s*\**\s*(?P<head>[\d ]+)\s*\**\s*\|"
    r"\s*\**\s*(?P<today>[\d ]+)\s*\**\s*\|"
    r"\s*\**\s*(?P<over_head>[\d.]+)x\s*\**\s*\|"
    r"\s*\**\s*(?P<over_java>[\d.]+)x\s*\**\s*\|$"
)

# A line of a table that is neither a header nor a separator.
DATA_ROW = re.compile(r"^\|\s*\**\s*[\d]")

# The sections of the document that hold a table, and the workload of each.
SECTIONS = {
    "Complex to complex": "c2c",
    "Real to complex": "r2c",
    "Through the image API": "api",
}

# The section that holds the table of the kernels.
KERNEL_SECTION = "The kernels of the committed port"

# The section that holds the table of the prime factor rewrite.
GOODTHOMAS_SECTION = "The prime factor algorithm of the original"


def number(text: str) -> int:
    return int(text.replace(" ", "").replace(" ", ""))


def close(given: float, actual: float, tolerance: float = 0.05, floor: float = 0.05) -> bool:
    """Whether the document and the measurement agree.

    The document writes the numbers with one or two decimals, so a small
    number can not be checked with a relative tolerance alone: `0.3` and
    `0.34` differ by more than five percent of the second one.  The absolute
    floor is the error that the rounding of the document can introduce, half
    of the last written digit.
    """
    return abs(given - actual) <= max(tolerance * abs(actual), floor)


def main() -> int:
    if not DATA.exists():
        print(f"{DATA} does not exist, run tools/bench_compare.py first")
        return 1
    data = json.loads(DATA.read_text(encoding="utf-8"))
    best = data.get("median") or data["best"]
    spread = data.get("spread", {})
    ratios = data.get("ratios", {})
    if "java" not in best or "moonbit" not in best:
        print("the measurement has no java or moonbit side")
        return 1
    old = best.get("old")

    # The table of the kernels comes from the separate comparison.
    kernel_best: dict = {}
    kernel_ratios: dict = {}
    if KERNEL_DATA.exists():
        kernel_data = json.loads(KERNEL_DATA.read_text(encoding="utf-8"))
        kernel_best = kernel_data.get("median") or kernel_data.get("best", {})
        kernel_ratios = kernel_data.get("ratios", {})

    problems: list[str] = []
    checked = 0
    workload = None
    in_kernels = False
    in_goodthomas = False
    for line in DOC.read_text(encoding="utf-8").splitlines():
        if line.startswith("### "):
            title = line[4:].strip()
            workload = SECTIONS.get(title)
            in_kernels = title == KERNEL_SECTION
            in_goodthomas = title == GOODTHOMAS_SECTION
        if line.startswith("| n |") or line.startswith("| ---"):
            continue

        m = ROW_GOODTHOMAS.match(line)
        if m and in_goodthomas:
            checked += 1
            name = m.group("workload")
            n = number(m.group("n"))
            key = f"{name}/{n}"
            java = best["java"].get(key)
            head = best.get("head", {}).get(key)
            today = best["moonbit"].get(key)
            if java is None or head is None or today is None:
                problems.append(f"{key}: the measurement is missing a side")
                continue
            if number(m.group("java")) != int(java):
                problems.append(
                    f"{key}: the document says java = {number(m.group('java'))}, "
                    f"the measurement is {java:.0f}"
                )
            if number(m.group("head")) != int(head):
                problems.append(
                    f"{key}: the document says head = {number(m.group('head'))}, "
                    f"the measurement is {head:.0f}"
                )
            if number(m.group("today")) != int(today):
                problems.append(
                    f"{key}: the document says today = {number(m.group('today'))}, "
                    f"the measurement is {today:.0f}"
                )
            names = ratios.get(key, {})
            for given, measured, what in (
                (m.group("over_head"), names.get("head/moonbit"), "head / today"),
                (m.group("over_java"), names.get("moonbit/java"), "today / java"),
            ):
                if measured is None:
                    continue
                if not close(float(given), measured, 0.02, 0.01):
                    problems.append(
                        f"{key}: the document says {what} = {given}x, "
                        f"the measurement is {measured:.2f}x"
                    )
            continue

        m = ROW_KERNELS.match(line)
        if m and in_kernels:
            checked += 1
            n = number(m.group("n"))
            workload = m.group("workload")
            key = f"{workload}/{n}"
            head = kernel_best.get("head", {}).get(key)
            direct = kernel_best.get("direct", {}).get(key)
            today = kernel_best.get("moonbit", {}).get(key)
            if head is None or direct is None or today is None:
                problems.append(f"{key}: the measurement is missing a side")
                continue
            if number(m.group("head")) != int(head):
                problems.append(
                    f"{key}: the document says head = {number(m.group('head'))}, "
                    f"the measurement is {head:.0f}"
                )
            if number(m.group("direct")) != int(direct):
                problems.append(
                    f"{key}: the document says direct = {number(m.group('direct'))}, "
                    f"the measurement is {direct:.0f}"
                )
            if number(m.group("today")) != int(today):
                problems.append(
                    f"{key}: the document says today = {number(m.group('today'))}, "
                    f"the measurement is {today:.0f}"
                )
            # The ratios are the medians of the per round ratios, they are
            # not the quotient of the two medians.
            names = kernel_ratios.get(key, {})
            for name, given, measured in (
                ("head", m.group("over_head"), names.get("head/moonbit")),
                ("direct", m.group("over_direct"), names.get("direct/moonbit")),
            ):
                if measured is None:
                    continue
                if not close(float(given), measured, 0.02, 0.01):
                    problems.append(
                        f"{key}: the document says {name} / today = {given}x, "
                        f"the measurement is {measured:.2f}x"
                    )
            continue

        m = ROW.match(line)
        if not m:
            # A row that is neither a header nor a separator, and that this
            # script does not understand, is a row that would be checked by
            # nothing.  That must not pass silently.
            if DATA_ROW.match(line):
                problems.append(f"the row {line.strip()!r} is not understood")
            continue
        n = number(m.group("n"))
        if workload is None:
            problems.append(f"the row for n = {n} is in an unknown section")
            continue
        key = f"{workload}/{n}"
        if key not in best["moonbit"]:
            problems.append(f"no measurement for {key}")
            continue
        checked += 1
        java = best["java"].get(key)
        after = best["moonbit"][key]
        before = old.get(key) if old else None
        names = ratios.get(key, {})
        if java is not None and number(m.group("java")) != int(java):
            problems.append(
                f"{key}: the document says java = {number(m.group('java'))}, "
                f"the measurement is {java:.0f}"
            )
        if before is not None and number(m.group("before")) != int(before):
            problems.append(
                f"{key}: the document says before = {number(m.group('before'))}, "
                f"the measurement is {before:.0f}"
            )
        if number(m.group("after")) != int(after):
            problems.append(
                f"{key}: the document says after = {number(m.group('after'))}, "
                f"the measurement is {after:.0f}"
            )
        if before is not None:
            speed = names.get("old/moonbit")
            if speed is None:
                speed = before / after
            if not close(float(m.group("speed")), speed):
                problems.append(
                    f"{key}: the document says the speedup is {m.group('speed')}x, "
                    f"it is {speed:.1f}x"
                )
        if java:
            ratio = names.get("moonbit/java")
            if ratio is None:
                ratio = after / java
            if not close(float(m.group("ratio")), ratio):
                problems.append(
                    f"{key}: the document says the ratio to the original is "
                    f"{m.group('ratio')}x, it is {ratio:.1f}x"
                )
        given_spread = m.group("spread")
        measured = spread.get("moonbit", {}).get(key)
        if given_spread and measured is not None:
            if not close(float(given_spread), measured, 0.02, 0.01):
                problems.append(
                    f"{key}: the document says the spread is {given_spread}x, "
                    f"the measurement is {measured:.2f}x"
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
