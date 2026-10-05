"""Runs every program under tests/ok and tests/err (Task 3 of Practice 4).

Unlike tests/fixtures, these two directories are discovered automatically:
dropping a new <name>.txt + <name>.expected pair in either one is enough,
no list to edit here.
"""

from pathlib import Path

import pytest

OK_DIR = Path(__file__).parent / "ok"
ERR_DIR = Path(__file__).parent / "err"

OK_CASES = sorted(p.stem for p in OK_DIR.glob("*.txt"))
ERR_CASES = sorted(p.stem for p in ERR_DIR.glob("*.txt"))


def test_at_least_six_ok_and_err_programs():
    assert len(OK_CASES) >= 6, "tests/ok needs at least 6 programs"
    assert len(ERR_CASES) >= 6, "tests/err needs at least 6 programs"


@pytest.mark.parametrize("case", OK_CASES)
def test_ok_program_compiles_and_runs(run_compiler, run_ir, case):
    source_file = OK_DIR / f"{case}.txt"
    expected = (OK_DIR / f"{case}.expected").read_text().strip()

    result, output_file = run_compiler(source_file)
    assert result.returncode == 0, f"compilation failed: {result.stderr}"
    assert output_file.exists()

    run_result = run_ir(output_file)
    assert run_result.returncode == 0
    assert run_result.stdout.strip() == expected


@pytest.mark.parametrize("case", ERR_CASES)
def test_err_program_is_rejected(run_compiler, case):
    source_file = ERR_DIR / f"{case}.txt"
    expected = (ERR_DIR / f"{case}.expected").read_text().strip()

    result, output_file = run_compiler(source_file)

    assert result.returncode != 0, "compiler must exit with a non-zero code on error"
    assert not output_file.exists(), "compiler must not write an output file on error"
    assert result.stderr.strip() == expected
