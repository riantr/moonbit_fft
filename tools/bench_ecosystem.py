#!/usr/bin/env python3
"""Measures the port against the best implementation of the ecosystem.

The port of the repository is a port of `net.imglib2.algorithm.fft2`, and its
kernel is the prime factor algorithm of the original: it takes the **lengths of
the original**, 240 of them, most of them not powers of two, and the powers of
two stop at 16.  The packages of the ecosystem are the other way round: they
mostly take a power of two, or any length through Bluestein.

One package of the ecosystem is in the same class as the port.  `HK-SHAO/dsp`
keeps a plan - the bit reversal and the tables of the cosines and the sines of
a window - and transforms in place in the memory of a slot that it hands out
once.  That is the structure the port has after its own rewrites, and it is the
one package that meets the port on equal terms.

The harness is `tools/ecomodule/bencheco`, and it is assembled into a shadow
module under `build/ecomodule`, because the comparison needs the ecosystem
package as a dependency and the library itself must not have one.  The shadow
module is the module of the working tree plus the dependency, which is the same
way the other sides of `BENCHMARK.md` are built.

Usage::

    python tools/bench_ecosystem.py
    python tools/bench_ecosystem.py --skip-build
    python tools/bench_ecosystem.py --out bench/bench_ecosystem.txt
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import re
import shutil
import statistics
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
MODULE = ROOT / "moonbit_fft2"
SHADOW = ROOT / "build" / "ecomodule"
HARNESS = ROOT / "tools" / "ecomodule" / "bencheco"
TXT = ROOT / "bench" / "bench_ecosystem.txt"
JSON = ROOT / "bench" / "bench_ecosystem.json"

# The best implementation of the ecosystem, and the reason it is the best one:
# it is the only package of the ecosystem that caches a plan and transforms in
# place in a slot, which is what the port does after its own rewrites.
PACKAGE = "HK-SHAO/dsp"
VERSION = "0.1.4"

# The window of the package and the closest valid length of the port.  The two
# of them meet nowhere exactly, which is a result of the comparison itself.
WORKLOADS = [
    (4096, 4095),
    (1024, 1008),
]

# The files of the module that are not part of the comparison.
SKIP_DIRS = {"_build", ".mooncakes", "benchmark", "benchab", "benchmachine", "bencheco"}

SIDE = re.compile(
    r"^round\s+(?P<round>\d+)\s+side\s+(?P<side>\w+)\s+"
    r"length\s+(?P<length>\d+)\s+(?P<ns>[\d.]+)\s+ns\s*$"
)
REFERENCE = re.compile(
    r"^round\s+(?P<round>\d+)\s+reference\s+clock\s+(?P<clock>[\d.]+)\s+us\s*\|\s*"
    r"memory\s+(?P<memory>[\d.]+)\s+ns/elem"
)


def decode(raw: bytes) -> str:
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return raw.decode("utf-16")
    return raw.decode("utf-8", errors="replace")


def assemble() -> None:
    """Builds the shadow module from the module of the working tree."""
    if SHADOW.exists():
        shutil.rmtree(SHADOW)
    SHADOW.mkdir(parents=True)
    copied = 0
    for source in sorted(MODULE.rglob("*")):
        if not source.is_file():
            continue
        relative = source.relative_to(MODULE)
        if relative.parts[0] in SKIP_DIRS:
            continue
        target = SHADOW / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied += 1
    # The dependency goes into the module file of the shadow module only: the
    # library itself must not depend on a package of the ecosystem.
    module_file = SHADOW / "moon.mod"
    text = module_file.read_text(encoding="utf-8")
    if PACKAGE not in text:
        if not text.endswith("\n"):
            text += "\n"
        text += "\nimport {\n  \"%s@%s\",\n}\n" % (PACKAGE, VERSION)
        module_file.write_text(text, encoding="utf-8")
    harness = SHADOW / "bencheco"
    harness.mkdir(parents=True, exist_ok=True)
    for source in sorted(HARNESS.iterdir()):
        if source.is_file():
            shutil.copy2(source, harness / source.name)
            copied += 1
    print("the shadow module is %s, %d files" % (SHADOW, copied))


def resolved_version() -> str:
    """The version of the ecosystem package that was really resolved."""
    module_file = SHADOW / ".mooncakes" / PACKAGE / "moon.mod"
    if not module_file.exists():
        module_file = SHADOW / ".mooncakes" / PACKAGE / "moon.mod.json"
    if not module_file.exists():
        return VERSION
    text = module_file.read_text(encoding="utf-8", errors="replace")
    match = re.search(r'"version"\s*:\s*"([^"]+)"', text)
    return match.group(1) if match else VERSION


def build_and_run(skip_build: bool) -> str:
    if not skip_build:
        subprocess.run(
            ["moon", "-C", str(SHADOW), "build", "--release",
             "--target", "native", "./bencheco"],
            check=True,
        )
    proc = subprocess.run(
        ["moon", "-C", str(SHADOW), "run", "--release",
         "--target", "native", "./bencheco"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=str(ROOT),
    )
    out = decode(proc.stdout)
    if proc.returncode != 0:
        print(out[-4000:])
        raise SystemExit("the harness exited with %d" % proc.returncode)
    return out


def unit_cost(ns: float, n: int) -> float:
    """The nanoseconds per element and per `log2` of the length.

    The two sides are not measured at the same length - the port takes the
    lengths of the original and the package takes the powers of two - so the
    cost of an element of a transform is the number that can be put next to
    each other.  A transform costs `n log2(n)` butterflies.
    """
    return ns / (n * math.log2(n))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="use the binary of the last build instead of building again",
    )
    parser.add_argument(
        "--out",
        type=pathlib.Path,
        default=TXT,
        help="the file the table is written to; the numbers go next to it "
        "in a file with the same name and the extension `.json`",
    )
    parser.add_argument(
        "--assemble-only",
        action="store_true",
        help="only assemble the shadow module, do not run the measurement",
    )
    args = parser.parse_args()

    assemble()
    if args.assemble_only:
        return 0
    print("measuring")
    out = build_and_run(args.skip_build)

    # round -> length -> side -> ns
    rounds: dict[int, dict[int, dict[str, float]]] = {}
    refs: dict[int, tuple[float, float]] = {}
    reference_lines: list[str] = []
    checksum = ""
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("CHECKSUM "):
            checksum = line[len("CHECKSUM "):].strip()
            continue
        match = SIDE.match(line)
        if match:
            index = int(match.group("round"))
            length = int(match.group("length"))
            rounds.setdefault(index, {}).setdefault(length, {})[
                match.group("side")
            ] = float(match.group("ns"))
            continue
        match = REFERENCE.match(line)
        if match:
            index = int(match.group("round"))
            refs[index] = (float(match.group("clock")), float(match.group("memory")))
            reference_lines.append(line)
    if not rounds:
        print(out[-4000:])
        print("the harness produced no measurement")
        return 1

    sides = sorted({side for r in rounds.values() for l in r.values() for side in l})
    if sides != ["hkdsp", "port"]:
        print("the measurement has the sides %s, it must have the port and the "
              "package" % sides)
        return 1

    median: dict[str, dict[str, float]] = {}
    spread: dict[str, dict[str, float]] = {}
    per_unit: dict[str, dict[str, float]] = {}
    ratios: dict[str, dict[str, float]] = {}
    # The harness decides how many rounds it runs, and every side has to have
    # the same number of them: a side that is missing a round would be
    # compared with the others on a different amount of noise.
    measured = {
        len([r for r in rounds.values() if window in r and side in r[window]])
        for window, _ in WORKLOADS
        for side in sides
    }
    if len(measured) != 1:
        print("the sides do not have the same number of rounds: %s"
              % sorted(measured))
        return 1
    round_count = measured.pop()
    if round_count < 8:
        print("the measurement has %d rounds, too few for a median" % round_count)
        return 1
    for window, port_length in WORKLOADS:
        key = str(window)
        median[key] = {}
        spread[key] = {}
        per_unit[key] = {}
        ratios[key] = {}
        for side in sides:
            values = [
                r[window][side]
                for r in rounds.values()
                if window in r and side in r[window]
            ]
            median[key][side] = statistics.median(values)
            spread[key][side] = (max(values) / min(values)) if len(values) > 1 else 1.0
            length = port_length if side == "port" else window
            per_unit[key][side] = unit_cost(median[key][side], length)
        paired = [
            r[window]["hkdsp"] / r[window]["port"]
            for r in rounds.values()
            if window in r and {"hkdsp", "port"} <= set(r[window])
        ]
        ratios[key]["hkdsp/port"] = statistics.median(paired)

    clocks = [v[0] for v in refs.values()]
    memories = [v[1] for v in refs.values()]
    # A reference of zero is not a fast machine: it is a loop that the
    # compiler removed because nothing read its result.  MoonBit does that to
    # a computation whose value is dropped, and the run then looks perfect and
    # says nothing.  It must not pass.
    if not clocks or statistics.median(clocks) <= 0:
        print("the clock of the machine reads %r: the reference was removed as "
              "dead code, the measurement cannot be trusted" % (
                  statistics.median(clocks) if clocks else None))
        return 1
    if statistics.median(memories) <= 0:
        print("the memory reference reads %r: the pass over the array was "
              "removed as dead code" % statistics.median(memories))
        return 1
    reference = {
        "rounds": len(refs),
        "clock": {
            "median": statistics.median(clocks) if clocks else 0.0,
            "min": min(clocks) if clocks else 0.0,
            "max": max(clocks) if clocks else 0.0,
        },
        "memory": {
            "median": statistics.median(memories) if memories else 0.0,
            "min": min(memories) if memories else 0.0,
            "max": max(memories) if memories else 0.0,
        },
    }

    # The text, in the style of the other tables of the repository.
    lines: list[str] = []
    lines.append("the port of the repository against %s %s" % (
        PACKAGE, resolved_version()))
    lines.append("the median of the %d rounds, the ratios taken per round" % (
        round_count))
    lines.append("")
    header = "%-8s %9s %14s %14s %11s" % (
        "window", "n port", "port ns", "hkdsp ns", "hkdsp/port")
    lines.append(header)
    lines.append("-" * len(header))
    for window, port_length in WORKLOADS:
        key = str(window)
        lines.append("%-8d %9d %14.0f %14.0f %10.3fx" % (
            window, port_length, median[key]["port"], median[key]["hkdsp"],
            ratios[key]["hkdsp/port"]))
    lines.append("")
    lines.append("the cost of an element, in ns per n log2(n):")
    for window, port_length in WORKLOADS:
        key = str(window)
        lines.append("  %-6d port %.3f (%d)  hkdsp %.3f (%d)  hkdsp/port %.3f" % (
            window, per_unit[key]["port"], port_length,
            per_unit[key]["hkdsp"], window,
            per_unit[key]["hkdsp"] / per_unit[key]["port"]))
    lines.append("")
    lines.append("the spread of the rounds, the slowest over the fastest:")
    for window, _ in WORKLOADS:
        key = str(window)
        lines.append("  %-6d port %.2fx  hkdsp %.2fx" % (
            window, spread[key]["port"], spread[key]["hkdsp"]))
    lines.append("")
    if reference["rounds"]:
        lines.append("the machine: clock median %.0f us (%.0f to %.0f), "
                     "memory median %.3f ns/elem (%.3f to %.3f)" % (
                         reference["clock"]["median"], reference["clock"]["min"],
                         reference["clock"]["max"], reference["memory"]["median"],
                         reference["memory"]["min"], reference["memory"]["max"]))
    lines.append("checksum %s" % checksum)
    text = "\n".join(lines)
    print(text)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text + "\n", encoding="utf-8")
    data = {
        "rounds": round_count,
        "statistic": "the median of the rounds; the ratios are taken per round "
        "and medianed",
        "ecosystem": {"package": PACKAGE, "version": resolved_version()},
        "lengths": {
            str(window): {"port": port_length, "hkdsp": window}
            for window, port_length in WORKLOADS
        },
        "median": median,
        "spread": spread,
        "per_unit": per_unit,
        "ratios": ratios,
        "reference": reference,
        "checksum": checksum,
    }
    json_path = args.out.with_suffix(".json")
    json_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n",
                         encoding="utf-8")
    # The rounds themselves are kept next to the median, so that the spread of
    # a reading can be told from a change of the programs.
    rounds_path = args.out.with_name(args.out.stem + "_rounds.txt")
    rounds_path.write_text(out, encoding="utf-8")
    print("written to %s and %s" % (args.out, json_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
