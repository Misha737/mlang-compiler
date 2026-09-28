from llvmlite import ir
import llvmlite.binding as llvm
from src.lexer import CompileError

I32 = ir.IntType(32)
I8 = ir.IntType(8)
I8_PTR = ir.PointerType(I8)

OPERATIONS = {"+": "add", "-": "sub", "*": "mul"}


def error_at(node, message):
    return CompileError(f"line {node.line}:{node.col}: {message}")


class CodeGen:
    def __init__(self):
        self.module = ir.Module(name="p1")
        self.module.triple = llvm.get_default_triple()
        main = ir.Function(self.module, ir.FunctionType(I32, []), name="main")
        self.builder = ir.IRBuilder(main.append_basic_block("entry"))
        self.printf = ir.Function(self.module, ir.FunctionType(I32, [I8_PTR], var_arg=True), name="printf")

        text = b"Program exit with result %d\n\0"
        self.fmt = ir.GlobalVariable(self.module, ir.ArrayType(I8, len(text)), name="fmt")
        self.fmt.linkage = "private"
        self.fmt.global_constant = True
        self.fmt.initializer = ir.Constant(ir.ArrayType(I8, len(text)), bytearray(text))

        self.symbols = {}

    def generate(self, program):
        program.accept(self)
        return self.module

    def visit_program(self, node):
        for statement in node.statements:
            statement.accept(self)
        node.exit.accept(self)

    def visit_decl(self, node):
        if node.name in self.symbols:
            raise error_at(node, f"variable '{node.name}' is already declared")
        value = node.init.accept(self)
        alloca = self.builder.alloca(I32, name=node.name)
        self.builder.store(value, alloca)
        self.symbols[node.name] = (alloca, node.mutable)

    def visit_assign(self, node):
        if node.name not in self.symbols:
            raise error_at(node, f"variable '{node.name}' is used before its declaration")
        alloca, mutable = self.symbols[node.name]
        if not mutable:
            raise error_at(node, f"cannot assign to '{node.name}': it is not mut")
        value = node.value.accept(self)
        self.builder.store(value, alloca)

    def visit_exit(self, node):
        value = node.value.accept(self)
        self.builder.call(self.printf, [self.builder.bitcast(self.fmt, I8_PTR), value])
        self.builder.ret(ir.Constant(I32, 0))

    def visit_binop(self, node):
        left = node.left.accept(self)
        right = node.right.accept(self)
        return getattr(self.builder, OPERATIONS[node.op])(left, right)

    def visit_var(self, node):
        if node.name not in self.symbols:
            raise error_at(node, f"variable '{node.name}' is used before its declaration")
        alloca, _ = self.symbols[node.name]
        return self.builder.load(alloca)

    def visit_const(self, node):
        return ir.Constant(I32, node.value)
