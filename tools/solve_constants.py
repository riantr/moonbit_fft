#!/usr/bin/env python3
"""Solves the constants of the small transforms of the Java original.

The small transforms of the original, `edu.mines.jtk.dsp.Pfacc`, are hand
written factorisations of the discrete Fourier transform.  Their constants
are **single precision**, because the original evaluates the whole transform
in single precision.

The port accumulates in double precision, so it cannot use the constants of
the original: a root of unity that is wrong in the seventh digit puts the
same error into every output of the stage, and the port would lose the
accuracy that its double precision accumulation buys.

The constants are therefore **solved** here, in double precision, from the
structure of the original.

The structure of a small transform is a **real linear** map of the input
onto the output: the real and the imaginary parts are mixed, so the map is a
matrix of `2r` rows over `2r` columns, and every constant is a factor of a
sum of the inputs.  So the map has the shape

    M(c) = M(0) + sum over k of c_k * D_k

where `M(0)` is the map with all the constants set to zero and `D_k` is the
map with the constant `k` set to one.  The wanted map is the discrete
Fourier transform of the size `r` with the twist `mu`, which is known in
double precision, so the constants are the solution of the linear system

    M(0) + sum over k of c_k * D_k = M_wanted

which is solved here in the least squares sense.  The residual of the
solution is reported, and it is the proof that the structure of the original
is the factorisation it claims to be.

Usage::

    python tools/solve_constants.py
"""

from __future__ import annotations

import argparse
import cmath
import math
import pathlib
import re
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent.parent

# The decompiled original.
DEFAULT_JAVA = ROOT / "build" / "jtsrc" / "src" / "edu" / "mines" / "jtk" / "dsp" / "Pfacc.java"

RADICES = [2, 3, 4, 5, 7, 8, 9, 11, 13, 16]

TOKEN = re.compile(
    r"\s*(z\[j\d+(\s*\+\s*1)?\]|[A-Za-z_]\w*|\d+\.?\d*[fFdD]?|\(|\)|\+|-|\*)"
)


class Parser:
    """A parser of the expressions of the original."""

    def __init__(self, text: str) -> None:
        self.tokens: list[str] = []
        position = 0
        while position < len(text):
            match = TOKEN.match(text, position)
            if match is None:
                break
            self.tokens.append(match.group(1))
            position = match.end()
        self.position = 0

    def peek(self) -> str | None:
        if self.position < len(self.tokens):
            return self.tokens[self.position]
        return None

    def take(self) -> str:
        token = self.tokens[self.position]
        self.position += 1
        return token

    def expression(self) -> tuple:
        """A sum of terms, with their signs."""
        terms: list[tuple[int, tuple]] = []
        sign = 1
        while True:
            token = self.peek()
            if token == "+":
                self.take()
                continue
            if token == "-":
                self.take()
                sign = -sign
                continue
            if token is None or token == ")":
                break
            terms.append((sign, self.term()))
            sign = 1
        return ("sum", terms)

    def term(self) -> tuple:
        """A product of factors."""
        factors = [self.factor()]
        while self.peek() == "*":
            self.take()
            factors.append(self.factor())
        return ("product", factors)

    def factor(self) -> tuple:
        """A number, a name, an element of the array or a parenthesised sum."""
        token = self.take()
        if token == "(":
            inner = self.expression()
            self.take()  # the closing parenthesis
            return inner
        if token.startswith("z["):
            imaginary = "+" in token
            slot = int(re.search(r"j(\d+)", token).group(1))
            return ("array", slot, imaginary)
        if re.fullmatch(r"\d+\.?\d*[fFdD]?", token):
            return ("number", float(token.rstrip("fFdD")))
        return ("name", token)


def parse_statements(body: str) -> list[tuple]:
    """The statements of the round of a small transform."""
    statements: list[tuple] = []
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        match = re.match(r"float (\w+) = (.*);$", line)
        if match:
            statements.append(("let", match.group(1), Parser(match.group(2)).expression()))
            continue
        match = re.match(r"z\[(j\d+)(\s*\+\s*1)?\] = (.*);$", line)
        if match:
            slot = int(match.group(1)[1:])
            imaginary = match.group(2) is not None
            statements.append(("set", slot, imaginary, Parser(match.group(3)).expression()))
            continue
        raise ValueError("the line %r is not understood" % line)
    return statements


def evaluate(
    expression: tuple,
    constants: dict[str, float],
    values: dict[str, float],
    z: list[float],
    derived: dict[str, tuple] | None = None,
) -> float:
    """The value of an expression."""
    kind = expression[0]
    if kind == "number":
        return expression[1]
    if kind == "name":
        name = expression[1]
        if name in constants:
            return constants[name]
        if name in values:
            return values[name]
        if derived is not None and name in derived:
            # A constant that the original derives from the other ones.
            value = evaluate(derived[name], constants, values, z, derived)
            values[name] = value
            return value
        raise KeyError(name)
    if kind == "array":
        _, slot, imaginary = expression
        return z[2 * slot + (1 if imaginary else 0)]
    if kind == "sum":
        total = 0.0
        for sign, term in expression[1]:
            total = total + sign * evaluate(term, constants, values, z, derived)
        return total
    if kind == "product":
        total = 1.0
        for factor in expression[1]:
            total = total * evaluate(factor, constants, values, z, derived)
        return total
    raise ValueError("the expression %r is not understood" % (expression,))


def map_of(
    statements: list[tuple],
    r: int,
    constants: dict[str, float],
    derived: dict[str, tuple] | None = None,
) -> np.ndarray:
    """The map of the small transform, for the given constants.

    The map is the real `2r` by `2r` matrix of the outputs over the inputs of
    one round, with the slots of the round as the indices.  The columns are
    the images of the unit vectors, so the map is evaluated once per column.
    """
    size = 2 * r
    out = np.zeros((size, size))
    for column in range(size):
        z = [0.0] * size
        z[column] = 1.0
        values: dict[str, float] = {}
        for statement in statements:
            if statement[0] == "let":
                values[statement[1]] = evaluate(
                    statement[2], constants, values, z, derived
                )
                continue
            _, slot, imaginary, expression = statement
            value = evaluate(expression, constants, values, z, derived)
            z[2 * slot + (1 if imaginary else 0)] = value
        out[:, column] = z
    return out


def wanted_map(r: int, mu: int) -> np.ndarray:
    """The discrete Fourier transform of the size `r` with the twist `mu`.

    The convention is the one of the original: the roots of unity are raised
    to the power `mu`, and the exponent is positive.  The map is the real
    representation of the complex one, in the order of the array of the
    original, which holds the real and the imaginary parts interleaved.
    """
    size = 2 * r
    out = np.zeros((size, size))
    for p in range(r):
        for s in range(r):
            root = cmath.exp(2j * math.pi * mu * p * s / r)
            out[2 * p, 2 * s] = root.real
            out[2 * p, 2 * s + 1] = -root.imag
            out[2 * p + 1, 2 * s] = root.imag
            out[2 * p + 1, 2 * s + 1] = root.real
    return out


def solve(
    statements: list[tuple],
    r: int,
    mu: int,
    names: list[str],
    derived: dict[str, tuple] | None = None,
) -> tuple[list[float], float]:
    """The constants of the small transform, in double precision.

    It returns the constants and the residual of the solution, which is the
    distance between the map of the structure and the wanted map.
    """
    zero = {name: 0.0 for name in names}
    base = map_of(statements, r, zero, derived)
    columns = []
    for name in names:
        constants = {other: 0.0 for other in names}
        constants[name] = 1.0
        columns.append((map_of(statements, r, constants, derived) - base).reshape(-1))
    target = (wanted_map(r, mu) - base).reshape(-1)
    if not names:
        residual = float(np.max(np.abs(target)))
        return [], residual
    matrix = np.array(columns).T
    solution, *_ = np.linalg.lstsq(matrix, target, rcond=None)
    constants = {name: float(value) for name, value in zip(names, solution)}
    residual_map = map_of(statements, r, constants, derived)
    residual = float(np.max(np.abs(residual_map - wanted_map(r, mu))))
    return [constants[name] for name in names], residual


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--java", type=pathlib.Path, default=DEFAULT_JAVA)
    args = parser.parse_args()
    if not args.java.exists():
        print(
            "%s does not exist, the decompiled original is needed to solve the "
            "constants of its butterflies.  Create it with "
            "`python tools/decompile.py`." % args.java
        )
        return 1
    text = args.java.read_text(encoding="utf-8")

    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    import gen_java_kernels as kernels

    failures = 0
    for r in RADICES:
        function = kernels.find_function(text, r)
        function.split()
        body = kernels.round_body(function.body)
        statements = parse_statements(body)
        names = sorted(kernels.branch_constants(function.prologue), key=lambda x: (len(x), x))
        # The constants that the original derives from the other ones, `c5 =
        # c1 * c4`, are not unknowns: they follow from the ones that are.
        derived = {
            name: Parser(expression).expression()
            for name, expression in kernels.derived_constants(function.prologue)
        }
        for mu in kernels.TWISTS[r]:
            values, residual = solve(statements, r, mu, names, derived)
            print(
                "radix %2d twist %2d: %s residual %.3e"
                % (r, mu, " ".join("%+.6f" % value for value in values), residual)
            )
            if residual > 1.0e-12:
                failures += 1
    if failures:
        print("%d failures" % failures)
        return 1
    print("every structure reproduces the transform of the original")
    return 0


if __name__ == "__main__":
    sys.exit(main())
