#!/usr/bin/env python3
"""Measures the port against every package of the ecosystem that transforms.

The port of the repository is a port of `net.imglib2.algorithm.fft2`, and its
kernel is the prime factor algorithm of the original: it takes the **lengths of
the original**, 240 of them, most of them not powers of two, and the powers of
two stop at 16.  The packages of the ecosystem are the other way round: the
complex ones take a power of two, or any length through Bluestein.

Every package that really transforms a complex signal is measured, each one
through **its own fastest entry point** for the length at hand.  The harness is
`tools/ecomodule/bencheco`, and it is assembled into a shadow module under
`build/ecomodule`, because the comparison needs the ecosystem packages as
dependencies and the library itself must not have one.  The shadow module is the
module of the working tree plus the dependencies, with the harness of the working
tree next to it, which is how the other sides of `BENCHMARK.md` are built.

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
# The packages of the comparison: the harness that times the sides, and the probe
# that dumps their spectra so that a reference can hold them to the right answer.
HARNESS = ROOT / "tools" / "ecomodule"
PACKAGES = ("bencheco", "spec9")
TXT = ROOT / "bench" / "bench_ecosystem.txt"
JSON = ROOT / "bench" / "bench_ecosystem.json"

# The packages of the ecosystem that transform a complex signal.  Two of them
# offer both a radix path and a Bluestein one, and both paths are measured: which
# of the two is faster is a property of the package and not of the length, so a
# single row would have to choose, and the choice would be a claim.
ECOSYSTEM = [
    ("hkdsp", "HK-SHAO/dsp", "0.1.4", "slot_open then forward, plan and slot cached"),
    ("hx/radix4", "hwlxmm/dsp", "0.1.0", "fft_radix4, in place"),
    ("hx/bluestein", "hwlxmm/dsp", "0.1.0", "fft_bluestein"),
    ("lc/radix4", "lcyllp/moonbit-nlse-ssfm", "0.1.0", "fft_radix4"),
    ("lc/bluestein", "lcyllp/moonbit-nlse-ssfm", "0.1.0", "fft_bluestein, what its fft entry calls"),
    ("moonnum", "amor2025/moonNum", "0.1.0", "fft, which dispatches to its radix-2"),
    ("mspec", "chgttyyr/MoonSpectrum", "0.2.2", "fft"),
    ("mdsp", "2227057182/moonbit-dsp", "0.1.0", "fft, real input"),
]

# A dependency of the harness itself, not a package of the comparison: the probe
# that dumps the spectra writes them with the file system of `moonbitlang/x`.
SUPPORT = [("moonbitlang/x", "0.4.46")]

# The side of the port, always the base of the comparison.
PORT = "port"

# The window of the packages and the closest valid length of the port.  The two
# of them meet nowhere exactly, which is a result of the comparison itself.
WORKLOADS = [
    (4096, 4095),
    (1024, 1008),
]

# The files of the module that are not part of the comparison.
SKIP_DIRS = {"_build", ".mooncakes", "benchmark", "benchab", "benchmachine", "bencheco"}

SIDE = re.compile(
    r"^round\s+(?P<round>\d+)\s+side\s+(?P<side>\S+)\s+"
    r"length\s+(?P<length>\d+)\s+(?P<ns>[\d.]+)\s+ns\s*$"
)
REPEATS = re.compile(
    r"^side\s+(?P<side>\S+)\s+length\s+(?P<length>\d+)\s+repeats\s+(?P<n>\d+)\s*$"
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
    # The dependencies go into the module file of the shadow module only: the
    # library itself must not depend on a package of the ecosystem.
    module_file = SHADOW / "moon.mod"
    text = module_file.read_text(encoding="utf-8")
    missing = [
        f'  "{package}@{version}",'
        for _, package, version, _ in ECOSYSTEM
        if f'"{package}@' not in text
    ] + [
        f'  "{package}@{version}",'
        for package, version in SUPPORT
        if f'"{package}@' not in text
    ]
    if missing:
        if not text.endswith("\n"):
            text += "\n"
        text += "\nimport {\n" + "\n".join(missing) + "\n}\n"
        module_file.write_text(text, encoding="utf-8")
    for package in PACKAGES:
        harness = SHADOW / package
        harness.mkdir(parents=True, exist_ok=True)
        for source in sorted((HARNESS / package).iterdir()):
            if source.is_file():
                shutil.copy2(source, harness / source.name)
                copied += 1
    print("the shadow module is %s, %d files" % (SHADOW, copied))


def resolved_version(package: str) -> str:
    """The version of an ecosystem package that was really resolved."""
    for name in ("moon.mod", "moon.mod.json"):
        module_file = SHADOW / ".mooncakes" / package / name
        if module_file.exists():
            text = module_file.read_text(encoding="utf-8", errors="replace")
            match = re.search(r'"version"\s*:\s*"([^"]+)"', text)
            if match:
                return match.group(1)
    for _, name, version, _ in ECOSYSTEM:
        if name == package:
            return version
    return ""


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

    The sides are not measured at the same length - the port takes the lengths
    of the original and the packages take the powers of two - so the cost of an
    element of a transform is the number that can be put next to each other.  A
    transform costs `n log2(n)` butterflies.
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
    repeats: dict[str, dict[str, int]] = {}
    checksum = ""
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("CHECKSUM "):
            checksum = line[len("CHECKSUM "):].strip()
            continue
        match = REPEATS.match(line)
        if match:
            repeats.setdefault(match.group("side"), {})[
                match.group("length")
            ] = int(match.group("n"))
            continue
        match = SIDE.match(line)
        if match:
            rounds.setdefault(int(match.group("round")), {}).setdefault(
                int(match.group("length")), {}
            )[match.group("side")] = float(match.group("ns"))
            continue
        match = REFERENCE.match(line)
        if match:
            refs[int(match.group("round"))] = (
                float(match.group("clock")), float(match.group("memory")))
    if not rounds:
        print(out[-4000:])
        print("the harness produced no measurement")
        return 1

    sides = sorted({side for r in rounds.values() for l in r.values() for side in l})
    expected = sorted([PORT] + [name for name, _, _, _ in ECOSYSTEM])
    if sides != expected:
        print("the measurement has the sides %s, it must have %s"
              % (sides, expected))
        return 1

    # Every side has to have the same number of rounds at every window: a side
    # that is missing a round would be compared with the others on a different
    # amount of noise.  A side is looked up at **its own** length, because the
    # port is measured at the closest length of its own table and not at the
    # window itself.
    def length_of(side: str, port_length: int, window: int) -> int:
        return port_length if side == PORT else window

    def of_round(record: dict[int, dict[str, float]], side: str,
                 port_length: int, window: int) -> float | None:
        return record.get(length_of(side, port_length, window), {}).get(side)

    measured = {
        len([r for r in rounds.values()
             if of_round(r, side, port_length, window) is not None])
        for window, port_length in WORKLOADS
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

    median: dict[str, dict[str, float]] = {}
    spread: dict[str, dict[str, float]] = {}
    per_unit: dict[str, dict[str, float]] = {}
    ratios: dict[str, dict[str, float]] = {}
    lengths: dict[str, dict[str, int]] = {}
    for window, port_length in WORKLOADS:
        key = str(window)
        median[key] = {}
        spread[key] = {}
        per_unit[key] = {}
        ratios[key] = {}
        lengths[key] = {}
        for side in sides:
            values = [
                value
                for r in rounds.values()
                if (value := of_round(r, side, port_length, window)) is not None
            ]
            length = length_of(side, port_length, window)
            lengths[key][side] = length
            median[key][side] = statistics.median(values)
            spread[key][side] = (max(values) / min(values)) if len(values) > 1 else 1.0
            per_unit[key][side] = unit_cost(median[key][side], length)
        for side in sides:
            paired = []
            for record in rounds.values():
                mine = of_round(record, side, port_length, window)
                base = of_round(record, PORT, port_length, window)
                if mine is not None and base:
                    paired.append(mine / base)
            ratios[key][f"{side}/{PORT}"] = statistics.median(paired)

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
            "median": statistics.median(clocks),
            "min": min(clocks),
            "max": max(clocks),
        },
        "memory": {
            "median": statistics.median(memories),
            "min": min(memories),
            "max": max(memories),
        },
    }

    # The text, in the style of the other tables of the repository.
    lines: list[str] = []
    lines.append("the port of the repository against the packages of the "
                 "ecosystem")
    lines.append("the median of the %d rounds, the ratios taken per round"
                 % round_count)
    lines.append("")
    header = "%-9s %7s %13s %11s %11s" % (
        "side", "n", "median ns", "per unit", "over the port")
    for window, port_length in WORKLOADS:
        key = str(window)
        lines.append("window %d, the port at %d:" % (window, port_length))
        lines.append(header)
        lines.append("-" * len(header))
        for side in [PORT] + [name for name, _, _, _ in ECOSYSTEM]:
            lines.append("%-9s %7d %13.0f %11.3f %10.3fx" % (
                side, lengths[key][side], median[key][side],
                per_unit[key][side], ratios[key][f"{side}/{PORT}"]))
        lines.append("")
    lines.append("the spread of the rounds, the slowest over the fastest:")
    for window, _ in WORKLOADS:
        key = str(window)
        lines.append("  %d: %s" % (window, "  ".join(
            "%s %.2fx" % (side, spread[key][side])
            for side in [PORT] + [name for name, _, _, _ in ECOSYSTEM])))
    lines.append("")
    lines.append("the repeats of a segment, chosen so that it lasts about 4 ms:")
    for window, _ in WORKLOADS:
        key = str(window)
        lines.append("  %d: %s" % (window, "  ".join(
            "%s %d" % (side, repeats.get(side, {}).get(
                str(lengths[key][side]), 0))
            for side in [PORT] + [name for name, _, _, _ in ECOSYSTEM])))
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
        "ecosystem": [
            {
                "side": side,
                "package": package,
                "version": resolved_version(package),
                "entry": entry,
            }
            for side, package, _, entry in ECOSYSTEM
        ],
        "lengths": lengths,
        "median": median,
        "spread": spread,
        "per_unit": per_unit,
        "ratios": ratios,
        "repeats": repeats,
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
