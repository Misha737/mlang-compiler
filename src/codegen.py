from llvmlite import ir
import llvmlite.binding as llvm

from src.ast_nodes import MemberNode, StringNode, VarNode

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
        self.struct_types = {}
        self.structs = {}
        self.functions = {}
        self.this = None
        self.scanf = None
        self.constants = {}

    def generate(self, program):
        program.accept(self)
        return self.module

    def coerce(self, value, have, want):
        if have == "i32" and want == "i64":
            return self.builder.sext(value, I64, name="wide")
        return value

    def llvm_type(self, type_name):
        return LLVM_TYPES.get(type_name) or self.struct_types[type_name]

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
        for struct in node.structs:
            struct.accept(self)
        for function in node.functions:
            self.declare_function(function)
        for struct in node.structs:
            for method in struct.methods:
                self.declare_member_function(method)
        for struct in node.structs:
            for method in struct.methods:
                method.accept(self)
        for function in node.functions:
            function.accept(self)
        for statement in node.statements:
            statement.accept(self)
        node.exit.accept(self)

    def declare_function(self, node):
        signature = ir.FunctionType(
            self.llvm_type(node.result_type),
            [self.llvm_type(param.type_name) for param in node.params],
        )
        self.functions[node] = ir.Function(self.module, signature, name=f"fn.{node.name}")

    def declare_member_function(self, node):
        this_type = ir.PointerType(self.struct_types[node.owner.name])
        signature = ir.FunctionType(
            self.llvm_type(node.result_type),
            [this_type, *[self.llvm_type(param.type_name) for param in node.params]],
        )
        self.functions[node] = ir.Function(self.module, signature, name=f"{node.owner.name}_{node.name}")

    def define_function(self, node, offset, this):
        function = self.functions[node]
        saved = self.function, self.entry, self.builder, self.last_slot, self.this
        self.function = function
        self.entry = function.append_basic_block("entry")
        self.builder = ir.IRBuilder(self.entry)
        self.last_slot = None
        self.this = this
        for param, argument in zip(node.params, function.args[offset:]):
            argument.name = param.name
            slot = self.alloca_in_entry(self.llvm_type(param.type_name), param.name)
            self.builder.store(argument, slot)
            self.slots[param] = slot
        node.body.accept(self)
        self.function, self.entry, self.builder, self.last_slot, self.this = saved

    def visit_fn(self, node):
        self.define_function(node, 0, None)

    def visit_member_fn(self, node):
        function = self.functions[node]
        function.args[0].name = "this"
        self.define_function(node, 1, function.args[0])

    def var_pointer(self, node):
        if node.field is not None:
            indices = [ir.Constant(I32, 0), ir.Constant(I32, node.field.index)]
            return self.builder.gep(self.this, indices, inbounds=True)
        return self.slots[node.decl]

    def member_pointer(self, node):
        indices = [ir.Constant(I32, 0)]
        if node.field is not None:
            indices.append(ir.Constant(I32, node.field.index))
            base = self.this
        else:
            base = self.slots[node.decl]
        indices.extend(ir.Constant(I32, field.index) for field in node.fields)
        return self.builder.gep(base, indices, inbounds=True)

    def visit_member(self, node):
        return self.builder.load(self.member_pointer(node))

    def visit_field_assign(self, node):
        value = self.coerce(node.value.accept(self), node.value.type, node.target.type)
        self.builder.store(value, self.member_pointer(node.target))

    def object_pointer(self, obj):
        if isinstance(obj, MemberNode):
            return self.member_pointer(obj)
        return self.var_pointer(obj)

    def visit_member_call(self, node):
        pointer = self.object_pointer(node.obj)
        arguments = [
            self.coerce(arg.accept(self), arg.type, param.type_name)
            for arg, param in zip(node.args, node.method.params)
        ]
        return self.builder.call(self.functions[node.method], [pointer, *arguments])

    def visit_call(self, node):
        arguments = [
            self.coerce(arg.accept(self), arg.type, param.type_name)
            for arg, param in zip(node.args, node.function.params)
        ]
        if node.this_call:
            arguments.insert(0, self.this)
        return self.builder.call(self.functions[node.function], arguments)

    def constant_string(self, text):
        if text not in self.constants:
            name = f"str.{len(self.constants)}"
            data = text.encode("latin-1") + b"\0"
            const = ir.GlobalVariable(self.module, ir.ArrayType(I8, len(data)), name=name)
            const.linkage = "private"
            const.global_constant = True
            const.initializer = ir.Constant(ir.ArrayType(I8, len(data)), bytearray(data))
            self.constants[text] = const
        return self.builder.bitcast(self.constants[text], I8_PTR)

    def printf_text(self, text, *arguments):
        self.builder.call(self.printf, [self.constant_string(text), *arguments])

    def bool_text(self, value):
        true_ptr = self.builder.bitcast(self.true_str, I8_PTR)
        false_ptr = self.builder.bitcast(self.false_str, I8_PTR)
        return self.builder.select(value, true_ptr, false_ptr)

    def value_pointer(self, node):
        if isinstance(node, MemberNode):
            return self.member_pointer(node)
        if isinstance(node, VarNode):
            return self.var_pointer(node)
        slot = self.alloca_in_entry(self.llvm_type(node.type), "tmp")
        self.builder.store(node.accept(self), slot)
        return slot

    def print_value(self, prefix, type_name, value, suffix=""):
        if type_name == "bool":
            self.printf_text(prefix + "%s" + suffix, self.bool_text(value))
        elif type_name == "i64":
            self.printf_text(prefix + "%lld" + suffix, value)
        else:
            self.printf_text(prefix + "%d" + suffix, value)

    def print_struct(self, pointer, struct, closing):
        self.printf_text(f"{struct.name}{{")
        for position, field in enumerate(struct.fields):
            prefix = ("" if position == 0 else ", ") + f"{field.name}: "
            field_pointer = self.builder.gep(
                pointer, [ir.Constant(I32, 0), ir.Constant(I32, field.index)], inbounds=True
            )
            if field.type_name in self.structs:
                self.printf_text(prefix)
                self.print_struct(field_pointer, self.structs[field.type_name], "}")
            else:
                self.print_value(prefix, field.type_name, self.builder.load(field_pointer))
        self.printf_text(closing)

    def visit_print(self, node):
        arg = node.arg
        if isinstance(arg, StringNode):
            self.printf_text("%s\n", self.constant_string(arg.text))
        elif arg.type in self.structs:
            self.print_struct(self.value_pointer(arg), self.structs[arg.type], "}\n")
        else:
            self.print_value("", arg.type, arg.accept(self), "\n")

    def visit_read(self, node):
        if self.scanf is None:
            signature = ir.FunctionType(I32, [I8_PTR], var_arg=True)
            self.scanf = ir.Function(self.module, signature, name="scanf")
        slot = self.alloca_in_entry(I32, "read")
        self.builder.store(ir.Constant(I32, 0), slot)
        self.builder.call(self.scanf, [self.constant_string("%d"), slot])
        return self.builder.load(slot)

    def visit_struct(self, node):
        self.structs[node.name] = node
        struct_type = self.module.context.get_identified_type(node.name)
        struct_type.set_body(*[self.llvm_type(field.type_name) for field in node.fields])
        self.struct_types[node.name] = struct_type

    def visit_init(self, node):
        if node.copy:
            return node.values[0].accept(self)
        aggregate = ir.Constant(self.struct_types[node.type], ir.Undefined)
        for field, value in zip(node.struct.fields, node.values):
            element = self.coerce(value.accept(self), value.type, field.type_name)
            aggregate = self.builder.insert_value(aggregate, element, field.index)
        return aggregate

    def visit_decl(self, node):
        value = node.init.accept(self)
        value = self.coerce(value, node.init.type, node.type_name)
        slot = self.alloca_in_entry(self.llvm_type(node.type_name), node.name)
        self.builder.store(value, slot)
        self.slots[node] = slot

    def visit_object_decl(self, node):
        slot = self.alloca_in_entry(self.llvm_type(node.type_name), node.name)
        if node.copy:
            self.builder.store(node.values[0].accept(self), slot)
        else:
            for field, value in zip(node.struct.fields, node.values):
                element = self.coerce(value.accept(self), value.type, field.type_name)
                pointer = self.builder.gep(slot, [ir.Constant(I32, 0), ir.Constant(I32, field.index)], inbounds=True)
                self.builder.store(element, pointer)
        self.slots[node] = slot

    def visit_assign(self, node):
        value = node.value.accept(self)
        value = self.coerce(value, node.value.type, node.target_type)
        self.builder.store(value, self.var_pointer(node))

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
        if node.function is not None:
            self.builder.ret(self.coerce(value, node.value.type, node.function.result_type))
            return
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
        return self.builder.load(self.var_pointer(node))

    def visit_const(self, node):
        return ir.Constant(LLVM_TYPES[node.type], node.value)

    def visit_bool(self, node):
        return ir.Constant(I1, 1 if node.value else 0)
