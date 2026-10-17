#!/usr/bin/env python3
"""One version, three places, asserted to agree — and, with a tag argument, to
agree with the tag as well. Modelled on the WordPress plugin's check-version
script in the main repo, for the same reason: the same fact in several files is
only safe when something fails loudly when they diverge.

Prints the bare version on success, which the release workflow captures.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import tomllib

ROOT = Path(__file__).resolve().parent.parent


def main(argv: list[str]) -> int:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    module = re.search(r'^VERSION = "([^"]+)"', (ROOT / "src/rankraft/_version.py").read_text(), re.M)
    sources: dict[str, str | None] = {
        "pyproject.toml": pyproject,
        "src/rankraft/_version.py": module.group(1) if module else None,
    }

    if len(argv) > 1:
        tag = re.fullmatch(r"v(\d+\.\d+\.\d+(?:[-.][\w.]+)?)", argv[1])
        if not tag:
            print(f"check-version: tag {argv[1]!r} is not vX.Y.Z", file=sys.stderr)
            return 1
        sources["git tag"] = tag.group(1)

    distinct = set(sources.values())
    if len(distinct) != 1 or None in distinct:
        width = max(len(k) for k in sources)
        print("check-version: these do not agree\n", file=sys.stderr)
        for name, value in sources.items():
            print(f"  {name.ljust(width)}  {value or '(not found)'}", file=sys.stderr)
        return 1

    print(pyproject)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
