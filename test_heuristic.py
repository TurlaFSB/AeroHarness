import clang.cindex
from clang.cindex import CursorKind

clang.cindex.Config.set_library_file('/usr/lib/llvm-18/lib/libclang.so')
index = clang.cindex.Index.create()

def test_file(filename):
    print(f"Testing {filename}")
    tu = index.parse(filename, args=['-x', 'c'])
    
    # 1. Identify MMIO base names (variables, functions, macros)
    # We will just scan all tokens in the file.
    mmio_bases = set()
    
    tokens = list(tu.get_tokens(extent=tu.cursor.extent))
    
    # Heuristics for MMIO type names:
    # 1. Ends with _regs (Zephyr)
    # 2. Ends with _TypeDef (CMSIS)
    
    # Let's find functions or variables declared with these types.
    for i in range(len(tokens) - 2):
        t = tokens[i].spelling
        if t.endswith('_regs') or t.endswith('_TypeDef'):
            # Look ahead to find the variable/function name
            # Pattern: struct xxx_regs * varname
            # Pattern: xxx_TypeDef * varname
            # Or inline xxx_TypeDef * dev(...)
            j = i + 1
            while j < len(tokens) and tokens[j].spelling in ['*', 'const', 'volatile']:
                j += 1
            if j < len(tokens):
                name = tokens[j].spelling
                if name.isidentifier():
                    mmio_bases.add(name)
    
    # Macros like RCC?
    # Macros are harder because they are replaced. But wait, in the AST tokens they might just be expanded or unexpanded.
    # Actually, in P2IM, a lot of MMIO accesses use global macros like `RCC->...` or `GPIOA->...`
    # Let's add any all-caps token before `->` as a potential MMIO base if it's not followed by a known software struct.
    
    print(f"Discovered MMIO bases: {mmio_bases}")
    
    # 2. Find accesses
    accesses = 0
    for i in range(len(tokens) - 1):
        if tokens[i].spelling in ['->', '.']:
            lhs = tokens[i-1].spelling
            if lhs == ')':
                # e.g. dev(uart)->CR1
                # backtrack to find the function name
                paren_count = 1
                k = i - 2
                while k >= 0 and paren_count > 0:
                    if tokens[k].spelling == ')': paren_count += 1
                    elif tokens[k].spelling == '(': paren_count -= 1
                    k -= 1
                if k >= 0:
                    lhs = tokens[k].spelling
            
            if lhs in mmio_bases or (lhs.isupper() and len(lhs) >= 3):  # RCC, GPIOA
                rhs = tokens[i+1].spelling
                # print(f"Found access: {lhs}->{rhs}")
                accesses += 1
    print(f"Total accesses found: {accesses}\n")

test_file("uart_pl011.c")
test_file("p2im-unit_tests/RIOT/RIOT-ENV/cpu/stm32_common/periph/uart.c")
