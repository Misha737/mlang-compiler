from llvmlite import ir
import llvmlite.binding as llvm

I32 = ir.IntType(32)
I64 = ir.IntType(64)
I1 = ir.IntType(1)
I8 = ir.IntType(8)
I8_PTR = ir.PointerType(I8)

LLVM_TYPES = {"i32": I32, "i64": I64, "bool": I1}
OPERATIONS = {"+": "add", "-": "sub", "*": "mul"}


def global_string(module, name, text):
    data = text.encode() + b"\0"
    const = ir.GlobalVariable(module, ir.ArrayType(I8, len(data)), name=name)
    const.linkage = "private"
    const.global_constant = True
    const.initializer = ir.Constant(ir.ArrayType(I8, len(data)), bytearray(data))
    return const


class CodeGen:
    def __init__(self):
        self.module = ir.Module(name="p1")
        self.module.triple = llvm.get_default_triple()
        self.function = ir.Function(self.module, ir.FunctionType(I32, []), name="main")
        self.entry = self.function.append_basic_block("entry")
        self.builder = ir.IRBuilder(self.entry)
        self.last_slot = None
        self.printf = ir.Function(self.module, ir.FunctionType(I32, [I8_PTR], var_arg=True), name="printf")

        self.fmt_int = global_string(self.module, "fmt_int", "Program exit with result %lld\n")
        self.fmt_bool = global_string(self.module, "fmt_bool", "Program exit with result %s\n")
        self.true_str = global_string(self.module, "true_str", "true")
        self.false_str = global_string(self.module, "false_str", "false")

        self.slots = {}

    def generate(self, program):
        program.accept(self)
        return self.module

    def coerce(self, value, have, want):
        if have == "i32" and want == "i64":
            return self.builder.sext(value, I64, name="wide")
        return value

    def alloca_in_entry(self, llvm_type, name):
        current = self.builder.block
        if self.last_slot is None:
            self.builder.position_at_start(self.entry)
        else:
            self.builder.position_after(self.last_slot)
        self.last_slot = self.builder.alloca(llvm_type, name=name)
        self.builder.position_at_end(current)
        return self.last_slot

    def visit_program(self, node):
        for statement in node.statements:
            statement.accept(self)
        node.exit.accept(self)

    def visit_decl(self, node):
        value = node.init.accept(self)
        value = self.coerce(value, node.init.type, node.type_name)
        slot = self.alloca_in_entry(LLVM_TYPES[node.type_name], node.name)
        self.builder.store(value, slot)
        self.slots[node] = slot

    def visit_assign(self, node):
        value = node.value.accept(self)
        value = self.coerce(value, node.value.type, node.decl.type_name)
        self.builder.store(value, self.slots[node.decl])

    def visit_block(self, node):
        for statement in node.statements:
            statement.accept(self)
        if node.exit:
            node.exit.accept(self)

    def visit_if(self, node):
        condition = node.condition.accept(self)
        then_bb = self.function.append_basic_block("then")
        else_bb = self.function.append_basic_block("else") if node.else_block else None
        merge_bb = self.function.append_basic_block("merge")
        self.builder.cbranch(condition, then_bb, else_bb or merge_bb)
        self.builder.position_at_end(then_bb)
        node.then_block.accept(self)
        if not self.builder.block.is_terminated:
            self.builder.branch(merge_bb)
        if else_bb:
            self.builder.position_at_end(else_bb)
            node.else_block.accept(self)
            if not self.builder.block.is_terminated:
                self.builder.branch(merge_bb)
        self.builder.position_at_end(merge_bb)

    def visit_while(self, node):
        cond_bb = self.function.append_basic_block("cond")
        body_bb = self.function.append_basic_block("body")
        end_bb = self.function.append_basic_block("end")
        self.builder.branch(cond_bb)
        self.builder.position_at_end(cond_bb)
        condition = node.condition.accept(self)
        self.builder.cbranch(condition, body_bb, end_bb)
        self.builder.position_at_end(body_bb)
        node.body.accept(self)
        if not self.builder.block.is_terminated:
            self.builder.branch(cond_bb)
        self.builder.position_at_end(end_bb)

    def visit_exit(self, node):
        value = node.value.accept(self)
        if node.value.type == "bool":
            true_ptr = self.builder.bitcast(self.true_str, I8_PTR)
            false_ptr = self.builder.bitcast(self.false_str, I8_PTR)
            text = self.builder.select(value, true_ptr, false_ptr)
            fmt = self.builder.bitcast(self.fmt_bool, I8_PTR)
            self.builder.call(self.printf, [fmt, text])
        else:
            value = self.coerce(value, node.value.type, "i64")
            fmt = self.builder.bitcast(self.fmt_int, I8_PTR)
            self.builder.call(self.printf, [fmt, value])
        self.builder.ret(ir.Constant(I32, 0))

    def visit_binop(self, node):
        left = node.left.accept(self)
        right = node.right.accept(self)
        if node.op in OPERATIONS:
            left = self.coerce(left, node.left.type, node.type)
            right = self.coerce(right, node.right.type, node.type)
            return getattr(self.builder, OPERATIONS[node.op])(left, right)
        if node.left.type != "bool":
            wide = "i64" if "i64" in (node.left.type, node.right.type) else "i32"
            left = self.coerce(left, node.left.type, wide)
            right = self.coerce(right, node.right.type, wide)
        return self.builder.icmp_signed(node.op, left, right)

    def visit_not(self, node):
        return self.builder.not_(node.operand.accept(self))

    def visit_var(self, node):
        return self.builder.load(self.slots[node.decl])

    def visit_const(self, node):
        return ir.Constant(LLVM_TYPES[node.type], node.value)

    def visit_bool(self, node):
        return ir.Constant(I1, 1 if node.value else 0)
