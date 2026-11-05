#!/usr/bin/env python3
"""Fills the placeholders of the documents from the measurements.

The documents hold placeholders of the form `{{NAME}}`, and this script
replaces them with the numbers of `bench/bench_compare.json`, the machine
readable result of `tools/bench_compare.py`.  The tables of the documents are
built the same way, so that no number in them is typed by hand.

The measurements of the rounds are tracked in `bench/`, one file per round,
so that the tables can be checked on a fresh clone.  Every round needs its
own file, because the `head` side of a comparison is the port as it is
committed, so the same table means something different in every round.

The placeholders are:

* `{{TABLE_C2C}}`, `{{TABLE_R2C}}`, `{{TABLE_API}}` - the tables of the three
  workloads,
* `{{TABLE_KERNELS}}` - the table of the kernels,
* `{{TABLE_GOODTHOMAS}}` - the table of the prime factor rewrite of the kernel,
* `{{TABLE_ORIGINAL}}` - the table of the rewrite of the butterflies,
* `{{CHECKSUM_JAVA}}`, `{{CHECKSUM_MOONBIT}}` - the checksums of the two sides,
* `{{RANGE}}`, `{{RANGE_LOW}}`, `{{RANGE_HIGH}}` - how much slower the port is
  than the JVM, over all the lengths of the three workloads,
* `{{C2C_MS}}`, `{{C2C_FACTOR}}`, `{{C2C_RATIO}}`, `{{C2C_SPEEDUP}}`,
  `{{OLD_C2C_S}}` - the transform of `n = 32 760`, against the lower bound of
  a textbook transform and against the original,
* `{{GAP_FACTOR}}` - the price of the array accesses of the runtime.

Every round of work is measured on its own, because the `head` side of a
comparison is the port as it is committed, so the same table means something
different in every round.  The measurement of the prime factor rewrite is
therefore read from `build/bench_goodthomas.json`, which is the result of the
round that did that rewrite, and the measurement of the rewrite of the
butterflies is read from `build/bench_compare.json`, which is the result of
the round that did that one.

Usage::

    python tools/render_benchmark.py
    python tools/render_benchmark.py --check
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
# The measurements of the rounds are tracked, so that the tables of the
# documents can be checked on a fresh clone.
BENCH = ROOT / "bench"
DATA = BENCH / "bench_compare.json"
# The comparison of the kernels is a separate measurement, so that the slow
# baseline of the main comparison does not sit between the sides that are
# compared.
KERNEL_DATA = BENCH / "bench_kernels.json"
# The measurement of the round that replaced the kernel by the prime factor
# algorithm of the original.  It is kept apart, because the `head` side of the
# comparison is the port as it is committed, so the same table means something
# different in every round.
GT_DATA = BENCH / "bench_goodthomas.json"
# The measurement of the control of the factorisation of the original: the
# port of today against the port with the small transform in its direct form.
DIRECT_DATA = BENCH / "bench_direct.json"

# The comparison of the port with the packages of the ecosystem, written by
# `tools/bench_ecosystem.py` and held to its reference by
# `tools/check_ecospectra.py`.
ECO_DATA = BENCH / "bench_ecosystem.json"

# The documents that hold the numbers of the measurements.
DOCUMENTS = (
    ROOT / "BENCHMARK.md",
    ROOT / "README.md",
    ROOT / "moonbit_fft" / "README.md",
)

# The lower bound of a textbook radix-2 transform of n = 32768 on this
# machine, in milliseconds, in the release build.  It is a measurement, it is
# quoted in the documents.
TEXTBOOK_MS = 1.00

WORKLOADS = ["c2c", "r2c", "api"]


def grouped(value: float) -> str:
    """Formats an integer with spaces as the thousands separator."""
    return f"{int(value):,}".replace(",", " ")


def all_ratios_of(best: dict) -> list[float]:
    """The ratio of the port to the original, over all the lengths."""
    out = []
    for key, value in best["moonbit"].items():
        java = best["java"].get(key)
        if java:
            out.append(value / java)
    return out


def slowest(best: dict) -> tuple[float, float, str]:
    """The ratio of the port to the original, over the lengths where the port
    is the slower one.

    The port is faster than the original at the small lengths that go through
    the image API, and those cases do not belong into a factor that says how
    much slower the port is.
    """
    cases = []
    for key, value in best["moonbit"].items():
        java = best["java"].get(key)
        if java and value > java:
            cases.append((value / java, key))
    if not cases:
        return 1.0, 1.0, "-"
    cases.sort()
    low = cases[0][0]
    high = cases[-1][0]
    return low, high, cases[-1][1]


def table(best: dict, workload: str, old: dict | None, spread: dict, ratios: dict) -> str:
    """The table of one workload.

    The ratio to the original and the speedup over the old kernel are the
    medians of the per round ratios, so that the part of the noise that both
    sides see cancels out.
    """
    lines = [
        "| n | Java ns/op | before ns/op | after ns/op | speedup | after / Java | spread |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    keys = sorted(
        (k for k in best["moonbit"] if k.startswith(workload + "/")),
        key=lambda k: int(k.split("/")[1]),
    )
    for key in keys:
        n = int(key.split("/")[1])
        after = best["moonbit"][key]
        java = best["java"].get(key)
        before = old.get(key) if old else None
        names = ratios.get(key, {})
        ratio = names.get("moonbit/java")
        if ratio is None and java:
            ratio = after / java
        # The speedup over the old kernel: the old kernel takes this many
        # times the time of the port.
        speed = names.get("old/moonbit")
        if speed is None and before:
            speed = before / after
        spread_value = spread.get("moonbit", {}).get(key)
        spread_text = f"{spread_value:.2f}x" if spread_value else "-"
        lines.append(
            "| %d | %s | %s | %s | %s | %s | %s |"
            % (
                n,
                grouped(java) if java else "-",
                grouped(before) if before else "-",
                grouped(after),
                f"{speed:.1f}x" if speed else "-",
                f"{ratio:.1f}x" if ratio else "-",
                spread_text,
            )
        )
    return "\n".join(lines)


def goodthomas_table(best: dict, ratios: dict) -> str:
    """The table of the prime factor rewrite.

    The `head` side is the port as it is committed, the `moonbit` side is the
    port of the working tree, which uses the prime factor algorithm of the
    original.  The ratio `head / moonbit` is taken per round and then
    medianed, so that the part of the noise that both sides see cancels out.
    A value above one means that the committed port is the slower one.
    """
    lines = [
        "| workload | n | Java ns/op | head ns/op | today ns/op | head / today | today / Java |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for workload in WORKLOADS:
        keys = sorted(
            (k for k in best["moonbit"] if k.startswith(workload + "/")),
            key=lambda k: int(k.split("/")[1]),
        )
        if not keys:
            continue
        if len(lines) > 2:
            lines.append("")
        for key in keys:
            n = int(key.split("/")[1])
            today = best["moonbit"][key]
            head = best.get("head", {}).get(key)
            java = best["java"].get(key)
            names = ratios.get(key, {})
            over_head = names.get("head/moonbit")
            over_java = names.get("moonbit/java")
            lines.append(
                "| %s | %d | %s | %s | %s | %s | %s |"
                % (
                    workload,
                    n,
                    grouped(java) if java else "-",
                    grouped(head) if head else "-",
                    grouped(today),
                    f"{over_head:.2f}x" if over_head else "-",
                    f"{over_java:.2f}x" if over_java else "-",
                )
            )
    return "\n".join(lines)


def direct_table(best: dict, ratios: dict) -> str:
    """The table of the control of the factorisation of the original.

    The `direct` side is the port of today with the small transform in its
    direct form: every output is the sum of the `r` inputs times the `r` roots
    of unity.  It computes the same transform as the port of today, so the
    ratio of the two sides is what the factorisation of the original is
    worth.  A value above one under `direct / today` means that the direct
    form is the slower one.

    The measurement has only the two sides of the comparison, because it is
    run in its own session and the machine is not always idle; the ratio is
    taken per round and then medianed, so it does not depend on the load.
    """
    lines = [
        "| workload | n | direct ns/op | today ns/op | direct / today |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for workload in WORKLOADS:
        keys = sorted(
            (k for k in best.get("moonbit", {}) if k.startswith(workload + "/")),
            key=lambda k: int(k.split("/")[1]),
        )
        if not keys:
            continue
        if len(lines) > 2:
            lines.append("")
        for key in keys:
            n = int(key.split("/")[1])
            today = best["moonbit"][key]
            direct = best.get("direct", {}).get(key)
            names = ratios.get(key, {})
            over_direct = names.get("direct/moonbit")
            lines.append(
                "| %s | %d | %s | %s | %s |"
                % (
                    workload,
                    n,
                    grouped(direct) if direct else "-",
                    grouped(today),
                    f"{over_direct:.2f}x" if over_direct else "-",
                )
            )
    return "\n".join(lines)


def kernel_table(best: dict, ratios: dict) -> str:
    """The table of the kernels, for the three workloads.

    The two columns on the right are the ratios of the sides, taken per round
    and then medianed, so that the part of the noise that both sides see
    cancels out.  A value above one means that the side in the numerator is
    the slower one, so `1.10x` under `direct / today` means that the direct
    small transform is ten percent slower than the symmetric one.
    """
    lines = [
        "| workload | n | head ns/op | direct ns/op | today ns/op | head / today | direct / today |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for workload in WORKLOADS:
        keys = sorted(
            (k for k in best["moonbit"] if k.startswith(workload + "/")),
            key=lambda k: int(k.split("/")[1]),
        )
        if not keys:
            continue
        if lines:
            lines.append("")
        for key in keys:
            n = int(key.split("/")[1])
            today = best["moonbit"][key]
            head = best.get("head", {}).get(key)
            direct = best.get("direct", {}).get(key)
            names = ratios.get(key, {})
            over_head = names.get("head/moonbit")
            over_direct = names.get("direct/moonbit")
            lines.append(
                "| %s | %d | %s | %s | %s | %s | %s |"
                % (
                    workload,
                    n,
                    grouped(head) if head else "-",
                    grouped(direct) if direct else "-",
                    grouped(today),
                    f"{over_head:.2f}x" if over_head else "-",
                    f"{over_direct:.2f}x" if over_direct else "-",
                )
            )
    return "\n".join(lines)


def replace_block(text: str, name: str, body: str) -> str:
    """Replaces the body of a marked block.

    The blocks are written as

        <!--t:NAME--> ... <!--/t-->

    The comments are invisible in the rendered document, and they survive the
    rendering, so the script can be run again after a new measurement: it
    replaces the body of the block and nothing else.  A plain `{{NAME}}`
    placeholder is accepted as well, for the first run.
    """
    start = f"<!--t:{name}-->"
    end = "<!--/t-->"
    if start in text and end in text:
        head, rest = text.split(start, 1)
        _, tail = rest.split(end, 1)
        return head + start + "\n" + body + "\n" + end + tail
    return text.replace("{{" + name + "}}", body)


def replace_value(text: str, name: str, value: str) -> str:
    """Replaces the value of a marked span.

    The span is written as `<!--v:NAME--> ... <!--/v-->`, and the plain
    `{{NAME}}` placeholder is accepted as well.  A name may be used more than
    once in a document, and every use is replaced.
    """
    start = f"<!--v:{name}-->"
    end = "<!--/v-->"
    if start in text and end in text:
        out: list[str] = []
        rest = text
        while start in rest:
            head, tail = rest.split(start, 1)
            _, tail = tail.split(end, 1)
            out.append(head)
            out.append(start)
            out.append(value)
            out.append(end)
            rest = tail
        out.append(rest)
        return "".join(out)
    return text.replace("{{" + name + "}}", value)


def eco_values(eco: dict) -> dict[str, str]:
    """The values of the placeholders of the ecosystem comparison.

    `ECO_NEAR` is the range of the ratios of the one package that is in the
    class of the port, `HK-SHAO/dsp`, over the two windows the two of them can
    share; `ECO_FAR` is the range over every other side, rounded to whole
    numbers, because a reader of a README wants the order of a difference and
    not its third digit.
    """
    ratios = eco.get("ratios", {})
    near: list[float] = []
    far: list[float] = []
    for window in ratios:
        for name, value in ratios[window].items():
            side = name.split("/")[0]
            if side == "port":
                continue
            if side == "hkdsp":
                near.append(value)
            else:
                far.append(value)
    return {
        "ECO_NEAR": ("%.2fx to %.2fx" % (min(near), max(near)))
        if near else "not measured",
        "ECO_FAR": ("%d to %d" % (round(min(far)), round(max(far))))
        if far else "not measured",
        "ECO_ROUNDS": str(eco.get("rounds", 0)),
    }


def values_of(data: dict, kernel_data: dict, gt_data: dict, direct_data: dict, eco_data: dict) -> dict[str, str]:
    """The values of the placeholders."""
    best = data.get("median") or data["best"]
    spread = data.get("spread", {})
    old = best.get("old")
    checksums = data.get("checksums", {})
    ratios = data.get("ratios", {})

    # The kernel that transformed `O(n^2)` is the same code in every round, and
    # it is thousands of times slower than the port, so the session it was
    # measured in does not matter.  It is taken from the round of the prime
    # factor rewrite, which measured it.
    gt_best = gt_data.get("median") or gt_data.get("best", {})
    gt_ratios = gt_data.get("ratios", {})
    if old is None:
        old = gt_best.get("old")

    # The table of the kernels comes from the separate comparison, and the
    # ratio of its sides is taken from there as well.
    kernel_best = kernel_data.get("median") or kernel_data.get("best", {})
    kernel_ratios = kernel_data.get("ratios", {})

    all_ratios = all_ratios_of(best)
    low, high = min(all_ratios), max(all_ratios)
    slow_low, slow_high, slow_case = slowest(best)

    c2c = best["moonbit"]["c2c/32760"]
    c2c_ms = c2c / 1e6
    java_c2c = best["java"]["c2c/32760"]
    old_c2c = old["c2c/32760"] if old else 0

    # How much the symmetric decomposition of the small transform bought.
    # It is the median of the per round ratios, so that the noise that both
    # sides see cancels out.  The short and the long transforms are reported
    # separately, because they say different things: the fixed costs dominate
    # the short ones, and the butterflies dominate the long ones.
    short_values = []
    long_values = []
    for key in kernel_best.get("moonbit", {}):
        value = kernel_ratios.get(key, {}).get("direct/moonbit")
        if not value:
            continue
        if int(key.split("/")[1]) >= 4095:
            long_values.append(value)
        else:
            short_values.append(value)
    if long_values:
        kernel_range = (
            "%.2fx to %.2fx for the long transforms, and %.2fx to %.2fx for the "
            "short ones"
            % (
                min(long_values),
                max(long_values),
                min(short_values) if short_values else 1.0,
                max(short_values) if short_values else 1.0,
            )
        )
    else:
        kernel_range = "not measured"

    # How much the prime factor rewrite of the kernel bought: the ratio of
    # the committed port to the port of the working tree, per round.  The
    # ratio of the two sides is the time of the committed port divided by
    # the time of the port of today, so a value above one is the gain.  The
    # measurement is the one of the round that did that rewrite, not the one
    # of the round that is running now.
    gains = []
    long_gains = []
    for key in gt_best.get("moonbit", {}):
        value = gt_ratios.get(key, {}).get("head/moonbit")
        if not value:
            continue
        gains.append(value)
        if int(key.split("/")[1]) >= 4095:
            long_gains.append(value)
    if gains:
        gt_range = "%.2fx to %.2fx" % (min(gains), max(gains))
        gt_long = "%.2fx to %.2fx" % (min(long_gains), max(long_gains))
    else:
        gt_range = "not measured"
        gt_long = "not measured"

    # How much the rewrite of the butterflies bought: the same ratio, taken
    # from the measurement of the round that did that rewrite.
    orig_gains = []
    orig_long = []
    for key in best.get("moonbit", {}):
        value = ratios.get(key, {}).get("head/moonbit")
        if not value:
            continue
        orig_gains.append(value)
        if int(key.split("/")[1]) >= 4095:
            orig_long.append(value)
    if orig_gains:
        orig_range = "%.2fx to %.2fx" % (min(orig_gains), max(orig_gains))
        orig_long_range = "%.2fx to %.2fx" % (min(orig_long), max(orig_long))
    else:
        orig_range = "not measured"
        orig_long_range = "not measured"

    # What the factorisation of the original is worth against the direct
    # evaluation of the small transform.
    direct_best = direct_data.get("median") or direct_data.get("best", {})
    direct_ratios = direct_data.get("ratios", {})
    direct_values = []
    direct_long = []
    for key in direct_best.get("moonbit", {}):
        value = direct_ratios.get(key, {}).get("direct/moonbit")
        if not value:
            continue
        direct_values.append(value)
        if int(key.split("/")[1]) >= 4095:
            direct_long.append(value)
    if direct_values:
        direct_range = "%.2fx to %.2fx" % (min(direct_values), max(direct_values))
        direct_long_range = "%.2fx to %.2fx" % (min(direct_long), max(direct_long))
    else:
        direct_range = "not measured"
        direct_long_range = "not measured"

    return {
        "TABLE_C2C": table(best, "c2c", old, spread, ratios),
        "TABLE_R2C": table(best, "r2c", old, spread, ratios),
        "TABLE_API": table(best, "api", old, spread, ratios),
        "TABLE_KERNELS": kernel_table(kernel_best, kernel_ratios),
        "TABLE_GOODTHOMAS": goodthomas_table(gt_best, gt_ratios),
        "TABLE_ORIGINAL": goodthomas_table(best, ratios),
        "TABLE_DIRECT": direct_table(direct_best, direct_ratios),
        "CHECKSUM_JAVA": checksums.get("java", "-"),
        "CHECKSUM_MOONBIT": checksums.get("moonbit", "-"),
        "RANGE": f"{slow_low:.1f} to {slow_high:.1f}",
        "RANGE_LOW": f"{slow_low:.1f}",
        "RANGE_HIGH": f"{slow_high:.1f}",
        "RANGE_ALL": f"{low:.1f} to {high:.1f}",
        "SLOWEST_CASE": slow_case,
        "C2C_MS": f"{c2c_ms:.1f}",
        "C2C_FACTOR": f"{c2c_ms / TEXTBOOK_MS:.1f}",
        "C2C_RATIO": f"{c2c / java_c2c:.1f}",
        "C2C_SPEEDUP": f"{old_c2c / c2c:.0f}",
        "OLD_C2C_S": f"{old_c2c / 1e9:.1f}",
        # The price of the array accesses: the cost of one element of the
        # textbook transform against the cost of one point of the Java
        # original.
        "GAP_FACTOR": f"{30.4 / 8.6:.1f}",
        "KERNEL_RANGE": kernel_range,
        "GT_RANGE": gt_range,
        "GT_LONG": gt_long,
        "ORIG_RANGE": orig_range,
        "ORIG_LONG": orig_long_range,
        "DIRECT_RANGE": direct_range,
        "DIRECT_LONG": direct_long_range,
        **eco_values(eco_data),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="only report the documents that are not in sync, do not write",
    )
    args = parser.parse_args()

    if not DATA.exists():
        print(f"{DATA} does not exist, run tools/bench_compare.py first")
        return 1
    data = json.loads(DATA.read_text(encoding="utf-8"))
    kernel_data = {}
    if KERNEL_DATA.exists():
        kernel_data = json.loads(KERNEL_DATA.read_text(encoding="utf-8"))
    else:
        print(f"{KERNEL_DATA} does not exist, the table of the kernels is empty")
    gt_data = {}
    if GT_DATA.exists():
        gt_data = json.loads(GT_DATA.read_text(encoding="utf-8"))
    else:
        print(f"{GT_DATA} does not exist, the table of the prime factor rewrite is empty")
    direct_data = {}
    if DIRECT_DATA.exists():
        direct_data = json.loads(DIRECT_DATA.read_text(encoding="utf-8"))
    else:
        print(f"{DIRECT_DATA} does not exist, the table of the control is empty")
    eco_data = {}
    if ECO_DATA.exists():
        eco_data = json.loads(ECO_DATA.read_text(encoding="utf-8"))
    else:
        print(f"{ECO_DATA} does not exist, the ecosystem comparison is empty")
    values = values_of(data, kernel_data, gt_data, direct_data, eco_data)

    out_of_sync = []
    for document in DOCUMENTS:
        text = document.read_text(encoding="utf-8")
        rendered = text
        for name, value in values.items():
            if name.startswith("TABLE_"):
                rendered = replace_block(rendered, name, value)
            else:
                rendered = replace_value(rendered, name, value)
        left = re.findall(r"\{\{[A-Z_0-9]+\}\}", rendered)
        if left:
            print(f"{document}: the placeholders {sorted(set(left))} are unknown")
            return 1
        if rendered != text:
            out_of_sync.append(document)
            if not args.check:
                document.write_text(rendered, encoding="utf-8", newline="")
    if args.check:
        if out_of_sync:
            for document in out_of_sync:
                print(f"{document} is not in sync with the measurements")
            return 1
        print("OK: the documents are in sync with the measurements")
        return 0

    for document in DOCUMENTS:
        print(f"{document.relative_to(ROOT)} rendered from {DATA.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
