import pytest

from src.lexer import lex, CompileError
from src.parser import Parser
from src.semantic import SemanticChecker


def check(source: str):
    """Lex, parse and type-check a program without touching LLVM at all."""
    tree = Parser(lex(source.encode())).parse_program()
    SemanticChecker().check(tree)
    return tree


def check_error(source: str) -> str:
    with pytest.raises(CompileError) as exc_info:
        check(source)
    return str(exc_info.value)


# --- accepted programs: widening, and each place a type is computed -------

def test_i32_widens_into_an_i64_variable():
    check("i32 a{10}\ni64 b{a}\nexit b\n")


def test_arithmetic_of_two_i32_stays_i32():
    tree = check("i32 a{10}\ni32 b{a * 5}\nexit b\n")
    assert tree.statements[1].init.type == "i32"


def test_arithmetic_of_i32_and_i64_widens_to_i64():
    tree = check("i32 a{10}\ni64 b{20}\ni64 c{a + b}\nexit c\n")
    assert tree.statements[2].init.type == "i64"


def test_comparison_of_mixed_width_integers_is_bool():
    tree = check("i32 a{10}\ni64 b{20}\nbool c{a == b}\nexit c\n")
    assert tree.statements[2].init.type == "bool"


def test_comparison_of_two_bools_is_bool():
    check("bool a{true}\nbool b{false}\nbool c{a != b}\nexit c\n")


def test_bool_exit_is_allowed():
    check("bool a{true}\nexit a\n")


def test_warm_up_program_is_rejected_at_the_narrowing_line():
    # i32 a{10}; i64 b{a}; bool c{a == b}; i32 d{a + b}  <- rejected here
    message = check_error(
        "i32 a{10}\n"
        "i64 b{a}\n"
        "bool c{a == b}\n"
        "i32 d{a + b}\n"
        "bool e{c == 1}\n"
        "exit d\n"
    )
    assert message == "line 4:5: cannot initialise 'd' of type i32 with a value of type i64"


# --- rejected programs, one per rule ---------------------------------------

def test_arithmetic_on_bool_is_rejected():
    assert check_error("bool x{true}\ni32 y{x + 1}\nexit y\n") == \
        "line 2:9: cannot apply '+' to bool"


def test_comparing_bool_with_an_integer_is_rejected():
    assert check_error("bool b{true}\ni32 n{5}\nbool c{b == n}\nexit c\n") == \
        "line 3:10: cannot compare bool with i32"


def test_comparing_an_integer_constant_with_bool_is_rejected():
    assert check_error("bool b{true}\nbool c{b == 1}\nexit c\n") == \
        "line 2:10: cannot compare bool with i32"


def test_narrowing_a_computed_value_into_a_declaration_is_rejected():
    assert check_error("i32 a{10}\ni64 b{20}\ni32 c{a + b}\nexit c\n") == \
        "line 3:5: cannot initialise 'c' of type i32 with a value of type i64"


def test_narrowing_a_variable_into_a_declaration_is_rejected():
    assert check_error("i64 b{20}\ni32 g{b}\nexit g\n") == \
        "line 2:5: cannot initialise 'g' of type i32 with a value of type i64"


def test_narrowing_assignment_is_rejected():
    assert check_error("i32 mut x{1}\ni64 y{5}\nx := y\nexit x\n") == \
        "line 3:1: cannot assign to 'x' of type i32 with a value of type i64"


def test_oversized_constant_in_an_i32_slot_is_rejected():
    assert check_error("i32 d{3000000000}\nexit d\n") == \
        "line 1:7: constant 3000000000 does not fit in i32"


def test_bool_does_not_initialise_from_an_integer():
    assert check_error("bool b{5}\nexit b\n") == \
        "line 1:6: cannot initialise 'b' of type bool with a value of type i32"


def test_constant_too_large_for_any_type_is_rejected():
    message = check_error("i64 huge{99999999999999999999}\nexit huge\n")
    assert message == "line 1:10: constant 99999999999999999999 does not fit in i64"


def test_using_a_variable_in_its_own_initialiser_is_rejected():
    # visit_decl must evaluate init before the name enters the symbol table.
    assert check_error("i32 x{x}\nexit x\n") == \
        "line 1:7: variable 'x' is used before its declaration"


# --- constant width boundaries ---------------------------------------------

I32_MAX = 2 ** 31 - 1
I64_MAX = 2 ** 63 - 1


def test_constant_at_the_i32_boundary_is_i32():
    tree = check(f"i32 a{{{I32_MAX}}}\nexit a\n")
    assert tree.statements[0].init.type == "i32"


def test_constant_one_past_the_i32_boundary_is_i64():
    tree = check(f"i64 a{{{I32_MAX + 1}}}\nexit a\n")
    assert tree.statements[0].init.type == "i64"


def test_constant_one_past_the_i32_boundary_does_not_fit_an_i32_slot():
    message = check_error(f"i32 a{{{I32_MAX + 1}}}\nexit a\n")
    assert message == f"line 1:7: constant {I32_MAX + 1} does not fit in i32"


def test_constant_at_the_i64_boundary_is_i64():
    tree = check(f"i64 a{{{I64_MAX}}}\nexit a\n")
    assert tree.statements[0].init.type == "i64"


def test_constant_one_past_the_i64_boundary_is_rejected():
    message = check_error(f"i64 a{{{I64_MAX + 1}}}\nexit a\n")
    assert message == f"line 1:7: constant {I64_MAX + 1} does not fit in i64"


# --- the three checks carried over from Practice 3, now in this pass ------

def test_already_declared_is_still_reported():
    assert check_error("i32 x{1}\ni32 x{2}\nexit x\n") == \
        "line 2:5: variable 'x' is already declared"


def test_use_before_declaration_is_still_reported():
    assert check_error("i32 x{y}\nexit x\n") == \
        "line 1:7: variable 'y' is used before its declaration"


def test_assign_to_non_mut_is_still_reported():
    assert check_error("i32 x{1}\nx := 2\nexit x\n") == \
        "line 2:1: cannot assign to 'x': it is not mut"
