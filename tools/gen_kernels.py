#!/usr/bin/env python3
"""Generate the specialised butterflies of the mixed radix transform.

The generic transform of `moonbit_fft2/mixed_radix.mbt` evaluates the small
discrete Fourier transform of every stage with a precomputed matrix.  That
matrix costs `r * r` complex multiplications and, worse, `r * r` array
accesses per butterfly, which dominates the run time in MoonBit.

This generator writes one specialised butterfly per radix instead.  The
constants of the small transform are compile time literals, exactly like the
`P120`, `P142`, ... constants of the prime factor algorithm of the Java
original, so the inner loop of the butterfly needs no matrix at all.  The
twiddle factors of the stage still depend on the length of the transform and
are read from the plan.

Usage::

    python tools/gen_kernels.py --out moonbit_fft2/kernels.mbt
"""

from __future__ import annotations

import argparse
import math
import pathlib

# The radices the valid transform lengths are built from.
RADICES = [2, 3, 5, 7, 11, 13]


def fmt(value: float) -> str:
    """Formats a double as a literal that keeps all of its bits."""
    if value == 0.0:
        return "0.0"
    if value == 1.0:
        return "1.0"
    if value == -1.0:
        return "-1.0"
    text = repr(value)
    if "." not in text and "e" not in text and "E" not in text:
        text += ".0"
    return text


def root(r: int, k: int) -> tuple[float, float]:
    """The root of unity `exp(-2 * pi * i * k / r)`.

    The trivial roots of unity are returned exactly, so that the generated
    code uses an addition or a subtraction instead of a multiplication by a
    constant that is one or minus one.
    """
    k = k % r
    if k == 0:
        return (1.0, 0.0)
    if r % 2 == 0 and k == r // 2:
        return (-1.0, 0.0)
    if r % 4 == 0 and k == r // 4:
        return (0.0, -1.0)
    if r % 4 == 0 and k == 3 * r // 4:
        return (0.0, 1.0)
    angle = -2.0 * math.pi * k / r
    cr = math.cos(angle)
    ci = math.sin(angle)
    # The remaining roots have a vanishing component, which the trigonometry
    # does not return exactly.
    if abs(cr) < 1e-15:
        cr = 0.0
    if abs(ci) < 1e-15:
        ci = 0.0
    return (cr, ci)


def emit_dft_term(
    out: list[str],
    indent: str,
    s: int,
    p: int,
    r: int,
    re_name: str,
    im_name: str,
    acc_re: str,
    acc_im: str,
) -> None:
    """Emits one term of the small discrete Fourier transform."""
    cr, ci = root(r, (s * p) % r)
    # The trivial roots of unity are written out, so that the compiler does
    # not have to fold them.
    if ci == 0.0 and cr == 1.0:
        out.append(f"{indent}{acc_re} = {acc_re} + {re_name}")
        out.append(f"{indent}{acc_im} = {acc_im} + {im_name}")
        return
    if ci == 0.0 and cr == -1.0:
        out.append(f"{indent}{acc_re} = {acc_re} - {re_name}")
        out.append(f"{indent}{acc_im} = {acc_im} - {im_name}")
        return
    if cr == 0.0 and ci == 1.0:
        out.append(f"{indent}{acc_re} = {acc_re} - {im_name}")
        out.append(f"{indent}{acc_im} = {acc_im} + {re_name}")
        return
    if cr == 0.0 and ci == -1.0:
        out.append(f"{indent}{acc_re} = {acc_re} + {im_name}")
        out.append(f"{indent}{acc_im} = {acc_im} - {re_name}")
        return
    out.append(
        f"{indent}{acc_re} = {acc_re} + {re_name} * {fmt(cr)}"
    )
    out.append(
        f"{indent}{acc_re} = {acc_re} - {im_name} * {fmt(ci)}"
    )
    out.append(
        f"{indent}{acc_im} = {acc_im} + {re_name} * {fmt(ci)}"
    )
    out.append(
        f"{indent}{acc_im} = {acc_im} + {im_name} * {fmt(cr)}"
    )


def emit_radix(r: int) -> list[str]:
    """Emits the butterfly of one radix."""
    out: list[str] = []
    out.append("///|")
    out.append(f"/// The butterfly of the radix {r} stage of the mixed radix transform.")
    out.append("///")
    out.append("/// The values of the butterfly are read from `re` and `im`, the")
    out.append("/// twiddle factors of the stage from `tw_re` and `tw_im`, and the")
    out.append("/// result is written back to `re` and `im`.")
    out.append("fn stage_r" + str(r) + "(")
    out.append("  n : Int32,")
    out.append("  l : Int32,")
    out.append("  m : Int32,")
    out.append("  tw_off : Int32,")
    out.append("  tw_re : Array[Double],")
    out.append("  tw_im : Array[Double],")
    out.append("  re : Array[Double],")
    out.append("  im : Array[Double],")
    out.append(") -> Unit {")
    out.append("  let nblocks = n / l")
    out.append("  let mut b = 0")
    out.append("  while b < nblocks {")
    out.append("    let base = b * l")
    out.append("    let mut k0 = 0")
    out.append("    while k0 < m {")
    # Gather the values of the butterfly and apply the twiddle factors.  The
    # factor of the first value is one, it is skipped.
    for s in range(r):
        idx = f"base + k0 + {s} * m"
        out.append(f"      let x{s}_re = re[{idx}]")
        out.append(f"      let x{s}_im = im[{idx}]")
        if s == 0:
            out.append(f"      let u{s}_re = x{s}_re")
            out.append(f"      let u{s}_im = x{s}_im")
        else:
            tw = f"tw_off + k0 * {r} + {s}"
            out.append(f"      let t{s} = {tw}")
            out.append(f"      let u{s}_re = x{s}_re * tw_re[t{s}] - x{s}_im * tw_im[t{s}]")
            out.append(f"      let u{s}_im = x{s}_re * tw_im[t{s}] + x{s}_im * tw_re[t{s}]")
    # The small discrete Fourier transform of the butterfly.
    for p in range(r):
        out.append(f"      let mut v{p}_re = 0.0")
        out.append(f"      let mut v{p}_im = 0.0")
        for s in range(r):
            emit_dft_term(
                out,
                "      ",
                s,
                p,
                r,
                f"u{s}_re",
                f"u{s}_im",
                f"v{p}_re",
                f"v{p}_im",
            )
    for p in range(r):
        out.append(f"      re[base + k0 + {p} * m] = v{p}_re")
        out.append(f"      im[base + k0 + {p} * m] = v{p}_im")
    out.append("      k0 = k0 + 1")
    out.append("    }")
    out.append("    b = b + 1")
    out.append("  }")
    out.append("}")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=pathlib.Path, required=True)
    args = parser.parse_args()

    lines: list[str] = []
    lines.append("///|")
    lines.append("/// The specialised butterflies of the mixed radix transform.")
    lines.append("///")
    lines.append("/// This file is generated by `tools/gen_kernels.py`, do not edit it")
    lines.append("/// by hand.")
    lines.append("")
    for r in RADICES:
        lines.extend(emit_radix(r))
        lines.append("")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes("\n".join(lines).encode("utf-8"))


if __name__ == "__main__":
    main()
