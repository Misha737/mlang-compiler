from src.lexer import CompileError
from src.ast_nodes import ConstNode

I32_MAX = 2 ** 31 - 1
I64_MAX = 2 ** 63 - 1

ARITHMETIC_OPS = ("+", "-", "*")
COMPARISON_OPS = ("==", "!=")


def error_at(node, message):
    return CompileError(f"line {node.line}:{node.col}: {message}")


class SemanticChecker:
    def __init__(self):
        self.symbols = {}  # name -> DeclNode

    def check(self, program):
        program.accept(self)
        return program

    def visit_program(self, node):
        for statement in node.statements:
            statement.accept(self)
        node.exit.accept(self)

    def visit_decl(self, node):
        if node.name in self.symbols:
            raise error_at(node, f"variable '{node.name}' is already declared")
        node.init.accept(self)
        self.check_assignable(node.init, node.type_name, node, f"initialise '{node.name}'")
        self.symbols[node.name] = node

    def visit_assign(self, node):
        if node.name not in self.symbols:
            raise error_at(node, f"variable '{node.name}' is used before its declaration")
        decl = self.symbols[node.name]
        if not decl.mutable:
            raise error_at(node, f"cannot assign to '{node.name}': it is not mut")
        node.decl = decl
        node.value.accept(self)
        self.check_assignable(node.value, decl.type_name, node, f"assign to '{node.name}'")

    def visit_exit(self, node):
        node.value.accept(self)

    def visit_binop(self, node):
        left, right = node.left.accept(self), node.right.accept(self)
        if node.op in ARITHMETIC_OPS:
            if "bool" in (left, right):
                raise error_at(node, f"cannot apply '{node.op}' to bool")
            node.type = "i64" if "i64" in (left, right) else "i32"
        else:
            both_bool = left == right == "bool"
            both_int = left in ("i32", "i64") and right in ("i32", "i64")
            if not (both_bool or both_int):
                raise error_at(node, f"cannot compare {left} with {right}")
            node.type = "bool"
        return node.type

    def visit_var(self, node):
        if node.name not in self.symbols:
            raise error_at(node, f"variable '{node.name}' is used before its declaration")
        node.decl = self.symbols[node.name]
        node.type = node.decl.type_name
        return node.type

    def visit_const(self, node):
        if node.value <= I32_MAX:
            node.type = "i32"
        elif node.value <= I64_MAX:
            node.type = "i64"
        else:
            raise error_at(node, f"constant {node.value} does not fit in i64")
        return node.type

    def visit_bool(self, node):
        node.type = "bool"
        return node.type

    def check_assignable(self, expr, want, at, what):
        have = expr.type
        if have == want or (have == "i32" and want == "i64"):
            return
        if want == "i32" and have == "i64" and isinstance(expr, ConstNode):
            raise error_at(expr, f"constant {expr.value} does not fit in i32")
        raise error_at(at, f"cannot {what} of type {want} with a value of type {have}")
