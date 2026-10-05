from llvmlite import ir

from src.ast_nodes import ProgramNode, DeclNode, ExitNode, VarNode, ConstNode
from src.codegen import CodeGen


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
