from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"

VALID_CASES = [
    "valid_basic",         # int x; x := 5; exit x
    "valid_arithmetic",    # int x, y; y := x + 3; exit y
    "valid_reassign",      # int x; x := 5; x := x + 10; exit x (reassign + self-reference)
]

INVALID_CASES = [
    "fail_undeclared",   # using a variable before declaring it
    "fail_redeclare",    # declaring the same variable twice
    "fail_no_exit",      # program does not end with exit
]


@pytest.mark.parametrize("case", VALID_CASES)
def test_valid_program_compiles(run_compiler, case):
    source_file = FIXTURES_DIR / f"{case}.mlang"

    result, output_file = run_compiler(source_file)

    assert result.returncode == 0, f"expected success, got stderr: {result.stderr}"
    assert output_file.exists(), "compiler must write the .ll output file"
    assert output_file.read_text().strip() != ""


@pytest.mark.parametrize("case", VALID_CASES)
def test_valid_program_runs_with_expected_output(run_compiler, run_ir, case):
    source_file = FIXTURES_DIR / f"{case}.mlang"
    expected = (FIXTURES_DIR / f"{case}.expected").read_text().strip()

    result, output_file = run_compiler(source_file)
    assert result.returncode == 0, f"compilation failed: {result.stderr}"

    run_result = run_ir(output_file)
    assert run_result.returncode == 0
    assert run_result.stdout.strip() == expected


@pytest.mark.parametrize("case", INVALID_CASES)
def test_invalid_program_fails(run_compiler, case):
    source_file = FIXTURES_DIR / f"{case}.mlang"
    expected_lines = (FIXTURES_DIR / f"{case}.expected").read_text().strip().splitlines()

    result, output_file = run_compiler(source_file)

    assert result.returncode != 0, "compiler must exit with a non-zero code on error"
    assert not output_file.exists(), "compiler must not write an output file on error"
    for expected in expected_lines:
        assert expected.lower() in result.stderr.lower(), (
            f"expected {expected!r} in stderr, got: {result.stderr!r}"
        )
