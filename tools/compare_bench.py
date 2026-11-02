#!/usr/bin/env python3
"""Join the Java and the MoonBit benchmark results into one table.

Both sides print the lines

    CASE <impl> <workload> n=<length> ns_per_op=<nanoseconds>

so the two outputs can be joined by workload and length.

Usage::

    python tools/compare_bench.py build/bench_java.txt build/bench_moonbit.txt
"""

from __future__ import annotations

import argparse
import pathlib
import re

LINE = re.compile(r"^CASE\s+(?P<impl>\w+)\s+(?P<workload>\w+)\s+n=(?P<n>\d+)\s+ns_per_op=(?P<ns>[\d.]+)\s*$")

WORKLOADS = [
    ("c2c", "FftComplex / FftComplex  (complex to complex)"),
    ("r2c", "FftReal / FftReal  (real to complex)"),
    ("api", "FFTMethods.realToComplex / real_to_complex"),
]


def read(path: pathlib.Path) -> dict:
    out = {}
    if not path.exists():
        return out
    # The benchmark output is written through a shell redirection, which on
    # Windows may produce UTF-16 (PowerShell) or UTF-8 (cmd, native tools).
    raw = path.read_bytes()
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        text = raw.decode("utf-16")
    else:
        text = raw.decode("utf-8", errors="replace")
    for line in text.splitlines():
        m = LINE.match(line.strip())
        if not m:
            continue
        key = (m.group("workload"), int(m.group("n")))
        out[key] = (m.group("impl"), float(m.group("ns")))
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("java", type=pathlib.Path)
    parser.add_argument("moonbit", type=pathlib.Path)
    args = parser.parse_args()

    java = read(args.java)
    moon = read(args.moonbit)

    print("%-6s %8s %14s %14s %10s" % ("work", "n", "java ns/op", "moonbit ns/op", "moonbit/java"))
    print("-" * 60)
    for key, title in WORKLOADS:
        lengths = sorted({n for (w, n) in list(java) + list(moon) if w == key})
        if not lengths:
            continue
        print("# " + title)
        for n in lengths:
            j = java.get((key, n))
            m = moon.get((key, n))
            if j is None or m is None:
                missing = "java" if j is None else "moonbit"
                print("%-6s %8d %14s %14s %10s" % (key, n, j[1] if j else "-", m[1] if m else "-", "no " + missing))
                continue
            ratio = m[1] / j[1] if j[1] else 0.0
            print(
                "%-6s %8d %14.0f %14.0f %9.1fx"
                % (key, n, j[1], m[1], ratio)
            )
        print()


if __name__ == "__main__":
    main()
