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

Two styles are available for the odd radices:

``direct``
    The small transform is evaluated the obvious way, every output is the
    sum of the `r` inputs times the `r` roots of unity.  That costs `4 * (r
    - 1) * (r - 1)` real multiplications and as many additions.

``symmetric``
    The small transform uses the symmetry of the roots of unity.  For an odd
    radix `r` the inputs are paired, `A_s = x_s + x_{r-s}` and `B_s = x_s -
    x_{r-s}`, and the output `p` becomes

        X[p] = x_0 + sum over s of (A_s * cos(2 pi s p / r)
                                    - i * B_s * sin(2 pi s p / r))

    while `X[r-p]` uses the same two sums with the opposite sign of the
    sine.  That costs `(r - 1) * (r - 1)` real multiplications, a quarter
    of the direct form, and fewer additions as well.  The prime factor
    algorithm of the Java original uses the same idea.

Usage::

    python tools/gen_kernels.py --out moonbit_fft2/kernels.mbt
    python tools/gen_kernels.py --out moonbit_fft2/kernels.mbt --style direct
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


def cossin(r: int, k: int) -> tuple[float, float]:
    """The cosine and the sine of `2 * pi * k / r`.

    The signs are the ones of the forward transform of the port, which uses
    `exp(-2 * pi * i * j * k / n)`.
    """
    k = k % r
    angle = 2.0 * math.pi * k / r
    cr = math.cos(angle)
    ci = math.sin(angle)
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


def emit_header(out: list[str], r: int) -> None:
    """Emits the documentation and the signature of one butterfly."""
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
            # The two twiddle factors are read into locals, so that the
            # butterfly reads them from the table once instead of twice.
            out.append(f"      let w{s}_re = tw_re[t{s}]")
            out.append(f"      let w{s}_im = tw_im[t{s}]")
            out.append(
                f"      let u{s}_re = x{s}_re * w{s}_re - x{s}_im * w{s}_im"
            )
            out.append(
                f"      let u{s}_im = x{s}_re * w{s}_im + x{s}_im * w{s}_re"
            )


def emit_direct(r: int) -> list[str]:
    """Emits the butterfly of one radix, with the direct small transform."""
    out: list[str] = []
    emit_header(out, r)
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


def emit_symmetric(r: int) -> list[str]:
    """Emits the butterfly of one odd radix, with the symmetric small transform.

    The inputs are paired, `A_s = u_s + u_{r-s}` and `B_s = u_s - u_{r-s}`,
    and the output `p` is

        X[p] = u_0 + sum over s of (A_s * cos(2 pi s p / r)
                                    - i * B_s * sin(2 pi s p / r))

    The output `r - p` uses the same sums with the opposite sign of the
    sine, so both of them cost the same four dot products.
    """
    out: list[str] = []
    half = (r - 1) // 2
    emit_header(out, r)
    # The pairs of the inputs.
    for s in range(1, half + 1):
        other = r - s
        out.append(f"      let a{s}_re = u{s}_re + u{other}_re")
        out.append(f"      let a{s}_im = u{s}_im + u{other}_im")
        out.append(f"      let b{s}_re = u{s}_re - u{other}_re")
        out.append(f"      let b{s}_im = u{s}_im - u{other}_im")
    # The output zero is the sum of all the inputs.
    out.append("      let mut v0_re = u0_re")
    out.append("      let mut v0_im = u0_im")
    for s in range(1, half + 1):
        out.append(f"      v0_re = v0_re + a{s}_re")
        out.append(f"      v0_im = v0_im + a{s}_im")
    # The outputs one to half, and their partners.
    #
    # With A_s = a_s + i * alpha_s and B_s = b_s + i * beta_s the output p is
    #
    #   Re(X[p]) = Re(x_0) + sum (Re(A_s) cos + Im(B_s) sin)
    #   Im(X[p]) = Im(x_0) + sum (Im(A_s) cos - Re(B_s) sin)
    #
    # and the output r - p has the opposite sign of the sine part.  So four
    # dot products per output pair are enough.
    for p in range(1, half + 1):
        out.append(f"      let mut c{p}_re = u0_re")
        out.append(f"      let mut c{p}_im = u0_im")
        out.append(f"      let mut d{p}_re = 0.0")
        out.append(f"      let mut d{p}_im = 0.0")
        for s in range(1, half + 1):
            cr, ci = cossin(r, (s * p) % r)
            out.append(f"      c{p}_re = c{p}_re + a{s}_re * {fmt(cr)}")
            out.append(f"      c{p}_im = c{p}_im + a{s}_im * {fmt(cr)}")
            out.append(f"      d{p}_re = d{p}_re + b{s}_re * {fmt(ci)}")
            out.append(f"      d{p}_im = d{p}_im + b{s}_im * {fmt(ci)}")
    # Write the results back.
    out.append("      re[base + k0 + 0 * m] = v0_re")
    out.append("      im[base + k0 + 0 * m] = v0_im")
    for p in range(1, half + 1):
        other = r - p
        out.append(f"      re[base + k0 + {p} * m] = c{p}_re + d{p}_im")
        out.append(f"      im[base + k0 + {p} * m] = c{p}_im - d{p}_re")
        out.append(f"      re[base + k0 + {other} * m] = c{p}_re - d{p}_im")
        out.append(f"      im[base + k0 + {other} * m] = c{p}_im + d{p}_re")
    out.append("      k0 = k0 + 1")
    out.append("    }")
    out.append("    b = b + 1")
    out.append("  }")
    out.append("}")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=pathlib.Path, required=True)
    parser.add_argument(
        "--style",
        choices=["symmetric", "direct"],
        default="symmetric",
        help="the style of the small transform of the odd radices",
    )
    args = parser.parse_args()

    lines: list[str] = []
    lines.append("///|")
    lines.append("/// The specialised butterflies of the mixed radix transform.")
    lines.append("///")
    lines.append("/// This file is generated by `tools/gen_kernels.py`, do not edit it")
    lines.append("/// by hand.")
    lines.append("")
    for r in RADICES:
        if r % 2 == 0 or args.style == "direct":
            lines.extend(emit_direct(r))
        else:
            lines.extend(emit_symmetric(r))
        lines.append("")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes("\n".join(lines).encode("utf-8"))


if __name__ == "__main__":
    main()
