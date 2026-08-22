"""Emit the runtime dependency declarations from pyproject.toml.

Intended to run inside the Docker resolve stage, where pyproject.toml is copied
into the working directory. Outputs one requirement per line in a form pip
accepts via -r.
"""

from __future__ import annotations

import tomllib
from pathlib import Path


def main() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    print("\n".join(pyproject["project"]["dependencies"]))


if __name__ == "__main__":
    main()
