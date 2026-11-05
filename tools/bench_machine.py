#!/usr/bin/env python3
"""Measures the transform of the port together with the state of the machine.

The probe is `moonbit_fft/benchmachine`: it runs the transform of the port
in rounds, and next to every round it measures two references, a loop of
integer arithmetic and a sequential pass over a megabyte of doubles.  When
the transform slows down and the references slow down with it, the machine
is the reason and not the transform.

The result is written as text and as JSON, so that the numbers of the
document can be checked against it by `tools/check_benchmark.py` on a fresh
clone, without running the measurement again.

Usage::

    python tools/bench_machine.py [--rounds 20] [--skip-build]
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PKG = ROOT / "moonbit_fft" / "benchmachine"
TXT = ROOT / "bench" / "bench_machine.txt"
JSON = ROOT / "bench" / "bench_machine.json"

# "round 3 transform 421293.0 ns | clock 81391.0 us | memory 0.999 ns/elem | ..."
ROUND = re.compile(
    r"^round\s+(?P<round>\d+)\s+transform\s+(?P<transform>[\d.]+)\s+ns\s*\|\s*"
    r"clock\s+(?P<clock>[\d.]+)\s+us\s*\|\s*"
    r"memory\s+(?P<memory>[\d.]+)\s+ns/elem"
)


def build() -> pathlib.Path:
    subprocess.run(
        ["moon", "-C", str(ROOT / "moonbit_fft"), "build",
         "--release", "--target", "native", "./benchmachine"],
        check=True,
    )
    return (
        ROOT / "moonbit_fft" / "_build" / "native" / "release" / "build"
        / "benchmachine" / "benchmachine.exe"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-build", action="store_true")
    args = parser.parse_args()

    exe = build() if not args.skip_build else (
        ROOT / "moonbit_fft" / "_build" / "native" / "release" / "build"
        / "benchmachine" / "benchmachine.exe"
    )
    if not exe.exists():
        print("%s does not exist, build it first" % exe)
        return 1
    out = subprocess.run(
        [str(exe)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True
    ).stdout.decode("utf-8", "replace")

    rounds = []
    for line in out.splitlines():
        m = ROUND.match(line)
        if m:
            rounds.append({
                "round": int(m.group("round")),
                "transform": float(m.group("transform")),
                "clock": float(m.group("clock")),
                "memory": float(m.group("memory")),
            })
    if not rounds:
        print("the probe produced no rounds:\n%s" % out[-2000:])
        return 1

    TXT.parent.mkdir(parents=True, exist_ok=True)
    # The output is written as it is: the probe ends its lines with a carriage
    # return and a line feed already, and a text mode would add a second line
    # feed to them.
    TXT.write_bytes(out.encode("utf-8"))
    JSON.write_text(
        json.dumps({"rounds": rounds}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    for r in rounds:
        print("round %2d transform %9.0f ns | clock %8.0f us | memory %.3f ns/elem" % (
            r["round"], r["transform"], r["clock"], r["memory"]))
    print("wrote %s and %s" % (TXT, JSON))
    return 0


if __name__ == "__main__":
    sys.exit(main())
