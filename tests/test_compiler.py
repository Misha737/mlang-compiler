from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"

VALID_CASES = [
    "valid_const_decl",
    "valid_mut_decl",
    "valid_arithmetic",
    "valid_spacing",
    "valid_reassign",
    "valid_practice2",
]

INVALID_CASES = [
    "fail_unknown_byte",
    "fail_unterminated_brace",
    "fail_assign_const",
    "fail_use_before_decl",
    "fail_missing_initializer",
]

SYNTAX_ERROR_CASES = [
    "fail_syntax_statement_start",
    "fail_syntax_missing_assign",
    "fail_syntax_extra_token",
    "fail_syntax_line_ends_early",
    "fail_syntax_two_operators",
    "fail_syntax_after_exit",
    "fail_syntax_no_exit",
    "fail_syntax_exit_operation",
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


def test_tokens_flag_prints_token_list(run_dump):
    source_file = FIXTURES_DIR / "tokens_worked_example.mlang"
    expected = (FIXTURES_DIR / "tokens_worked_example.expected").read_text().strip()

    result = run_dump("--tokens", source_file)

    assert result.returncode == 0, f"expected success, got stderr: {result.stderr}"
    assert result.stdout.strip() == expected


def test_tokens_flag_reports_lexical_error(run_dump):
    source_file = FIXTURES_DIR / "fail_unknown_byte.mlang"

    result = run_dump("--tokens", source_file)

    assert result.returncode != 0
    assert result.stdout == ""
    assert "unexpected byte" in result.stderr


@pytest.mark.parametrize("case", VALID_CASES)
def test_ast_flag_prints_tree(run_dump, case):
    source_file = FIXTURES_DIR / f"{case}.mlang"
    expected = (FIXTURES_DIR / f"{case}.ast").read_text().strip()

    result = run_dump("--ast", source_file)

    assert result.returncode == 0, f"expected success, got stderr: {result.stderr}"
    assert result.stdout.strip() == expected


@pytest.mark.parametrize("case", SYNTAX_ERROR_CASES)
def test_ast_flag_reports_syntax_error(run_dump, case):
    source_file = FIXTURES_DIR / f"{case}.mlang"
    expected = (FIXTURES_DIR / f"{case}.expected").read_text().strip()

    result = run_dump("--ast", source_file)

    assert result.returncode != 0
    assert result.stdout == ""
    assert result.stderr.strip() == expected


@pytest.mark.parametrize("case", INVALID_CASES)
def test_invalid_program_fails(run_compiler, case):
    source_file = FIXTURES_DIR / f"{case}.mlang"
    expected = (FIXTURES_DIR / f"{case}.expected").read_text().strip()

    result, output_file = run_compiler(source_file)

    assert result.returncode != 0, "compiler must exit with a non-zero code on error"
    assert not output_file.exists(), "compiler must not write an output file on error"
    assert result.stderr.strip() == expected
