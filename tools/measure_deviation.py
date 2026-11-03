#!/usr/bin/env python3
"""Measure the numerical margin between the port and the Java original.

The generated parity test is instrumented so that every case reports the
largest ratio between the observed deviation and the tolerance that the
test allows.  The test suite is run, the maximum over all cases is printed.

The instrumented test is **not** written into the module of the port: the
module is copied into a shadow directory under `build/` first, and the copy is
the one that is patched and run.  The tracked sources are therefore left
exactly as they were, and the measurement can be taken on a read only
checkout.

A ratio well below 1 means that the port reproduces the original with a
comfortable margin.

Usage::

    python tools/measure_deviation.py
"""

from __future__ import annotations

import pathlib
import re
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PKG = ROOT / "moonbit_fft2"
SHADOW = ROOT / "build" / "deviationmodule"

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


def patch() -> pathlib.Path:
    """Copies the module into a shadow directory and instruments the copy.

    The tracked sources of the port are not touched, so that the measurement
    can be taken on a read only checkout and cannot leave the working tree in
    a state that has to be cleaned up.
    """
    if SHADOW.exists():
        shutil.rmtree(SHADOW)
    shutil.copytree(
        PKG,
        SHADOW,
        ignore=shutil.ignore_patterns("_build", ".mooncakes"),
    )
    parity = SHADOW / "parity_wbtest.mbt"
    text = parity.read_text(encoding="utf-8")
    if OLD not in text:
        raise SystemExit(
            "the parity test does not have the expected helper, regenerate it "
            "with tools/gen_parity.py first"
        )
    text = text.replace(OLD, NEW, 1)
    text = text.replace(SCALE, SCALE_NEW, 1)
    parity.write_text(text, encoding="utf-8", newline="")
    return SHADOW


def main() -> None:
    module = patch()
    proc = subprocess.run(
        ["moon", "test"],
        cwd=str(module),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
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
