# Compiler

A compiler for a small statically typed language. Source programs are compiled to LLVM IR via `llvmlite`.

## Environment setup

Reference environment: Ubuntu 24.04 (native Linux, WSL 2, Multipass, or Docker).

1. Install the LLVM toolchain:

```bash
   sudo apt update
   sudo apt install -y llvm clang python3 python3-venv python3-pip binutils file
   llc --version
   clang --version
```

2. Create a virtual environment and install `llvmlite`:

```bash
   python3 -m venv ~/lcd
   source ~/lcd/bin/activate
   pip install 'llvmlite==0.49.*'
   python3 -c "import llvmlite.binding as b; print(b.llvm_version_info)"   # (22, 1, 0)
```

Activate the virtual environment (`source ~/lcd/bin/activate`) in every new shell before running the compiler or the tests. Keep this exact `llvmlite` version for the whole term.

## Project layout

```
compiler.py       # entry point: lexer -> statement parsing -> LLVM IR generation
src/lexer.py          # hand-written state machine lexer
tests/
  test_compiler.py
  conftest.py
  fixtures/       # .mlang source programs and their .expected outputs
```

## Running the compiler

```bash
python3 compiler.py input.mlang output.ll
```

To run the generated IR directly, without linking:

```bash
lli output.ll
```

To produce a native executable:

```bash
llc -filetype=obj -relocation-model=pic output.ll -o output.o
clang -fPIE output.o -o program
./program
```

## Running the tests

Install `pytest`:

```bash
pip install pytest
```

Run the suite from the repository root:

```bash
python3 -m pytest tests/
```
