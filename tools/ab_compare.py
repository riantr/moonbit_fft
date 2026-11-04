#!/usr/bin/env python3
"""Compares two builds of the port, with their rounds paired.

The machine this runs on is busy and its noise is bimodal, so a single
number of either build says little.  The two builds are therefore run
alternately, and their rounds are **paired**: the ratio of the two sides in
the same round cancels the part of the noise that both of them see.  The
median of those per round ratios is the number that is reported, and the
spread of the rounds of each side is reported next to it.

The order of the two sides is rotated in every round, so that neither side
can profit from a warm cache or a quiet moment that the other one does not
get.

The result is written as JSON, so that the numbers of the document can be
checked against it by `tools/check_benchmark.py` on a fresh clone, without
running the measurement again.

Usage::

    python tools/ab_compare.py <exe_a> <exe_b> [rounds] [out.json]

The two executables are the probes of `moonbit_fft2/benchab`, built with::

    moon -C moonbit_fft2 build --release --target native ./benchab
"""

from __future__ import annotations

import json
import pathlib
import statistics
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def run(exe: str) -> list[float]:
    """The rounds of one run of the probe, in nanoseconds per call."""
    out = subprocess.run(
        [exe], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True
    ).stdout.decode("utf-8", "replace")
    values = []
    for line in out.splitlines():
        # "ROUND <index> <ns per call> ns" - the time is the third field, the
        # second one is the number of the round.
        if line.startswith("ROUND "):
            parts = line.split()
            if len(parts) < 3:
                raise SystemExit("%s produced a malformed round: %r" % (exe, line))
            values.append(float(parts[2]))
    if not values:
        raise SystemExit("%s produced no rounds:\n%s" % (exe, out[-2000:]))
    return values


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    a_exe, b_exe = sys.argv[1], sys.argv[2]
    rounds = int(sys.argv[3]) if len(sys.argv) > 3 else 5
    out_path = pathlib.Path(sys.argv[4]) if len(sys.argv) > 4 else None

    a_rounds: list[list[float]] = []
    b_rounds: list[list[float]] = []
    for i in range(rounds):
        # The order is rotated, so that neither side can profit from a warm
        # cache or a quiet moment that the other one does not get.
        if i % 2 == 0:
            a_rounds.append(run(a_exe))
            b_rounds.append(run(b_exe))
        else:
            b_rounds.append(run(b_exe))
            a_rounds.append(run(a_exe))

    ratios = []
    for a, b in zip(a_rounds, b_rounds):
        pairs = list(zip(a, b))
        n = min(len(pairs), 21)
        for j in range(n):
            if pairs[j][1] > 0.0:
                ratios.append(pairs[j][0] / pairs[j][1])
    a_all = [v for r in a_rounds for v in r]
    b_all = [v for r in b_rounds for v in r]
    print("a median %.0f ns  min %.0f  max %.0f" % (
        statistics.median(a_all), min(a_all), max(a_all)))
    print("b median %.0f ns  min %.0f  max %.0f" % (
        statistics.median(b_all), min(b_all), max(b_all)))
    if not ratios:
        print("no rounds could be paired")
        return 1
    print("per round ratio a/b: median %.4f  min %.4f  max %.4f  n=%d" % (
        statistics.median(ratios), min(ratios), max(ratios), len(ratios)))

    result = {
        "rounds": rounds,
        "a": {
            "median": statistics.median(a_all),
            "min": min(a_all),
            "max": max(a_all),
            "values": a_all,
        },
        "b": {
            "median": statistics.median(b_all),
            "min": min(b_all),
            "max": max(b_all),
            "values": b_all,
        },
        "ratio": {
            "median": statistics.median(ratios),
            "min": min(ratios),
            "max": max(ratios),
            "pairs": len(ratios),
        },
    }
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print("wrote %s" % out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
