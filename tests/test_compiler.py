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
    "valid_precedence",
    "valid_mul_middle",
    "valid_left_assoc",
    "valid_assign_expr",
    "valid_no_spaces",
    "valid_chain",
    "valid_types_demo",
]

INVALID_CASES = [
    "fail_unknown_byte",
    "fail_assign_const",
    "fail_use_before_decl",
    "fail_missing_initializer",
    "fail_redeclared",
    "fail_assign_undeclared",
    "fail_exit_undeclared",
    "fail_expr_use_before_decl",
    "fail_parenthesis",
    "fail_division",
    "fail_colon_alone",
    "fail_equals_alone",
]

# Front end only (Task 1 of Practice 5): if/else, blocks and ! parse and dump
# correctly. Compiling these programs needs the scope stack and the basic-block
# code generation added in Tasks 2 and 3.
BLOCKS_AST_CASES = [
    "valid_scope_warmup",
    "valid_if_else",
    "valid_not_operator",
]

# Semantic pass (Task 2 of Practice 4): these fail before code generation is
# ever reached, so they exercise the full CLI even though CodeGen cannot yet
# handle i64/bool. See tests/test_semantic.py for the unit-level coverage of
# every type rule, run without LLVM at all.
SEMANTIC_ERROR_CASES = [
    "fail_arith_bool",
    "fail_compare_bool_int",
    "fail_narrowing_binop",
    "fail_narrowing_var",
    "fail_narrowing_assign",
    "fail_const_overflow_i32",
    "fail_bool_from_int",
    "fail_const_overflow_i64",
    "fail_warm_up_narrowing",
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
    "fail_syntax_tight_operators",
    "fail_syntax_trailing_operator",
    "fail_syntax_operator_after_brace",
    "fail_syntax_extra_operand",
    "fail_syntax_unary_minus",
    "fail_unterminated_brace",
    "fail_bang_statement",
    "fail_if_no_brace_line",
    "fail_if_brace_same_line",
    "fail_empty_block",
    "fail_else_without_if",
    "fail_brace_never_closed",
    "fail_stmt_after_block_exit",
    "fail_if_eof",
    "fail_else_brace_same_line",
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


def test_tokens_flag_reads_bang_again_unless_followed_by_equals(run_dump):
    source_file = FIXTURES_DIR / "tokens_bang.mlang"
    expected = (FIXTURES_DIR / "tokens_bang.expected").read_text().strip()

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


@pytest.mark.parametrize("case", BLOCKS_AST_CASES)
def test_ast_flag_prints_block_tree(run_dump, case):
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


@pytest.mark.parametrize("case", INVALID_CASES + SYNTAX_ERROR_CASES + SEMANTIC_ERROR_CASES)
def test_invalid_program_fails(run_compiler, case):
    source_file = FIXTURES_DIR / f"{case}.mlang"
    expected = (FIXTURES_DIR / f"{case}.expected").read_text().strip()

    result, output_file = run_compiler(source_file)

    assert result.returncode != 0, "compiler must exit with a non-zero code on error"
    assert not output_file.exists(), "compiler must not write an output file on error"
    assert result.stderr.strip() == expected
