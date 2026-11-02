#!/usr/bin/env python3
"""Measures the port and the original alternately and compares them.

The machine this runs on is busy, and two runs of the *same* program differ
by a factor of two.  The difference is not a smooth jitter: it is bimodal.
The same binary, on the same input, six times in a row, gave

    44.1 ms, 20.8 ms, 42.2 ms, 40.6 ms, 41.4 ms, 39.5 ms

for the complex to complex transform of `n = 32 760`, so one run in six was
twice as fast as the others.  A statistic that keeps the *fastest* of the
runs therefore does not measure the program, it measures the luck of the
schedule, and it favours whichever side of the comparison happened to get a
lucky round.  Taking the fastest is exactly the wrong thing to do here.

This script therefore does two things differently:

* it keeps the **median** of the rounds, not the fastest, and it reports the
  spread as well, so that the reader can see how much of a difference is
  noise,
* it compares the sides **through their ratios, per round**: the ratio of
  two sides in the same round cancels the part of the noise that is common to
  both of them, and the median of those ratios is the number that is reported.
  The rounds are interleaved on purpose, and the order of the sides is
  rotated in every round, so that neither the order nor the load of the
  machine can favour one of them.

Usage::

    python tools/bench_compare.py --rounds 3
    python tools/bench_compare.py --rounds 3 --with-baseline
    python tools/bench_compare.py --rounds 3 --with-direct
    python tools/bench_compare.py --rounds 5 --with-direct --with-head \
        --sides moonbit,direct,head
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import shutil
import statistics
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
MODULE = ROOT / "moonbit_fft2"
LIB = ROOT / "tools" / "lib"

LINE = re.compile(
    r"^CASE\s+(?P<impl>\w+)\s+(?P<workload>\w+)\s+n=(?P<n>\d+)\s+ns_per_op=(?P<ns>[\d.]+)\s*$"
)
CHECKSUM = re.compile(r"^CHECKSUM\s+(?P<sum>\S+)\s*$")

WORKLOADS = [
    ("c2c", "FftComplex / FftComplex  (complex to complex)"),
    ("r2c", "FftReal / FftReal  (real to complex)"),
    ("api", "FFTMethods.realToComplex / real_to_complex"),
]


def decode(raw: bytes) -> str:
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return raw.decode("utf-16")
    return raw.decode("utf-8", errors="replace")


def parse(output: bytes) -> tuple[dict[tuple[str, int], float], str]:
    values: dict[tuple[str, int], float] = {}
    checksum = ""
    for line in decode(output).splitlines():
        m = LINE.match(line.strip())
        if m:
            values[(m.group("workload"), int(m.group("n")))] = float(m.group("ns"))
            continue
        c = CHECKSUM.match(line.strip())
        if c:
            checksum = c.group("sum")
    return values, checksum


def java_command() -> list[str]:
    cp = ";".join(
        [
            str(BUILD / "bench"),
            str(BUILD / "classes"),
            str(LIB / "imglib2-6.1.0.jar"),
            str(LIB / "mines-jtk-20151125.jar"),
        ]
    )
    return ["java", "-cp", cp, "Bench"]


def moonbit_command(module: pathlib.Path) -> list[str]:
    return ["moon", "-C", str(module), "run", "--target", "native", "./benchmark"]


class Side:
    """One side of the comparison."""

    def __init__(self, name: str, command: list[str]) -> None:
        self.name = name
        self.command = command
        self.rounds: list[dict[tuple[str, int], float]] = []
        self.checksum = ""

    def run(self) -> None:
        proc = subprocess.run(
            self.command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=str(ROOT),
        )
        values, checksum = parse(proc.stdout)
        if not values:
            raise SystemExit(
                f"{self.name} produced no measurements:\n"
                + decode(proc.stdout)[-2000:]
            )
        self.rounds.append(values)
        self.checksum = checksum

    def median(self) -> dict[tuple[str, int], float]:
        """The median of the rounds, per case.

        The median, not the fastest: the noise of this machine is bimodal,
        and the fastest of the rounds is the one that is most likely to be a
        lucky outlier rather than the speed of the program.
        """
        out: dict[tuple[str, int], float] = {}
        for values in self.rounds:
            for key, value in values.items():
                out.setdefault(key, []).append(value)  # type: ignore[union-attr]
        return {key: statistics.median(values) for key, values in out.items()}

    def spread(self, key: tuple[str, int]) -> float:
        values = [r[key] for r in self.rounds if key in r]
        if len(values) < 2:
            return 1.0
        return max(values) / min(values)


def ratio_table(sides: list[Side]) -> dict[tuple[str, int], dict[str, float]]:
    """The ratios of every pair of sides, per round, and their median.

    The ratio of two sides in the *same* round cancels the part of the noise
    that both of them see, which is the part that the order of the runs and
    the load of the machine contribute.  The median over the rounds is then a
    number that is not at the mercy of one lucky round.

    The name of a ratio is `a/b` and its value is the time of `a` divided by
    the time of `b`, so a value above one means that `a` is the slower one.
    """
    out: dict[tuple[str, int], dict[str, list[float]]] = {}
    for left_side in sides:
        for right_side in sides:
            if left_side.name == right_side.name:
                continue
            name = f"{left_side.name}/{right_side.name}"
            for round_index in range(
                min(len(left_side.rounds), len(right_side.rounds))
            ):
                left = left_side.rounds[round_index]
                right = right_side.rounds[round_index]
                for key, value in left.items():
                    if key in right and right[key] > 0:
                        out.setdefault(key, {}).setdefault(name, []).append(
                            value / right[key]
                        )
    return {
        key: {name: statistics.median(values) for name, values in names.items()}
        for key, names in out.items()
    }


def pre_kernel_revision() -> str:
    """The revision before the transform kernel was rewritten.

    It is the parent of the commit that added `moonbit_fft2/mixed_radix.mbt`,
    which is the commit that replaced the direct evaluation of the discrete
    Fourier transform by the mixed radix one.
    """
    out = subprocess.run(
        [
            "git",
            "-C",
            str(ROOT),
            "log",
            "--diff-filter=A",
            "--format=%H",
            "--",
            "moonbit_fft2/mixed_radix.mbt",
        ],
        stdout=subprocess.PIPE,
        check=True,
    ).stdout.decode("utf-8")
    commits = [line.strip() for line in out.splitlines() if line.strip()]
    if not commits:
        raise SystemExit("no revision added moonbit_fft2/mixed_radix.mbt")
    parent = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", f"{commits[-1]}^"],
        stdout=subprocess.PIPE,
        check=True,
    ).stdout.decode("utf-8")
    return parent.strip()


def baseline_side(rev: str) -> Side:
    """The port with the kernel of a given revision."""
    shadow = BUILD / "oldmodule"
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "bench_baseline.py"),
            "--rev",
            rev,
            "--assemble-only",
        ],
        check=True,
        cwd=str(ROOT),
    )
    return Side("old", moonbit_command(shadow))


def head_side() -> Side:
    """The port as it is committed, without the changes of the working tree."""
    shadow = BUILD / "headmodule"
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "bench_baseline.py"),
            "--rev",
            "HEAD",
            "--assemble-only",
            "--shadow",
            str(shadow),
        ],
        check=True,
        cwd=str(ROOT),
    )
    return Side("head", moonbit_command(shadow))


def direct_side() -> Side:
    """The port of today, with the small transform in its direct form.

    Everything else is the working tree, only `kernels.mbt` is regenerated
    with `--style direct`.  The difference to the port of today is therefore
    exactly the symmetric decomposition of the small transform, and the two
    sides are measured in the same session, one after the other.
    """
    shadow = BUILD / "directmodule"
    if shadow.exists():
        shutil.rmtree(shadow)
    shadow.mkdir(parents=True)
    for source in sorted(MODULE.rglob("*")):
        if not source.is_file():
            continue
        relative = source.relative_to(MODULE)
        if relative.parts[0] in ("_build", ".mooncakes"):
            continue
        target = shadow / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "gen_kernels.py"),
            "--out",
            str(shadow / "kernels.mbt"),
            "--style",
            "direct",
        ],
        check=True,
        cwd=str(ROOT),
    )
    return Side("direct", moonbit_command(shadow))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument(
        "--with-baseline",
        action="store_true",
        help="also measure the port with the kernel it had before the rewrite",
    )
    parser.add_argument(
        "--with-direct",
        action="store_true",
        help="also measure the port of today with the direct small transform, "
        "so that the effect of the symmetric decomposition is measured in the "
        "same session",
    )
    parser.add_argument(
        "--with-head",
        action="store_true",
        help="also measure the port as it is committed, without the changes of "
        "the working tree",
    )
    parser.add_argument(
        "--sides",
        default="",
        help="the sides to measure, comma separated, out of java, moonbit, "
        "direct, head, old.  It overrides the flags above.  The order of the "
        "sides is rotated in every round, so that the order in which they are "
        "run cannot favour one of them.",
    )
    parser.add_argument(
        "--rotate",
        action="store_true",
        default=True,
        help="rotate the order of the sides in every round (the default)",
    )
    parser.add_argument(
        "--no-rotate",
        dest="rotate",
        action="store_false",
        help="keep the order of the sides in every round",
    )
    parser.add_argument(
        "--baseline-rev",
        default="",
        help="the revision of the baseline, the parent of the commit that "
        "added the mixed radix kernel by default",
    )
    parser.add_argument(
        "--out",
        type=pathlib.Path,
        default=BUILD / "bench_compare.txt",
        help="the file the table is written to",
    )
    args = parser.parse_args()

    sides = [
        Side("java", java_command()),
        Side("moonbit", moonbit_command(MODULE)),
    ]
    if args.with_baseline:
        rev = args.baseline_rev or pre_kernel_revision()
        print(f"the baseline is the port at {rev}")
        sides.append(baseline_side(rev))
    if args.with_direct:
        print("the direct side is the port of today with the direct small transform")
        sides.append(direct_side())
    if args.with_head:
        print("the head side is the port as it is committed")
        sides.append(head_side())

    # An explicit list of sides overrides the flags.  It exists so that a
    # measurement can be repeated with a different set of sides without
    # touching the flags, and so that the order of the sides can be chosen.
    if args.sides:
        wanted = [name.strip() for name in args.sides.split(",") if name.strip()]
        unknown = [name for name in wanted if name not in {s.name for s in sides}]
        if unknown:
            raise SystemExit(f"unknown sides: {unknown}")
        sides = [side for side in sides if side.name in wanted]

    for round_index in range(args.rounds):
        # The order of the sides is rotated in every round.  Without that, a
        # side that always runs right after the slow baseline would be
        # measured under different conditions than a side that always runs
        # first.
        order = sides[round_index % len(sides) :] + sides[: round_index % len(sides)]
        for side in order:
            side.run()
            print(
                f"round {round_index + 1}/{args.rounds}: {side.name} done",
                flush=True,
            )

    best = {side.name: side.median() for side in sides}
    ratios = ratio_table(sides)
    lines: list[str] = []
    lines.append("checksums:")
    for side in sides:
        lines.append(f"  {side.name:8s} {side.checksum}")
    lines.append("")
    header = "%-6s %8s" % ("work", "n")
    for side in sides:
        header += " %14s %7s" % (side.name + " ns/op", "spread")
    lines.append(header)
    lines.append("-" * len(header))
    for key, title in WORKLOADS:
        lengths = sorted({n for (w, n) in best[sides[0].name] if w == key})
        if not lengths:
            continue
        lines.append("# " + title)
        for n in lengths:
            row = "%-6s %8d" % (key, n)
            for side in sides:
                value = best[side.name].get((key, n))
                row += " %14s" % (f"{value:.0f}" if value is not None else "-")
                row += " %6.2fx" % (side.spread((key, n)))
            lines.append(row)
        lines.append("")

    lines.append("the ratios, per round and then medianed:")
    lines.append("")
    for key, title in WORKLOADS:
        lengths = sorted({n for (w, n) in best[sides[0].name] if w == key})
        if not lengths:
            continue
        lines.append("# " + title)
        pairs = [
            f"{a.name}/{b.name}"
            for a in sides
            for b in sides
            if a.name != b.name
        ]
        lines.append("%-6s %8s" % ("work", "n") + "".join(" %12s" % p for p in pairs))
        for n in lengths:
            row = "%-6s %8d" % (key, n)
            names = ratios.get((key, n), {})
            for pair in pairs:
                value = names.get(pair)
                row += " %11.2fx" % (value if value is not None else 0.0)
            lines.append(row)
        lines.append("")

    text = "\n".join(lines)
    print(text)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text + "\n", encoding="utf-8")
    print(f"written to {args.out}")

    # The same numbers in a form that a program can read, so that the tables
    # of the document can be checked against them.
    data = {
        "rounds": args.rounds,
        "statistic": "median of the rounds",
        "checksums": {side.name: side.checksum for side in sides},
        "spread": {
            side.name: {f"{k[0]}/{k[1]}": side.spread(k) for k in best[side.name]}
            for side in sides
        },
        "best": {
            side.name: {f"{k[0]}/{k[1]}": v for k, v in best[side.name].items()}
            for side in sides
        },
        "median": {
            side.name: {f"{k[0]}/{k[1]}": v for k, v in best[side.name].items()}
            for side in sides
        },
        "ratios": {
            f"{k[0]}/{k[1]}": names for k, names in ratios.items()
        },
    }
    json_path = args.out.with_suffix(".json")
    json_path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    print(f"written to {json_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
