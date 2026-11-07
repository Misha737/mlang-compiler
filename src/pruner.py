from src.ast_nodes import Node


class Pruner:
    def __init__(self, dead):
        self.dead = dead

    def prune(self, tree):
        self.visit(tree)
        return tree

    def is_dead(self, node):
        binding = node.binding()
        return binding is not None and id(binding) in self.dead

    def visit(self, node):
        for items in vars(node).values():
            if isinstance(items, list) and items and all(isinstance(item, Node) for item in items):
                items[:] = [item for item in items if not self.is_dead(item)]
        for child in node.children():
            self.visit(child)
