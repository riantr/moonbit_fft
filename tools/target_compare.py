#!/usr/bin/env python3
"""Compares the wasm build of the port with the native build of the same source.

`moon run` builds for **wasm** unless a target is named, so a benchmark that
is started by hand measures the wasm build.  The two builds are run
alternately, and the order is rotated in every round, so that neither of them
always runs in the second slot.  The rounds of the two sides are paired: the
ratio of the two sides in the same round cancels the part of the noise that
both of them see, and the median of those per round ratios is the number
that is reported.

Only the `ROUND` lines of the probe are used.  The `MEASURE` lines come
after the rounds, and by then the machine has been under a load for seconds
and has lost about half of its speed; the slower build reaches that point
later in wall clock time and is therefore less degraded, so the two
protocols do not agree.

The result is written as JSON, so that the numbers of the document can be
checked against it by `tools/check_benchmark.py` on a fresh clone, without
running the measurement again.

Usage::

    python tools/target_compare.py [rounds] [out.json]
"""

from __future__ import annotations

import pathlib
import statistics
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import cpu_flags  # noqa: E402

PKG = ROOT / "moonbit_fft"
DEFAULT_OUT = ROOT / "bench" / "bench_target.json"


def run(target: str | None) -> list[float]:
    """The rounds of the probe of one target, in nanoseconds per call."""
    cmd = ["moon", "-C", str(PKG), "run", "--release"]
    if target:
        cmd += ["--target", target]
    cmd += ["./benchab"]
    out = subprocess.run(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True
    ).stdout.decode("utf-8", "replace")
    values = []
    for line in out.splitlines():
        # "ROUND <index> <ns per call> ns" - the time is the third field, the
        # second one is the number of the round.
        if line.startswith("ROUND "):
            parts = line.split()
            if len(parts) < 3:
                raise SystemExit("malformed round: %r" % line)
            values.append(float(parts[2]))
    if not values:
        raise SystemExit("no rounds:\n%s" % out[-2000:])
    return values


def main() -> int:
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    out_path = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_OUT

    wasm_rounds: list[list[float]] = []
    native_rounds: list[list[float]] = []
    for i in range(rounds):
        # The order is rotated: the side that runs second is not always the
        # same one.
        if i % 2 == 0:
            wasm_rounds.append(run(None))
            native_rounds.append(run("native"))
        else:
            native_rounds.append(run("native"))
            wasm_rounds.append(run(None))

    ratios = []
    for wasm, native in zip(wasm_rounds, native_rounds):
        for w, n in zip(wasm, native):
            if n > 0.0:
                ratios.append(w / n)
    wasm_all = [v for r in wasm_rounds for v in r]
    native_all = [v for r in native_rounds for v in r]
    print("wasm   median %.0f ns  min %.0f  max %.0f" % (
        statistics.median(wasm_all), min(wasm_all), max(wasm_all)))
    print("native median %.0f ns  min %.0f  max %.0f" % (
        statistics.median(native_all), min(native_all), max(native_all)))
    print("per round ratio wasm/native: median %.3f  min %.3f  max %.3f  n=%d" % (
        statistics.median(ratios), min(ratios), max(ratios), len(ratios)))
    print("ratio of the medians: %.3f" % (
        statistics.median(wasm_all) / statistics.median(native_all)))

    result = {
        "rounds": rounds,
        "wasm": {
            "median": statistics.median(wasm_all),
            "min": min(wasm_all),
            "max": max(wasm_all),
            "values": wasm_all,
        },
        "native": {
            "median": statistics.median(native_all),
            "min": min(native_all),
            "max": max(native_all),
            "values": native_all,
        },
        "ratio": {
            "median": statistics.median(ratios),
            "min": min(ratios),
            "max": max(ratios),
            "pairs": len(ratios),
        },
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # The file carries the identity of the machine, so that a number of this
    # directory can be told from a number of another machine.
    cpu_flags.write(out_path, result)
    print("wrote %s" % out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
