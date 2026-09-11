import shutil
import subprocess
import sys
from pathlib import Path

import pytest

COMPILER_PATH = Path(__file__).parent.parent / "src" / "compiler.py"
FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def run_compiler(tmp_path):
    """Runs `python3 compiler.py <source> <output.ll>` and returns (CompletedProcess, output_path)."""

    def _run(source_file: Path):
        output_file = tmp_path / "output.ll"
        result = subprocess.run(
            [sys.executable, str(COMPILER_PATH), str(source_file), str(output_file)],
            capture_output=True,
            text=True,
        )
        return result, output_file

    return _run


@pytest.fixture
def run_ir():
    """Runs a compiled .ll file with `lli` (the LLVM interpreter) and returns the CompletedProcess.

    Skips the test if `lli` isn't installed, so the suite still runs on machines
    without a full LLVM toolchain.
    """

    def _run(ll_file: Path):
        if shutil.which("lli") is None:
            pytest.skip("lli (LLVM interpreter) is not installed")
        result = subprocess.run(["lli", str(ll_file)], capture_output=True, text=True)
        return result

    return _run
