#!/usr/bin/env python3
"""Identifies the CPU that a measurement was taken on.

The numbers of `bench/` are only comparable inside one machine: this one loses
about half of its speed after some seconds of load, and another machine would
sit at a different absolute level altogether.  A measurement therefore has to
carry the identity of the machine it came from, and a gate that compares
documents against the measurement has to notice when it is not running on that
machine any more.

The identity is the marketing name of the processor, the identifier the
platform reports (family, model, stepping), the number of logical cores and
the instruction set extensions the OS says are available.  The fingerprint is
a hash of exactly those, so that a different machine is one comparison away.

`IsProcessorFeaturePresent` is the source of the extension bits: it needs no
compiler and no portable executable, and on the machine of this repository its
answer was cross checked against a CPUID probe (see `tools/v128probe/README.md`
for the probe and for the one bit it got wrong, RDRAND, which is why this file
records the source next to the bits).

A measurement of `bench/` is written through `write()`, which puts this
identity on the file, so that a number always says which machine it belongs
to.  `stamp()` does the same for a measurement that was taken before the field
existed: it records where the numbers came from, it does not measure anything.

Usage::

    python tools/cpu_flags.py           # the identity, for a reader
    python tools/cpu_flags.py --json    # the identity, for a script
    python tools/cpu_flags.py --suggest # the cc-flags this CPU deserves
    python tools/cpu_flags.py --stamp bench/bench_copy.json ...  # record it
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import pathlib
import platform
import sys

# The feature codes of `IsProcessorFeaturePresent`, by the names the compiler
# drivers use for the same thing.
FEATURES = {
    6: "sse",
    10: "sse2",
    13: "sse3",
    36: "ssse3",
    37: "sse4_1",
    38: "sse4_2",
    39: "avx",
    40: "avx2",
    41: "avx512f",
}

# The flags that keep the toolchain defaults: `link.native.cc-flags` replaces
# the default set instead of adding to it, and the default set carries `/O2`.
BASE_FLAGS = "/O2 /utf-8 /wd4819"


def marketing_name() -> str:
    """The name of the processor as the operating system spells it."""
    if platform.system() != "Windows":
        return ""
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
        )
        value, _ = winreg.QueryValueEx(key, "ProcessorNameString")
        return str(value).strip()
    except Exception:
        return ""


def feature_bits() -> tuple[dict[str, bool], str]:
    """The extension bits the OS reports, and where they came from."""
    if platform.system() != "Windows":
        return {}, "unsupported platform"
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        present = kernel32.IsProcessorFeaturePresent
        present.argtypes = [ctypes.c_uint32]
        present.restype = ctypes.c_bool
    except Exception as error:  # pragma: no cover - only on a broken OS
        return {}, "unavailable: %s" % error
    return {name: bool(present(code)) for code, name in FEATURES.items()}, (
        "IsProcessorFeaturePresent"
    )


def fingerprint(identity: dict) -> str:
    """A short stable hash of the fields that make one machine another one."""
    parts = [
        identity.get("name", ""),
        identity.get("identifier", ""),
        "%d" % identity.get("logical_cores", 0),
        ",".join(sorted(k for k, v in identity.get("isa", {}).items() if v)),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


def suggest(identity: dict) -> str:
    """The cc-flags that this CPU can be compiled for."""
    flags = BASE_FLAGS
    if identity.get("isa", {}).get("avx2"):
        flags += " /arch:AVX2"
    return flags


def detect() -> dict:
    """The identity of the machine this runs on."""
    bits, source = feature_bits()
    identity = {
        "name": marketing_name(),
        "identifier": platform.processor() or platform.machine(),
        "machine": platform.machine(),
        "system": platform.system(),
        "logical_cores": os.cpu_count() or 0,
        "isa": bits,
        "source": source,
    }
    identity["fingerprint"] = fingerprint(identity)
    identity["suggested_cc_flags"] = suggest(identity)
    return identity


def summary(identity: dict) -> str:
    """One line for a document."""
    labels = [
        ("sse", "SSE"),
        ("sse2", "SSE2"),
        ("sse3", "SSE3"),
        ("ssse3", "SSSE3"),
        ("sse4_1", "SSE4.1"),
        ("sse4_2", "SSE4.2"),
        ("avx", "AVX"),
        ("avx2", "AVX2"),
        ("avx512f", "AVX-512F"),
    ]
    extensions = " ".join(
        label for key, label in labels if identity["isa"].get(key)
    )
    name = identity["name"] or identity["identifier"] or "unknown processor"
    return "%s (%s, %d logical cores, %s, fingerprint %s)" % (
        name,
        identity["identifier"],
        identity["logical_cores"],
        extensions or "no extensions reported",
        identity["fingerprint"],
    )


def write(path: pathlib.Path, payload: dict) -> dict:
    """Writes a measurement of `bench/` with the identity of this machine.

    Every measurement goes through here, so that no file of the directory can
    be told from a number whose machine is unknown.  The payload is written in
    the one shape the other measurements use: sorted keys, two spaces, and one
    line feed at the end.
    """
    stamped = dict(payload)
    identity = detect()
    stamped["cpu"] = identity
    path.write_text(
        json.dumps(stamped, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return identity


def stamp(path: pathlib.Path) -> dict:
    """Records the identity in a measurement that has none, without measuring."""
    return write(path, json.loads(path.read_text(encoding="utf-8")))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="print the identity as JSON")
    parser.add_argument(
        "--suggest", action="store_true", help="print only the cc-flags to use"
    )
    parser.add_argument(
        "--stamp",
        nargs="+",
        metavar="JSON",
        help="record the identity in these measurements, without measuring again",
    )
    args = parser.parse_args()
    if args.stamp:
        paths = [pathlib.Path(name) for name in args.stamp]
        absent = [str(path) for path in paths if not path.exists()]
        if absent:
            print("%s does not exist, measure first" % ", ".join(absent))
            return 1
        for path in paths:
            identity = stamp(path)
            print("stamped %s" % path)
        print("cpu: %s" % summary(identity))
        return 0
    identity = detect()
    if args.suggest:
        print(identity["suggested_cc_flags"])
        return 0
    if args.json:
        print(json.dumps(identity, indent=2, sort_keys=True))
        return 0
    print("name       : %s" % (identity["name"] or "-"))
    print("identifier : %s" % identity["identifier"])
    print("cores      : %d logical" % identity["logical_cores"])
    print("extensions : %s" % (
        " ".join(name for name, present in sorted(identity["isa"].items()) if present)
        or "-"
    ))
    print("source     : %s" % identity["source"])
    print("fingerprint: %s" % identity["fingerprint"])
    print("cc-flags   : %s" % identity["suggested_cc_flags"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
