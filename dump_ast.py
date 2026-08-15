import sys
import clang.cindex
from clang.cindex import CursorKind

def dump(node, indent):
    print(" " * indent + f"{node.kind} {node.spelling} {node.type.spelling}")
    for c in node.get_children():
        dump(c, indent + 2)

def analyze(filename):
    clang.cindex.Config.set_library_file('/usr/lib/llvm-18/lib/libclang.so')
    index = clang.cindex.Index.create()
    tu = index.parse(filename, args=['-x', 'c'])
    for c in tu.cursor.get_children():
        if c.kind == CursorKind.FUNCTION_DECL and c.spelling == "pl011_enable":
            dump(c, 0)
            print("TOKENS:")
            for t in c.get_tokens():
                print(t.spelling, t.kind)

if __name__ == "__main__":
    analyze(sys.argv[1])
