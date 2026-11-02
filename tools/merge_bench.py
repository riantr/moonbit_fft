#!/usr/bin/env python3
"""Merge several benchmark runs into one, keeping the fastest result per case.

The runs of the two implementations are done under the same protocol but the
machine load makes them differ by a few tens of percent.  For a statement
about the port being slower than the original the conservative choice is the
fastest measurement of the port, so this script keeps the minimum per case.

Usage::

    python tools/merge_bench.py build/bench_moonbit_run1.txt build/bench_moonbit_run2.txt
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

LINE = re.compile(
    r"^CASE\s+(?P<impl>\w+)\s+(?P<workload>\w+)\s+n=(?P<n>\d+)\s+ns_per_op=(?P<ns>[\d.]+)\s*$"
)


def decode(path: pathlib.Path) -> str:
    raw = path.read_bytes()
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return raw.decode("utf-16")
    return raw.decode("utf-8", errors="replace")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", nargs="+", type=pathlib.Path)
    args = parser.parse_args()

    best: dict[tuple[str, int], tuple[float, str]] = {}
    for run in args.runs:
        for line in decode(run).splitlines():
            m = LINE.match(line.strip())
            if not m:
                continue
            key = (m.group("workload"), int(m.group("n")))
            value = float(m.group("ns"))
            impl = m.group("impl")
            if key not in best or value < best[key][0]:
                best[key] = (value, impl)

    for (workload, n), (value, impl) in sorted(
        best.items(), key=lambda kv: (kv[0][0], kv[0][1])
    ):
        # The implementation of the run that produced the fastest result is
        # kept, so that a merge of the Java runs does not claim to be a
        # measurement of the port.
        sys.stdout.write(
            "CASE %s %s n=%d ns_per_op=%s\n" % (impl, workload, n, repr(value))
        )


if __name__ == "__main__":
    main()
