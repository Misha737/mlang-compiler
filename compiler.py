import sys
from dataclasses import dataclass, field
from llvmlite import ir
import llvmlite.binding as llvm
from src.lexer import lex, format_tokens, CompileError
from src.parser import Parser

DUMP_FLAGS = ("--tokens", "--ast")

def parse_arguments():
    args = sys.argv[1:]
    flags = [arg for arg in args if arg in DUMP_FLAGS]
    paths = [arg for arg in args if arg not in DUMP_FLAGS]
    if len(flags) > 1 or len(paths) != (1 if flags else 2):
        print("usage: compiler.py input output.ll | compiler.py --tokens input | compiler.py --ast input", file=sys.stderr)
        sys.exit(1)
    return {
        "source_path": paths[0],
        "output_path": None if flags else paths[1],
        "dump": flags[0] if flags else None,
    }

@dataclass
class Env:
    module: ir.Module
    builder: ir.IRBuilder
    printf: ir.Function
    fmt: ir.GlobalVariable
    symbols: dict = field(default_factory=dict)
    I32 = ir.IntType(32)
    I8 = ir.IntType(8)
    P = ir.PointerType(I8)

def error_at(token, message):
    print(f"compilation error: line {token.line}:{token.col}: {message}", file=sys.stderr)
    sys.exit(1)

def get_operand_value(env, token):
    if token.kind == "number":
        return ir.Constant(env.I32, int(token.text))
    if token.kind == "ident":
        if token.text not in env.symbols:
            error_at(token, f"variable '{token.text}' is used before its declaration")
        alloca, _ = env.symbols[token.text]
        return env.builder.load(alloca)
    error_at(token, f"expected a constant or variable, got '{token.text}'")

def eval_expression(env, tokens, anchor):
    if len(tokens) == 0:
        error_at(anchor, "expected an expression")
    if any(t.kind in ("lbrace", "rbrace") for t in tokens):
        error_at(tokens[0], "unexpected '{' or '}' in expression")
    if len(tokens) == 1:
        return get_operand_value(env, tokens[0])
    if len(tokens) == 3 and tokens[1].kind == "operator" and tokens[1].text in ("+", "-", "*"):
        lhs = get_operand_value(env, tokens[0])
        rhs = get_operand_value(env, tokens[2])
        op = tokens[1].text
        if op == "+":
            return env.builder.add(lhs, rhs)
        if op == "-":
            return env.builder.sub(lhs, rhs)
        return env.builder.mul(lhs, rhs)
    error_at(tokens[0], "invalid expression")

def process_declaration(env, tokens):
    idx = 1
    is_mut = False
    if idx < len(tokens) and tokens[idx].kind == "keyword" and tokens[idx].text == "mut":
        is_mut = True
        idx += 1
    if idx >= len(tokens) or tokens[idx].kind != "ident":
        error_at(tokens[idx - 1], "expected a variable name")
    name_token = tokens[idx]
    name = name_token.text
    idx += 1
    if name in env.symbols:
        error_at(name_token, f"variable '{name}' is already declared")
    if idx >= len(tokens) or tokens[idx].kind != "lbrace":
        error_at(name_token, f"variable '{name}' needs an initializer in {{}}")
    if tokens[-1].kind != "rbrace":
        error_at(tokens[-1], "expected '}' to close initializer")
    inner = tokens[idx + 1:-1]
    value = eval_expression(env, inner, tokens[idx])
    alloca = env.builder.alloca(env.I32, name=name)
    env.builder.store(value, alloca)
    env.symbols[name] = (alloca, is_mut)

def process_assignment(env, tokens):
    name_token = tokens[0]
    name = name_token.text
    if name not in env.symbols:
        error_at(name_token, f"variable '{name}' is used before its declaration")
    alloca, is_mut = env.symbols[name]
    if not is_mut:
        error_at(name_token, f"cannot assign to '{name}': it is not mut")
    if len(tokens) < 2 or not (tokens[1].kind == "operator" and tokens[1].text == ":="):
        error_at(name_token, "invalid statement")
    value = eval_expression(env, tokens[2:], tokens[1])
    env.builder.store(value, alloca)

def process_exit(env, tokens):
    if len(tokens) != 2:
        error_at(tokens[0], "exit expects exactly one operand")
    value = get_operand_value(env, tokens[1])
    env.builder.call(env.printf, [env.builder.bitcast(env.fmt, env.P), value])
    env.builder.ret(ir.Constant(env.I32, 0))

def process_line(env, tokens):
    first = tokens[0]
    if first.kind == "keyword" and first.text == "i32":
        process_declaration(env, tokens)
    elif first.kind == "keyword" and first.text == "exit":
        process_exit(env, tokens)
    elif first.kind == "ident":
        process_assignment(env, tokens)
    else:
        error_at(first, "line is not a valid statement")

def compile(lines):
    module = ir.Module(name="p1")
    module.triple = llvm.get_default_triple()
    main = ir.Function(module, ir.FunctionType(ir.IntType(32), []), name="main")
    builder = ir.IRBuilder(main.append_basic_block("entry"))

    printf = ir.Function(module, ir.FunctionType(ir.IntType(32), [ir.PointerType(ir.IntType(8))], var_arg=True), name="printf")

    text = b"Program exit with result %d\n\0"
    fmt = ir.GlobalVariable(module, ir.ArrayType(ir.IntType(8), len(text)), name="fmt")
    fmt.linkage = "private"
    fmt.global_constant = True
    fmt.initializer = ir.Constant(ir.ArrayType(ir.IntType(8), len(text)), bytearray(text))

    env = Env(module=module, builder=builder, fmt=fmt, printf=printf)

    last_token = None
    for line_tokens in lines:
        if not line_tokens:
            continue
        if env.builder.block.is_terminated:
            error_at(line_tokens[0], "code after exit is not allowed")
        process_line(env, line_tokens)
        last_token = line_tokens[-1]

    if not env.builder.block.is_terminated:
        if last_token is not None:
            error_at(last_token, "program must end with exit")
        print("compilation error: line 1:1: program must end with exit", file=sys.stderr)
        sys.exit(1)

    return env.module

args = parse_arguments()
with open(args["source_path"], "rb") as file:
    data = file.read()

dump = args["dump"]
try:
    lines_tokens = lex(data)
    if dump == "--ast":
        tree = Parser(lines_tokens).parse_program()
    elif dump is None:
        module = compile(lines_tokens)
except CompileError as e:
    print(f"compilation error: {e}", file=sys.stderr)
    sys.exit(1)

if dump == "--tokens":
    print(format_tokens(lines_tokens))
elif dump == "--ast":
    print(tree.dump())
else:
    with open(args["output_path"], "w", encoding="utf-8") as file:
        file.write(str(module))
