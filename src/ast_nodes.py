class Node:
    def __init__(self, line, col):
        self.line = line
        self.col = col

    def label(self):
        raise NotImplementedError

    def children(self):
        return []

    def accept(self, visitor):
        raise NotImplementedError

    def dump(self, depth=0):
        rows = ["  " * depth + self.label()]
        for child in self.children():
            rows.append(child.dump(depth + 1))
        return "\n".join(rows)


class ProgramNode(Node):
    def __init__(self, line, col, statements, exit, structs=None, functions=None):
        super().__init__(line, col)
        self.structs = structs or []
        self.functions = functions or []
        self.statements = statements
        self.exit = exit

    def label(self):
        return "Program"

    def children(self):
        return [*self.structs, *self.functions, *self.statements, self.exit]

    def accept(self, visitor):
        return visitor.visit_program(self)


class FieldNode(Node):
    def __init__(self, line, col, name, type_name, mutable, type_pos):
        super().__init__(line, col)
        self.name = name
        self.type_name = type_name
        self.mutable = mutable
        self.type_pos = type_pos

    def label(self):
        return f"Member {self.name} {self.type_name} {'mut' if self.mutable else 'const'}"


class StructNode(Node):
    def __init__(self, line, col, name, fields, methods=None):
        super().__init__(line, col)
        self.name = name
        self.fields = fields
        self.methods = methods or []

    def label(self):
        return f"Struct {self.name}"

    def children(self):
        return [*self.fields, *self.methods]

    def accept(self, visitor):
        return visitor.visit_struct(self)


class ParamNode(Node):
    mutable = False

    def __init__(self, line, col, name, type_name, type_pos):
        super().__init__(line, col)
        self.name = name
        self.type_name = type_name
        self.type_pos = type_pos

    def label(self):
        return f"Param {self.name} {self.type_name}"


class FnNode(Node):
    def __init__(self, line, col, name, params, result_type, result_pos, body):
        super().__init__(line, col)
        self.name = name
        self.params = params
        self.result_type = result_type
        self.result_pos = result_pos
        self.body = body

    def label(self):
        return f"Fn {self.name} {self.result_type}"

    def children(self):
        return [*self.params, self.body]

    def accept(self, visitor):
        return visitor.visit_fn(self)


class MemberFnNode(FnNode):
    def label(self):
        return f"MemberFn {self.name} -> {self.result_type}"

    def accept(self, visitor):
        return visitor.visit_member_fn(self)


class StmtNode(Node):
    pass


class DeclNode(StmtNode):
    def __init__(self, line, col, name, type_name, mutable, init):
        super().__init__(line, col)
        self.name = name
        self.type_name = type_name
        self.mutable = mutable
        self.init = init

    def label(self):
        return f"Decl {self.name} {self.type_name} {'mut' if self.mutable else 'const'}"

    def children(self):
        return [self.init]

    def accept(self, visitor):
        return visitor.visit_decl(self)


class IfNode(StmtNode):
    def __init__(self, line, col, condition, then_block, else_block):
        super().__init__(line, col)
        self.condition = condition
        self.then_block = then_block
        self.else_block = else_block

    def label(self):
        return "If"

    def children(self):
        blocks = [self.then_block] if self.else_block is None else [self.then_block, self.else_block]
        return [self.condition, *blocks]

    def accept(self, visitor):
        return visitor.visit_if(self)


class WhileNode(StmtNode):
    def __init__(self, line, col, condition, body):
        super().__init__(line, col)
        self.condition = condition
        self.body = body

    def label(self):
        return "While"

    def children(self):
        return [self.condition, self.body]

    def accept(self, visitor):
        return visitor.visit_while(self)


class BlockNode(Node):
    def __init__(self, line, col, statements, exit):
        super().__init__(line, col)
        self.statements = statements
        self.exit = exit

    def label(self):
        return "Block"

    def children(self):
        return [*self.statements] if self.exit is None else [*self.statements, self.exit]

    def accept(self, visitor):
        return visitor.visit_block(self)


class ObjectDeclNode(StmtNode):
    def __init__(self, line, col, name, type_name, mutable, values, type_pos, brace_pos):
        super().__init__(line, col)
        self.name = name
        self.type_name = type_name
        self.mutable = mutable
        self.values = values
        self.type_pos = type_pos
        self.brace_pos = brace_pos

    def label(self):
        return f"Decl {self.name} {self.type_name} {'mut' if self.mutable else 'const'}"

    def children(self):
        return self.values

    def accept(self, visitor):
        return visitor.visit_object_decl(self)


class FieldAssignNode(StmtNode):
    def __init__(self, line, col, target, value):
        super().__init__(line, col)
        self.target = target
        self.value = value

    def label(self):
        return f"Assign {self.target.path}"

    def children(self):
        return [self.value]

    def accept(self, visitor):
        return visitor.visit_field_assign(self)


class PrintNode(StmtNode):
    def __init__(self, line, col, arg):
        super().__init__(line, col)
        self.arg = arg

    def label(self):
        return "Print"

    def children(self):
        return [self.arg]

    def accept(self, visitor):
        return visitor.visit_print(self)


class AssignNode(StmtNode):
    decl = None
    field = None

    def __init__(self, line, col, name, value):
        super().__init__(line, col)
        self.name = name
        self.value = value

    def label(self):
        return f"Assign {self.name}"

    def children(self):
        return [self.value]

    def accept(self, visitor):
        return visitor.visit_assign(self)


class ExitNode(Node):
    def __init__(self, line, col, value):
        super().__init__(line, col)
        self.value = value
        self.function = None

    def label(self):
        return "Exit"

    def children(self):
        return [self.value]

    def accept(self, visitor):
        return visitor.visit_exit(self)


class ExprNode(Node):
    pass


class BinOpNode(ExprNode):
    def __init__(self, line, col, op, left, right):
        super().__init__(line, col)
        self.op = op
        self.left = left
        self.right = right

    def label(self):
        return f"BinOp {self.op}"

    def children(self):
        return [self.left, self.right]

    def accept(self, visitor):
        return visitor.visit_binop(self)


class NotNode(ExprNode):
    def __init__(self, line, col, operand):
        super().__init__(line, col)
        self.operand = operand

    def label(self):
        return "Not"

    def children(self):
        return [self.operand]

    def accept(self, visitor):
        return visitor.visit_not(self)


class StringNode(ExprNode):
    def __init__(self, line, col, text):
        super().__init__(line, col)
        self.text = text

    def label(self):
        return f'String "{self.text}"'

    def accept(self, visitor):
        return visitor.visit_string(self)


class ReadNode(ExprNode):
    def label(self):
        return "Read"

    def accept(self, visitor):
        return visitor.visit_read(self)


class CallNode(ExprNode):
    this_call = False

    def __init__(self, line, col, name, args):
        super().__init__(line, col)
        self.name = name
        self.args = args

    def label(self):
        return f"Call {self.name}"

    def children(self):
        return self.args

    def accept(self, visitor):
        return visitor.visit_call(self)


class InitNode(ExprNode):
    def __init__(self, line, col, values):
        super().__init__(line, col)
        self.values = values

    def label(self):
        return "Init"

    def children(self):
        return self.values

    def accept(self, visitor):
        return visitor.visit_init(self)


class MemberCallNode(ExprNode):
    def __init__(self, line, col, obj, name, args):
        super().__init__(line, col)
        self.obj = obj
        self.name = name
        self.args = args

    def label(self):
        return f"MemberCall {self.name}"

    def children(self):
        return [self.obj, *self.args]

    def accept(self, visitor):
        return visitor.visit_member_call(self)


class MemberNode(ExprNode):
    decl = None
    field = None

    def __init__(self, line, col, name, links):
        super().__init__(line, col)
        self.name = name
        self.links = links

    @property
    def path(self):
        return self.name + "".join(f".{link[0]}" for link in self.links)

    def label(self):
        return f"Field {self.path}"

    def accept(self, visitor):
        return visitor.visit_member(self)


class VarNode(ExprNode):
    decl = None
    field = None

    def __init__(self, line, col, name):
        super().__init__(line, col)
        self.name = name

    def label(self):
        return f"Var {self.name}"

    def accept(self, visitor):
        return visitor.visit_var(self)


class ConstNode(ExprNode):
    def __init__(self, line, col, value):
        super().__init__(line, col)
        self.value = value

    def label(self):
        return f"Const {self.value}"

    def accept(self, visitor):
        return visitor.visit_const(self)


class BoolNode(ExprNode):
    def __init__(self, line, col, value):
        super().__init__(line, col)
        self.value = value

    def label(self):
        return f"Bool {'true' if self.value else 'false'}"

    def accept(self, visitor):
        return visitor.visit_bool(self)
