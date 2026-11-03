"""Copies the measurements of the rounds into the tracked `bench` directory.

The tables of `BENCHMARK.md` quote the numbers of the measurements, and
`tools/check_benchmark.py` checks them against the machine readable result of
`tools/bench_compare.py`.  The result of every round is tracked, so that the
tables of the document can be checked on a fresh clone, without running the
benchmark first.

Usage::

    python tools/publish_bench.py
"""

import pathlib
import shutil

ROOT = pathlib.Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
BENCH = ROOT / "bench"

FILES = [
    # the measurement of the round of the symmetric small transform
    ("bench_kernels.json", "bench_kernels.txt"),
    # the measurement of the round of the prime factor rewrite
    ("bench_goodthomas.json", "bench_goodthomas.txt"),
    # the measurement of the round of the rewrite of the butterflies
    ("bench_compare.json", "bench_compare.txt"),
    # the measurement of the control of the factorisation
    ("bench_direct.json", "bench_direct.txt"),
]


def main() -> int:
    BENCH.mkdir(parents=True, exist_ok=True)
    for data, text in FILES:
        source = BUILD / data
        if not source.exists():
            print(f"{data} is missing, skipped")
            continue
        shutil.copy2(source, BENCH / data)
        other = BUILD / text
        if other.exists():
            shutil.copy2(other, BENCH / text)
        print(f"{data} published")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
