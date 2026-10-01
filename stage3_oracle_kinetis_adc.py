# Stage 3 oracle run for the second-RTOS/target pipeline (Section B item 3,
# Oct 1 2026): kinetis_adc_calibrate (RIOT OS, Kinetis K64F ADC driver).
# Reuses the EXACT same deterministic AST-pattern-matching algorithm as
# stage3_oracle_multi.py (get_ast_context / analyze_access), just pointed at
# this new proposals file, so Stage 3 verification methodology is identical
# to the rest of the project -- not a new ad hoc checker.
import sys
import json
import clang.cindex
from clang.cindex import CursorKind, TokenKind

clang.cindex.Config.set_library_file('/usr/lib/llvm-18/lib/libclang.so')


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
    print("Initializing simplified static-AST oracle (kinetis_adc_calibrate run)")
    index = clang.cindex.Index.create()

    with open("llm_proposals_kinetis_adc_calibrate.json") as f:
        proposals = json.load(f)

    confirmed = 0
    disagreements = []
    unconfident = []

    tus = {}
    for key, data in proposals.items():
        if data["model"] == "not_applicable_write_only":
            confirmed += 1
            print(f"  {data['register']:6s} @ line {data['line']:4d}: not_applicable_write_only -> CONFIRMED (auto)")
            continue

        source_file = data["source"]
        if source_file not in tus:
            tus[source_file] = index.parse(source_file, args=[
                '-x', 'c',
            ], options=clang.cindex.TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD)

        parents = get_ast_context(tus[source_file].cursor, data["line"], data["register"])
        oracle_model = analyze_access(parents)

        if oracle_model == "unconfident":
            unconfident.append(key)
            print(f"  {data['register']:6s} @ line {data['line']:4d}: proposed={data['model']:12s} oracle=unconfident -> UNCONFIDENT")
        elif oracle_model == data["model"]:
            confirmed += 1
            print(f"  {data['register']:6s} @ line {data['line']:4d}: proposed={data['model']:12s} oracle={oracle_model:12s} -> CONFIRMED")
        else:
            disagreements.append(key)
            print(f"  {data['register']:6s} @ line {data['line']:4d}: proposed={data['model']:12s} oracle={oracle_model:12s} -> DISAGREEMENT")

    print()
    print(f"Oracle Evaluation Complete ({len(proposals)} total registers processed):")
    print(f"  Confirmed: {confirmed}")
    print(f"  Unconfident (fallback/unsupported AST pattern): {len(unconfident)}")
    print(f"  Disagreements: {len(disagreements)}")


if __name__ == "__main__":
    main()
