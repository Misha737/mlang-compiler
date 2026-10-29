from src.lexer import CompileError
from src.ast_nodes import (
    ProgramNode, DeclNode, AssignNode, ExitNode,
    BinOpNode, VarNode, ConstNode, BoolNode, IfNode, WhileNode, BlockNode, NotNode,
    StructNode, FieldNode, ObjectDeclNode, FnNode, ParamNode, CallNode,
    MemberNode, FieldAssignNode, InitNode, MemberFnNode, MemberCallNode,
    PrintNode, StringNode, ReadNode, FieldOfNode, LambdaNode, CaptureNode,
)

TYPE_NAMES = ("i32", "i64", "bool")
RESERVED_NAMES = ("read", "print")

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
        if tok.kind == "keyword" and tok.text in RESERVED_NAMES and what.endswith("name"):
            raise CompileError(f"line {tok.line}:{tok.col}: '{tok.text}' is reserved and cannot be used as {what}")
        raise CompileError(f"line {tok.line}:{tok.col}: expected {what}, got '{tok.text}'")

    def end_of_line(self):
        last = self.toks[-1]
        return last.line, last.col + len(last.text)

    def parse_program(self):
        structs, functions, statements, exit_node = [], [], [], None
        while self.peek_line() is not None:
            self.next_line()
            if exit_node is not None:
                raise CompileError(f"line {self.toks[0].line}:{self.toks[0].col}: code after exit is not allowed")
            if self.at("keyword", "struct"):
                if functions or statements:
                    self.fail_at_peek("'struct' must come before any function or statement")
                structs.append(self.parse_struct())
            elif self.at_lambda():
                statements.append(self.parse_lambda())
            elif self.at("keyword", "fn"):
                if statements:
                    self.fail_at_peek("'fn' must come before any statement")
                functions.append(self.parse_fn())
            elif self.at("keyword", "exit"):
                exit_node = self.parse_exit_line()
            else:
                statements.append(self.parse_statement())
        if exit_node is None:
            line, col = self.end_of_line() if self.lines else (1, 1)
            raise CompileError(f"line {line}:{col}: program must end with exit")
        first = self.lines[0][0]
        return ProgramNode(first.line, first.col, statements, exit_node, structs, functions)

    def fail_at_peek(self, message):
        tok = self.peek()
        raise CompileError(f"line {tok.line}:{tok.col}: {message}")

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
        if self.at("keyword", "print"):
            return self.parse_print()
        if self.at("keyword", "read"):
            self.eat()
            if self.at("lparen"):
                raise CompileError(f"line {tok.line}:{tok.col}: a call alone is not a statement")
            raise CompileError(f"line {tok.line}:{tok.col}: 'read' is reserved and cannot be used as a variable name")
        if self.at("string"):
            raise CompileError(f"line {tok.line}:{tok.col}: a string literal can only be the argument of print")
        if self.at("keyword", "else"):
            raise CompileError(f"line {tok.line}:{tok.col}: 'else' without an 'if'")
        if self.at_lambda():
            return self.parse_lambda()
        if self.at("keyword", "struct") or self.at("keyword", "fn"):
            self.fail_at_peek(f"'{tok.text}' is not allowed inside a block")
        if self.at("keyword") and tok.text in TYPE_NAMES:
            node = self.parse_decl()
        elif self.at("ident"):
            node = self.parse_ident_statement()
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

    def parse_print(self):
        keyword = self.eat()
        self.expect("lparen", "'('")
        if self.at("rparen"):
            raise CompileError(f"line {keyword.line}:{keyword.col}: print needs one argument")
        if self.at("string"):
            literal = self.eat()
            arg = StringNode(literal.line, literal.col, literal.text[1:-1])
        else:
            arg = self.parse_expr()
        if self.at("comma"):
            raise CompileError(f"line {keyword.line}:{keyword.col}: print takes one argument")
        self.expect("rparen", "')'")
        self.expect_end_of_statement()
        return PrintNode(keyword.line, keyword.col, arg)

    def parse_read(self):
        keyword = self.eat()
        self.expect("lparen", "'('")
        if not self.at("rparen"):
            raise CompileError(f"line {keyword.line}:{keyword.col}: read takes no arguments")
        self.eat()
        return self.parse_postfix(ReadNode(keyword.line, keyword.col))

    def parse_while(self):
        keyword = self.eat()
        condition = self.parse_expr()
        self.expect_end_of_statement()
        body = self.parse_block(keyword)
        return WhileNode(keyword.line, keyword.col, condition, body)

    def expect_open_brace(self, owner):
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
        return opening

    def parse_struct(self):
        keyword = self.eat()
        name = self.expect("ident", "a struct name")
        self.expect_end_of_statement()
        opening = self.expect_open_brace(keyword)
        fields, methods = [], []
        while True:
            if self.peek_line() is None:
                raise CompileError(f"line {opening.line}:{opening.col}: '{{' is never closed")
            self.next_line()
            if self.at("rbrace"):
                self.eat()
                self.expect_end_of_statement()
                break
            if self.at("keyword", "fn"):
                if not fields:
                    self.fail_at_peek("a member function cannot come before the first field")
                methods.append(self.parse_fn(member=True))
                continue
            if methods:
                self.fail_at_peek("a field cannot come after a member function")
            fields.append(self.parse_field())
        if not fields:
            raise CompileError(f"line {opening.line}:{opening.col}: empty struct")
        return StructNode(name.line, name.col, name.text, fields, methods)

    def parse_type_token(self, what):
        tok = self.peek()
        if self.at("ident") or (self.at("keyword") and tok.text in TYPE_NAMES):
            return self.eat()
        self.fail_expected(what)

    def parse_fn(self, member=False):
        keyword = self.eat()
        name = self.expect("ident", "a function name")
        self.expect("operator", "':=' after the function name", ":=")
        if member and self.at("lbracket"):
            self.fail_at_peek("a member function cannot have a capture list")
        params, result_tok = self.parse_signature()
        self.expect_end_of_statement()
        body = self.parse_block(keyword)
        if body.exit is None:
            raise CompileError(f"line {name.line}:{name.col}: function '{name.text}' must end with exit")
        node_class = MemberFnNode if member else FnNode
        return node_class(name.line, name.col, name.text, params, result_tok.text, (result_tok.line, result_tok.col), body)

    def at_lambda(self):
        ahead = self.toks[self.pos:self.pos + 4]
        return (
            len(ahead) == 4
            and ahead[0].kind == "keyword" and ahead[0].text == "fn"
            and ahead[1].kind == "ident"
            and ahead[2].kind == "operator" and ahead[2].text == ":="
            and ahead[3].kind == "lbracket"
        )

    def parse_captures(self):
        self.expect("lbracket", "'['")
        captures = []
        if not self.at("rbracket"):
            captures.append(self.parse_capture())
            while self.at("comma"):
                self.eat()
                captures.append(self.parse_capture())
        self.expect("rbracket", "']'")
        return captures

    def parse_capture(self):
        mutable = self.at("keyword", "mut")
        if mutable:
            self.eat()
        name = self.expect("ident", "a capture name")
        return CaptureNode(name.line, name.col, name.text, mutable)

    def parse_lambda(self):
        keyword = self.eat()
        name = self.expect("ident", "a lambda name")
        self.expect("operator", "':=' after the lambda name", ":=")
        captures = self.parse_captures()
        params, result_tok = self.parse_signature()
        self.expect_end_of_statement()
        body = self.parse_block(keyword)
        if body.exit is None:
            raise CompileError(f"line {name.line}:{name.col}: lambda '{name.text}' must end with exit")
        return LambdaNode(
            name.line, name.col, name.text, captures, params,
            result_tok.text, (result_tok.line, result_tok.col), body,
        )

    def parse_signature(self):
        self.expect("lparen", "'('")
        params = []
        if not self.at("rparen"):
            params.append(self.parse_param())
            while self.at("comma"):
                self.eat()
                params.append(self.parse_param())
        self.expect("rparen", "')'")
        self.expect("arrow", "'->'")
        return params, self.parse_type_token("a result type")

    def parse_param(self):
        type_tok = self.parse_type_token("a parameter type")
        name = self.expect("ident", "a parameter name")
        return ParamNode(name.line, name.col, name.text, type_tok.text, (type_tok.line, type_tok.col))

    def parse_field(self):
        type_tok = self.parse_type_token("a field type")
        mutable = self.at("keyword", "mut")
        if mutable:
            self.eat()
        name = self.expect("ident", "a field name")
        self.expect_end_of_statement()
        return FieldNode(name.line, name.col, name.text, type_tok.text, mutable, (type_tok.line, type_tok.col))

    def parse_block(self, owner):
        opening = self.expect_open_brace(owner)
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

    def parse_value(self):
        if self.at("lbrace"):
            opening, values = self.parse_values()
            return InitNode(opening.line, opening.col, values)
        return self.parse_expr()

    def parse_values(self):
        opening = self.eat()
        values = [self.parse_value()]
        while self.at("comma"):
            self.eat()
            values.append(self.parse_value())
        self.expect("rbrace", "'}'")
        return opening, values

    def parse_decl(self):
        type_tok = self.eat()
        mutable = self.at("keyword", "mut")
        if mutable:
            self.eat()
        name = self.expect("ident", "a variable name")
        if not self.at("lbrace"):
            raise CompileError(f"line {name.line}:{name.col}: variable '{name.text}' needs an initializer in {{}}")
        opening, values = self.parse_values()
        for value in values:
            if isinstance(value, InitNode):
                raise CompileError(f"line {value.line}:{value.col}: type '{type_tok.text}' cannot be initialised with {{}}")
        if len(values) != 1:
            raise CompileError(f"line {opening.line}:{opening.col}: type '{type_tok.text}' takes 1 value in {{}}, got {len(values)}")
        return DeclNode(name.line, name.col, name.text, type_tok.text, mutable, values[0])

    def parse_ident_statement(self):
        first = self.eat()
        if self.at("lparen"):
            raise CompileError(f"line {first.line}:{first.col}: a call alone is not a statement")
        if self.at("dot"):
            target = self.parse_chain(first)
            if isinstance(target, MemberCallNode):
                raise CompileError(f"line {first.line}:{first.col}: a call alone is not a statement")
            if not isinstance(target, MemberNode):
                raise CompileError(f"line {first.line}:{first.col}: a call result cannot be the target of an assignment")
            self.expect("operator", f"':=' after '{target.path}'", ":=")
            return FieldAssignNode(first.line, first.col, target, self.parse_expr())
        if self.at("ident") or self.at("keyword", "mut"):
            return self.parse_object_decl(first)
        return self.parse_assign(first)

    def parse_object_decl(self, type_tok):
        mutable = self.at("keyword", "mut")
        if mutable:
            self.eat()
        name = self.expect("ident", "a variable name")
        if not self.at("lbrace"):
            raise CompileError(f"line {name.line}:{name.col}: variable '{name.text}' needs an initializer in {{}}")
        opening, values = self.parse_values()
        return ObjectDeclNode(
            name.line, name.col, name.text, type_tok.text, mutable, values,
            (type_tok.line, type_tok.col), (opening.line, opening.col),
        )

    def parse_assign(self, name):
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

    def parse_chain(self, root):
        links = []
        while self.at("dot"):
            self.eat()
            link = self.expect("ident", "a field name")
            if self.at("lparen"):
                if links:
                    obj = MemberNode(root.line, root.col, root.text, links)
                else:
                    obj = VarNode(root.line, root.col, root.text)
                return self.parse_postfix(MemberCallNode(link.line, link.col, obj, link.text, self.parse_args()))
            links.append((link.text, link.line, link.col))
        return MemberNode(root.line, root.col, root.text, links)

    def parse_args(self):
        self.eat()
        args = []
        if not self.at("rparen"):
            args.append(self.parse_expr())
            while self.at("comma"):
                self.eat()
                args.append(self.parse_expr())
        self.expect("rparen", "')'")
        return args

    def parse_call(self, name):
        return self.parse_postfix(CallNode(name.line, name.col, name.text, self.parse_args()))

    def parse_postfix(self, node):
        while self.at("dot"):
            dot = self.eat()
            link = self.expect("ident", "a field name")
            if self.at("lparen"):
                node = MemberCallNode(link.line, link.col, node, link.text, self.parse_args(), (dot.line, dot.col))
            elif isinstance(node, FieldOfNode):
                node.links.append((link.text, link.line, link.col))
            else:
                node = FieldOfNode(dot.line, dot.col, node, [(link.text, link.line, link.col)])
        return node

    def parse_factor(self):
        tok = self.peek()
        if self.at("number"):
            self.eat()
            return ConstNode(tok.line, tok.col, int(tok.text))
        if self.at("string"):
            raise CompileError(f"line {tok.line}:{tok.col}: a string literal can only be the argument of print")
        if self.at("keyword", "read"):
            return self.parse_read()
        if self.at("keyword", "print"):
            raise CompileError(f"line {tok.line}:{tok.col}: print has no value")
        if self.at("keyword", "true") or self.at("keyword", "false"):
            self.eat()
            return BoolNode(tok.line, tok.col, tok.text == "true")
        if self.at("ident"):
            self.eat()
            if self.at("lparen"):
                return self.parse_call(tok)
            if self.at("dot"):
                return self.parse_chain(tok)
            return VarNode(tok.line, tok.col, tok.text)
        if self.at_operator("!"):
            self.eat()
            return NotNode(tok.line, tok.col, self.parse_factor())
        self.fail_expected("a constant or a variable")
