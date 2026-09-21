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
    def __init__(self, line, col, statements, exit):
        super().__init__(line, col)
        self.statements = statements
        self.exit = exit

    def label(self):
        return "Program"

    def children(self):
        return [*self.statements, self.exit]

    def accept(self, visitor):
        return visitor.visit_program(self)


class StmtNode(Node):
    pass


class DeclNode(StmtNode):
    def __init__(self, line, col, name, mutable, init):
        super().__init__(line, col)
        self.name = name
        self.mutable = mutable
        self.init = init

    def label(self):
        return f"Decl {self.name} {'mut' if self.mutable else 'const'}"

    def children(self):
        return [self.init]

    def accept(self, visitor):
        return visitor.visit_decl(self)


class AssignNode(StmtNode):
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


class VarNode(ExprNode):
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
