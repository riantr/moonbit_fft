#!/usr/bin/env python3
"""Checks the golden data of the `JC2C` cases against a double precision reference.

The oracle drives `edu.mines.jtk.dsp.FftComplex.complexToComplex(sign, cx, cy)`
of the original for the `JC2C` cases.  That class is the one the `FftComplex`
of the port mirrors, and it is the one whose copy of the input into the
output the port no longer does, so these cases hold the port to the original
where it matters.

The golden data of a case is the output of the original, which accumulates
in single precision.  This script recomputes the same transform in double
precision with numpy and compares the two, which checks two things at once:
that the golden data holds the direction the case asks for - the forward and
the inverse transform of the same input are different - and that the numbers
themselves are the spectrum and not something else.

Usage::

    python tools/check_jc2c.py [--cases build/cases] [--tolerance 2e-3]
"""

from __future__ import annotations

import argparse
import pathlib
import struct
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent.parent


def read_f32(path: pathlib.Path) -> np.ndarray:
    raw = path.read_bytes()
    return np.frombuffer(raw, dtype="<f4")


def read_golden(path: pathlib.Path) -> np.ndarray:
    """The values of one oracle output file.

    The oracle writes the bits of every sample as `%08x` of the integer
    `Float.floatToRawIntBits` returns, so the hex string is the *integer* of
    the bit pattern and not a byte sequence of the file.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    values: list[float] = []
    index = 0
    while index < len(lines):
        parts = lines[index].strip().split()
        if not parts:
            index += 1
            continue
        if parts[0] == "N":
            count = int(parts[1])
            for i in range(count):
                values.append(
                    struct.unpack(
                        "<f", struct.pack("<I", int(lines[index + 1 + i], 16))
                    )[0]
                )
            index += count
        elif parts[0] == "EXTRA":
            index += 1 + int(parts[1])
        index += 1
    return np.array(values, dtype=np.float64)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", default=str(ROOT / "build" / "cases"))
    parser.add_argument(
        "--tolerance", type=float, default=2e-3,
        help="the relative deviation that is accepted, the original accumulates "
             "in single precision",
    )
    args = parser.parse_args()
    cases = pathlib.Path(args.cases)
    java = cases / "java"
    if not java.is_dir():
        print("%s does not exist, run the oracle first" % java)
        return 1

    problems = 0
    checked = 0
    for golden_path in sorted(java.glob("jc2c_*.txt")):
        name = golden_path.stem
        forward = name.endswith("_fwd")
        n = int(name.split("_")[2])
        src = read_f32(cases / name / "in.bin").astype(np.float64)
        cx = src[0::2] + 1j * src[1::2]
        # The convention of the original and of the port: the forward
        # transform is the sum with `exp(-2 pi i j k / n)`, the inverse is the
        # same sum with the other sign and it is *not* normalised.
        spectrum = np.fft.fft(cx) if forward else np.fft.ifft(cx) * n
        reference = np.empty(2 * n, dtype=np.float64)
        reference[0::2] = spectrum.real
        reference[1::2] = spectrum.imag
        golden = read_golden(golden_path)
        if golden.shape != reference.shape:
            print("%s: the golden holds %d values, the reference has %d" % (
                name, golden.size, reference.size))
            problems += 1
            continue
        scale = max(1.0, float(np.abs(reference).max()))
        deviation = float(np.abs(golden - reference).max())
        if deviation > args.tolerance * scale:
            print("%s: the golden deviates %.3g from the reference (scale %.3g)" % (
                name, deviation, scale))
            problems += 1
        else:
            print("%-20s n=%-5d %s  max deviation %.3g (scale %.3g)" % (
                name, n, "fwd" if forward else "inv", deviation, scale))
        checked += 1

    print()
    print("checked %d golden files, %d problems" % (checked, problems))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
