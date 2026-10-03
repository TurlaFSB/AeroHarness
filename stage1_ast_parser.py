import os
import re
import sys
import json
import clang.cindex
from clang.cindex import CursorKind, TokenKind

_CLANG_ARGS = [
    '-x', 'c',
    '-DCONFIG_UART_INTERRUPT_DRIVEN=1',
    '-DCONFIG_UART_USE_RUNTIME_CONFIGURE=1',
    '-DCONFIG_PINCTRL=1',
    '-DCONFIG_RESET=1',
    '-DCONFIG_CLOCK_CONTROL=1',
    '-DCONFIG_UART_PL011_SBSA=1',
    '-DDT_ANY_COMPAT_HAS_PROP_STATUS_OKAY(a,b)=1',
    '-DCPU_FAM_STM32F1=1'
]

_TYPE_SUFFIXES = ('_regs', '_TypeDef', '_Type', '_t')
_SKIP_QUALIFIERS = ('*', 'const', 'volatile', '__IO', 'struct')


def _scan_tokens_for_mmio_bases(all_tokens):
    """
    Shared with analyze_ast's own main-file scan (Oct 3 2026 fix, see
    _collect_local_header_mmio_bases below for why this was extracted). Scans a token
    stream for `<TYPE_SUFFIX> [qualifiers] <name>` patterns and returns the set of names
    found -- works identically whether `name` turns out to be a variable (the original,
    sole use case) or a function (the new case this fix adds), since the token pattern
    itself doesn't distinguish the two: `volatile struct pl011_regs *uart = ...` and
    `volatile struct pl011_regs *get_uart(...)` differ only in what comes after `name`,
    which this loop never looks at.
    """
    bases = set()
    for i in range(len(all_tokens) - 2):
        t = all_tokens[i].spelling
        if t.endswith(_TYPE_SUFFIXES):
            j = i + 1
            while j < len(all_tokens) and all_tokens[j].spelling in _SKIP_QUALIFIERS:
                j += 1
            if j < len(all_tokens):
                name = all_tokens[j].spelling
                if name.isidentifier():
                    bases.add(name)
    return bases


def _collect_local_header_mmio_bases(filename):
    """
    NOTE (Oct 3 2026, item 12 investigation -- "53 vs 42" reproducibility bug): root-caused
    why a fresh run of this script against uart_pl011.c only finds 42 of the real 53 MMIO
    accesses the committed llm_proposals.json has. All 11 missing accesses are the exact
    same pattern: `get_uart(dev)->reg` (a helper-FUNCTION call whose return type is the
    MMIO struct pointer), as opposed to a bare struct-typed local variable. The existing
    mmio_bases scan (now _scan_tokens_for_mmio_bases) only ever saw `get_uart` as a base
    when some OTHER line in the same file happened to re-spell `volatile struct pl011_regs
    *uart = get_uart(dev)` -- it had no way to learn `get_uart`'s own return type, because
    `get_uart`'s actual declaration lives in `uart_pl011_registers.h` (included via `#include
    "uart_pl011_registers.h"`), and confirmed directly: `tu.cursor.get_tokens()` on the
    *main* file's parse NEVER includes any token from an included header file, regardless of
    whether that header resolves successfully -- this is `cursor.get_tokens()`'s normal
    scope, not a parse failure. (Separately confirmed: trying to fix this by pointing a full
    `-I zephyr-src/include` at the real Zephyr tree instead cascades into dozens of missing
    `CONFIG_*`/arch defines this project doesn't otherwise need -- not worth it just for this.)

    Fixed by parsing each of the main file's own local, quote-style `#include "X.h"` headers
    (same directory) as its OWN standalone translation unit -- confirmed this lets
    `uart_pl011_registers.h` contribute `get_uart` to mmio_bases even though its own single
    remaining dependency (`zephyr/device.h`) still 404s: a `TranslationUnit.diagnostics`
    fatal doesn't stop clang's *lexer* from tokenizing the rest of that file's own text, only
    from pulling in further headers -- exactly the same resilience the main-file parse
    already relied on. Returns the union of mmio_bases found in each resolvable local header,
    to be merged into the main file's own mmio_bases before the main accesses-scan runs.
    """
    bases = set()
    try:
        with open(filename, "r", encoding="utf-8", errors="replace") as f:
            source_text = f.read()
    except OSError:
        return bases

    source_dir = os.path.dirname(os.path.abspath(filename))
    for match in re.finditer(r'^\s*#\s*include\s*"([^"]+)"', source_text, re.MULTILINE):
        header_name = match.group(1)
        header_path = os.path.join(source_dir, header_name)
        if not os.path.isfile(header_path):
            continue  # a quote-include that isn't a local sibling file -- nothing to add
        try:
            header_index = clang.cindex.Index.create()
            header_tu = header_index.parse(
                header_path, args=['-x', 'c'],
                options=clang.cindex.TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD
            )
            header_tokens = list(header_tu.cursor.get_tokens())
            bases |= _scan_tokens_for_mmio_bases(header_tokens)
        except clang.cindex.TranslationUnitLoadError:
            continue  # a header too broken to even lex at all -- skip it, don't abort Stage 1
    return bases

def traverse(node, functions, mmio_bases, current_func=None):
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
                    is_mmio = False
                    lhs = tokens[i-1].spelling
                    if lhs == ')':
                        paren_count = 1
                        k = i - 2
                        while k >= 0 and paren_count > 0:
                            if tokens[k].spelling == ')': paren_count += 1
                            elif tokens[k].spelling == '(': paren_count -= 1
                            k -= 1
                        if k >= 0 and tokens[k].kind == TokenKind.IDENTIFIER:
                            lhs = tokens[k].spelling
                            
                    if lhs in mmio_bases or (lhs.isupper() and len(lhs) >= 2):
                        is_mmio = True
                        
                    if not is_mmio:
                        continue
                        
                    if tokens[i+1].kind == TokenKind.IDENTIFIER:
                        reg_name = tokens[i+1].spelling
                        access_type = "read"
                        if i + 2 < len(tokens):
                            next_token = tokens[i+2].spelling
                            if next_token == '=':
                                access_type = "write"
                            elif next_token in ('|=', '&=', '^=', '<<=', '>>=', '++', '--'):
                                access_type = "read-modify-write"
                                
                        functions[current_func]["mmio_accesses"].append({
                            "register": reg_name,
                            "line": tokens[i+1].location.line,
                            "method": "heuristic",
                            "access_type": access_type
                        })
                elif tokens[i].kind == TokenKind.IDENTIFIER and tokens[i+1].kind == TokenKind.PUNCTUATION and tokens[i+1].spelling == '(':
                    if tokens[i].spelling not in functions[current_func]["calls"] and tokens[i].spelling != current_func:
                        functions[current_func]["calls"].append(tokens[i].spelling)

    if current_func:
        if node.kind == CursorKind.CALL_EXPR:
            if node.spelling and node.spelling not in functions[current_func]["calls"]:
                functions[current_func]["calls"].append(node.spelling)
        
    for child in node.get_children():
        traverse(child, functions, mmio_bases, current_func)

def analyze_ast(filename):
    clang.cindex.Config.set_library_file('/usr/lib/llvm-18/lib/libclang.so')
    index = clang.cindex.Index.create()

    tu = index.parse(filename, args=_CLANG_ARGS,
                      options=clang.cindex.TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD)

    constants = []
    functions = {}

    for cursor in tu.cursor.get_children():
        if cursor.kind == CursorKind.MACRO_DEFINITION:
            if cursor.location.file and cursor.location.file.name == filename:
                constants.append(cursor.spelling)

    all_tokens = list(tu.cursor.get_tokens())
    mmio_bases = _scan_tokens_for_mmio_bases(all_tokens)
    # Oct 3 2026 fix (item 12): also pick up getter-FUNCTION accessors (e.g. `get_uart`)
    # whose return type is only declared in a local #include'd header -- see
    # _collect_local_header_mmio_bases's docstring for why the main-file token scan above
    # can never see these on its own.
    mmio_bases |= _collect_local_header_mmio_bases(filename)

    traverse(tu.cursor, functions, mmio_bases)
    
    for f in functions.values():
        unique_mmio = []
        seen = {}
        for m in f["mmio_accesses"]:
            key = f"{m['register']}:{m['line']}"
            if key not in seen:
                seen[key] = m
                if "access_type" not in m:
                    seen[key]["access_type"] = "read"
            else:
                if "access_type" in m and m["access_type"] != "read":
                    seen[key]["access_type"] = m["access_type"]
        f["mmio_accesses"] = list(seen.values())
        
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
        "ordering_edges": _compute_ordering_edges(functions),
        "extraction_warnings": [d.spelling for d in tu.diagnostics if d.severity >= 3]
    }

    with open("ast_output.json", "w") as f:
        json.dump(output, f, indent=2)


def _compute_ordering_edges(functions):
    """
    Work Plan item 11 (Oct 3 2026): Objective 1 claims call graphs are used to "deduce...
    mock hardware configurations," but `ARCHITECTURE.md` already honestly documents that the
    one place this is actually exercised end to end (the state-machine dispatcher harness,
    `fuzz_state_machine.c`) got its `pl011_init()`-must-run-first ordering from a human
    reading function NAMES, not from anything Stage 1 itself derived -- "the call graph had
    no ordering constraints to use." The existing `calls` list (direct CALL_EXPR edges) is
    real, but useless for this specific case: `pl011_init`, `pl011_poll_in`, `pl011_poll_out`
    and `pl011_isr` never call each other at all -- their real dependency is that they all
    touch the SAME device's hardware registers, not that one invokes another.

    This infers a genuine, data-grounded ordering constraint from exactly that: for every
    register R, if function A's only access to R is a `write` or `read-modify-write` and
    function B's access to R is a plain `read` (never writing it), emit a `before` edge
    A -> B, justified by "B reads a register that only A (among the analyzed functions)
    ever writes." This is no longer naming-convention-derived -- it comes straight from the
    `mmio_accesses` data this file already extracts (and, since the Oct 3 2026 item-12 fix,
    now extracts far more completely).

    Verified directly against `uart_pl011.c` (Oct 3 2026) -- and the actual output does NOT
    fully match what an earlier draft of this docstring claimed, which is recorded here
    rather than silently corrected, per this project's own "verify independently, don't
    trust prior notes (including your own)" discipline:

    - It DOES recover `pl011_init -> pl011_irq_rx_ready` and `pl011_init -> pl011_irq_tx_ready`
      (via `cr`/`imsc`), and `pl011_isr -> pl011_irq_rx_ready`/`pl011_irq_tx_ready` (via `imsc`)
      -- real, data-grounded config/status-handshake dependencies that the old naming-only
      approach could not have stated with any evidence at all.
    - It does NOT recover `pl011_init` as a prerequisite of `pl011_poll_in`, `pl011_poll_out`,
      or `pl011_isr` directly -- which is the specific edge `fuzz_state_machine.c` actually
      hand-codes. The reason is structural, not a tuning bug: `pl011_init`'s only overlap with
      `cr`/`imsc` is a read-modify-write (it flips the UARTEN/interrupt-mask bits of a register
      it also has to read first), so under this heuristic's rule it only ever counts as a
      *writer*, never a *reader* -- and `pl011_poll_in`/`pl011_poll_out`/`pl011_isr` never touch
      `cr` at all, so there is no shared register, write-then-read or otherwise, connecting them
      to `pl011_init` in the extracted data. The real dependency ("UART must be enabled before
      you poll it") is an implicit hardware *enable-flag* semantic, not a shared-register access
      pattern -- so register-co-access analysis is the wrong tool to recover this specific edge,
      not an edge case this implementation got wrong. This is reported as a genuine open gap,
      not patched over by special-casing `cr`/UARTEN, which would just be a new naming guess
      wearing this function's clothes.
    - The predicted false positive DOES appear as predicted: `pl011_poll_out -> pl011_poll_in`
      via `dr` (`pl011_fifo_fill -> pl011_fifo_read`/`pl011_poll_in` likewise) -- `dr` is a
      single address that is actually two different physical registers depending on direction
      (RX read-path vs TX write-path on real PL011 hardware), not a shared configuration/status
      register, so "poll_out before poll_in" is not a real prerequisite at all. This function
      has no way to generically distinguish a bidirectional data register from a real
      state/config register from the AST alone, so its output is a set of CANDIDATE ordering
      edges for a human (or a downstream consumer) to sanity-check, not a guaranteed-correct
      final ordering.

    Net honest claim for the paper: this closes part of the naming-convention gap (some real,
    previously-unstated dependencies are now data-grounded) but does NOT fully replace the
    hand-coded `pl011_init`-first assumption in the dispatcher harness, which still rests on a
    human reading function names for that specific edge. `ARCHITECTURE.md` should keep saying
    so rather than being updated to claim this is solved.
    """
    writers = {}  # register -> set of function names that write or RMW it
    readers = {}  # register -> set of function names whose ONLY access to it is a plain read

    for fn_name, fdata in functions.items():
        for acc in fdata.get("mmio_accesses", []):
            reg = acc["register"]
            is_write = acc.get("access_type") in ("write", "read-modify-write")
            if is_write:
                writers.setdefault(reg, set()).add(fn_name)
            else:
                readers.setdefault(reg, set()).add(fn_name)

    edges = {}  # (before, after) -> set of registers justifying the edge
    for reg in set(writers) | set(readers):
        for w in writers.get(reg, ()):
            for r in readers.get(reg, ()):
                if w == r:
                    continue
                # Only a genuine prerequisite if r never ALSO writes this register itself
                # (a function that both reads and writes the same register is managing its
                # own state, not depending on w for it).
                if r in writers.get(reg, ()):
                    continue
                edges.setdefault((w, r), set()).add(reg)

    return [
        {"before": w, "after": r, "via_registers": sorted(regs)}
        for (w, r), regs in sorted(edges.items())
    ]


if __name__ == "__main__":
    analyze_ast(sys.argv[1])
