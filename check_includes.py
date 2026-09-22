import clang.cindex
from clang.cindex import CursorKind
import os

clang.cindex.Config.set_library_file('/usr/lib/llvm-18/lib/libclang.so')
index = clang.cindex.Index.create()

riot_env = "p2im-unit_tests/RIOT/RIOT-ENV"
args = [
    "-x", "c",
    f"-I{riot_env}/core/include",
    f"-I{riot_env}/drivers/include",
    f"-I{riot_env}/cpu/cortexm_common/include",
    f"-I{riot_env}/cpu/stm32_common/include",
    f"-I{riot_env}/cpu/stm32f1/include",
    "-DCPU_FAM_STM32F1",
    "-DCPU_MODEL_STM32F103RB"
]

tu = index.parse(f"{riot_env}/cpu/stm32_common/periph/uart.c", args=args)
for diag in tu.diagnostics:
    print(diag)

def traverse(node):
    if node.kind == CursorKind.FUNCTION_DECL and node.spelling == "dev":
        print(f"Function {node.spelling}, return type: {node.result_type.spelling}")
    for c in node.get_children():
        traverse(c)
        
traverse(tu.cursor)
