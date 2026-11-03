#!/usr/bin/env python3
"""Decompiles the original Java bytecode into readable Java.

The port is a translation of the original, so the original has to be readable
to be translated.  The original is shipped as bytecode only, and the
decompiler CFR is tracked in `tools/lib`, so the decompiled sources can be
rebuilt from a fresh clone with this script.

Two directories are produced:

    build/jtsrc/classes/   the class files, under their package path
    build/jtsrc/src/       the decompiled Java

The classes are the ones of the JTransforms library, `edu.mines.jtk.dsp` and
`edu.mines.jtk.util`, because the butterfly of the prime factor transform
lives in `edu.mines.jtk.dsp.Pfacc`.  The classes of `net.imglib2.algorithm.fft2`
are the ones that `tools/stage_classes.py` lays out, they are the driver of the
oracle and not the kernel.

The decompiler is run on the class file and not on the jar, so that the result
does not depend on the order of the entries of the jar.

Usage::

    python tools/decompile.py
    python tools/decompile.py --jar tools/lib/mines-jtk-20151125.jar --out build/jtsrc/src
"""

from __future__ import annotations

import argparse
import pathlib
import shutil
import subprocess
import sys
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent

DEFAULT_JAR = ROOT / "tools" / "lib" / "mines-jtk-20151125.jar"
DEFAULT_CFR = ROOT / "tools" / "lib" / "cfr-0.152.jar"
DEFAULT_CLASSES = ROOT / "build" / "jtsrc" / "classes"
DEFAULT_SRC = ROOT / "build" / "jtsrc" / "src"

# The classes of the original that are read to translate the port.
DEFAULT_TARGETS = [
    "edu/mines/jtk/dsp/Pfacc",
    "edu/mines/jtk/dsp/Fft",
    "edu/mines/jtk/dsp/FftComplex",
    "edu/mines/jtk/dsp/FftReal",
    "edu/mines/jtk/util/ArrayMath",
]


def extract(jar: pathlib.Path, targets: list[str], out: pathlib.Path) -> None:
    """Extracts the class files of the targets into `out`, under their path."""
    with zipfile.ZipFile(jar) as archive:
        names = set(archive.namelist())
        for target in targets:
            entry = target + ".class"
            if entry not in names:
                raise SystemExit("the jar has no class file: " + entry)
            destination = out / entry
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(entry) as source:
                destination.write_bytes(source.read())


def decompile(cfr: pathlib.Path, source: pathlib.Path, out: pathlib.Path) -> None:
    """Runs the decompiler on one class file."""
    command = [
        "java",
        "-jar",
        str(cfr),
        str(source),
        "--outputdir",
        str(out),
        "--silent",
        "true",
    ]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        sys.stderr.write(result.stdout)
        sys.stderr.write(result.stderr)
        raise SystemExit("the decompiler failed on " + str(source))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jar", type=pathlib.Path, default=DEFAULT_JAR, help="the jar of the original")
    parser.add_argument("--cfr", type=pathlib.Path, default=DEFAULT_CFR, help="the decompiler")
    parser.add_argument("--classes", type=pathlib.Path, default=DEFAULT_CLASSES, help="where the class files go")
    parser.add_argument("--out", type=pathlib.Path, default=DEFAULT_SRC, help="where the Java goes")
    parser.add_argument(
        "--target",
        action="append",
        default=None,
        help="the class to decompile, without the .class suffix, repeatable",
    )
    args = parser.parse_args()

    jar = args.jar.resolve()
    cfr = args.cfr.resolve()
    classes = args.classes.resolve()
    out = args.out.resolve()
    targets = args.target if args.target else DEFAULT_TARGETS

    if not jar.exists():
        print("%s does not exist, the bytecode of the original is needed." % jar)
        return 1
    if not cfr.exists():
        print("%s does not exist, the decompiler is needed." % cfr)
        return 1
    if shutil.which("java") is None:
        print("java is not on the path, it is needed to run the decompiler.")
        return 1

    extract(jar, targets, classes)

    written = 0
    for target in targets:
        source = classes / (target + ".class")
        decompile(cfr, source, out)
        produced = out / (target + ".java")
        if not produced.exists():
            raise SystemExit("the decompiler produced no source for " + target)
        written += 1

    summary = classes.parent / "summary.txt"
    summary.write_text(
        "Summary for %s\nDecompiled with CFR %s\n" % (jar, cfr.stem.replace("cfr-", "")),
        encoding="utf-8",
    )
    print("decompiled %d classes into %s" % (written, out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
