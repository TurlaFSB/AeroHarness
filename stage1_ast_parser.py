import sys
import json
import clang.cindex
from clang.cindex import CursorKind, TokenKind

def traverse(node, functions, current_func=None):
    if node.kind == CursorKind.FUNCTION_DECL:
        has_body = any(c.kind == CursorKind.COMPOUND_STMT for c in node.get_children())
        if has_body:
            current_func = node.spelling
            functions[current_func] = {
                "signature": f"{node.type.spelling} {node.spelling}",
                "params": [],
                "calls": [],
                "mmio_accesses": []
            }
            for arg in node.get_arguments():
                is_ptr = "*" in arg.type.spelling
                functions[current_func]["params"].append({
                    "name": arg.spelling,
                    "type": arg.type.spelling,
                    "is_pointer": is_ptr
                })
                
            # Token scan fallback for missing AST nodes due to unresolvable types
            tokens = list(node.get_tokens())
            for i in range(len(tokens) - 1):
                if tokens[i].kind == TokenKind.PUNCTUATION and tokens[i].spelling in ('->', '.'):
                    if tokens[i+1].kind == TokenKind.IDENTIFIER:
                        functions[current_func]["mmio_accesses"].append({
                            "register": tokens[i+1].spelling,
                            "line": tokens[i+1].location.line,
                            "method": "heuristic"
                        })
                elif tokens[i].kind == TokenKind.IDENTIFIER and tokens[i+1].kind == TokenKind.PUNCTUATION and tokens[i+1].spelling == '(':
                    if tokens[i].spelling not in functions[current_func]["calls"] and tokens[i].spelling != current_func:
                        functions[current_func]["calls"].append(tokens[i].spelling)

    if current_func:
        if node.kind == CursorKind.CALL_EXPR:
            if node.spelling and node.spelling not in functions[current_func]["calls"]:
                functions[current_func]["calls"].append(node.spelling)
        
        if node.kind == CursorKind.MEMBER_REF_EXPR:
            access_name = node.spelling
            line = node.location.line
            functions[current_func]["mmio_accesses"].append({
                "register": access_name,
                "line": line,
                "method": "ast"
            })
            
    for child in node.get_children():
        traverse(child, functions, current_func)

def analyze_ast(filename):
    clang.cindex.Config.set_library_file('/usr/lib/llvm-18/lib/libclang.so')
    index = clang.cindex.Index.create()
    
    tu = index.parse(filename, args=[
        '-x', 'c',
        '-DCONFIG_UART_INTERRUPT_DRIVEN=1',
        '-DCONFIG_UART_USE_RUNTIME_CONFIGURE=1',
        '-DCONFIG_PINCTRL=1',
        '-DCONFIG_RESET=1',
        '-DCONFIG_CLOCK_CONTROL=1',
        '-DCONFIG_UART_PL011_SBSA=1',
        '-DDT_ANY_COMPAT_HAS_PROP_STATUS_OKAY(a,b)=1'
    ], 
                     options=clang.cindex.TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD)
    
    constants = []
    functions = {}
    
    for cursor in tu.cursor.get_children():
        if cursor.kind == CursorKind.MACRO_DEFINITION:
            if cursor.location.file and cursor.location.file.name == filename:
                constants.append(cursor.spelling)
            
    traverse(tu.cursor, functions)
    
    for f in functions.values():
        unique_mmio = []
        seen = set()
        for m in f["mmio_accesses"]:
            key = f"{m['register']}:{m['line']}"
            if key not in seen:
                seen.add(key)
                unique_mmio.append(m)
        f["mmio_accesses"] = unique_mmio
        
        # Deduplicate calls
        unique_calls = []
        seen_calls = set()
        for c in f["calls"]:
            if c not in seen_calls:
                seen_calls.add(c)
                unique_calls.append(c)
        f["calls"] = unique_calls

    output = {
        "constants": constants,
        "functions": functions,
        "extraction_warnings": [d.spelling for d in tu.diagnostics if d.severity >= 3]
    }
    
    with open("ast_output.json", "w") as f:
        json.dump(output, f, indent=2)
        
if __name__ == "__main__":
    analyze_ast(sys.argv[1])
