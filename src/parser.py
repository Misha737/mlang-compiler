from src.lexer import CompileError
from src.ast_nodes import (
    ProgramNode, DeclNode, AssignNode, ExitNode,
    BinOpNode, VarNode, ConstNode, BoolNode, IfNode, WhileNode, BlockNode, NotNode,
)

TYPE_NAMES = ("i32", "i64", "bool")

class Parser:
    def __init__(self, lines):
        self.lines = [toks for toks in lines if toks]
        self.line_pos = 0
        self.toks = []
        self.pos = 0

    def peek_line(self):
        return self.lines[self.line_pos] if self.line_pos < len(self.lines) else None

    def next_line(self):
        self.toks, self.pos = self.lines[self.line_pos], 0
        self.line_pos += 1

    def peek(self):
        return self.toks[self.pos] if self.pos < len(self.toks) else None

    def eat(self):
        tok = self.toks[self.pos]
        self.pos += 1
        return tok

    def at(self, kind, text=None):
        tok = self.peek()
        return tok is not None and tok.kind == kind and (text is None or tok.text == text)

    def at_operator(self, *texts):
        tok = self.peek()
        return tok is not None and tok.kind == "operator" and tok.text in texts

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
        statements, exit_node = [], None
        while self.peek_line() is not None:
            self.next_line()
            if exit_node is not None:
                raise CompileError(f"line {self.toks[0].line}:{self.toks[0].col}: code after exit is not allowed")
            if self.at("keyword", "exit"):
                exit_node = self.parse_exit_line()
            else:
                statements.append(self.parse_statement())
        if exit_node is None:
            line, col = self.end_of_line() if self.lines else (1, 1)
            raise CompileError(f"line {line}:{col}: program must end with exit")
        first = self.lines[0][0]
        return ProgramNode(first.line, first.col, statements, exit_node)

    def expect_end_of_statement(self):
        tok = self.peek()
        if tok is not None:
            raise CompileError(f"line {tok.line}:{tok.col}: unexpected '{tok.text}' after the statement")

    def parse_statement(self):
        tok = self.peek()
        if self.at("keyword", "if"):
            return self.parse_if()
        if self.at("keyword", "while"):
            return self.parse_while()
        if self.at("keyword", "else"):
            raise CompileError(f"line {tok.line}:{tok.col}: 'else' without an 'if'")
        if self.at("keyword") and tok.text in TYPE_NAMES:
            node = self.parse_decl()
        elif self.at("ident"):
            node = self.parse_assign()
        else:
            raise CompileError(f"line {tok.line}:{tok.col}: cannot start a statement with '{tok.text}'")
        self.expect_end_of_statement()
        return node

    def parse_if(self):
        keyword = self.eat()
        condition = self.parse_expr()
        self.expect_end_of_statement()
        then_block = self.parse_block(keyword)
        else_block = None
        following = self.peek_line()
        if following is not None and following[0].kind == "keyword" and following[0].text == "else":
            self.next_line()
            else_keyword = self.eat()
            self.expect_end_of_statement()
            else_block = self.parse_block(else_keyword)
        return IfNode(keyword.line, keyword.col, condition, then_block, else_block)

    def parse_while(self):
        keyword = self.eat()
        condition = self.parse_expr()
        self.expect_end_of_statement()
        body = self.parse_block(keyword)
        return WhileNode(keyword.line, keyword.col, condition, body)

    def parse_block(self, owner):
        following = self.peek_line()
        if following is None:
            line, col = self.end_of_line()
            raise CompileError(f"line {line}:{col}: expected '{{' on its own line after '{owner.text}', found end of input")
        if following[0].kind != "lbrace":
            tok = following[0]
            raise CompileError(f"line {tok.line}:{tok.col}: expected '{{' on its own line after '{owner.text}', got '{tok.text}'")
        self.next_line()
        opening = self.eat()
        self.expect_end_of_statement()
        statements, exit_node = [], None
        while True:
            following = self.peek_line()
            if following is None:
                raise CompileError(f"line {opening.line}:{opening.col}: '{{' is never closed")
            self.next_line()
            if self.at("rbrace"):
                self.eat()
                self.expect_end_of_statement()
                break
            if exit_node is not None:
                tok = self.toks[0]
                raise CompileError(f"line {tok.line}:{tok.col}: statement after 'exit' in the same block")
            if self.at("keyword", "exit"):
                exit_node = self.parse_exit_line()
            else:
                statements.append(self.parse_statement())
        if not statements and exit_node is None:
            raise CompileError(f"line {opening.line}:{opening.col}: empty block")
        return BlockNode(opening.line, opening.col, statements, exit_node)

    def parse_decl(self):
        type_tok = self.eat()
        mutable = self.at("keyword", "mut")
        if mutable:
            self.eat()
        name = self.expect("ident", "a variable name")
        if not self.at("lbrace"):
            raise CompileError(f"line {name.line}:{name.col}: variable '{name.text}' needs an initializer in {{}}")
        self.eat()
        init = self.parse_expr()
        self.expect("rbrace", "'}'")
        return DeclNode(name.line, name.col, name.text, type_tok.text, mutable, init)

    def parse_assign(self):
        name = self.eat()
        self.expect("operator", f"':=' after '{name.text}'", ":=")
        value = self.parse_expr()
        return AssignNode(name.line, name.col, name.text, value)

    def parse_exit_line(self):
        keyword = self.eat()
        node = ExitNode(keyword.line, keyword.col, self.parse_factor())
        self.expect_end_of_statement()
        return node

    def parse_expr(self):
        node = self.parse_arith()
        if self.at_operator("==", "!="):
            op = self.eat()
            node = BinOpNode(op.line, op.col, op.text, node, self.parse_arith())
        return node

    def parse_arith(self):
        node = self.parse_term()
        while self.at_operator("+", "-"):
            op = self.eat()
            node = BinOpNode(op.line, op.col, op.text, node, self.parse_term())
        return node

    def parse_term(self):
        node = self.parse_factor()
        while self.at_operator("*"):
            op = self.eat()
            node = BinOpNode(op.line, op.col, op.text, node, self.parse_factor())
        return node

    def parse_factor(self):
        tok = self.peek()
        if self.at("number"):
            self.eat()
            return ConstNode(tok.line, tok.col, int(tok.text))
        if self.at("keyword", "true") or self.at("keyword", "false"):
            self.eat()
            return BoolNode(tok.line, tok.col, tok.text == "true")
        if self.at("ident"):
            self.eat()
            return VarNode(tok.line, tok.col, tok.text)
        if self.at_operator("!"):
            self.eat()
            return NotNode(tok.line, tok.col, self.parse_factor())
        self.fail_expected("a constant or a variable")
