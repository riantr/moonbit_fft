#!/usr/bin/env python3
"""Generate the MoonBit source for the JTransforms FFT-length tables.

The tables are extracted verbatim from `edu.mines.jtk.dsp.Pfacc` (the
`edu.mines:mines-jtk` artifact used by the original imglib2-fft) so that the
dimension arithmetic of the MoonBit port is bit-identical to the Java
original.
"""

import argparse
import os


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", required=True, help="text file with 'n cost' rows")
    ap.add_argument("--out", required=True, help="MoonBit source file to write")
    args = ap.parse_args()

    rows = []
    with open(args.table, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            n, c = line.split()
            rows.append((int(n), c))

    ns = [str(r[0]) for r in rows]
    cs = [r[1] for r in rows]

    def wrap(items, indent, width=96):
        out = []
        line = indent
        for it in items:
            piece = it + ", "
            if len(line) + len(piece) > width:
                out.append(line.rstrip())
                line = indent
            line += piece
        if line.strip():
            out.append(line.rstrip().rstrip(","))
        return "\n".join(out)

    body = []
    body.append("/// Valid FFT lengths, sorted ascending.")
    body.append("///")
    body.append("/// Taken verbatim from `edu.mines.jtk.dsp.Pfacc` in the")
    body.append("/// `edu.mines:mines-jtk` artifact that the original imglib2-fft")
    body.append("/// depends on, so that size arithmetic matches the Java original.")
    body.append("let ntable : Array[Int] = [")
    body.append(wrap(ns, "  "))
    body.append("]")
    body.append("")
    body.append("/// Relative cost of each entry of `ntable`, used to pick the")
    body.append("/// \"fast\" transform length.  Also taken verbatim from JTransforms.")
    body.append("let ctable : Array[Double] = [")
    body.append(wrap(cs, "  "))
    body.append("]")
    body.append("")

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(body))
    print("wrote %s (%d entries)" % (args.out, len(rows)))


if __name__ == "__main__":
    main()
