from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"

VALID_CASES = [
    "valid_const_decl",
    "valid_mut_decl",
    "valid_arithmetic",
    "valid_spacing",
    "valid_reassign",
]

INVALID_CASES = [
    "fail_unknown_byte",
    "fail_unterminated_brace",
    "fail_assign_const",
    "fail_use_before_decl",
    "fail_missing_initializer",
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
