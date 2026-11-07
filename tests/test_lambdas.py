from pathlib import Path

import pytest

from src.lexer import CompileError, lex
from src.parser import Parser
from src.semantic import SemanticChecker

ADD_K = """i32 mut k{10}
fn add_k := [k](i32 y) -> i32
{
    i32 r{k + y}
    exit r
}
k := 100
print(add_k(5))
exit add_k(1)
"""


def checked_tree(source):
    tree = Parser(lex(source.encode())).parse_program()
    SemanticChecker().check(tree)
    return tree


def error_of(source):
    with pytest.raises(CompileError) as info:
        checked_tree(source)
    return str(info.value)


def test_ast_keeps_the_lambda_as_parsed(tmp_path, run_dump):
    source = tmp_path / "p.mlang"
    source.write_text(ADD_K)
    result = run_dump("--ast", source)
    assert result.returncode == 0
    assert "Lambda add_k -> i32" in result.stdout
    assert "Capture k" in result.stdout
    assert "Struct lambda.add_k" not in result.stdout
    assert "CallableCall" not in result.stdout


def test_ast_checked_shows_struct_declaration_and_callable_call(tmp_path, run_dump):
    source = tmp_path / "p.mlang"
    source.write_text(ADD_K)
    result = run_dump("--ast-checked", source)
    assert result.returncode == 0
    lines = result.stdout.splitlines()
    assert "  Lambda add_k -> i32" in lines
    assert "    Struct lambda.add_k" in lines
    assert "      Member k i32 const" in lines
    assert "      MemberFn call -> i32" in lines
    assert "    Decl add_k lambda.add_k const" in lines
    assert "    CallableCall add_k" in lines


def test_mut_capture_makes_the_field_and_the_closure_mut(tmp_path, run_dump):
    source = tmp_path / "p.mlang"
    source.write_text(
        "i32 n{0}\nfn f := [mut n]() -> i32\n{\n    n := n + 1\n    exit n\n}\nexit f()\n"
    )
    result = run_dump("--ast-checked", source)
    assert "Capture mut n" not in result.stdout
    assert "Member n i32 mut" in result.stdout
    assert "Decl f lambda.f mut" in result.stdout


def test_lambda_structs_are_registered_under_unique_names():
    tree = checked_tree(
        "fn a := (i32 n) -> i32\n{\n    fn f := [n](i32 y) -> i32\n    {\n        exit y\n    }\n    exit n\n}\n"
        "fn b := (i32 n) -> i32\n{\n    fn f := [n](i32 y) -> i32\n    {\n        exit y\n    }\n    exit n\n}\n"
        "exit 0\n"
    )
    assert [s.name for s in tree.lambda_structs] == ["lambda.f", "lambda.f.1"]


def test_lambda_cannot_capture_a_top_level_variable_from_inside_a_function():
    message = error_of(
        "fn f := () -> i32\n{\n    fn g := [k](i32 y) -> i32\n    {\n        exit y\n    }\n    exit 1\n}\n"
        "i32 k{1}\nexit 0\n"
    )
    assert message == "line 3:14: cannot capture 'k': no variable 'k' is visible here"


def test_lambda_cannot_be_called_before_its_declaration():
    assert error_of("exit f(1)\n").endswith("unknown function 'f'")


def test_capture_list_on_member_function_is_a_parse_error():
    source = "struct S\n{\n    i32 a\n    fn f := [a]() -> i32\n    {\n        exit 1\n    }\n}\nexit 0\n"
    with pytest.raises(CompileError, match="a member function cannot have a capture list"):
        Parser(lex(source.encode())).parse_program()
