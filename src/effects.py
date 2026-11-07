from src.ast_nodes import CallNode, LambdaNode, MemberCallNode, PrintNode, ReadNode, WhileNode


def callee(node):
    if isinstance(node, CallNode):
        if node.rewritten is not None:
            return node.rewritten.method
        return node.function
    if isinstance(node, MemberCallNode):
        if node.rewritten is not None:
            return node.rewritten.method
        return node.method
    return None


def has_effect(node, effects):
    if isinstance(node, ReadNode):
        return True
    target = callee(node)
    if target is not None and id(target) in effects:
        return True
    return any(has_effect(child, effects) for child in node.children())


def scan_body(node, found):
    if isinstance(node, (PrintNode, ReadNode, WhileNode)):
        found["direct"] = True
    target = callee(node)
    if target is not None:
        found["calls"].add(id(target))
    if isinstance(node, LambdaNode):
        return
    for child in node.children():
        scan_body(child, found)


def all_units(tree):
    units = list(tree.functions)
    for struct in [*tree.structs, *tree.lambda_structs]:
        units.extend(struct.methods)
    return units


def reaches(start, calls):
    seen = set()
    pending = list(calls[start])
    while pending:
        current = pending.pop()
        if current == start:
            return True
        if current in seen:
            continue
        seen.add(current)
        pending.extend(calls.get(current, ()))
    return False


def functions_with_effects(tree):
    units = all_units(tree)
    calls = {}
    effects = set()
    for unit in units:
        found = {"direct": False, "calls": set()}
        scan_body(unit.body, found)
        calls[id(unit)] = found["calls"]
        if found["direct"] or getattr(unit, "mutating", False):
            effects.add(id(unit))
    for unit in units:
        if reaches(id(unit), calls):
            effects.add(id(unit))
    changed = True
    while changed:
        changed = False
        for unit in units:
            if id(unit) not in effects and calls[id(unit)] & effects:
                effects.add(id(unit))
                changed = True
    return effects
