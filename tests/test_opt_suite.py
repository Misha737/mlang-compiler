"""Runs every program under tests/opt with --remove-unused.

<name>.astc is the exact output of --remove-unused --ast-checked, <name>.expected
is what the compiled program prints. Dropping a new triple in tests/opt is enough.
"""

import subprocess
import sys
from pathlib import Path

import pytest

OPT_DIR = Path(__file__).parent / "opt"
COMPILER_PATH = Path(__file__).parent.parent / "compiler.py"

OPT_CASES = sorted(p.stem for p in OPT_DIR.glob("*.txt"))


def test_at_least_six_opt_programs():
    assert len(OPT_CASES) >= 6, "tests/opt needs at least 6 programs"


@pytest.mark.parametrize("case", OPT_CASES)
def test_opt_tree_after_the_pass(case):
    result = subprocess.run(
        [sys.executable, str(COMPILER_PATH), "--remove-unused", "--ast-checked", str(OPT_DIR / f"{case}.txt")],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == (OPT_DIR / f"{case}.astc").read_text().strip()


@pytest.mark.parametrize("case", OPT_CASES)
def test_opt_program_prints_the_same(run_ir, tmp_path, case):
    output_file = tmp_path / "output.ll"
    result = subprocess.run(
        [sys.executable, str(COMPILER_PATH), "--remove-unused", str(OPT_DIR / f"{case}.txt"), str(output_file)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    run_result = run_ir(output_file)
    assert run_result.returncode == 0
    assert run_result.stdout.strip() == (OPT_DIR / f"{case}.expected").read_text().strip()
