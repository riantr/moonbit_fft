#!/usr/bin/env python3
"""Measures what the time of the transform is spent on.

It assembles shadow modules in which parts of the butterfly are removed, and
measures them against the real kernel, alternately, in the same session.  The
difference between two of them is the cost of the part that was removed.

Three variants are measured:

``real``
    the kernel as it is.

``notwiddle``
    the twiddle factors are not applied: the butterfly reads the same data,
    but it neither reads the twiddle table nor multiplies by it.  The
    difference to ``real`` is what the twiddle factors cost, the reads of the
    table and the complex multiplications together.

``notdft``
    the multiplications of the small discrete Fourier transform are replaced
    by additions of the same values: the butterfly reads and writes the same
    data and does the same additions, but it does not multiply.  The
    difference to ``real`` is what the multiplications of the small transform
    cost.

``neither``
    both of the above.  What is left is the movement of the data and the
    bookkeeping of the loops.

None of the variants computes the right answer, of course.  They are only
here to be timed.

Usage::

    python tools/probe_attribution.py
"""

from __future__ import annotations

import pathlib
import re
import shutil
import statistics
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
MODULE = ROOT / "moonbit_fft"
SHADOWS = ROOT / "build"

# The application of the twiddle factors, one pair of lines per input:
#
#   let u1_re = x1_re * w1_re - x1_im * w1_im
#   let u1_im = x1_re * w1_im + x1_im * w1_re
TWIDDLE = re.compile(
    r"      let u(\d)_re = x\1_re \* w\1_re - x\1_im \* w\1_im\n"
    r"      let u\1_im = x\1_re \* w\1_im \+ x\1_im \* w\1_re\n"
)

# One term of a dot product of the small transform:
#
#   c1_re = c1_re + a1_re * 0.2
#
# The multiplication becomes an addition of the same value, so that the shape
# of the code and the number of the operations stay the same.
DOT = re.compile(
    r"      (c\d+_(?:re|im)) = \1 \+ (a\d+_(?:re|im)) \* (-?[\d.]+)\n"
)
DOT_ADDITION = r"      \1 = \1 + \2\n"


def assemble(name: str, patch) -> None:
    """Builds a shadow module with the kernel patched."""
    shadow = SHADOWS / name
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

    kernels = shadow / "kernels.mbt"
    text = kernels.read_text(encoding="utf-8")
    text = patch(text)
    kernels.write_text(text, encoding="utf-8", newline="")


def patch_twiddle(text: str) -> str:
    return TWIDDLE.sub(
        "      let u\\1_re = x\\1_re\n      let u\\1_im = x\\1_im\n", text
    )


def patch_dft(text: str) -> str:
    return DOT.sub(DOT_ADDITION, text)


def patch_both(text: str) -> str:
    return patch_dft(patch_twiddle(text))


LINE = re.compile(
    r"^CASE\s+(?P<impl>\w+)\s+(?P<workload>\w+)\s+n=(?P<n>\d+)\s+ns_per_op=(?P<ns>[\d.]+)\s*$"
)


def measure(command: list[str]) -> dict[tuple[str, int], float]:
    proc = subprocess.run(
        command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=str(ROOT)
    )
    out = proc.stdout.decode("utf-8", errors="replace")
    values = {}
    for line in out.splitlines():
        m = LINE.match(line.strip())
        if m:
            values[(m.group("workload"), int(m.group("n")))] = float(m.group("ns"))
    if not values:
        raise SystemExit("no measurements:\n" + out[-2000:])
    return values


def command_for(name: str) -> list[str]:
    module = MODULE if name == "real" else SHADOWS / name
    return [
        "moon",
        "-C",
        str(module),
        "run",
        "--target",
        "native",
        "--release",
        "./benchmark",
    ]


def main() -> int:
    for name, patch in (
        ("notwiddle", patch_twiddle),
        ("notdft", patch_dft),
        ("neither", patch_both),
    ):
        assemble(name, patch)
        print(f"the shadow module of {name} is ready")

    names = ["real", "notwiddle", "notdft", "neither"]
    rounds = []
    for index in range(3):
        order = names[index % len(names) :] + names[: index % len(names)]
        current = {}
        for name in order:
            current[name] = measure(command_for(name))
            print(f"round {index + 1}: {name} done", flush=True)
        rounds.append(current)

    def median_of(name: str, key) -> float:
        return statistics.median(
            [r[name][key] for r in rounds if key in r.get(name, {})]
        )

    keys = sorted(rounds[0]["real"], key=lambda k: (k[0], k[1]))
    print()
    print(
        "%-12s %11s %9s %9s %9s %9s %9s"
        % ("case", "ns/op", "twiddle", "dft mult", "all mult", "data", "other")
    )
    for key in keys:
        try:
            real = median_of("real", key)
            without_twiddle = median_of("notwiddle", key)
            without_dft = median_of("notdft", key)
            neither = median_of("neither", key)
        except statistics.StatisticsError:
            continue
        n = key[1]
        twiddle = real - without_twiddle
        dft = real - without_dft
        all_mult = real - neither
        data = neither
        other = real - all_mult
        print(
            "%-12s %11.0f %8.1f%% %8.1f%% %8.1f%% %8.1f%% %8.1f%%"
            % (
                key[0] + "/" + str(n),
                real,
                twiddle / real * 100,
                dft / real * 100,
                all_mult / real * 100,
                data / real * 100,
                other / real * 100,
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
