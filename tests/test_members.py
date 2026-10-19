import pytest
import llvmlite.binding as llvm
from llvmlite import ir

from src.codegen import CodeGen
from src.lexer import CompileError, lex
from src.parser import Parser
from src.semantic import SemanticChecker

POINT = (
    "struct Point\n{\n    i32 mut x\n    i32 mut y\n"
    "    fn d2 := () -> i32\n    {\n        i32 r{x * x + y * y}\n        exit r\n    }\n"
    "    fn shift := (i32 dx) -> i32\n    {\n        x := x + dx\n        exit x\n    }\n}\n"
)


def check(source):
    tree = Parser(lex(source.encode())).parse_program()
    SemanticChecker().check(tree)
    return tree


def generate(source):
    return CodeGen().generate(check(source))


def check_error(source):
    with pytest.raises(CompileError) as exc_info:
        check(source)
    return str(exc_info.value)


def methods_of(tree, struct_name):
    struct = next(s for s in tree.structs if s.name == struct_name)
    return {m.name: m for m in struct.methods}


def test_assigning_a_field_makes_a_function_mutating():
    methods = methods_of(check(POINT + "exit 0\n"), "Point")
    assert methods["shift"].mutating
    assert not methods["d2"].mutating


def test_mutation_spreads_through_a_cycle_of_member_functions():
    tree = check(
        "struct S\n{\n    i32 mut n\n"
        "    fn a := (i32 k) -> i32\n    {\n        if k == 0\n        {\n            n := n + 1\n            exit n\n        }\n"
        "        i32 r{b(k - 1)}\n        exit r\n    }\n"
        "    fn b := (i32 k) -> i32\n    {\n        i32 r{a(k)}\n        exit r\n    }\n}\nexit 0\n"
    )
    methods = methods_of(tree, "S")
    assert methods["a"].mutating and methods["b"].mutating


def test_a_local_named_like_a_field_does_not_make_a_function_mutating():
    tree = check(
        "struct S\n{\n    i32 v\n"
        "    fn f := () -> i32\n    {\n        i32 mut v{1}\n        v := 2\n        exit v\n    }\n}\nexit 0\n"
    )
    assert not methods_of(tree, "S")["f"].mutating


def test_a_cycle_that_never_assigns_stays_non_mutating():
    tree = check(
        "struct S\n{\n    i32 n\n"
        "    fn a := () -> i32\n    {\n        i32 r{b()}\n        exit r\n    }\n"
        "    fn b := () -> i32\n    {\n        i32 r{a()}\n        exit r\n    }\n}\nexit 0\n"
    )
    methods = methods_of(tree, "S")
    assert not methods["a"].mutating and not methods["b"].mutating


def test_a_field_name_resolves_to_the_field_of_this():
    tree = check(POINT + "exit 0\n")
    exit_node = methods_of(tree, "Point")["shift"].body.exit
    assert exit_node.value.decl is None
    assert exit_node.value.field.name == "x"


def test_a_parameter_hides_a_field():
    tree = check(
        "struct S\n{\n    i32 v\n    fn f := (i32 v) -> i32\n    {\n        exit v\n    }\n}\nexit 0\n"
    )
    exit_value = methods_of(tree, "S")["f"].body.exit.value
    assert exit_value.field is None
    assert exit_value.decl.name == "v"


def test_a_member_function_hides_a_global_function():
    tree = check(
        "struct S\n{\n    i32 v\n    fn g := () -> i32\n    {\n        exit 3\n    }\n"
        "    fn f := () -> i32\n    {\n        i32 r{g()}\n        exit r\n    }\n}\n"
        "fn g := () -> i32\n{\n    exit 100\n}\nexit 0\n"
    )
    call = methods_of(tree, "S")["f"].body.statements[0].init
    assert call.this_call
    assert call.function is methods_of(tree, "S")["g"]


def test_a_mutating_call_on_a_const_object_is_rejected():
    assert check_error(POINT + "Point q{3, 4}\ni32 b{q.shift(1)}\nexit b\n") == \
        "line 17:7: cannot call mutating function 'shift' on 'q': 'q' is not mut"


def test_a_mutating_call_through_a_const_field_is_rejected_at_that_field():
    source = (
        POINT + "struct Circle\n{\n    Point center\n    i32 radius\n}\n"
        "Point q{3, 4}\nCircle mut c{q, 2}\ni32 e{c.center.shift(1)}\nexit e\n"
    )
    assert check_error(source) == \
        "line 23:9: cannot call mutating function 'shift' through 'c.center': field 'center' is not mut"


def test_a_non_mutating_call_is_allowed_on_a_const_object():
    check(POINT + "Point q{3, 4}\ni32 a{q.d2()}\nexit a\n")


def test_the_mutation_rule_follows_a_call_through_a_field_of_this():
    source = (
        "struct A\n{\n    i32 mut n\n    fn inc := () -> i32\n    {\n        n := n + 1\n        exit n\n    }\n}\n"
        "struct B\n{\n    A a\n    fn go := () -> i32\n    {\n        i32 r{a.inc()}\n        exit r\n    }\n}\nexit 0\n"
    )
    assert check_error(source) == \
        "line 15:15: cannot call mutating function 'inc' through 'a': field 'a' is not mut"


def test_member_function_ir_takes_a_pointer_to_the_object_first():
    function = generate(POINT + "exit 0\n").get_global("Point_shift")
    this, dx = function.args
    assert this.name == "this" and str(this.type) == '%"Point"*'
    assert str(dx.type) == "i32"


def test_a_field_assignment_in_a_member_function_is_gep_load_add_store():
    function = generate(POINT + "exit 0\n").get_global("Point_shift")
    names = [instr.opname for instr in function.blocks[0].instructions]
    assert ["getelementptr", "load", "load", "add", "getelementptr", "store"] == names[
        names.index("getelementptr"):names.index("getelementptr") + 6
    ]


def test_a_call_passes_the_address_of_the_object():
    module = generate(POINT + "Point mut p{3, 4}\ni32 n{p.shift(2)}\nexit n\n")
    main = module.get_global("main")
    calls = [i for i in main.blocks[0].instructions if isinstance(i, ir.CallInstr)]
    shift = next(c for c in calls if c.callee.name == "Point_shift")
    assert shift.args[0] is next(
        i for i in main.blocks[0].instructions if isinstance(i, ir.AllocaInstr) and i.name == "p"
    )


def test_a_call_on_a_nested_field_passes_a_gep_into_the_outer_object():
    source = (
        POINT + "struct Circle\n{\n    Point center\n    i32 radius\n}\n"
        "Point p{3, 4}\nCircle c{p, 2}\nexit c.center.d2()\n"
    )
    main = generate(source).get_global("main")
    call = next(
        i for i in main.blocks[0].instructions if isinstance(i, ir.CallInstr) and i.callee.name == "Point_d2"
    )
    assert call.args[0].opname == "getelementptr"


def test_generated_ir_with_members_read_and_print_is_valid():
    source = (
        POINT + "Point mut p{read(), read()}\nprint(p)\nprint(p.shift(1))\nprint(\"done\")\nprint(p.x == 4)\nexit p.x\n"
    )
    llvm.parse_assembly(str(generate(source))).verify()


def test_read_writes_into_an_alloca_in_the_entry_block():
    main = generate("i32 a{read()}\nexit a\n").get_global("main")
    entry = main.blocks[0]
    slot = next(i for i in entry.instructions if isinstance(i, ir.AllocaInstr) and i.name == "read")
    scanf = next(i for i in entry.instructions if isinstance(i, ir.CallInstr) and i.callee.name == "scanf")
    assert scanf.args[1] is slot
    assert any(isinstance(i, ir.LoadInstr) and i.operands[0] is slot for i in entry.instructions)


def test_print_uses_one_printf_with_the_matching_format():
    module = generate("i64 big{5}\nprint(1)\nprint(big)\nprint(true)\nexit 0\n")
    text = str(module)
    for fmt in ('c"%d\\0a\\00"', 'c"%lld\\0a\\00"', 'c"%s\\0a\\00"'):
        assert fmt in text
    assert text.count("declare i32 @\"printf\"") == 1
