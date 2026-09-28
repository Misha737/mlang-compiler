import sys
from src.lexer import lex, format_tokens, CompileError
from src.parser import Parser
from src.codegen import CodeGen

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

args = parse_arguments()
with open(args["source_path"], "rb") as file:
    data = file.read()

dump = args["dump"]
try:
    lines_tokens = lex(data)
    if dump != "--tokens":
        tree = Parser(lines_tokens).parse_program()
        if dump is None:
            module = CodeGen().generate(tree)
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
