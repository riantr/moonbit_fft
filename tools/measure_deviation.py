#!/usr/bin/env python3
"""Measure the numerical margin between the port and the Java original.

The generated parity test is instrumented so that every case reports the
largest ratio between the observed deviation and the tolerance that the
test allows.  The test suite is run, the maximum over all cases is printed
and the parity test is regenerated afterwards, so the working tree is left
unchanged.

A ratio well below 1 means that the port reproduces the original with a
comfortable margin.

Usage::

    python tools/measure_deviation.py
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PKG = ROOT / "moonbit_fft2"
PARITY = PKG / "parity_wbtest.mbt"

OLD = """    let allowed = tolerance * (scale + want.abs())
    assert_true(
      diff <= allowed,
      msg="value \\{i}: expected \\{want}, got \\{got}, allowed \\{allowed}",
    )
    i = i + 1
  }
}"""

NEW = """    let allowed = tolerance * (scale + want.abs())
    let ratio = if allowed > 0.0 { diff / allowed } else { 0.0 }
    if ratio > worst { worst = ratio }
    assert_true(
      diff <= allowed,
      msg="value \\{i}: expected \\{want}, got \\{got}, allowed \\{allowed}",
    )
    i = i + 1
  }
  println("DEVIATION " + worst.to_string())
}"""

SCALE = """  let mut i = 0
  while i < expected.length() {
    let magnitude"""

SCALE_NEW = """  let mut worst = Float::from_double(0.0)
  let mut i = 0
  while i < expected.length() {
    let magnitude"""


def patch() -> None:
    text = PARITY.read_text(encoding="utf-8")
    if OLD not in text:
        raise SystemExit(
            "the parity test does not have the expected helper, regenerate it "
            "with tools/gen_parity.py first"
        )
    text = text.replace(OLD, NEW, 1)
    text = text.replace(SCALE, SCALE_NEW, 1)
    PARITY.write_text(text, encoding="utf-8", newline="")


def regenerate() -> None:
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "gen_parity.py"),
            "--cases",
            str(ROOT / "build" / "cases"),
            "--out",
            str(PARITY),
        ],
        check=True,
    )
    subprocess.run(["moon", "fmt"], cwd=str(PKG), check=True)


def main() -> None:
    patch()
    try:
        proc = subprocess.run(
            ["moon", "test"],
            cwd=str(PKG),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    finally:
        regenerate()
    ratios = []
    output = (proc.stdout or "") + "\n" + (proc.stderr or "")
    for line in output.splitlines():
        if "DEVIATION" not in line:
            continue
        m = re.search(r"DEVIATION\s+([0-9.eE+-]+)", line)
        if m:
            ratios.append(float(m.group(1)))
    ratios = [r for r in ratios if r == r]
    print("moon test exit:", proc.returncode)
    print("cases with a deviation report:", len(ratios))
    if ratios:
        ratios.sort()
        print("largest ratio to the tolerance: %.6f" % ratios[-1])
        print("top five:", ["%.6f" % r for r in ratios[-5:]])
    if proc.returncode != 0:
        print("---- output tail ----")
        print("\n".join(output.splitlines()[-25:]))


if __name__ == "__main__":
    main()
