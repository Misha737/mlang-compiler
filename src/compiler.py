import sys
from dataclasses import dataclass
from llvmlite import ir
import llvmlite.binding as llvm

def parse_arguments():
    args = sys.argv[1:]

    if(len(args) != 2):
        print("Number of arguments must equal 2", file=sys.stderr)
        sys.exit(1)

    return {
            "source_path": args[0],
            "output_path": args[1]
        }


def tokenize(path):
    array_tokens = []
    with open(path, "r", encoding="utf-8") as file:
        for line in file:
            tokens = line.split()
            array_tokens.append(tokens)
    return array_tokens


@dataclass
class Env:
    module: ir.Module
    builder: ir.IRBuilder
    printf: ir.Function
    symbols: dict
    line_index: int
    fmt: ir.GlobalVariable
    I32, I8 = ir.IntType(32), ir.IntType(8)
    P = ir.PointerType(I8)

def error_compilation(env, message):
    print(f'''
Compilation error:
Line {env.line_index}: {message}
    ''', file=sys.stderr)
    sys.exit(1)


def declare(env, name):
    if name in ["int", "exit"]:
        error_compilation(env, "")
    if name[0].isdigit():
        error_compilation(env, "")
    if not all(ch.isalnum() or ch == "_" for ch in name):
        error_compilation(env, "")
    env.symbols[name] = env.builder.alloca(env.I32, name=name)

def exit_program(env, variable):
    env.builder.call(env.printf, [env.builder.bitcast(env.fmt, env.P), env.builder.load(env.symbols[variable])]) 
    env.builder.ret(ir.Constant(env.I32, 0))

def get_constant(env, operand):
    if operand.isdigit():
        return ir.Constant(env.I32, operand)
    else:
        if not (operand in env.symbols.keys()):
            error_compilation(env, "")
        return env.builder.load(env.symbols[operand])

def operate(env, operator, operand1, operand2):
    operand1 = get_constant(env, operand1)
    operand2 = get_constant(env, operand2)
    match operator:
        case "+":
            return env.builder.add(operand1, operand2)
        case "-":
            return env.builder.sub(operand1, operand2)
        case "*":
            return env.builder.mul(operand1, operand2)
        case _:
            error_compilation(env, "")

def assign(env, assignee, constant):
    if not (assignee in env.symbols.keys()):
        error_compilation(env, "")
    env.builder.store(constant, env.symbols[assignee])

def process(env, line):
    if len(line) < 1:
        return
    match line[0]:
        case "int":
            if len(line) != 2:
                error_compilation(env, "")
            if line[1] in env.symbols.keys():
                error_compilation(env, "")
            declare(env, line[1])
        case "exit":
            if len(line) != 2:
                error_compilation(env, "")
            if not (line[1] in env.symbols.keys()):
                error_compilation(env, "")
            exit_program(env, line[1])
        case x if x in env.symbols.keys():
            if len(line) < 3:
                error_compilation(env, "")
            if line[1] != ":=":
                error_compilation(env, "")
            if len(line) == 5:
                assign(env, line[0], operate(env, line[3], line[2], line[4]))
            elif len(line) == 3:
                assign(env, line[0], get_constant(env, line[2]))
            else:
                error_compilation(env, "")
        case _:
            error_compilation(env, "Invalid syntax")

def compile(lines):
    I32, I8 = ir.IntType(32), ir.IntType(8)
    P = ir.PointerType(I8)

    module = ir.Module(name="p1")
    module.triple = llvm.get_default_triple()
    main = ir.Function(module, ir.FunctionType(I32, []), name="main")
    builder = ir.IRBuilder(main.append_basic_block("entry"))

    printf = ir.Function(module, ir.FunctionType(I32, [ir.PointerType(I8)], var_arg=True), name="printf")

    text = b"Program exit with result %d\n\0"
    fmt = ir.GlobalVariable(module, ir.ArrayType(I8, len(text)), name="fmt")
    fmt.linkage = "private"
    fmt.global_constant = True
    fmt.initializer = ir.Constant(ir.ArrayType(I8, len(text)), bytearray(text))

    symbols = {}

    env = Env(module=module, builder=builder, fmt=fmt, symbols=symbols, line_index=0, printf=printf)


    for line in lines:
        env.line_index += 1
        if env.builder.block.is_terminated:
            error_compilation(env, "Code after exit")
        process(env, line)

    if not env.builder.block.is_terminated:
        error_compilation(env, "Program must end with exit")

    return env.module


args = parse_arguments()
tokens_array = tokenize(args["source_path"])
module = compile(tokens_array)

with open(args["output_path"], "w", encoding="utf-8") as file:
    file.write(str(module))
