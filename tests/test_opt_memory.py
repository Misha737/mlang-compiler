import gc
import weakref

from src.lexer import lex
from src.parser import Parser
from src.semantic import SemanticChecker
from src.use_counter import remove_unused

DECLARATION = "i32 x{10}\ni32 y{x}\ni32 z{15}\nexit z\n"
FUNCTION = (
    "fn twice := (i32 a) -> i32\n{\n    i32 r{a + a}\n    exit r\n}\n"
    "fn unused := () -> i32\n{\n    exit twice(1)\n}\nexit 0\n"
)


def removed_node_is_freed(source, pick):
    tree = Parser(lex(source.encode())).parse_program()
    SemanticChecker().check(tree)
    reference = weakref.ref(pick(tree))
    gc.disable()
    try:
        remove_unused(tree)
        freed_at_once = reference() is None
        gc.collect()
        freed_after_collect = reference() is None
    finally:
        gc.enable()
    return freed_at_once, freed_after_collect


def test_removed_declaration_is_freed_by_reference_counting():
    assert removed_node_is_freed(DECLARATION, lambda tree: tree.statements[1]) == (True, True)


def test_removed_function_waits_for_the_cycle_collector():
    assert removed_node_is_freed(FUNCTION, lambda tree: tree.functions[1]) == (False, True)
