import clang.cindex
from clang.cindex import CursorKind

clang.cindex.Config.set_library_file('/usr/lib/llvm-18/lib/libclang.so')
index = clang.cindex.Index.create()
tu = index.parse("p2im-unit_tests/RIOT/RIOT-ENV/cpu/stm32_common/periph/uart.c", args=['-x', 'c'])

def traverse(node):
    if node.kind == CursorKind.FUNCTION_DECL and node.spelling == "dev":
        print([t.spelling for t in node.get_tokens()])
    for c in node.get_children():
        traverse(c)
        
traverse(tu.cursor)
