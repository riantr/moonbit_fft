#!/usr/bin/env python3
"""Generate the specialised butterflies of the Good-Thomas transform.

The transform of `moonbit_fft2/mixed_radix.mbt` is the prime factor algorithm
of the Java original: the length is split into pairwise coprime factors and
every factor selects a small kernel.  Because the factors are coprime, the
stages need no twiddle factor at all, which is where most of the work of the
transform is saved.

The structure of one stage is this.  The stage has the radix `r`, the length is
`n`, and `m = n / r` is the number of butterflies of the stage.  The value
`kfac` is the inverse of `m` modulo `r`.  The butterfly of the round `i` takes
its `r` values from the positions

    p[t] = i + m * ((t - i) * kfac mod r)      for t = 0 .. r - 1

applies a discrete Fourier transform of the size `r` to them and writes the
result back to the same positions.  The roots of unity of that small transform
are raised to the power `kfac`, which is the twist of the original.  The twist
is in the roots of unity and not in the indices, so the small transform needs
no permutation at all.

The constants of the small transform therefore depend on the length of the
transform and are read from the plan of the stage.  They are loaded into
locals before the rounds, so that the inner loop reads them from the
registers.

Two styles are available:

``symmetric``
    The small transform uses the symmetry of the roots of unity.  For an odd
    radix `r` the inputs are paired, `A_s = x_s + x_{r-s}` and `B_s = x_s -
    x_{r-s}`, and the output `p` becomes

        X[p] = x_0 + sum over s of (A_s * cos(2 pi kfac s p / r)
                                    - i * B_s * sin(2 pi kfac s p / r))

    while `X[r-p]` uses the same two sums with the opposite sign of the sine.
    The prime factor algorithm of the Java original uses the same idea.

``direct``
    The small transform is evaluated the obvious way, every output is the sum
    of the `r` inputs times the `r` roots of unity.  That costs `4 * (r - 1) *
    (r - 1)` real multiplications and as many additions.

Usage::

    python tools/gen_kernels.py --out moonbit_fft2/kernels.mbt
    python tools/gen_kernels.py --out moonbit_fft2/kernels.mbt --style direct
"""

from __future__ import annotations

import argparse
import pathlib

# The radices the valid transform lengths are built from.  They are the prime
# powers of the primes 2, 3, 5, 7, 11 and 13 that the valid lengths of the
# original use.
RADICES = [2, 3, 4, 5, 7, 8, 9, 11, 13, 16]


def pairs_of(r: int) -> tuple[bool, int, int]:
    """The shape of the small transform of one radix.

    It returns whether the radix is even, the middle of the radix, and the
    last index of the pairs.  For an odd radix the pairs run from one to
    `(r - 1) / 2`, for an even radix they run from one to `r / 2 - 1`, because
    the input `r / 2` is paired with itself.
    """
    if r % 2 == 0:
        return True, r // 2, r // 2 - 1
    return False, (r - 1) // 2, (r - 1) // 2


class Coefficient:
    """The coefficient of one term of the small transform.

    The value is `cos(2 pi kfac * v / r)` or `sin(2 pi kfac * v / r)`, where
    `v` is the product of the two indices of the term.  The value is read from
    the plan of the stage, unless it does not depend on `kfac` at all.
    """

    def __init__(self, r: int, v: int, sine: bool) -> None:
        self.r = r
        self.v = v
        self.sine = sine
        self.local = ""
        self.sign = 1
        self.literal: str | None = None

    def resolve(self) -> None:
        """Finds out whether the value is a literal or a local of the plan."""
        r = self.r
        v = self.v
        if v == 0:
            self.literal = "0.0" if self.sine else "1.0"
            return
        if r % 2 == 0 and v == r // 2:
            # cos(pi * kfac) is minus one and sin(pi * kfac) is zero, because
            # kfac is odd for an even radix.
            self.literal = "0.0" if self.sine else "-1.0"
            return
        w = v if v <= r // 2 else r - v
        # The cosine of the root v and the cosine of the root r - v are the
        # same, only the sine changes its sign.
        self.sign = -1 if (self.sine and v > r // 2) else 1
        if r % 4 == 0 and w == r // 4 and not self.sine:
            # cos(pi * kfac / 2) is zero, because kfac is odd.
            self.literal = "0.0"
            return
        self.local = ("s" if self.sine else "c") + str(w)

    def action(self) -> tuple[str, str]:
        """How the term is added: an addition, a subtraction or a product."""
        if self.literal is not None:
            if self.literal == "0.0":
                return ("skip", "")
            if self.literal == "1.0":
                return ("add", "")
            return ("sub", "")
        if self.sign < 0:
            return ("submul", self.local)
        return ("mul", self.local)


def emit_term(
    out: list[str],
    indent: str,
    acc_re: str,
    acc_im: str,
    re_name: str,
    im_name: str,
    coefficient: Coefficient,
) -> None:
    """Emits one term of the small transform."""
    kind, text = coefficient.action()
    if kind == "skip":
        return
    if kind == "add":
        out.append(f"{indent}{acc_re} = {acc_re} + {re_name}")
        out.append(f"{indent}{acc_im} = {acc_im} + {im_name}")
        return
    if kind == "sub":
        out.append(f"{indent}{acc_re} = {acc_re} - {re_name}")
        out.append(f"{indent}{acc_im} = {acc_im} - {im_name}")
        return
    if kind == "submul":
        out.append(f"{indent}{acc_re} = {acc_re} - {re_name} * {text}")
        out.append(f"{indent}{acc_im} = {acc_im} - {im_name} * {text}")
        return
    out.append(f"{indent}{acc_re} = {acc_re} + {re_name} * {text}")
    out.append(f"{indent}{acc_im} = {acc_im} + {im_name} * {text}")


def emit_term_imag(
    out: list[str],
    indent: str,
    acc_re: str,
    acc_im: str,
    re_name: str,
    im_name: str,
    coefficient: Coefficient,
) -> None:
    """Emits one term of the small transform, where the sine multiplies the
    imaginary part of the input and changes the sign of the real part."""
    kind, text = coefficient.action()
    if kind == "skip":
        return
    if kind == "add":
        out.append(f"{indent}{acc_re} = {acc_re} + {im_name}")
        out.append(f"{indent}{acc_im} = {acc_im} - {re_name}")
        return
    if kind == "sub":
        out.append(f"{indent}{acc_re} = {acc_re} - {im_name}")
        out.append(f"{indent}{acc_im} = {acc_im} + {re_name}")
        return
    if kind == "submul":
        out.append(f"{indent}{acc_re} = {acc_re} - {im_name} * {text}")
        out.append(f"{indent}{acc_im} = {acc_im} + {re_name} * {text}")
        return
    out.append(f"{indent}{acc_re} = {acc_re} + {im_name} * {text}")
    out.append(f"{indent}{acc_im} = {acc_im} - {re_name} * {text}")


def collect_locals(r: int, style: str) -> list[str]:
    """The roots of unity that the butterfly of one radix needs."""
    even, half, last = pairs_of(r)
    names: set[str] = set()
    if style == "direct":
        for t in range(r):
            for s in range(r):
                v = (s * t) % r
                for sine in (False, True):
                    coefficient = Coefficient(r, v, sine)
                    coefficient.resolve()
                    if coefficient.local:
                        names.add(coefficient.local)
        return sorted(names)
    for p in range(1, last + 1):
        for s in range(1, last + 1):
            v = (s * p) % r
            for sine in (False, True):
                coefficient = Coefficient(r, v, sine)
                coefficient.resolve()
                if coefficient.local:
                    names.add(coefficient.local)
    return sorted(names)


def emit_header(out: list[str], r: int, style: str) -> None:
    """Emits the documentation and the signature of one butterfly."""
    out.append("///|")
    out.append(
        f"/// The butterfly of the radix {r} stage of the Good-Thomas transform."
    )
    out.append("///")
    out.append("/// The values of the butterfly are read from `re` and `im`, the")
    out.append("/// roots of unity of the stage from `consts`, and the result is")
    out.append("/// written back to `re` and `im`.")
    out.append("///")
    out.append("/// The constants of the stage start at `off` in `consts`: the")
    out.append(f"/// cosines of the {r // 2 + 1} roots come first, then the sines.")
    # The radix two needs no root of unity at all, the parameters are then
    # unused and the compiler would warn about them.
    used = "" if collect_locals(r, style) else "_"
    out.append(f"fn stage_r{r}(")
    out.append("  m : Int32,")
    out.append("  kfac : Int32,")
    out.append(f"  {used}consts : Array[Double],")
    out.append(f"  {used}off : Int32,")
    out.append("  re : Array[Double],")
    out.append("  im : Array[Double],")
    out.append(") -> Unit {")
    out.append(f"  let mr = m * {r}")
    out.append("  let delta = 1 - m * kfac")
    out.append("  let mut limit = m * kfac")
    for t in range(r):
        out.append(f"  let mut p{t} = m * (({t} * kfac) % {r})")


def emit_constants(out: list[str], r: int, names: list[str]) -> None:
    """Emits the loads of the roots of unity into locals.

    The constants of the stage are the cosines of the roots first, then the
    sines, so the sine of the root `w` sits at `r / 2 + 1 + w` in the stage.
    """
    half = r // 2 + 1
    for name in names:
        kind = name[0]
        index = int(name[1:])
        offset = 0 if kind == "c" else half
        out.append(f"  let {name} = consts[off + {offset + index}]")


def emit_symmetric_body(out: list[str], r: int) -> None:
    """Emits the small transform of one butterfly."""
    even, half, last = pairs_of(r)
    # The terms of the small transform, and whether they use the sums and the
    # differences of the pairs at all.  The radix four is an example: all of
    # its cosines are zero, because the twist is odd.
    actions = []
    cosine_used = False
    sine_used = False
    for p in range(1, last + 1):
        for s in range(1, last + 1):
            v = (s * p) % r
            cosine = Coefficient(r, v, False)
            sine = Coefficient(r, v, True)
            cosine.resolve()
            sine.resolve()
            actions.append((p, s, cosine, sine))
            if cosine.action()[0] != "skip":
                cosine_used = True
            if sine.action()[0] != "skip":
                sine_used = True
    # The pairs of the inputs.
    for s in range(1, last + 1):
        other = r - s
        if cosine_used:
            out.append(f"    let a{s}_re = v{s}_re + v{other}_re")
            out.append(f"    let a{s}_im = v{s}_im + v{other}_im")
        if sine_used:
            out.append(f"    let b{s}_re = v{s}_re - v{other}_re")
            out.append(f"    let b{s}_im = v{s}_im - v{other}_im")
    # The output zero is the sum of all the inputs.
    if even:
        out.append("    let mut out0_re = 0.0")
        out.append("    let mut out0_im = 0.0")
        for s in range(r):
            out.append(f"    out0_re = out0_re + v{s}_re")
            out.append(f"    out0_im = out0_im + v{s}_im")
    else:
        out.append("    let mut out0_re = v0_re")
        out.append("    let mut out0_im = v0_im")
        for s in range(1, last + 1):
            out.append(f"    out0_re = out0_re + a{s}_re")
            out.append(f"    out0_im = out0_im + a{s}_im")
    # The middle output of an even radix is the sum of the even inputs minus
    # the sum of the odd ones.
    if even:
        out.append(f"    let mut out{half}_re = 0.0")
        out.append(f"    let mut out{half}_im = 0.0")
        for s in range(r):
            sign = " + " if s % 2 == 0 else " - "
            out.append(f"    out{half}_re = out{half}_re{sign}v{s}_re")
            out.append(f"    out{half}_im = out{half}_im{sign}v{s}_im")
    # The outputs one to half, and their partners.
    for p in range(1, last + 1):
        other = r - p
        out.append(f"    let mut out{p}_re = 0.0")
        out.append(f"    let mut out{p}_im = 0.0")
        out.append(f"    let mut out{other}_re = 0.0")
        out.append(f"    let mut out{other}_im = 0.0")
        if cosine_used:
            out.append(f"    let mut c{p}_re = 0.0")
            out.append(f"    let mut c{p}_im = 0.0")
            out.append(f"    c{p}_re = v0_re")
            out.append(f"    c{p}_im = v0_im")
        else:
            out.append(f"    let c{p}_re = v0_re")
            out.append(f"    let c{p}_im = v0_im")
        if sine_used:
            out.append(f"    let mut d{p}_re = 0.0")
            out.append(f"    let mut d{p}_im = 0.0")
        else:
            out.append(f"    let d{p}_re = 0.0")
            out.append(f"    let d{p}_im = 0.0")
        for s in range(1, last + 1):
            v = (s * p) % r
            cosine = Coefficient(r, v, False)
            sine = Coefficient(r, v, True)
            cosine.resolve()
            sine.resolve()
            emit_term(
                out, "    ", f"c{p}_re", f"c{p}_im", f"a{s}_re", f"a{s}_im", cosine
            )
            emit_term(
                out, "    ", f"d{p}_re", f"d{p}_im", f"b{s}_re", f"b{s}_im", sine
            )
        if even:
            # The middle input of an even radix contributes the same value to
            # the output p and to the output r - p.
            sign = " + " if p % 2 == 0 else " - "
            out.append(f"    out{p}_re = c{p}_re + d{p}_im{sign}v{half}_re")
            out.append(f"    out{p}_im = c{p}_im - d{p}_re{sign}v{half}_im")
            out.append(f"    out{other}_re = c{p}_re - d{p}_im{sign}v{half}_re")
            out.append(f"    out{other}_im = c{p}_im + d{p}_re{sign}v{half}_im")
        else:
            out.append(f"    out{p}_re = c{p}_re + d{p}_im")
            out.append(f"    out{p}_im = c{p}_im - d{p}_re")
            out.append(f"    out{other}_re = c{p}_re - d{p}_im")
            out.append(f"    out{other}_im = c{p}_im + d{p}_re")


def emit_round(out: list[str], r: int) -> None:
    """Emits the round of the butterfly: the gather, the transform, the write."""
    for t in range(r):
        out.append(f"    let v{t}_re = re[p{t}]")
        out.append(f"    let v{t}_im = im[p{t}]")
    emit_symmetric_body(out, r)
    for t in range(r):
        out.append(f"    re[p{t}] = out{t}_re")
        out.append(f"    im[p{t}] = out{t}_im")


def emit_direct_body(out: list[str], r: int) -> None:
    """Emits the small transform of one butterfly, in its direct form."""
    for t in range(r):
        out.append(f"    let mut out{t}_re = 0.0")
        out.append(f"    let mut out{t}_im = 0.0")
        for s in range(r):
            v = (s * t) % r
            cosine = Coefficient(r, v, False)
            sine = Coefficient(r, v, True)
            cosine.resolve()
            sine.resolve()
            emit_term(
                out, "    ", f"out{t}_re", f"out{t}_im", f"v{s}_re", f"v{s}_im", cosine
            )
            emit_term_imag(
                out, "    ", f"out{t}_re", f"out{t}_im", f"v{s}_re", f"v{s}_im", sine
            )


def emit_kernel(r: int, style: str) -> list[str]:
    """Emits one butterfly."""
    out: list[str] = []
    emit_header(out, r, style)
    emit_constants(out, r, collect_locals(r, style))
    out.append("  let mut i = 0")
    out.append("  while i < m {")
    for t in range(r):
        out.append(f"    let v{t}_re = re[p{t}]")
        out.append(f"    let v{t}_im = im[p{t}]")
    if style == "direct":
        emit_direct_body(out, r)
    else:
        emit_symmetric_body(out, r)
    for t in range(r):
        out.append(f"    re[p{t}] = out{t}_re")
        out.append(f"    im[p{t}] = out{t}_im")
    # The positions of the next round: every offset loses kfac and wraps
    # around.
    for t in range(r):
        out.append(f"    if p{t} < limit {{")
        out.append(f"      p{t} = p{t} + mr")
        out.append("    }")
        out.append(f"    p{t} = p{t} + delta")
    out.append("    limit = limit + 1")
    out.append("    i = i + 1")
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
        help="the style of the small transform",
    )
    args = parser.parse_args()

    lines: list[str] = []
    lines.append("///|")
    lines.append("/// The specialised butterflies of the Good-Thomas transform.")
    lines.append("///")
    lines.append("/// This file is generated by `tools/gen_kernels.py`, do not edit it")
    lines.append("/// by hand.")
    lines.append("")
    for r in RADICES:
        lines.extend(emit_kernel(r, args.style))
        lines.append("")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes("\n".join(lines).encode("utf-8"))


if __name__ == "__main__":
    main()
