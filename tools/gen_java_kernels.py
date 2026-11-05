#!/usr/bin/env python3
"""Translates the butterflies of the Java original into MoonBit.

The kernel of the original, `edu.mines.jtk.dsp.Pfacc`, applies one small
transform per factor of the length.  The small transforms are the functions
`pfa2` ... `pfa16` of that class, and they are what this script translates.

Two things make the original fast, and the port has to have both of them.

* The small transform is a **hand written factorisation** of the discrete
  Fourier transform of the size `r`, not the direct evaluation of the sum.
  The factorisation of `pfa13` needs twelve products per pair of outputs,
  where the direct evaluation needs `r * r` of them, and it keeps only a
  handful of values alive at a time, where the direct evaluation keeps all of
  them.  The butterfly of the port that used the symmetry of the roots of
  unity kept about fifty values alive for the radix 13, which does not fit
  into the sixteen registers of the machine, so the compiler had to spill
  most of them.
* The constants of the small transform are **literals in the code**.  The
  original picks them with a branch on the twist of the stage, once per
  stage.  The port generates one kernel per twist, so that the constants are
  literals there as well and the compiler keeps them out of the registers
  altogether.

The twist of a stage is the exponent of the roots of unity of its small
transform.  The original uses `mu = r - kfac` for the forward transform, where
`kfac` is the inverse of the number of butterflies modulo `r`, and that is
the same twist as the one of the port, which uses the inverse convention of
the roots of unity.

The output of this script is a MoonBit file with one function per pair of a
radix and a twist.

Two styles are available:

``original``
    The factorisation of the original, translated line by line.  This is the
    kernel of the port.

``direct``
    The **direct evaluation** of the same small transform: every output is the
    sum of the `r` inputs times the `r` roots of unity.  It is the control of
    the measurement, and it is the way the port evaluated the small transform
    before the factorisation of the original was adopted.  The twist of the
    stage is the same in both styles, so the two kernels compute exactly the
    same transform.

Usage::

    python tools/gen_java_kernels.py --out moonbit_fft/kernels.mbt
    python tools/gen_java_kernels.py --out build/kernels_direct.mbt --style direct
    python tools/gen_java_kernels.py --out build/kernels_java.mbt --java build/jtsrc/src/edu/mines/jtk/dsp/Pfacc.java
"""

from __future__ import annotations

import argparse
import math
import pathlib
import re
import struct
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

# The decompiled original.  It is produced by `tools/decompile.py` out of the
# bytecode of the jar of the original, see the header of that script.
DEFAULT_JAVA = ROOT / "build" / "jtsrc" / "src" / "edu" / "mines" / "jtk" / "dsp" / "Pfacc.java"

# The radices of the valid lengths and the twists that they need.  The twists
# are the ones that the valid lengths of the original produce, see
# `tools/verify_goodthomas.py`.
TWISTS: dict[int, list[int]] = {
    2: [1],
    3: [1, 2],
    4: [1, 3],
    5: [1, 2, 3, 4],
    7: [1, 2, 3, 4, 5, 6],
    8: [1, 3, 5, 7],
    9: [1, 2, 4, 5, 7, 8],
    11: list(range(1, 11)),
    13: list(range(1, 13)),
    16: [1, 3, 5, 7, 9, 11, 13, 15],
}


class JavaFunction:
    """One of the small transforms of the original."""

    def __init__(self, r: int, text: str) -> None:
        self.r = r
        self.text = text
        self.prologue = ""
        self.body = ""

    def split(self) -> None:
        """Splits the function into its constants and its loop."""
        loop = self.text.index("for (int i = 0; i < m; ++i) {")
        self.prologue = self.text[:loop]
        self.body = self.text[loop:]


def find_function(text: str, r: int) -> JavaFunction:
    """The function of the radix `r` of the original."""
    match = re.search(r"private static void pfa%d\(float\[\] z," % r, text)
    if match is None:
        raise ValueError("the original has no kernel of the radix %d" % r)
    start = match.start()
    # The body of the function ends at its closing brace, which is found by
    # matching the braces: the next function of the class is not a boundary,
    # because the class holds other functions in between.
    opening = text.index("{", match.end())
    depth = 0
    closing = opening
    for index in range(opening, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                closing = index
                break
    body = text[start : closing + 1]
    function = JavaFunction(r, body)
    function.split()
    return function


def as_float32(text: str) -> float:
    """The value of a single precision literal of the original.

    The constants of the original are single precision.  The port keeps them
    as they are, in double precision, so that the only difference to the
    original is the arithmetic and not the constants.
    """
    return struct.unpack("f", struct.pack("f", float(text.rstrip("f"))))[0]


def evaluate(expression: str, values: dict[str, float]) -> float:
    """The value of an expression of the constants of the original.

    The original computes its constants in single precision, so every step
    is rounded to single precision as well.
    """
    expression = expression.strip()
    match = re.fullmatch(r"([\w.]+)\s*([-+*/])\s*([\w.]+)", expression)
    if match is None:
        return as_float32(expression)
    left = values[match.group(1)] if match.group(1) in values else as_float32(match.group(1))
    right = values[match.group(3)] if match.group(3) in values else as_float32(match.group(3))
    operator = match.group(2)
    if operator == "*":
        result = left * right
    elif operator == "+":
        result = left + right
    elif operator == "-":
        result = left - right
    else:
        result = left / right
    return struct.unpack("f", struct.pack("f", result))[0]


def constants_of(prologue: str, mu: int) -> dict[str, float]:
    """The constants of the small transform for the twist `mu`.

    The original picks its constants with a chain of branches on the twist,
    and sometimes with a conditional expression.  Both forms are read here.
    Some of the constants are derived from the others, `c5 = c1 * c4`, and
    those are evaluated in single precision, like the original does.
    """
    values: dict[str, float] = {}
    # The conditional expression form: `c1 = mu == 1 ? 0.5f : -0.5f;`.
    for match in re.finditer(
        r"(\w+)\s*=\s*mu\s*==\s*(\d+)\s*\?\s*([-\d.eE]+f?)\s*:\s*([-\d.eE]+f?)\s*;",
        prologue,
    ):
        name = match.group(1)
        if int(match.group(2)) == mu:
            values[name] = as_float32(match.group(3))
        else:
            values.setdefault(name, as_float32(match.group(4)))
    # The branch form: `if (mu == 3) { c1 = ...; } else if ... else { ... }`.
    branches = re.findall(r"(?:if|else if)\s*\(mu\s*==\s*(\d+)\)\s*\{(.*?)\}", prologue, re.S)
    chosen: str | None = None
    fallback: str | None = None
    for condition, block in branches:
        if int(condition) == mu:
            chosen = block
            break
        fallback = block
    if chosen is None:
        # The last branch of the chain is the `else` one, which the regular
        # expression above does not catch.
        else_blocks = re.findall(r"else\s*\{(.*?)\}", prologue, re.S)
        if else_blocks:
            fallback = else_blocks[-1]
        chosen = fallback or ""
    for match in re.finditer(r"(\w+)\s*=\s*([^;]+);", chosen):
        # The conditional expression form is read above.
        if "?" in match.group(2):
            continue
        values[match.group(1)] = evaluate(match.group(2), values)
    # The constants that are derived from the others are declared outside of
    # the branches, and they are declared in the order of their dependency.
    for match in re.finditer(r"float (\w+)\s*=\s*([^;]+);", prologue):
        if "?" in match.group(2):
            continue
        values[match.group(1)] = evaluate(match.group(2), values)
    return values


def number(text: str) -> str:
    """The MoonBit form of a Java number literal."""
    if text.endswith("f"):
        text = text[:-1]
    return text


def round_body(body: str) -> str:
    """The body of the round of a small transform.

    The rotation of the positions at the end of the round is removed: the
    port visits the same positions with its own update.
    """
    body = re.sub(r"\n\s*int jt = j\d+ \+ 2;.*?j0 = jt;", "", body, flags=re.S)
    opening = body.index("for (int i = 0; i < m; ++i) {")
    opening = body.index("{", opening)
    depth = 0
    closing = opening
    for index in range(opening, len(body)):
        if body[index] == "{":
            depth += 1
        elif body[index] == "}":
            depth -= 1
            if depth == 0:
                closing = index
                break
    return body[opening + 1 : closing]


def branch_constants(prologue: str) -> list[str]:
    """The names of the constants that the branches of the original assign."""
    names: list[str] = []
    blocks = re.findall(r"(?:if|else if)\s*\(mu\s*==\s*(\d+)\)\s*\{(.*?)\}", prologue, re.S)
    blocks = [block for _, block in blocks]
    blocks += re.findall(r"else\s*\{(.*?)\}", prologue, re.S)
    for block in blocks:
        for match in re.finditer(r"(\w+)\s*=\s*[^;]+;", block):
            name = match.group(1)
            if name not in names:
                names.append(name)
    for match in re.finditer(r"(\w+)\s*=\s*mu\s*==\s*\d+\s*\?", prologue):
        name = match.group(1)
        if name not in names:
            names.append(name)
    return names


def derived_constants(prologue: str) -> list[tuple[str, str]]:
    """The constants that the original derives from the other ones.

    They are declared outside of the branches, `c5 = c1 * c4`, and they are
    declared in the order of their dependency.
    """
    out: list[tuple[str, str]] = []
    for match in re.finditer(r"float (\w+)\s*=\s*([^;]+);", prologue):
        # The conditional expression is a constant of its own, the branches
        # assign it.
        if "?" in match.group(2):
            continue
        out.append((match.group(1), match.group(2)))
    return out


def solved_constants(r: int, mu: int, function: JavaFunction) -> dict[str, float]:
    """The constants of a small transform, in double precision.

    The constants of the original are single precision, because the original
    evaluates its transforms in single precision.  The port accumulates in
    double precision, so the constants are solved from the structure of the
    original and the transform it has to reproduce, see
    `tools/solve_constants.py`.
    """
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    import solve_constants as solver

    body = round_body(function.body)
    statements = solver.parse_statements(body)
    names = sorted(branch_constants(function.prologue), key=lambda x: (len(x), x))
    # The constants that the original derives from the other ones.
    derived = {
        name: solver.Parser(expression).expression()
        for name, expression in derived_constants(function.prologue)
    }
    values, residual = solver.solve(statements, r, mu, names, derived)
    if residual > 1.0e-12:
        raise ValueError(
            "the structure of the radix %d with the twist %d does not reproduce "
            "the transform, the residual is %.3e" % (r, mu, residual)
        )
    constants = dict(zip(names, values))
    # The derived constants are computed from the solved ones, in double
    # precision.
    for name, expression in derived.items():
        constants[name] = solver.evaluate(expression, constants, {}, [], derived)
    return constants


def translate_body(body: str, r: int) -> list[str]:
    """Translates the loop of a small transform into MoonBit.

    The array of the original holds the real and the imaginary parts
    interleaved, the port holds them in two arrays, so `z[j3]` becomes
    `re[p3]` and `z[j3 + 1]` becomes `im[p3]`.
    """
    out: list[str] = []
    inner = round_body(body)
    for line in inner.splitlines():
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        if line.startswith("int "):
            continue
        # The declaration of a value.
        match = re.match(r"float (\w+) = (.*);$", line)
        if match:
            out.append(
                "    let %s = %s" % (match.group(1), translate_expression(match.group(2), r))
            )
            continue
        # An assignment to the array.
        match = re.match(r"z\[(j\d+)(\s*\+\s*1)?\] = (.*);$", line)
        if match:
            slot = match.group(1)
            array = "im" if match.group(2) else "re"
            out.append(
                "    %s[p%s] = %s"
                % (array, slot[1:], translate_expression(match.group(3), r))
            )
            continue
        raise ValueError("the line %r is not understood" % line)
    return out


def translate_expression(text: str, r: int) -> str:
    """Translates an expression of the original into MoonBit."""
    text = re.sub(r"z\[(j\d+)(\s*\+\s*1)?\]", lambda m: (
        ("im[p%s]" % m.group(1)[1:]) if m.group(2) else ("re[p%s]" % m.group(1)[1:])
    ), text)
    # The literals of the original are single precision, the port accumulates
    # in double precision.
    text = re.sub(r"([-\d.]+)f\b", r"\1", text)
    return text


def emit_kernel(r: int, mu: int, function: JavaFunction) -> list[str]:
    """Emits the MoonBit function of one radix and one twist."""
    constants = solved_constants(r, mu, function)
    out: list[str] = []
    out.append("///|")
    out.append(f"/// The butterfly of the radix {r} stage of the prime factor")
    out.append(f"/// transform, for the twist {mu}.")
    out.append("///")
    out.append(f"/// This is the small transform of the original, `Pfacc.pfa{r}`,")
    out.append(f"/// with the twist {mu}.  Its constants are solved in double")
    out.append("/// precision, see `tools/solve_constants.py`.")
    out.append("///|")
    out.append(f"fn stage_r{r}_mu{mu}(")
    out.append("  m : Int32,")
    out.append("  kfac : Int32,")
    out.append("  re : Array[Double],")
    out.append("  im : Array[Double],")
    out.append(") -> Unit {")
    out.append(f"  let mr = m * {r}")
    out.append("  let delta = 1 - m * kfac")
    out.append("  let mut limit = m * kfac")
    for t in range(r):
        out.append(f"  let mut p{t} = m * (({t} * kfac) % {r})")
    for name in sorted(constants, key=lambda x: (len(x), x)):
        out.append(f"  let {name} = {constants[name]!r}")
    out.append("  let mut i = 0")
    out.append("  while i < m {")
    for line in translate_body(function.body, r):
        out.append(line)
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


def emit_direct_kernel(r: int, mu: int) -> list[str]:
    """Emits the direct evaluation of the small transform of a stage.

    The small transform of the stage is

        y[t] = sum over s of v[s] * exp(2 pi i mu t s / r)

    where `mu` is the twist of the stage.  The port evaluates it in real
    arithmetic, so that every product of two complex numbers costs four real
    multiplications.  The output `y[0]` needs none of them, because the roots
    of the order zero are one, and the input `v[0]` needs none either, because
    it is multiplied by one.

    This is the control of the measurement of the factorisation of the
    original: it computes exactly the same transform as the kernel of the
    original, with the same twist, but it does not use its factorisation.
    """
    out: list[str] = []
    out.append("///|")
    out.append(f"/// The direct evaluation of the butterfly of the radix {r} stage")
    out.append(f"/// of the prime factor transform, for the twist {mu}.")
    out.append("///")
    out.append("/// This is the control of the measurement: it computes the same")
    out.append("/// small transform as `Pfacc.pfa%d` does, with the same twist, but" % r)
    out.append("/// without its factorisation.")
    out.append("///|")
    out.append(f"fn stage_r{r}_mu{mu}(")
    out.append("  m : Int32,")
    out.append("  kfac : Int32,")
    out.append("  re : Array[Double],")
    out.append("  im : Array[Double],")
    out.append(") -> Unit {")
    out.append(f"  let mr = m * {r}")
    out.append("  let delta = 1 - m * kfac")
    out.append("  let mut limit = m * kfac")
    for t in range(r):
        out.append(f"  let mut p{t} = m * (({t} * kfac) % {r})")
    # The roots of unity of the twist.  The ones of the order zero are one, so
    # they are not constants at all.
    for q in range(1, r):
        for s in range(1, r):
            angle = 2.0 * math.pi * mu * q * s / r
            out.append(f"  let c{q}_{s} = {math.cos(angle)!r}")
            out.append(f"  let s{q}_{s} = {math.sin(angle)!r}")
    out.append("  let mut i = 0")
    out.append("  while i < m {")
    for t in range(r):
        out.append(f"    let v{t}r = re[p{t}]")
        out.append(f"    let v{t}i = im[p{t}]")
    for q in range(r):
        if q == 0:
            # The roots of the order zero are one, so the sum is a plain sum.
            out.append("    let y0r = " + " + ".join(f"v{s}r" for s in range(r)))
            out.append("    let y0i = " + " + ".join(f"v{s}i" for s in range(r)))
            continue
        terms_re = ["v0r"]
        terms_im = ["v0i"]
        for s in range(1, r):
            terms_re.append(f"c{q}_{s} * v{s}r - s{q}_{s} * v{s}i")
            terms_im.append(f"s{q}_{s} * v{s}r + c{q}_{s} * v{s}i")
        out.append(f"    let y{q}r = " + " + ".join(terms_re))
        out.append(f"    let y{q}i = " + " + ".join(terms_im))
    for q in range(r):
        out.append(f"    re[p{q}] = y{q}r")
        out.append(f"    im[p{q}] = y{q}i")
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


def emit_dispatch() -> list[str]:
    """Emits the function that calls the butterfly of a radix and a twist.

    The twist of a stage is the exponent of the roots of unity of its small
    transform.  The original uses `r - kfac` for the forward transform, where
    `kfac` is the inverse of the number of butterflies modulo `r`, and that
    is the twist of the port as well: the roots of the port are the roots of
    the original, in the order in which the original uses them.
    """
    out: list[str] = []
    out.append("///|")
    out.append("/// Calls the butterfly of a radix and a twist.")
    out.append("///")
    out.append("/// The twist of the stage is the exponent of the roots of unity")
    out.append("/// of its small transform.")
    out.append("///|")
    out.append("fn stage_dispatch(")
    out.append("  r : Int32,")
    out.append("  mu : Int32,")
    out.append("  m : Int32,")
    out.append("  kfac : Int32,")
    out.append("  re : Array[Double],")
    out.append("  im : Array[Double],")
    out.append(") -> Unit {")
    radices = sorted(TWISTS)
    for index, r in enumerate(radices):
        keyword = "if" if index == 0 else "} else if"
        out.append(f"  {keyword} r == {r} {{")
        twists = TWISTS[r]
        for position, mu in enumerate(twists):
            condition = "if" if position == 0 else "} else if"
            out.append(f"    {condition} mu == {mu} {{")
            out.append(f"      stage_r{r}_mu{mu}(m, kfac, re, im)")
        out.append("    }")
    out.append("  } else {")
    out.append('    abort("the transform length has a factor without a butterfly")')
    out.append("  }")
    out.append("}")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=pathlib.Path, required=True)
    parser.add_argument(
        "--java",
        type=pathlib.Path,
        default=DEFAULT_JAVA,
        help="the decompiled original to translate",
    )
    parser.add_argument(
        "--style",
        choices=["original", "direct"],
        default="original",
        help="the factorisation of the original, or the direct evaluation of the "
        "same small transform, which is the control of the measurement",
    )
    args = parser.parse_args()

    if args.style == "direct":
        text = ""
    else:
        if not args.java.exists():
            print(
                "%s does not exist, the decompiled original is needed to "
                "translate its butterflies.  Create it with "
                "`python tools/decompile.py`." % args.java
            )
            return 1
        text = args.java.read_text(encoding="utf-8")
    lines: list[str] = []
    lines.append("///|")
    lines.append("/// The specialised butterflies of the prime factor transform.")
    lines.append("///")
    lines.append("/// This file is generated by `tools/gen_java_kernels.py`, do not edit")
    lines.append("/// it by hand.")
    lines.append("")
    for r in sorted(TWISTS):
        function = find_function(text, r) if args.style == "original" else None
        for mu in TWISTS[r]:
            if args.style == "direct":
                lines.extend(emit_direct_kernel(r, mu))
            else:
                lines.extend(emit_kernel(r, mu, function))
            lines.append("")
    lines.extend(emit_dispatch())
    lines.append("")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes("\n".join(lines).encode("utf-8"))
    print(f"{len(lines)} lines written to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
