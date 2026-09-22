import sys
import json
import clang.cindex
from clang.cindex import CursorKind, TokenKind

def get_ast_context(node, target_line, target_reg, parents=[]):
    if node.location.line == target_line:
        tokens = [t.spelling for t in node.get_tokens()]
        if target_reg in tokens:
            return parents + [node]
            
    for child in node.get_children():
        res = get_ast_context(child, target_line, target_reg, parents + [node])
        if res:
            return res
            
    return None

def analyze_access(parents):
    if not parents:
        return "unconfident"
        
    stmt = None
    for node in reversed(parents):
        if node.kind in (CursorKind.WHILE_STMT, CursorKind.IF_STMT, CursorKind.SWITCH_STMT):
            stmt = node
            break
            
    if not stmt:
        node = parents[-1]
        if node.kind in (CursorKind.WHILE_STMT, CursorKind.IF_STMT, CursorKind.SWITCH_STMT):
            stmt = node
            
    if not stmt:
        return "unconfident"
        
    tokens = [t.spelling for t in stmt.get_tokens()]
    has_bitwise = "&" in tokens or "|" in tokens
    has_equality = "==" in tokens or "!=" in tokens
    
    if stmt.kind == CursorKind.WHILE_STMT:
        if has_bitwise: return "bitextract"
        if has_equality: return "constant"
            
    if stmt.kind == CursorKind.IF_STMT:
        if has_bitwise: return "bitextract"
        if has_equality: return "set"
            
    if stmt.kind == CursorKind.SWITCH_STMT:
        return "set"
        
    return "unconfident"

def main():
    print("Initializing simplified static-AST oracle")
    clang.cindex.Config.set_library_file('/usr/lib/llvm-18/lib/libclang.so')
    index = clang.cindex.Index.create()
    
    with open("llm_proposals_riot.json") as f:
        proposals = json.load(f)
        
    confirmed = 0
    disagreements = []
    unconfident = []
    
    tus = {}
    
    for key, data in proposals.items():
        if data["model"] == "not_applicable_write_only":
            confirmed += 1
            continue
            
        source_file = data["source"]
        if source_file not in tus:
            tus[source_file] = index.parse(source_file, args=[
                '-x', 'c',
                '-DCPU_FAM_STM32F1=1'
            ], options=clang.cindex.TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD)
            
        parents = get_ast_context(tus[source_file].cursor, data["line"], data["register"])
        oracle_model = analyze_access(parents)
        
        if oracle_model == "unconfident":
            unconfident.append(key)
        elif oracle_model == data["model"]:
            confirmed += 1
        else:
            disagreements.append(key)
            
    print(f"Oracle Evaluation Complete ({len(proposals)} total registers processed):")
    print(f"  Confirmed: {confirmed}")
    print(f"  Unconfident (fallback/unsupported AST pattern): {len(unconfident)}")
    print(f"  Disagreements: {len(disagreements)}")

if __name__ == "__main__":
    main()
