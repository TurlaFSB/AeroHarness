import clang.cindex
try:
    index = clang.cindex.Index.create()
    print("libclang is available!")
except Exception as e:
    print(f"Error: {e}")
