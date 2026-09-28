class Token:
    def __init__(self, kind, text, line, col):
        self.kind = kind
        self.text = text
        self.line = line
        self.col = col

    def __repr__(self):
        return f"Token({self.kind!r}, {self.text!r}, {self.line}:{self.col})"

class CompileError(Exception):
    pass

KEYWORDS = {
    b"i32": "keyword",
    b"mut": "keyword",
    b"exit": "keyword",
}

def is_alpha(b: int) -> bool:
    return b == 0x5F or (0x41 <= b <= 0x5A) or (0x61 <= b <= 0x7A)

def is_digit(b: int) -> bool:
    return 0x30 <= b <= 0x39

def is_arithmetic(b: int) -> bool:
    return b in (ord("+"), ord("-"), ord("*"))

def format_tokens(lines):
    tokens = [token for line_tokens in lines for token in line_tokens]
    text_width = max((len(token.text) for token in tokens), default=0)
    kind_width = max((len(token.kind) for token in tokens), default=0)
    return "\n".join(
        f"{token.text:<{text_width}}  {token.kind:<{kind_width}}  {token.line}:{token.col}"
        for token in tokens
    )

def lex(data: bytes):
    lines = []
    tokens = []
    state, start, line, col = "START", 0, 1, 1
    count_brackets = 0
    open_brace_pos = (0, 0)
    i = 0

    def get_start_col():
        return col - (i - start)

    while i <= len(data):
        b = data[i] if i < len(data) else None
        if state == "START":
            if b is None: break
            elif b in (32, 9): pass # space, tab
            elif b == 10:
                if count_brackets != 0:
                    oline, ocol = open_brace_pos
                    raise CompileError(f"line {oline}:{ocol}: '{{' is not closed before the end of the line")
                lines.append(tokens); tokens = []; line += 1; col = 0
            elif is_alpha(b): state, start = "IDENT", i
            elif is_digit(b): state, start = "NUMBER", i
            elif b == ord("{"):
                tokens.append(Token("lbrace", "{", line, col))
                count_brackets += 1
                open_brace_pos = (line, col)
            elif b == ord("}"):
                tokens.append(Token("rbrace", "}", line, col))
                if count_brackets == 0:
                    raise CompileError(f"line {line}:{col}: '}}' connot be without '{{' before")
                count_brackets -= 1
            elif is_arithmetic(b): tokens.append(Token("operator", chr(b), line, col))
            elif b == ord(":"): state, start = "COLON", i
            elif b == ord("="): raise CompileError(f"line {line}:{col}: unexpected operator '='")
            else: raise CompileError(f"line {line}:{col}: unexpected byte '{chr(b)}'")
        elif state == "IDENT":
            if b is not None and (is_alpha(b) or is_digit(b)): pass
            else:
                word = data[start:i]
                tokens.append(Token(KEYWORDS.get(word, "ident"), word.decode(), line, get_start_col()))
                state = "START"; continue # re-read this byte in START
        elif state == "NUMBER":
            if b is not None and is_digit(b): pass
            elif b is not None and is_alpha(b):
                raise CompileError(f"line {line}:{col}: unexpected letter '{chr(b)}' in number")
            else:
                word = data[start:i]
                tokens.append(Token("number", word.decode(), line, get_start_col()))
                state = "START"; continue
        elif state == "COLON":
            if b == ord("="):
                tokens.append(Token("operator", ":=", line, get_start_col()))
                state = "START"
            else:
                raise CompileError(f"line {line}:{get_start_col()}: unexpected operator ':'")
        i += 1; col += 1
    if tokens: lines.append(tokens)
    return lines
