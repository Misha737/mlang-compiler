from src.lexer import CompileError
from src.ast_nodes import (
    ProgramNode, DeclNode, AssignNode, ExitNode,
    BinOpNode, VarNode, ConstNode,
)

ARITHMETIC = ("+", "-", "*")

class Parser:
    def __init__(self, lines):
        self.lines = lines
        self.toks = []
        self.pos = 0

    def peek(self):
        return self.toks[self.pos] if self.pos < len(self.toks) else None

    def eat(self):
        tok = self.toks[self.pos]
        self.pos += 1
        return tok

    def at(self, kind, text=None):
        tok = self.peek()
        return tok is not None and tok.kind == kind and (text is None or tok.text == text)

    def expect(self, kind, what, text=None):
        if not self.at(kind, text):
            self.fail_expected(what)
        return self.eat()

    def fail_expected(self, what):
        tok = self.peek()
        if tok is None:
            line, col = self.end_of_line()
            raise CompileError(f"line {line}:{col}: expected {what}, found end of line")
        raise CompileError(f"line {tok.line}:{tok.col}: expected {what}, got '{tok.text}'")

    def end_of_line(self):
        last = self.toks[-1]
        return last.line, last.col + len(last.text)

    def parse_program(self):
        statements, exit_node, first = [], None, None
        for toks in self.lines:
            if not toks:
                continue
            self.toks, self.pos = toks, 0
            if first is None:
                first = toks[0]
            if exit_node is not None:
                raise CompileError(f"line {toks[0].line}:{toks[0].col}: code after exit is not allowed")
            if self.at("keyword", "exit"):
                exit_node = self.parse_exit()
            else:
                statements.append(self.parse_statement())
            self.expect_end_of_statement()
        if exit_node is None:
            line, col = self.end_of_line() if first is not None else (1, 1)
            raise CompileError(f"line {line}:{col}: program must end with exit")
        return ProgramNode(first.line, first.col, statements, exit_node)

    def expect_end_of_statement(self):
        tok = self.peek()
        if tok is not None:
            raise CompileError(f"line {tok.line}:{tok.col}: unexpected '{tok.text}' after the statement")

    def parse_statement(self):
        tok = self.peek()
        if self.at("keyword", "i32"):
            return self.parse_decl()
        if self.at("ident"):
            return self.parse_assign()
        raise CompileError(f"line {tok.line}:{tok.col}: cannot start a statement with '{tok.text}'")

    def parse_decl(self):
        self.eat()
        mutable = self.at("keyword", "mut")
        if mutable:
            self.eat()
        name = self.expect("ident", "a variable name")
        if not self.at("lbrace"):
            raise CompileError(f"line {name.line}:{name.col}: variable '{name.text}' needs an initializer in {{}}")
        self.eat()
        init = self.parse_value()
        self.expect("rbrace", "'}'")
        return DeclNode(name.line, name.col, name.text, mutable, init)

    def parse_assign(self):
        name = self.eat()
        self.expect("operator", f"':=' after '{name.text}'", ":=")
        value = self.parse_value()
        return AssignNode(name.line, name.col, name.text, value)

    def parse_exit(self):
        keyword = self.eat()
        return ExitNode(keyword.line, keyword.col, self.parse_operand())

    def parse_value(self):
        left = self.parse_operand()
        tok = self.peek()
        if tok is not None and tok.kind == "operator" and tok.text in ARITHMETIC:
            self.eat()
            return BinOpNode(tok.line, tok.col, tok.text, left, self.parse_operand())
        return left

    def parse_operand(self):
        tok = self.peek()
        if self.at("number"):
            self.eat()
            return ConstNode(tok.line, tok.col, int(tok.text))
        if self.at("ident"):
            self.eat()
            return VarNode(tok.line, tok.col, tok.text)
        self.fail_expected("a constant or a variable")
