import clang.cindex
from clang.cindex import CursorKind
def get_ast_context(node, target_line, target_reg, parents=[]):
    if node.location.line == target_line:
        tokens = [t.spelling for t in node.get_tokens()]
        if target_reg in tokens and ("uart" in tokens or "get_uart" in tokens):
            return parents + [node]
    for child in node.get_children():
        res = get_ast_context(child, target_line, target_reg, parents + [node])
        if res: return res
    return None

clang.cindex.Config.set_library_file('/usr/lib/llvm-18/lib/libclang.so')
index = clang.cindex.Index.create()
tu = index.parse("uart_pl011.c", args=['-x', 'c'])
parents = get_ast_context(tu.cursor, 224, "fr")
print([p.kind for p in parents])
for p in parents:
    if p.kind == CursorKind.BINARY_OPERATOR:
        print("Tokens:", [t.spelling for t in p.get_tokens()])
