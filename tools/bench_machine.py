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
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

# The identity of the machine, so that the numbers of this file say which
# machine they belong to.  The helper sits next to this script.
import cpu_flags  # noqa: E402
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
    parser.add_argument(
        "--stamp-only",
        action="store_true",
        help="record the machine in the existing JSON without measuring again",
    )
    args = parser.parse_args()

    if args.stamp_only:
        # Records which machine a measurement was taken on, for a measurement
        # that was taken before the field existed.  The rounds are left exactly
        # as they are: this writes an identity, it does not measure anything.
        if not JSON.exists():
            print("%s does not exist, measure first" % JSON)
            return 1
        identity = cpu_flags.stamp(JSON)
        print("stamped %s" % cpu_flags.summary(identity))
        return 0

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
    identity = cpu_flags.write(JSON, {"rounds": rounds})
    for r in rounds:
        print("round %2d transform %9.0f ns | clock %8.0f us | memory %.3f ns/elem" % (
            r["round"], r["transform"], r["clock"], r["memory"]))
    print("cpu: %s" % cpu_flags.summary(identity))
    print("wrote %s and %s" % (TXT, JSON))
    return 0


if __name__ == "__main__":
    sys.exit(main())
