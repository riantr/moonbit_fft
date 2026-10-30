#!/usr/bin/env python3
"""Stage the original bytecode into the package layout that javac expects.

The class files of ``net.imglib2.algorithm.fft2`` are shipped flat in the
``fft2`` directory, but the compiler and the runtime look them up under their
package path.  This script copies them into

    build/classes/net/imglib2/algorithm/fft2/

which is the classpath root of the oracle.  It has to run before the oracle
is compiled, otherwise the imports of ``net.imglib2.algorithm.fft2`` cannot
be resolved.

Usage::

    python tools/stage_classes.py
    python tools/stage_classes.py --src fft2 --out build/classes
"""

from __future__ import annotations

import argparse
import pathlib
import shutil

PACKAGE = "net/imglib2/algorithm/fft2"


def main() -> None:
    root = pathlib.Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", default="fft2", help="directory with the class files")
    parser.add_argument("--out", default="build/classes", help="classpath root to create")
    parser.add_argument("--package", default=PACKAGE, help="package path of the classes")
    args = parser.parse_args()

    src = (root / args.src).resolve()
    target = (root / args.out).resolve() / args.package
    if not src.is_dir():
        raise SystemExit("no such directory: " + str(src))

    classes = sorted(src.glob("*.class"))
    if not classes:
        raise SystemExit("no class files found in " + str(src))

    target.mkdir(parents=True, exist_ok=True)
    for path in classes:
        shutil.copyfile(path, target / path.name)
    print("staged %d class files into %s" % (len(classes), target))


if __name__ == "__main__":
    main()
