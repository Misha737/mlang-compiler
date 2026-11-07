from src.ast_nodes import CallNode, MemberCallNode, ReadNode
from src.pruner import Pruner

def has_call_or_read(node):
    if isinstance(node, (CallNode, MemberCallNode, ReadNode)):
        return True
    return any(has_call_or_read(child) for child in node.children())


class UseCounter:
    def __init__(self):
        self.reads = {}

    def read(self, decl):
        if decl is not None:
            self.reads[id(decl)] = self.reads.get(id(decl), 0) + 1

    def visit_all(self, nodes):
        for node in nodes:
            node.accept(self)

    def visit_program(self, node):
        self.visit_all(node.structs)
        self.visit_all(node.functions)
        self.visit_all(node.statements)
        node.exit.accept(self)

    def visit_struct(self, node):
        self.visit_all(node.methods)

    def visit_fn(self, node):
        node.body.accept(self)

    def visit_member_fn(self, node):
        node.body.accept(self)

    def visit_lambda(self, node):
        self.visit_all(node.decl.values)
        node.body.accept(self)

    def visit_block(self, node):
        self.visit_all(node.statements)
        if node.exit is not None:
            node.exit.accept(self)

    def visit_if(self, node):
        node.condition.accept(self)
        node.then_block.accept(self)
        if node.else_block is not None:
            node.else_block.accept(self)

    def visit_while(self, node):
        node.condition.accept(self)
        node.body.accept(self)

    def visit_decl(self, node):
        self.reads.setdefault(id(node), 0)
        if has_call_or_read(node.init):
            self.read(node)
        node.init.accept(self)

    def visit_object_decl(self, node):
        self.reads.setdefault(id(node), 0)
        if any(has_call_or_read(value) for value in node.values):
            self.read(node)
        self.visit_all(node.values)

    def visit_assign(self, node):
        if has_call_or_read(node.value):
            self.read(node.decl)
        node.value.accept(self)

    def visit_field_assign(self, node):
        if has_call_or_read(node.value):
            self.read(node.target.decl)
        node.value.accept(self)

    def visit_print(self, node):
        node.arg.accept(self)

    def visit_exit(self, node):
        node.value.accept(self)

    def visit_binop(self, node):
        node.left.accept(self)
        node.right.accept(self)

    def visit_not(self, node):
        node.operand.accept(self)

    def visit_call(self, node):
        if node.rewritten is not None:
            node.rewritten.accept(self)
        else:
            self.visit_all(node.args)

    def visit_member_call(self, node):
        if node.rewritten is not None:
            node.rewritten.accept(self)
        else:
            node.obj.accept(self)
            self.visit_all(node.args)

    def visit_init(self, node):
        self.visit_all(node.values)

    def visit_field_of(self, node):
        node.base.accept(self)

    def visit_member(self, node):
        self.read(node.decl)

    def visit_var(self, node):
        self.read(node.decl)

    def visit_const(self, node):
        pass

    def visit_bool(self, node):
        pass

    def visit_string(self, node):
        pass

    def visit_read(self, node):
        pass


def remove_unused(tree):
 while True:
    counter = UseCounter();
    tree.accept(counter)
    dead = {d for d, k in counter.reads.items() if k == 0}
    if not dead: return tree
    Pruner(dead).prune(tree)
