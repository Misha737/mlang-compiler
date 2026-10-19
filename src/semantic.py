from src.lexer import CompileError
from src.ast_nodes import ConstNode, InitNode, MemberNode, StringNode, VarNode

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
        self.current_struct = None
        self.member_functions = []
        self.call_sites = []

    def check(self, program):
        program.accept(self)
        return program

    def find_name(self, name):
        for frame in reversed(self.scopes):
            if name in frame:
                return frame[name], None
        if self.current_struct is not None:
            for field in self.current_struct.fields:
                if field.name == name:
                    return None, field
        return None

    def lookup(self, node, name):
        found = self.find_name(name)
        if found is None:
            raise error_at(node, f"variable '{name}' is used before its declaration")
        return found

    def find_method(self, struct, name):
        return next((method for method in struct.methods if method.name == name), None)

    def note_field_write(self):
        self.current_function.assigns_field = True

    def visit_program(self, node):
        for struct in node.structs:
            struct.accept(self)
        for function in node.functions:
            self.declare_function(function)
        for struct in node.structs:
            for method in struct.methods:
                method.accept(self)
        for function in node.functions:
            function.accept(self)
        self.scopes.append({})
        for statement in node.statements:
            statement.accept(self)
        node.exit.accept(self)
        self.scopes.pop()
        self.finish_member_calls()

    def finish_member_calls(self):
        changed = True
        while changed:
            changed = False
            for method in self.member_functions:
                if not method.mutating and (method.assigns_field or any(c.mutating for c in method.this_calls)):
                    method.mutating = True
                    changed = True
        for node, obj, method in self.call_sites:
            if method.mutating:
                self.check_mutable_chain(node, obj)

    def check_mutable_chain(self, node, obj):
        path = obj.path if isinstance(obj, MemberNode) else obj.name
        head = f"cannot call mutating function '{node.name}'"
        if obj.decl is not None and not obj.decl.mutable:
            raise error_at(obj, f"{head} on '{path}': '{obj.name}' is not mut")
        if obj.field is not None and not obj.field.mutable:
            raise error_at(obj, f"{head} through '{path}': field '{obj.name}' is not mut")
        if isinstance(obj, MemberNode):
            for field, (_, line, col) in zip(obj.fields, obj.links):
                if not field.mutable:
                    raise CompileError(f"line {line}:{col}: {head} through '{path}': field '{field.name}' is not mut")

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

    def check_value_count(self, struct, values, brace_pos):
        if len(values) != len(struct.fields):
            line, col = brace_pos
            given = len(values)
            verb = "value is" if given == 1 else "values are"
            raise CompileError(
                f"line {line}:{col}: struct '{struct.name}' has {len(struct.fields)} fields, "
                f"but {given} {verb} given in {{}}"
            )

    def check_signature(self, node):
        seen = set()
        for param in node.params:
            if param.name in seen:
                raise error_at(param, f"duplicate parameter '{param.name}' in function '{node.name}'")
            seen.add(param.name)
            self.check_known_type(param.type_name, param.type_pos)
        self.check_known_type(node.result_type, node.result_pos)

    def declare_function(self, node):
        if node.name in self.functions:
            raise error_at(node, f"function '{node.name}' is already declared")
        self.check_signature(node)
        self.functions[node.name] = node

    def visit_fn(self, node):
        saved = self.scopes, self.current_function
        self.scopes = [{param.name: param for param in node.params}]
        self.current_function = node
        node.body.accept(self)
        self.scopes, self.current_function = saved

    def visit_member_fn(self, node):
        saved = self.scopes, self.current_function, self.current_struct
        self.scopes = [{param.name: param for param in node.params}]
        self.current_function = node
        self.current_struct = node.owner
        node.body.accept(self)
        self.scopes, self.current_function, self.current_struct = saved

    def check_arguments(self, node, function, label):
        if len(node.args) != len(function.params):
            raise error_at(
                node,
                f"{label} '{node.name}' takes {len(function.params)} arguments, got {len(node.args)}",
            )
        for arg, param in zip(node.args, function.params):
            arg.accept(self)
            self.check_assignable(arg, param.type_name, arg, f"pass argument to parameter '{param.name}'")

    def visit_call(self, node):
        method = self.find_method(self.current_struct, node.name) if self.current_struct is not None else None
        if method is not None:
            self.check_arguments(node, method, "member function")
            node.this_call = True
            self.current_function.this_calls.append(method)
            node.function = method
            node.type = method.result_type
            return node.type
        function = self.functions.get(node.name)
        if function is None:
            raise error_at(node, f"unknown function '{node.name}'")
        self.check_arguments(node, function, "function")
        node.function = function
        node.type = function.result_type
        return node.type

    def visit_field_of(self, node):
        type_name = node.base.accept(self)
        fields = []
        for index, (name, line, col) in enumerate(node.links):
            if type_name not in self.structs:
                if index == 0:
                    line, col = node.line, node.col
                    raise CompileError(
                        f"line {line}:{col}: cannot access field '{name}': the call returns {type_name}, which is not a struct"
                    )
                raise CompileError(f"line {line}:{col}: cannot access field '{name}': the value has type {type_name}, which is not a struct")
            field = next((f for f in self.structs[type_name].fields if f.name == name), None)
            if field is None:
                raise CompileError(f"line {line}:{col}: struct '{type_name}' has no field '{name}'")
            fields.append(field)
            type_name = field.type_name
        node.fields, node.type = fields, type_name
        return node.type

    def visit_member_call(self, node):
        obj = node.obj
        is_place = isinstance(obj, (VarNode, MemberNode))
        if isinstance(obj, VarNode) and self.find_name(obj.name) is None and obj.name in self.structs:
            raise error_at(obj, f"'{obj.name}' is a type: member functions are called on objects")
        type_name = obj.accept(self)
        if type_name not in self.structs:
            if is_place:
                raise error_at(node, f"type {type_name} has no member functions")
            line, col = node.dot_pos
            raise CompileError(f"line {line}:{col}: type {type_name} has no member functions")
        method = self.find_method(self.structs[type_name], node.name)
        if method is None:
            raise error_at(node, f"struct '{type_name}' has no member function '{node.name}'")
        self.check_arguments(node, method, "member function")
        if is_place:
            if obj.field is not None:
                self.current_function.this_calls.append(method)
            self.call_sites.append((node, obj, method))
        node.method = method
        node.type = method.result_type
        return node.type

    def resolve_chain(self, node):
        decl, root_field = self.lookup(node, node.name)
        root = decl if decl is not None else root_field
        type_name = root.type_name
        path = node.name
        fields = []
        for name, line, col in node.links:
            if type_name not in self.structs:
                raise CompileError(
                    f"line {line}:{col}: cannot access field '{name}': '{path}' has type {type_name}, which is not a struct"
                )
            field = next((f for f in self.structs[type_name].fields if f.name == name), None)
            if field is None:
                raise CompileError(f"line {line}:{col}: struct '{type_name}' has no field '{name}'")
            fields.append(field)
            type_name = field.type_name
            path += f".{name}"
        node.decl, node.field, node.fields, node.type = decl, root_field, fields, type_name
        return node.type

    def visit_member(self, node):
        return self.resolve_chain(node)

    def visit_field_assign(self, node):
        target = node.target
        type_name = self.resolve_chain(target)
        root = target.decl if target.decl is not None else target.field
        if not root.mutable:
            raise error_at(target, f"cannot assign to '{target.path}': '{target.name}' is not mut")
        if target.field is not None:
            self.note_field_write()
        for field, (_, line, col) in zip(target.fields, target.links):
            if not field.mutable:
                raise CompileError(f"line {line}:{col}: cannot assign to '{target.path}': field '{field.name}' is not mut")
        if type_name not in BUILTIN_TYPES:
            const_field = self.first_const_field(type_name)
            if const_field:
                raise error_at(node, f"cannot assign to '{target.path}': field '{const_field}' is not mut")
        node.value.accept(self)
        self.check_assignable(node.value, type_name, node, f"assign to '{target.path}'")

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
        field_names = {field.name for field in node.fields}
        method_names = set()
        for method in node.methods:
            if method.name in field_names:
                raise error_at(method, f"member function '{method.name}' has the same name as a field of struct '{node.name}'")
            if method.name in method_names:
                raise error_at(method, f"member function '{method.name}' is already declared in struct '{node.name}'")
            method_names.add(method.name)
            self.check_signature(method)
            method.owner = node
            method.mutating = False
            method.assigns_field = False
            method.this_calls = []
            self.member_functions.append(method)

    def visit_object_decl(self, node):
        if node.name in self.scopes[-1]:
            where = " in this block" if len(self.scopes) > 1 else ""
            raise error_at(node, f"variable '{node.name}' is already declared{where}")
        self.check_known_type(node.type_name, node.type_pos)
        struct = self.structs[node.type_name]
        node.struct = struct
        node.copy = self.check_initialiser(struct, node.values, node.brace_pos)
        self.scopes[-1][node.name] = node

    def check_initialiser(self, struct, values, brace_pos):
        if len(values) != 1:
            self.check_value_count(struct, values, brace_pos)
        for value in values:
            if not isinstance(value, InitNode):
                value.accept(self)
        if len(values) == 1 and not isinstance(values[0], InitNode) and values[0].type == struct.name:
            return True
        self.check_value_count(struct, values, brace_pos)
        for field, value in zip(struct.fields, values):
            if isinstance(value, InitNode):
                self.check_nested_init(value, field)
            else:
                self.check_assignable(value, field.type_name, value, f"initialise field '{field.name}'")
        return False

    def check_nested_init(self, node, field):
        if field.type_name not in self.structs:
            raise error_at(node, f"field '{field.name}' has type {field.type_name}, which cannot be initialised with {{}}")
        node.struct = self.structs[field.type_name]
        node.type = field.type_name
        node.copy = self.check_initialiser(node.struct, node.values, (node.line, node.col))

    def visit_decl(self, node):
        if node.name in self.scopes[-1]:
            where = " in this block" if len(self.scopes) > 1 else ""
            raise error_at(node, f"variable '{node.name}' is already declared{where}")
        node.init.accept(self)
        self.check_assignable(node.init, node.type_name, node, f"initialise '{node.name}'")
        self.scopes[-1][node.name] = node

    def visit_assign(self, node):
        decl, field = self.lookup(node, node.name)
        target = decl if decl is not None else field
        if not target.mutable:
            raise error_at(node, f"cannot assign to '{node.name}': it is not mut")
        if target.type_name not in BUILTIN_TYPES:
            const_field = self.first_const_field(target.type_name)
            if const_field:
                raise error_at(node, f"cannot assign to '{node.name}': field '{const_field}' is not mut")
        node.decl, node.field = decl, field
        node.target_type = target.type_name
        if field is not None:
            self.note_field_write()
        node.value.accept(self)
        self.check_assignable(node.value, target.type_name, node, f"assign to '{node.name}'")

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
        node.decl, node.field = self.lookup(node, node.name)
        node.type = (node.decl if node.decl is not None else node.field).type_name
        return node.type

    def visit_const(self, node):
        if node.value <= I32_MAX:
            node.type = "i32"
        elif node.value <= I64_MAX:
            node.type = "i64"
        else:
            raise error_at(node, f"constant {node.value} does not fit in i64")
        return node.type

    def visit_read(self, node):
        node.type = "i32"
        return node.type

    def visit_print(self, node):
        if not isinstance(node.arg, StringNode):
            node.arg.accept(self)

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
