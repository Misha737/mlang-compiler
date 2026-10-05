import pytest
import llvmlite.binding as llvm
from llvmlite import ir

from src.ast_nodes import ProgramNode, DeclNode, ExitNode, VarNode, ConstNode
from src.codegen import CodeGen
from src.lexer import lex
from src.parser import Parser
from src.semantic import SemanticChecker


def typed_const(value):
    node = ConstNode(1, 1, value)
    node.type = "i32"
    return node


def typed_var(name, decl):
    node = VarNode(1, 1, name)
    node.decl = decl
    node.type = decl.type_name
    return node


def test_slots_are_keyed_by_declaration_not_by_name():
    first = DeclNode(1, 5, "x", "i32", False, typed_const(1))
    second = DeclNode(2, 5, "x", "i32", False, typed_const(2))
    exit_node = ExitNode(3, 1, typed_var("x", first))
    program = ProgramNode(1, 1, [first, second], exit_node)

    codegen = CodeGen()
    codegen.generate(program)

    assert codegen.slots[first] is not codegen.slots[second]
    loads = [
        instr
        for block in codegen.builder.function.blocks
        for instr in block.instructions
        if isinstance(instr, ir.LoadInstr)
    ]
    assert [load.operands[0] for load in loads] == [codegen.slots[first]]


# --- basic blocks and entry-block slots (Practice 5) ----------------------

BLOCK_PROGRAMS = {
    "nested_warm_up": (
        "i32 mut x{10}\nif true\n{\n    bool mut x{true}\n    if x\n    {\n"
        "        i64 mut x{20}\n        exit x\n    }\n    exit x\n}\nexit x\n",
        5,
    ),
    "if_else_assign": (
        "i32 mut a{10}\nbool b{true}\nif b\n{\n    a := a + 5\n}\nelse\n{\n    a := a - 5\n}\nexit a\n",
        4,
    ),
    "both_arms_exit": ("if true\n{\n    exit 1\n}\nelse\n{\n    exit 2\n}\nexit 0\n", 4),
    "if_without_else": ("bool b{true}\ni32 mut a{1}\nif b\n{\n    a := 5\n}\nexit a\n", 3),
    "slot_declared_in_both_arms": (
        "bool b{true}\nif b\n{\n    i32 t{1}\n    exit t\n}\nelse\n{\n    i64 u{2}\n    exit u\n}\nexit 0\n",
        4,
    ),
}


def generate(source):
    tree = Parser(lex(source.encode())).parse_program()
    SemanticChecker().check(tree)
    return CodeGen().generate(tree)


@pytest.mark.parametrize("name", BLOCK_PROGRAMS)
def test_generated_ir_is_valid(name):
    source, _ = BLOCK_PROGRAMS[name]
    llvm.parse_assembly(str(generate(source))).verify()


@pytest.mark.parametrize("name", BLOCK_PROGRAMS)
def test_every_block_ends_in_exactly_one_terminator(name):
    source, _ = BLOCK_PROGRAMS[name]
    for block in generate(source).get_global("main").blocks:
        terminators = [i for i in block.instructions if isinstance(i, ir.instructions.Terminator)]
        assert len(terminators) == 1, block.name
        assert block.instructions[-1] is terminators[0], block.name


@pytest.mark.parametrize("name", BLOCK_PROGRAMS)
def test_every_alloca_is_in_the_entry_block_before_other_instructions(name):
    source, _ = BLOCK_PROGRAMS[name]
    blocks = generate(source).get_global("main").blocks
    for block in blocks[1:]:
        assert not [i for i in block.instructions if isinstance(i, ir.AllocaInstr)], block.name
    kinds = [isinstance(i, ir.AllocaInstr) for i in blocks[0].instructions]
    assert kinds == sorted(kinds, reverse=True)


@pytest.mark.parametrize("name", BLOCK_PROGRAMS)
def test_block_count(name):
    source, expected = BLOCK_PROGRAMS[name]
    assert len(generate(source).get_global("main").blocks) == expected


def test_shadowed_variables_get_three_separate_slots():
    source, _ = BLOCK_PROGRAMS["nested_warm_up"]
    entry = generate(source).get_global("main").blocks[0]
    slots = [i for i in entry.instructions if isinstance(i, ir.AllocaInstr)]
    assert [str(s.allocated_type) for s in slots] == ["i32", "i1", "i64"]
