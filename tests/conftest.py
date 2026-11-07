import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

COMPILER_PATH = Path(__file__).parent.parent / "compiler.py"
FIXTURES_DIR = Path(__file__).parent / "fixtures"


def pytest_addoption(parser):
    parser.addoption(
        "--remove-unused",
        action="store_true",
        default=False,
        help="compile every program with --remove-unused (same as REMOVE_UNUSED=1)",
    )


@pytest.fixture
def remove_unused(request):
    return request.config.getoption("--remove-unused") or os.environ.get("REMOVE_UNUSED") == "1"


@pytest.fixture
def run_compiler(tmp_path, remove_unused):
    """Runs `python3 compiler.py [--remove-unused] <source> <output.ll>` and returns (CompletedProcess, output_path)."""

    def _run(source_file: Path):
        output_file = tmp_path / "output.ll"
        flags = ["--remove-unused"] if remove_unused else []
        result = subprocess.run(
            [sys.executable, str(COMPILER_PATH), *flags, str(source_file), str(output_file)],
            capture_output=True,
            text=True,
        )
        return result, output_file

    return _run


@pytest.fixture
def run_dump():
    """Runs `python3 compiler.py <flag> <source>` (--tokens or --ast) and returns the CompletedProcess."""

    def _run(flag: str, source_file: Path):
        return subprocess.run(
            [sys.executable, str(COMPILER_PATH), flag, str(source_file)],
            capture_output=True,
            text=True,
        )

    return _run


@pytest.fixture
def run_ir():
    """Runs a compiled .ll file with `lli` (the LLVM interpreter) and returns the CompletedProcess.

    An optional stdin_file is passed to the program as its standard input.
    Skips the test if `lli` isn't installed, so the suite still runs on machines
    without a full LLVM toolchain.
    """

    def _run(ll_file: Path, stdin_file: Path = None):
        if shutil.which("lli") is None:
            pytest.skip("lli (LLVM interpreter) is not installed")
        stdin_text = stdin_file.read_text() if stdin_file is not None else ""
        return subprocess.run(["lli", str(ll_file)], input=stdin_text, capture_output=True, text=True)

    return _run
