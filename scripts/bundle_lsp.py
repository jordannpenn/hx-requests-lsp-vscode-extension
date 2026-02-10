#!/usr/bin/env python3
"""Bundle hx-requests-lsp and dependencies for VSCode extension."""

import subprocess
import shutil
import sys
from pathlib import Path

BUNDLED_LIBS = Path(__file__).parent.parent / "bundled" / "libs"
LOCAL_LSP_PATH = Path.home() / "dev" / "hx-requests-lsp"


def main():
    # Clean existing bundled libs
    if BUNDLED_LIBS.exists():
        shutil.rmtree(BUNDLED_LIBS)
    BUNDLED_LIBS.mkdir(parents=True)

    # Determine source: local path (for dev) or PyPI (for CI/release)
    if LOCAL_LSP_PATH.exists() and "--from-pypi" not in sys.argv:
        # Local development: install from sibling directory
        print(f"Installing from local path: {LOCAL_LSP_PATH}")
        source = str(LOCAL_LSP_PATH)
    else:
        # CI/Release: install from PyPI
        print("Installing from PyPI: hx-requests-lsp")
        source = "hx-requests-lsp"

    python_cmd = sys.executable
    version_result = subprocess.run(
        [python_cmd, "--version"],
        capture_output=True,
        text=True,
    )
    version_str = version_result.stdout or version_result.stderr
    print(f"Using Python: {python_cmd} ({version_str.strip()})")

    subprocess.run(
        [
            python_cmd,
            "-m",
            "pip",
            "install",
            "--target",
            str(BUNDLED_LIBS),
            "--no-user",
            "--ignore-requires-python",
            source,
        ],
        check=True,
    )

    print(f"Bundled LSP to {BUNDLED_LIBS}")


if __name__ == "__main__":
    main()
