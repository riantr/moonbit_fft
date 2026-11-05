#!/usr/bin/env python3
"""Proves that the machine checks of `tools/check_benchmark.py` can fail.

A check that has never been seen to fail is not known to check anything, so
every mutation below breaks one thing on purpose, runs the gate, and puts the
files back exactly as they were.  The files are handled as bytes: the working
copy of this repository uses the line endings of the platform, and a text mode
would rewrite them.

The mutations are:

1. the `Measured on` line of the document names another processor,
2. the fingerprint of `bench_machine.json` no longer matches its own fields,
3. `bench_machine.json` has no `cpu` field at all,
4. the measurement belongs to a machine that is not this one - self
   consistent, and the document agrees with it, so only the comparison with
   the running machine can catch it,
5. the same, with `MOONBIT_FFT_OTHER_MACHINE=1`, which has to let it pass.

Usage::

    python tools/negative_control_cpu.py
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import cpu_flags  # noqa: E402

DOC = ROOT / "BENCHMARK.md"
MACHINE = ROOT / "bench" / "bench_machine.json"
GATE = ROOT / "tools" / "check_benchmark.py"
ENV_ESCAPE = "MOONBIT_FFT_OTHER_MACHINE"


def gate(environment: dict[str, str] | None = None) -> int:
    """The exit code of the gate, with the escape hatch cleared unless asked."""
    env = dict(os.environ)
    env.pop(ENV_ESCAPE, None)
    if environment:
        env.update(environment)
    result = subprocess.run(
        [sys.executable, str(GATE)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
    )
    return result.returncode


def mutated(
    name: str,
    doc: bytes | None = None,
    machine: bytes | None = None,
    must_fail: bool = True,
    environment: dict[str, str] | None = None,
) -> bool:
    """Applies one mutation, runs the gate, and restores both files."""
    doc_before = DOC.read_bytes()
    machine_before = MACHINE.read_bytes()
    try:
        if doc is not None:
            DOC.write_bytes(doc)
        if machine is not None:
            MACHINE.write_bytes(machine)
        code = gate(environment)
        broke = code != 0
        ok = broke == must_fail
        print(
            "%s : %s (%s, exit %d)"
            % (
                "PASS" if ok else "FAIL",
                name,
                "the gate went red" if broke else "the gate stayed green",
                code,
            )
        )
        return ok
    finally:
        DOC.write_bytes(doc_before)
        MACHINE.write_bytes(machine_before)


def rewritten(change) -> bytes:
    """`bench_machine.json` with the given change applied and written back."""
    data = json.loads(MACHINE.read_text(encoding="utf-8"))
    change(data)
    return (json.dumps(data, indent=2, sort_keys=True) + "\n").encode("utf-8")


def measured_on(summary: str) -> bytes:
    """`BENCHMARK.md` with its `Measured on` line set to the given line."""
    text = DOC.read_bytes()
    start = text.index(b"Measured on: ")
    end = text.index(b"\r\n", start) if b"\r\n" in text[start:] else text.index(
        b"\n", start
    )
    return text[:start] + ("Measured on: " + summary).encode("utf-8") + text[end:]


def main() -> int:
    if not MACHINE.exists():
        print("%s does not exist" % MACHINE)
        return 1
    before = (DOC.read_bytes(), MACHINE.read_bytes())

    results = []

    # 1. The document names another processor.
    results.append(
        mutated(
            "the document names another processor",
            doc=DOC.read_bytes().replace(
                b"Measured on: 12th Gen", b"Measured on: 11th Gen", 1
            ),
        )
    )

    # 2. The fingerprint does not match the fields it summarises.
    results.append(
        mutated(
            "the fingerprint disagrees with its own fields",
            machine=rewritten(
                lambda data: data["cpu"].__setitem__("fingerprint", "0" * 16)
            ),
        )
    )

    # 3. The measurement carries no machine at all.
    results.append(
        mutated(
            "the measurement has no cpu field",
            machine=rewritten(lambda data: data.pop("cpu", None)),
        )
    )

    # 4. and 5. A self consistent measurement of another machine, with the
    # document agreeing with it: only the running machine can tell.
    other = {
        "name": "Some Other Processor",
        "identifier": "Fake Family 7 Model 1 Stepping 0, GenuineIntel",
        "machine": "AMD64",
        "system": "Windows",
        "logical_cores": 4,
        "isa": {"sse": True, "sse2": True, "avx": False, "avx2": False},
        "source": "written by tools/negative_control_cpu.py",
    }
    other["fingerprint"] = cpu_flags.fingerprint(other)
    other["suggested_cc_flags"] = cpu_flags.suggest(other)
    machine_of_other = rewritten(lambda data: data.__setitem__("cpu", other))
    doc_of_other = measured_on(cpu_flags.summary(other))

    results.append(
        mutated(
            "the measurement belongs to another machine",
            doc=doc_of_other,
            machine=machine_of_other,
        )
    )
    results.append(
        mutated(
            "the same, with the escape hatch set",
            doc=doc_of_other,
            machine=machine_of_other,
            must_fail=False,
            environment={ENV_ESCAPE: "1"},
        )
    )

    after = (DOC.read_bytes(), MACHINE.read_bytes())
    if after != before:
        print("FAIL : the control left the working tree changed")
        return 1
    caught = sum(1 for r in results if r)
    print("%d/%d mutations behaved as they should" % (caught, len(results)))
    return 0 if caught == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
