#!/usr/bin/env python3
"""Checks that the tables of `BENCHMARK.md` agree with the measurements.

The document quotes numbers that were produced by `tools/bench_compare.py`;
this script recomputes them from the machine readable result of that script
and compares them with what the document says, so that a table cannot drift
away from the measurements it claims to show.

The measurements of the rounds are tracked in `bench/`, one file per round,
so that the check runs on a fresh clone, without running the benchmark first.

Two kinds of tables are checked:

* the tables of the three workloads, one row per transform length, with the
  runtime of the original, the runtime of the port before the rewrite of the
  kernel, the runtime of the port of today, the speedup, the ratio to the
  original and the spread of the measurements,
* the table of the kernels, which compares the port of today with the port as
  it is committed and with the port of today with the direct small transform,
* the tables of the rounds, the prime factor rewrite and the rewrite of the
  butterflies, and the control of the factorisation,
* the table of the comparison of the two builds of the transform, with and
  without the copy of the input into the output,
* the table of the measurement of the machine, which shows the transform of
  the port next to the clock and the memory system of the machine.

Usage::

    python tools/check_benchmark.py
"""

from __future__ import annotations

import json
import math
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
# The measurements of the rounds are tracked, so that the tables of the
# document can be checked on a fresh clone.
BENCH = ROOT / "bench"
DOC = ROOT / "BENCHMARK.md"
# The two documents of the repository that repeat the numbers of the
# benchmark.  They are checked too, because a number that is corrected in
# one document and left in the other is a drift of its own.
READMES = (ROOT / "README.md", ROOT / "moonbit_fft2" / "README.md")
DATA = BENCH / "bench_compare.json"
# The comparison of the kernels is a separate measurement.
KERNEL_DATA = BENCH / "bench_kernels.json"
# The measurement of the round that replaced the kernel by the prime factor
# algorithm of the original.  The `head` side of a comparison is the port as
# it is committed, so every round needs its own measurement.
GT_DATA = BENCH / "bench_goodthomas.json"
# The measurement of the control of the factorisation of the original.
DIRECT_DATA = BENCH / "bench_direct.json"

# The comparison of the two builds of the transform, with and without the copy
# of the input into the output.
COPY_DATA = BENCH / "bench_copy.json"

# The measurement of the transform next to the state of the machine.
MACHINE_DATA = BENCH / "bench_machine.json"

# The comparison of the wasm build of the port with the native build.
TARGET_DATA = BENCH / "bench_target.json"

# The comparison of the port with the best package of the ecosystem.
ECO_DATA = BENCH / "bench_ecosystem.json"

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
KERNEL_SECTION = "The symmetry of the roots of unity"

# The section that holds the table of the prime factor rewrite.
GOODTHOMAS_SECTION = "The prime factor algorithm of the original"

# The section that holds the table of the rewrite of the butterflies.
ORIGINAL_SECTION = "The butterflies of the original"

# The section that holds the table of the control of the factorisation.
DIRECT_SECTION = "The control of the factorisation"

# A row of the table of the control:
#
#   | workload | n | direct ns/op | today ns/op | direct / today |
ROW_DIRECT = re.compile(
    r"^\|\s*(?P<workload>\w+)\s*\|\s*\**\s*(?P<n>[\d ]+)\s*\**\s*\|"
    r"\s*\**\s*(?P<direct>[\d ]+)\s*\**\s*\|"
    r"\s*\**\s*(?P<today>[\d ]+)\s*\**\s*\|"
    r"\s*\**\s*(?P<over_direct>[\d.]+)x\s*\**\s*\|$"
)

# A row of the table of the comparison of the two builds:
#
#   | the copy of the input first | 422 122 ns | 1.085x |
ROW_COPY = re.compile(
    r"^\|\s*(?P<what>[^|]+?)\s*\|\s*\**\s*(?P<median>[\d ]+)\s*ns\s*\**\s*\|"
    r"\s*\**\s*(?P<ratio>[\d.]+)x\s*\**\s*\|$"
)

# A row of the table of the machine:
#
#   | 0 | 441 497 ns | 62 450 us | 0.594 ns/elem |
ROW_MACHINE = re.compile(
    r"^\|\s*\**\s*(?P<round>\d+)\s*\**\s*\|"
    r"\s*\**\s*(?P<transform>[\d ]+)\s*ns\s*\**\s*\|"
    r"\s*\**\s*(?P<clock>[\d ]+)\s*us\s*\**\s*\|"
    r"\s*\**\s*(?P<memory>[\d.]+)\s*ns/elem\s*\**\s*\|$"
)

# A row of the table of the two sessions of the machine:
#
#   | in the session of `tools/bench_compare.py` | 245 929 ns | 857 332 ns | 3.44x |
ROW_IDLE = re.compile(
    r"^\|\s*(?P<when>[^|]+?)\s*\|\s*\**\s*(?P<java>[\d ]+)\s*ns\s*\**\s*\|"
    r"\s*\**\s*(?P<port>[\d ]+)\s*ns\s*\**\s*\|"
    r"\s*\**\s*(?P<ratio>[\d.]+)x\s*\**\s*\|$"
)

# A row of the table of the two targets:
#
#   | wasm, the default of `moon run` | 992 911 ns | 2.605x |
ROW_TARGET = re.compile(
    r"^\|\s*\**\s*(?P<what>[^|]+?)\s*\**\s*\|\s*\**\s*(?P<ns>[\d ]+)\s*ns\s*\**\s*\|"
    r"\s*\**\s*(?P<ratio>[\d.]+)x\s*\**\s*\|$"
)

# A row of the table of the ecosystem:
#
#   | 4 096 | 4 095 | 41 953 ns | 41 815 ns | 0.997x | 0.854 | 0.851 |
ROW_ECO = re.compile(
    r"^\|\s*\**\s*(?P<window>[\d ]+)\s*\**\s*\|"
    r"\s*\**\s*(?P<port_n>[\d ]+)\s*\**\s*\|"
    r"\s*\**\s*(?P<port>[\d ]+)\s*ns\s*\**\s*\|"
    r"\s*\**\s*(?P<package>[\d ]+)\s*ns\s*\**\s*\|"
    r"\s*\**\s*(?P<ratio>[\d.]+)x\s*\**\s*\|"
    r"\s*\**\s*(?P<port_unit>[\d.]+)\s*\**\s*\|"
    r"\s*\**\s*(?P<package_unit>[\d.]+)\s*\**\s*\|$"
)

# The section that holds the table of the ecosystem.
ECO_SECTION = "The best of the ecosystem"

# The section that holds the table of the comparison of the two builds.
COPY_SECTION = "The transform reads the input and writes the output"

# The section that holds the table of the measurement of the machine.
MACHINE_SECTION = "The machine loses its speed, and it hits everything"

# The section that holds the table of the two sessions of the machine.
IDLE_SECTION = "The machine is not idle, and the port feels it more than the original"

# The section that holds the table of the two targets.
TARGET_SECTION = "The target is the second thing to get right"


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

    # The table of the prime factor rewrite comes from the measurement of the
    # round that did that rewrite.  The kernel that transformed `O(n^2)` is the
    # same code in every round and it is thousands of times slower than the
    # port, so the session it was measured in does not matter.
    gt_best: dict = {}
    gt_ratios: dict = {}
    if GT_DATA.exists():
        gt_data = json.loads(GT_DATA.read_text(encoding="utf-8"))
        gt_best = gt_data.get("median") or gt_data.get("best", {})
        gt_ratios = gt_data.get("ratios", {})
    if old is None:
        old = gt_best.get("old")

    # The table of the control of the factorisation comes from its own
    # measurement.
    direct_best: dict = {}
    direct_ratios: dict = {}
    if DIRECT_DATA.exists():
        direct_data = json.loads(DIRECT_DATA.read_text(encoding="utf-8"))
        direct_best = direct_data.get("median") or direct_data.get("best", {})
        direct_ratios = direct_data.get("ratios", {})

    # The comparison of the two builds of the transform, with and without the
    # copy of the input into the output.
    copy_data: dict = {}
    if COPY_DATA.exists():
        copy_data = json.loads(COPY_DATA.read_text(encoding="utf-8"))

    # The measurement of the transform next to the state of the machine.
    machine_data: dict = {}
    if MACHINE_DATA.exists():
        machine_data = json.loads(MACHINE_DATA.read_text(encoding="utf-8"))
    machine_rounds = {
        int(r["round"]): r for r in machine_data.get("rounds", [])
    }

    # The comparison of the wasm build with the native build.
    target_data: dict = {}
    if TARGET_DATA.exists():
        target_data = json.loads(TARGET_DATA.read_text(encoding="utf-8"))

    # The comparison of the port with the best package of the ecosystem.
    eco_data: dict = {}
    if ECO_DATA.exists():
        eco_data = json.loads(ECO_DATA.read_text(encoding="utf-8"))

    problems: list[str] = []
    checked = 0
    workload = None
    in_kernels = False
    in_goodthomas = False
    in_original = False
    in_direct = False
    in_copy = False
    in_machine = False
    in_idle = False
    in_target = False
    in_eco = False
    copy_rows: list[re.Match[str]] = []
    idle_rows: list[re.Match[str]] = []
    target_rows: list[re.Match[str]] = []
    eco_rows: list[re.Match[str]] = []
    eco_lines: list[str] = []
    for line in DOC.read_text(encoding="utf-8").splitlines():
        if line.startswith("### "):
            title = line[4:].strip()
            workload = SECTIONS.get(title)
            in_kernels = title == KERNEL_SECTION
            in_goodthomas = title == GOODTHOMAS_SECTION
            in_original = title == ORIGINAL_SECTION
            in_direct = title == DIRECT_SECTION
            in_copy = title == COPY_SECTION
            in_machine = title == MACHINE_SECTION
            in_idle = title == IDLE_SECTION
            in_target = title == TARGET_SECTION
            in_eco = title == ECO_SECTION
        if in_eco:
            eco_lines.append(line)
        if line.startswith("| n |") or line.startswith("| ---"):
            continue

        if in_copy or in_machine or in_idle or in_target or in_eco:
            # A row of these sections is either a header, which holds no
            # measurement at all, or a row that the measurement must check.  A
            # row that holds a measurement and that this script does not
            # understand must not pass silently.
            if line.startswith("|"):
                if not re.search(r"\d[\d ]*(ns|us|x)\b", line):
                    continue
                if in_copy:
                    m = ROW_COPY.match(line)
                elif in_machine:
                    m = ROW_MACHINE.match(line)
                elif in_idle:
                    m = ROW_IDLE.match(line)
                elif in_eco:
                    m = ROW_ECO.match(line)
                else:
                    m = ROW_TARGET.match(line)
                if m:
                    checked += 1
                    if in_copy:
                        copy_rows.append(m)
                    elif in_idle:
                        idle_rows.append(m)
                    elif in_target:
                        target_rows.append(m)
                    elif in_eco:
                        eco_rows.append(m)
                    else:
                        index = int(m.group("round"))
                        measured = machine_rounds.get(index)
                        if measured is None:
                            problems.append(
                                f"the measurement has no round {index}"
                            )
                        else:
                            for given, actual, what in (
                                (m.group("transform"), measured["transform"],
                                 "the transform"),
                                (m.group("clock"), measured["clock"],
                                 "the clock"),
                            ):
                                if abs(number(given) - actual) > max(
                                    1.0, 0.005 * abs(actual)
                                ):
                                    problems.append(
                                        f"round {index}: the document says "
                                        f"{what} = {number(given)}, the "
                                        f"measurement is {actual:.0f}"
                                    )
                            if not close(
                                float(m.group("memory")),
                                measured["memory"], 0.02, 0.01,
                            ):
                                problems.append(
                                    f"round {index}: the document says the "
                                    f"memory = {m.group('memory')} ns/elem, the "
                                    f"measurement is {measured['memory']:.3f} "
                                    f"ns/elem"
                                )
                else:
                    problems.append(
                        f"the row {line.strip()!r} is not understood"
                    )
                continue

        m = ROW_DIRECT.match(line)
        if m and in_direct:
            checked += 1
            name = m.group("workload")
            n = number(m.group("n"))
            key = f"{name}/{n}"
            direct = direct_best.get("direct", {}).get(key)
            today = direct_best.get("moonbit", {}).get(key)
            if direct is None or today is None:
                problems.append(f"{key}: the measurement is missing a side")
                continue
            for given, measured, what in (
                (m.group("direct"), direct, "direct"),
                (m.group("today"), today, "today"),
            ):
                if number(given) != int(measured):
                    problems.append(
                        f"{key}: the document says {what} = {number(given)}, "
                        f"the measurement is {measured:.0f}"
                    )
            names = direct_ratios.get(key, {})
            measured = names.get("direct/moonbit")
            if measured is not None:
                if not close(float(m.group("over_direct")), measured, 0.02, 0.01):
                    problems.append(
                        f"{key}: the document says direct / today = "
                        f"{m.group('over_direct')}x, the measurement is "
                        f"{measured:.2f}x"
                    )
            continue

        m = ROW_GOODTHOMAS.match(line)
        if m and (in_goodthomas or in_original):
            checked += 1
            name = m.group("workload")
            n = number(m.group("n"))
            key = f"{name}/{n}"
            if in_goodthomas:
                side_best, side_ratios = gt_best, gt_ratios
            else:
                side_best, side_ratios = best, ratios
            java = side_best.get("java", {}).get(key)
            head = side_best.get("head", {}).get(key)
            today = side_best.get("moonbit", {}).get(key)
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
            names = side_ratios.get(key, {})
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

    # The table of the comparison of the two builds has two rows: the build
    # with the copy of the input into the output and the build without it.
    if copy_rows:
        if len(copy_rows) != 2:
            problems.append(
                f"the table of the two builds has {len(copy_rows)} rows, it "
                f"must have two"
            )
        elif not copy_data:
            problems.append(
                "the comparison of the two builds is not measured, "
                f"{COPY_DATA} does not exist"
            )
        else:
            first, second = copy_rows
            if "copy" not in first.group("what"):
                problems.append(
                    "the first row of the two builds is not the build with the "
                    "copy of the input"
                )
            if "reads one array" not in second.group("what"):
                problems.append(
                    "the second row of the two builds is not the build that "
                    "reads one array and writes another"
                )
            for row, side in ((first, "a"), (second, "b")):
                measured = copy_data.get(side, {}).get("median")
                if measured is None:
                    problems.append(f"the measurement has no {side} side")
                    continue
                if abs(number(row.group("median")) - measured) > max(
                    1.0, 0.005 * abs(measured)
                ):
                    problems.append(
                        f"the document says the median of the {side} side is "
                        f"{number(row.group('median'))} ns, the measurement is "
                        f"{measured:.0f} ns"
                    )
            ratio = copy_data.get("ratio", {}).get("median")
            if ratio is None:
                problems.append("the measurement has no ratio")
            else:
                for row, expected, what in (
                    (first, ratio, "the first"),
                    (second, 1.0 / ratio, "the second"),
                ):
                    if not close(float(row.group("ratio")), expected, 0.01, 0.005):
                        problems.append(
                            f"the document says the ratio of {what} row is "
                            f"{row.group('ratio')}x, the measurement is "
                            f"{expected:.3f}x"
                        )

    # The table of the two sessions of the machine holds the measurement of the
    # session of the comparison, the one of the tracked data.
    if idle_rows:
        if len(idle_rows) != 1:
            problems.append(
                f"the table of the two sessions has {len(idle_rows)} rows, it "
                f"must have one"
            )
        else:
            row = idle_rows[0]
            key = "c2c/32760"
            java = best.get("java", {}).get(key)
            port = best.get("moonbit", {}).get(key)
            if java is None or port is None:
                problems.append(
                    f"the measurement has no {key} to compare the document with"
                )
            else:
                for given, measured, what in (
                    (number(row.group("java")), java, "the original"),
                    (number(row.group("port")), port, "the port"),
                ):
                    if abs(given - measured) > max(1.0, 0.005 * abs(measured)):
                        problems.append(
                            f"the document says {what} = {given} ns, the "
                            f"measurement is {measured:.0f} ns"
                        )
            ratio = ratios.get(key, {}).get("moonbit/java")
            if ratio is not None and not close(
                float(row.group("ratio")), ratio, 0.02, 0.01
            ):
                problems.append(
                    f"the document says the ratio is {row.group('ratio')}x, the "
                    f"measurement is {ratio:.2f}x"
                )

    # The table of the two targets holds the wasm build and the native build
    # of the same source.
    if target_rows:
        if len(target_rows) != 2:
            problems.append(
                f"the table of the targets has {len(target_rows)} rows, it must "
                f"have two"
            )
        elif not target_data:
            problems.append(
                "the two targets are not measured, "
                f"{TARGET_DATA} does not exist"
            )
        else:
            for row in target_rows:
                what = row.group("what").lower()
                if "wasm" in what:
                    side = "wasm"
                elif "native" in what:
                    side = "native"
                else:
                    problems.append(
                        f"the row {row.group('what').strip()!r} is neither the "
                        f"wasm nor the native build"
                    )
                    continue
                measured = target_data.get(side, {}).get("median")
                if measured is None:
                    problems.append(f"the measurement has no {side} side")
                    continue
                if abs(number(row.group("ns")) - measured) > max(
                    1.0, 0.005 * abs(measured)
                ):
                    problems.append(
                        f"the document says the {side} build takes "
                        f"{number(row.group('ns'))} ns, the measurement is "
                        f"{measured:.0f} ns"
                    )
                ratio = target_data.get("ratio", {}).get("median")
                if ratio is not None:
                    expected = ratio if side == "wasm" else 1.0
                    if not close(float(row.group("ratio")), expected, 0.01, 0.005):
                        problems.append(
                            f"the document says the {side} build is "
                            f"{row.group('ratio')}x of the native one, the "
                            f"measurement is {expected:.3f}x"
                        )

    # The table of the ecosystem holds one row per window of the package, with
    # the closest valid length of the port next to it.
    if eco_rows:
        if not eco_data:
            problems.append(
                "the comparison with the ecosystem is not measured, "
                f"{ECO_DATA} does not exist"
            )
        else:
            lengths = eco_data.get("lengths", {})
            medians = eco_data.get("median", {})
            eco_ratios = eco_data.get("ratios", {})
            eco_unit = eco_data.get("per_unit", {})
            seen: set[str] = set()
            for row in eco_rows:
                window = number(row.group("window"))
                key = str(window)
                if key not in lengths:
                    problems.append(
                        f"the document has a row for the window {window}, the "
                        f"measurement has none"
                    )
                    continue
                seen.add(key)
                if number(row.group("port_n")) != lengths[key]["port"]:
                    problems.append(
                        f"{key}: the document says the port is measured at "
                        f"{number(row.group('port_n'))}, the measurement is at "
                        f"{lengths[key]['port']}"
                    )
                for given, measured, what in (
                    (row.group("port"), medians.get(key, {}).get("port"),
                     "the port"),
                    (row.group("package"), medians.get(key, {}).get("hkdsp"),
                     "the package"),
                ):
                    if measured is None:
                        problems.append(f"{key}: the measurement has no {what}")
                        continue
                    if abs(number(given) - measured) > max(
                        1.0, 0.005 * abs(measured)
                    ):
                        problems.append(
                            f"{key}: the document says {what} takes "
                            f"{number(given)} ns, the measurement is "
                            f"{measured:.0f} ns"
                        )
                for given, measured, what in (
                    (row.group("ratio"),
                     eco_ratios.get(key, {}).get("hkdsp/port"), "the ratio"),
                    (row.group("port_unit"),
                     eco_unit.get(key, {}).get("port"),
                     "the cost of an element of the port"),
                    (row.group("package_unit"),
                     eco_unit.get(key, {}).get("hkdsp"),
                     "the cost of an element of the package"),
                ):
                    if measured is None:
                        problems.append(f"{key}: the measurement has no {what}")
                        continue
                    if not close(float(given), measured, 0.02, 0.01):
                        problems.append(
                            f"{key}: the document says {what} is {given}, the "
                            f"measurement is {measured:.3f}"
                        )
            missing = set(lengths) - seen
            if missing:
                problems.append(
                    f"the table of the ecosystem has no row for the window "
                    f"{sorted(missing)}"
                )
            # The section says how many rounds the measurement has and which
            # version of the package it measured.  Both are numbers of the
            # measurement, and a document that drifts from them is a drift.
            eco_text = "\n".join(eco_lines)
            eco_rounds = eco_data.get("rounds")
            if eco_rounds and not re.search(r"\b%d rounds\b" % eco_rounds, eco_text):
                problems.append(
                    f"the section of the ecosystem does not say that the "
                    f"measurement has {eco_rounds} rounds"
                )
            version = eco_data.get("ecosystem", {}).get("version")
            if version and version not in eco_text:
                problems.append(
                    f"the section of the ecosystem does not name the version "
                    f"{version} of the package that was measured"
                )

    # The two documents of the repository repeat two numbers of the
    # benchmark: how many orders of magnitude the old port was slower, and
    # how many rounds the comparison of the workloads had.  A number that is
    # corrected in `BENCHMARK.md` and left in a README is a drift of its
    # own, and it is caught here.
    rounds_measured = data.get("rounds")
    orders = 0
    for key, value in ratios.items():
        speed = value.get("old/java")
        if speed:
            orders = max(orders, int(math.log10(speed)))
    if orders:
        words = {3: "three", 4: "four", 5: "five"}
        expected = words.get(orders, "four")
        # The phrase is written in bold in some places and in plain text in
        # others, so both are looked for.
        pattern = re.compile(
            r"(?:\*\*)?\b(one|two|three|four|five|six) orders of magnitude\b"
        )
        for document in (DOC,) + READMES:
            if not document.exists():
                continue
            text = document.read_text(encoding="utf-8")
            for match in pattern.finditer(text):
                word = match.group(1)
                if word != expected:
                    problems.append(
                        f"{document.name}: the document says the port used to be "
                        f"{word} orders of magnitude slower, the measurement is "
                        f"{expected}"
                    )
    if rounds_measured:
        for document in (DOC,) + READMES:
            if not document.exists():
                continue
            text = document.read_text(encoding="utf-8")
            for match in re.finditer(
                r"median of (one|two|three|four|five|six|\d+) rounds", text
            ):
                given = match.group(1)
                words = {
                    "one": 1, "two": 2, "three": 3,
                    "four": 4, "five": 5, "six": 6,
                }
                actual = int(given) if given.isdigit() else words.get(given)
                if actual != rounds_measured:
                    problems.append(
                        f"{document.name}: the document says the median of "
                        f"{given} rounds, the measurement has "
                        f"{rounds_measured}"
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
