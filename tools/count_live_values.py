"""Counts the values that are alive at the same time in one butterfly.

The claim that the kernel of the original keeps fewer values alive than the
symmetric kernel of the port used to be is a mechanism, and a mechanism has
to be counted.  A value is *alive* when it is written and read again later,
so the count is the number of the variables of the round that are used after
their last write.

Usage::

    python tools/count_live_values.py
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def kernel_of(text: str, start: str) -> str:
    """The body of the kernel that starts with the given signature."""
    index = text.index(start)
    end = text.find("\nfn ", index + 1)
    return text[index : end if end > 0 else len(text)]


def live_values(body: str) -> int:
    """The values of a round that are alive at the same time.

    The variables are counted with a last write and a last read: a variable
    that is written and then read is alive between the two, and a variable
    that is written and never read again is dead right after the write.  The
    count is the maximum over the body of the number of the variables that
    are alive at the same moment.
    """
    body = re.sub(r"///.*", "", body)
    body = re.sub(r"//.*", "", body)
    body = body[body.index("{") :]
    # The reads and the writes of every variable, in the order of the code.
    events: list[tuple[str, str]] = []
    for line in body.splitlines():
        line = line.strip()
        for match in re.finditer(r"\b([a-z]\w*)\s*=", line):
            events.append(("write", match.group(1)))
        for match in re.finditer(r"\b([a-z]\w*)\b", line):
            name = match.group(1)
            if name in ("let", "mut", "while", "if", "else", "Unit", "Array"):
                continue
            events.append(("read", name))
    # The last write of every variable, and the reads that follow it.
    last_write: dict[str, int] = {}
    for index, (kind, name) in enumerate(events):
        if kind == "write":
            last_write[name] = index
    alive_at: dict[int, set[str]] = {}
    for index, (kind, name) in enumerate(events):
        if kind == "read" and name in last_write and last_write[name] < index:
            for point in range(last_write[name], index):
                alive_at.setdefault(point, set()).add(name)
    if not alive_at:
        return 0
    return max(len(names) for names in alive_at.values())


def main() -> int:
    kernels = (ROOT / "moonbit_fft" / "kernels.mbt").read_text(encoding="utf-8")
    print("the kernel of the port, the radix 13:")
    print("  stage_r13_mu1: %d values alive" % live_values(kernel_of(kernels, "fn stage_r13_mu1(")))

    # The symmetric kernel of the previous generation is in the history.  The
    # path carries the **old** name of the module on purpose: that commit
    # predates the rename of the directory to `moonbit_fft/`.
    old = subprocess.run(
        ["git", "show", "cd434fd:moonbit_fft2/kernels.mbt"],
        cwd=str(ROOT),
        capture_output=True,
        check=True,
    ).stdout.decode("utf-8")
    print("the symmetric kernel of the previous generation, the radix 13:")
    print("  stage_r13: %d values alive" % live_values(kernel_of(old, "fn stage_r13(")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
