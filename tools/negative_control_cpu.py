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
4. a measurement of the directory has no `cpu` field at all,
5. a measurement of the directory names a second machine, self consistent and
   with the document untouched, so that only the agreement of the directory
   with `bench_machine.json` can catch it,
6. the directory belongs to a machine that is not this one - the document,
   the measurement of the machine and every other measurement name the same
   second machine, so nothing inside the directory disagrees and only the
   comparison with the running machine can catch it,
7. the same, with `MOONBIT_FFT_OTHER_MACHINE=1`, which has to let it pass.

A mutation that would not change its file is reported as a failure of its own:
a search that no longer matches must not look like a check that passed.

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
# The list of the measurements comes from the gate itself, so that a file that
# is added to the directory is covered here without being written down twice.
import check_benchmark  # noqa: E402

MEASUREMENTS = check_benchmark.MEASUREMENTS

DOC = ROOT / "BENCHMARK.md"
MACHINE = ROOT / "bench" / "bench_machine.json"
COPY = ROOT / "bench" / "bench_copy.json"
TARGET = ROOT / "bench" / "bench_target.json"
GATE = ROOT / "tools" / "check_benchmark.py"
ENV_ESCAPE = "MOONBIT_FFT_OTHER_MACHINE"

# The files a mutation may touch, and the files this control has to leave
# exactly as it found them.
WATCHED = (DOC,) + MEASUREMENTS


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
    files: dict[pathlib.Path, bytes],
    must_fail: bool = True,
    environment: dict[str, str] | None = None,
) -> bool:
    """Applies one mutation, runs the gate, and restores the files."""
    saved = {path: path.read_bytes() for path in files}
    idle = [path for path, content in files.items() if content == saved[path]]
    if idle:
        print(
            "FAIL : %s (the mutation does not change %s)"
            % (name, ", ".join(path.name for path in idle))
        )
        return False
    try:
        for path, content in files.items():
            path.write_bytes(content)
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
        for path, content in saved.items():
            path.write_bytes(content)


def rewritten(path: pathlib.Path, change) -> bytes:
    """The file with the given change applied, written back in the shape it has."""
    data = json.loads(path.read_text(encoding="utf-8"))
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


def machine(name: str, cores: int, isa: dict[str, bool]) -> dict:
    """An identity of a machine that is not this one, consistent with itself."""
    identity = {
        "name": name,
        "identifier": "Fake Family 6 Model 1 Stepping 0, GenuineIntel",
        "machine": "AMD64",
        "system": "Windows",
        "logical_cores": cores,
        "isa": isa,
        "source": "written by tools/negative_control_cpu.py",
    }
    identity["fingerprint"] = cpu_flags.fingerprint(identity)
    identity["suggested_cc_flags"] = cpu_flags.suggest(identity)
    return identity


def main() -> int:
    for path in MEASUREMENTS:
        if not path.exists():
            print("%s does not exist" % path)
            return 1
    before = {path: path.read_bytes() for path in WATCHED}

    results = []

    # 1. The document names another processor.
    results.append(
        mutated(
            "the document names another processor",
            {
                DOC: DOC.read_bytes().replace(
                    b"Measured on: 12th Gen", b"Measured on: 11th Gen", 1
                )
            },
        )
    )

    # 2. The fingerprint does not match the fields it summarises.
    results.append(
        mutated(
            "the fingerprint disagrees with its own fields",
            {
                MACHINE: rewritten(
                    MACHINE,
                    lambda data: data["cpu"].__setitem__("fingerprint", "0" * 16),
                )
            },
        )
    )

    # 3. The measurement of the machine carries no machine at all.
    results.append(
        mutated(
            "the measurement of the machine has no cpu field",
            {MACHINE: rewritten(MACHINE, lambda data: data.pop("cpu", None))},
        )
    )

    # 4. A measurement of the directory carries none either, while its numbers
    #    still read back: only the field is missing.
    results.append(
        mutated(
            "a measurement of the directory has no cpu field",
            {COPY: rewritten(COPY, lambda data: data.pop("cpu", None))},
        )
    )

    # 5. A measurement names a second machine, consistent with itself, and the
    #    document is untouched: the directory disagrees with the measurement of
    #    the machine, which is the only thing that can catch this.
    second = machine(
        "A Second Processor", 8, {"sse": True, "sse2": True, "avx": True, "avx2": False}
    )
    results.append(
        mutated(
            "a measurement belongs to a second machine",
            {TARGET: rewritten(TARGET, lambda data: data.__setitem__("cpu", second))},
        )
    )

    # 6. and 7. The whole directory belongs to another machine, consistently:
    # the document, the measurement of the machine, and every other file name
    # the same second machine.  Nothing inside the directory disagrees any
    # more, so only the comparison with the machine this runs on can catch it,
    # and the escape hatch - a reader who only wants the arithmetic of the
    # tables - has to let it pass.
    other = machine(
        "Some Other Processor", 4, {"sse": True, "sse2": True, "avx": False}
    )
    all_of_other = {
        path: rewritten(path, lambda data: data.__setitem__("cpu", other))
        for path in MEASUREMENTS
    }
    all_of_other[DOC] = measured_on(cpu_flags.summary(other))

    results.append(
        mutated("the directory belongs to another machine", all_of_other)
    )
    results.append(
        mutated(
            "the same, with the escape hatch set",
            all_of_other,
            must_fail=False,
            environment={ENV_ESCAPE: "1"},
        )
    )

    after = {path: path.read_bytes() for path in WATCHED}
    if after != before:
        print("FAIL : the control left the working tree changed")
        return 1
    caught = sum(1 for r in results if r)
    print("%d/%d mutations behaved as they should" % (caught, len(results)))
    return 0 if caught == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
