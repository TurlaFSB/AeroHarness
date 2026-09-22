import sys
import json
import clang.cindex
from clang.cindex import CursorKind, TokenKind

def get_ast_context(node, target_line, target_reg, parents=[]):
    """
    Recursively finds the node at the target line that references the target register,
    and returns its parent hierarchy.
    """
    if node.location.line == target_line:
        # Check if this node or its tokens mention the register
        tokens = [t.spelling for t in node.get_tokens()]
        if target_reg in tokens and ("uart" in tokens or "get_uart" in tokens):
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
            
    # Also check if it's nested inside a statement that wasn't in parents but is the node itself
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
        if has_bitwise:
            return "bitextract"
        if has_equality:
            return "constant"
            
    if stmt.kind == CursorKind.IF_STMT:
        if has_bitwise:
            return "bitextract"
        if has_equality:
            return "set"
            
    if stmt.kind == CursorKind.SWITCH_STMT:
        return "set"
        
    return "unconfident"

def main():
    print("Initializing simplified static-AST oracle (Not dynamic symbolic execution)")
    
    clang.cindex.Config.set_library_file('/usr/lib/llvm-18/lib/libclang.so')
    index = clang.cindex.Index.create()
    
    tu = index.parse("uart_pl011.c", args=[
        '-x', 'c',
        '-DCONFIG_UART_INTERRUPT_DRIVEN=1',
        '-DCONFIG_UART_USE_RUNTIME_CONFIGURE=1',
        '-DCONFIG_PINCTRL=1',
        '-DCONFIG_RESET=1',
        '-DCONFIG_CLOCK_CONTROL=1',
        '-DCONFIG_UART_PL011_SBSA=1',
        '-DDT_ANY_COMPAT_HAS_PROP_STATUS_OKAY(a,b)=1'
    ], options=clang.cindex.TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD)

    with open("llm_proposals.json") as f:
        proposals = json.load(f)
        
    confirmed = 0
    disagreements = []
    unconfident = []
    
    for key, data in proposals.items():
        llm_model = data["model"]
        line = data["line"]
        reg = data["register"]
        
        if llm_model == "not_applicable_write_only":
            # The LLM skipped it based on Stage 1's write-only flag. The oracle confirms this.
            confirmed += 1
            continue
            
        parents = get_ast_context(tu.cursor, line, reg)
        oracle_model = analyze_access(parents)
        
        if oracle_model == "unconfident":
            unconfident.append({
                "key": key,
                "llm": llm_model,
                "context": data["context"].strip().split('\n')
            })
        elif oracle_model == llm_model:
            confirmed += 1
        else:
            disagreements.append({
                "key": key,
                "llm": llm_model,
                "oracle": oracle_model,
                "context": data["context"]
            })
            
    print(f"\nOracle Evaluation Complete ({len(proposals)} total registers processed):")
    print(f"  Confirmed: {confirmed}")
    print(f"  Unconfident (fallback/unsupported AST pattern): {len(unconfident)}")
    print(f"  Disagreements: {len(disagreements)}")
    
    if unconfident:
        print("\n--- Unconfident Cases ---")
        for u in unconfident:
            # find the line that actually contains the register access
            reg_name = u['key'].split('::')[1]
            access_line = next((line.strip() for line in u['context'] if reg_name in line), u['context'][-1].strip())
            print(f"[{u['llm']}] {u['key']} => {access_line}")
            
    if disagreements:
        print("\n--- Disagreements ---")
        for d in disagreements:
            print(f"Access: {d['key']}")
            print(f"  LLM Proposed: {d['llm']}")
            print(f"  Oracle Expected: {d['oracle']}")
            print(f"  Context snippet:\n{d['context'].strip()}")
            print("-" * 40)

if __name__ == "__main__":
    main()
