from src.lexer import CompileError
from src.ast_nodes import ConstNode

I32_MAX = 2 ** 31 - 1
I64_MAX = 2 ** 63 - 1

BUILTIN_TYPES = ("i32", "i64", "bool")
INTEGER_TYPES = ("i32", "i64")
ARITHMETIC_OPS = ("+", "-", "*")
COMPARISON_OPS = ("==", "!=")


def error_at(node, message):
    return CompileError(f"line {node.line}:{node.col}: {message}")


class SemanticChecker:
    def __init__(self):
        self.scopes = []  # frames, innermost last: name -> DeclNode
        self.structs = {}  # name -> StructNode
        self.functions = {}  # name -> FnNode
        self.current_function = None

    def check(self, program):
        program.accept(self)
        return program

    def lookup(self, node, name):
        for frame in reversed(self.scopes):
            if name in frame:
                return frame[name]
        raise error_at(node, f"variable '{name}' is used before its declaration")

    def visit_program(self, node):
        for struct in node.structs:
            struct.accept(self)
        for function in node.functions:
            self.declare_function(function)
        for function in node.functions:
            function.accept(self)
        self.scopes.append({})
        for statement in node.statements:
            statement.accept(self)
        node.exit.accept(self)
        self.scopes.pop()

    def visit_block(self, node):
        self.scopes.append({})
        for statement in node.statements:
            statement.accept(self)
        if node.exit:
            node.exit.accept(self)
        self.scopes.pop()

    def visit_if(self, node):
        condition = node.condition.accept(self)
        if condition != "bool":
            raise error_at(node, f"the condition of 'if' must be bool, got {condition}")
        node.then_block.accept(self)
        if node.else_block:
            node.else_block.accept(self)

    def visit_while(self, node):
        condition = node.condition.accept(self)
        if condition != "bool":
            raise error_at(node, f"the condition of 'while' must be bool, got {condition}")
        node.body.accept(self)

    def check_known_type(self, type_name, pos, owner=None):
        if type_name in BUILTIN_TYPES or type_name in self.structs:
            return
        line, col = pos
        if type_name == owner:
            raise CompileError(f"line {line}:{col}: struct '{owner}' cannot contain itself")
        raise CompileError(f"line {line}:{col}: unknown type '{type_name}'")

    def first_const_field(self, type_name):
        for field in self.structs[type_name].fields:
            if not field.mutable:
                return field.name
            if field.type_name in self.structs:
                inner = self.first_const_field(field.type_name)
                if inner:
                    return f"{field.name}.{inner}"
        return None

    def check_value_count(self, node, struct):
        if len(node.values) != len(struct.fields):
            line, col = node.brace_pos
            given = len(node.values)
            verb = "value is" if given == 1 else "values are"
            raise CompileError(
                f"line {line}:{col}: struct '{struct.name}' has {len(struct.fields)} fields, "
                f"but {given} {verb} given in {{}}"
            )

    def declare_function(self, node):
        if node.name in self.functions:
            raise error_at(node, f"function '{node.name}' is already declared")
        seen = set()
        for param in node.params:
            if param.name in seen:
                raise error_at(param, f"duplicate parameter '{param.name}' in function '{node.name}'")
            seen.add(param.name)
            self.check_known_type(param.type_name, param.type_pos)
        self.check_known_type(node.result_type, node.result_pos)
        self.functions[node.name] = node

    def visit_fn(self, node):
        saved = self.scopes, self.current_function
        self.scopes = [{param.name: param for param in node.params}]
        self.current_function = node
        node.body.accept(self)
        self.scopes, self.current_function = saved

    def visit_call(self, node):
        function = self.functions.get(node.name)
        if function is None:
            raise error_at(node, f"unknown function '{node.name}'")
        if len(node.args) != len(function.params):
            raise error_at(
                node,
                f"function '{node.name}' takes {len(function.params)} arguments, got {len(node.args)}",
            )
        for arg, param in zip(node.args, function.params):
            arg.accept(self)
            self.check_assignable(arg, param.type_name, arg, f"pass argument to parameter '{param.name}'")
        node.function = function
        node.type = function.result_type
        return node.type

    def visit_struct(self, node):
        if node.name in self.structs:
            raise error_at(node, f"struct '{node.name}' is already declared")
        seen = set()
        for index, field in enumerate(node.fields):
            if field.name in seen:
                raise error_at(field, f"duplicate field '{field.name}' in struct '{node.name}'")
            seen.add(field.name)
            self.check_known_type(field.type_name, field.type_pos, owner=node.name)
            field.index = index
        self.structs[node.name] = node

    def visit_object_decl(self, node):
        if node.name in self.scopes[-1]:
            where = " in this block" if len(self.scopes) > 1 else ""
            raise error_at(node, f"variable '{node.name}' is already declared{where}")
        self.check_known_type(node.type_name, node.type_pos)
        struct = self.structs[node.type_name]
        node.struct = struct
        if len(node.values) != 1:
            self.check_value_count(node, struct)
        for value in node.values:
            value.accept(self)
        node.copy = len(node.values) == 1 and node.values[0].type == node.type_name
        if not node.copy:
            self.check_value_count(node, struct)
            for field, value in zip(struct.fields, node.values):
                self.check_assignable(value, field.type_name, value, f"initialise field '{field.name}'")
        self.scopes[-1][node.name] = node

    def visit_decl(self, node):
        if node.name in self.scopes[-1]:
            where = " in this block" if len(self.scopes) > 1 else ""
            raise error_at(node, f"variable '{node.name}' is already declared{where}")
        node.init.accept(self)
        self.check_assignable(node.init, node.type_name, node, f"initialise '{node.name}'")
        self.scopes[-1][node.name] = node

    def visit_assign(self, node):
        decl = self.lookup(node, node.name)
        if not decl.mutable:
            raise error_at(node, f"cannot assign to '{node.name}': it is not mut")
        if decl.type_name not in BUILTIN_TYPES:
            const_field = self.first_const_field(decl.type_name)
            if const_field:
                raise error_at(node, f"cannot assign to '{node.name}': field '{const_field}' is not mut")
        node.decl = decl
        node.value.accept(self)
        self.check_assignable(node.value, decl.type_name, node, f"assign to '{node.name}'")

    def visit_exit(self, node):
        value = node.value.accept(self)
        node.function = self.current_function
        if self.current_function is None:
            if value not in BUILTIN_TYPES:
                raise error_at(node, f"exit needs i32, i64 or bool, got {value}")
            return
        want = self.current_function.result_type
        if value != want and not (value == "i32" and want == "i64"):
            raise error_at(
                node,
                f"function '{self.current_function.name}' returns {want}, but exit has a value of type {value}",
            )

    def visit_binop(self, node):
        left, right = node.left.accept(self), node.right.accept(self)
        if node.op in ARITHMETIC_OPS:
            for operand in (left, right):
                if operand not in INTEGER_TYPES:
                    raise error_at(node, f"cannot apply '{node.op}' to {operand}")
            node.type = "i64" if "i64" in (left, right) else "i32"
        else:
            both_bool = left == right == "bool"
            both_int = left in ("i32", "i64") and right in ("i32", "i64")
            if not (both_bool or both_int):
                raise error_at(node, f"cannot compare {left} with {right}")
            node.type = "bool"
        return node.type

    def visit_not(self, node):
        operand = node.operand.accept(self)
        if operand != "bool":
            raise error_at(node, f"cannot apply '!' to {operand}")
        node.type = "bool"
        return node.type

    def visit_var(self, node):
        node.decl = self.lookup(node, node.name)
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
