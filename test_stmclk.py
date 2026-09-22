import clang.cindex
clang.cindex.Config.set_library_file('/usr/lib/llvm-18/lib/libclang.so')
idx=clang.cindex.Index.create()
tu=idx.parse('p2im-unit_tests/RIOT/RIOT-ENV/cpu/stm32_common/stmclk.c')
fns = [c for c in tu.cursor.walk_preorder() if c.kind == clang.cindex.CursorKind.FUNCTION_DECL]
print(f"Functions: {len(fns)}")
for f in fns:
    bodies = [c for c in f.get_children() if c.kind == clang.cindex.CursorKind.COMPOUND_STMT]
    print(f"Function {f.spelling}, bodies={len(bodies)}")
