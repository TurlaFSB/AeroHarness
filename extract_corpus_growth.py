import re

log_content = """INFO: Running with entropic power schedule (0xFF, 100).
INFO: Seed: 3232748249
INFO: Loaded 1 modules   (24 inline 8-bit counters): 24 [0x646489d890b8, 0x646489d890d0), 
INFO: Loaded 1 PC tables (24 PCs): 24 [0x646489d890d0,0x646489d89250), 
INFO: -max_len is not provided; libFuzzer will not generate inputs larger than 4096 bytes
INFO: A corpus is not provided, starting from an empty corpus
#2	INITED cov: 2 ft: 2 corp: 1/1b exec/s: 0 rss: 31Mb
	NEW_FUNC[1/2]: 0x646489d3af70 in pl011_isr(device const*) /mnt/d/aeroharness/harnesses/fuzz_pl011_isr.cpp:51
	NEW_FUNC[2/2]: 0x646489d3b430 in get_uart(device const*) /mnt/d/aeroharness/harnesses/../zephyr-src/drivers/serial/uart_pl011_registers.h:41
#32	NEW    cov: 8 ft: 9 corp: 2/4b lim: 4 exec/s: 0 rss: 32Mb L: 3/3 MS: 5 CrossOver-CopyPart-ShuffleBytes-ShuffleBytes-CrossOver-
#44	NEW    cov: 11 ft: 12 corp: 3/7b lim: 4 exec/s: 0 rss: 32Mb L: 3/3 MS: 2 ShuffleBytes-ChangeBinInt-
#59	NEW    cov: 12 ft: 13 corp: 4/10b lim: 4 exec/s: 0 rss: 32Mb L: 3/3 MS: 5 ChangeBit-EraseBytes-ChangeBinInt-ChangeBit-CrossOver-
	NEW_FUNC[1/1]: 0x646489d3af30 in dummy_irq_cb(device const*, void*) /mnt/d/aeroharness/harnesses/fuzz_pl011_isr.cpp:82
#95	NEW    cov: 16 ft: 17 corp: 5/13b lim: 4 exec/s: 0 rss: 32Mb L: 3/3 MS: 1 ChangeBit-
#2097152	pulse  cov: 16 ft: 17 corp: 5/13b lim: 4096 exec/s: 699050 rss: 191Mb
#4194304	pulse  cov: 16 ft: 17 corp: 5/13b lim: 4096 exec/s: 599186 rss: 349Mb
#8388608	pulse  cov: 16 ft: 17 corp: 5/13b lim: 4096 exec/s: 599186 rss: 601Mb
#16777216	pulse  cov: 16 ft: 17 corp: 5/13b lim: 4096 exec/s: 645277 rss: 603Mb
#33554432	pulse  cov: 16 ft: 17 corp: 5/13b lim: 4096 exec/s: 729444 rss: 603Mb
#44583870	DONE   cov: 16 ft: 17 corp: 5/13b lim: 4096 exec/s: 730883 rss: 603Mb
Done 44583870 runs in 61 second(s)
"""

# We want lines starting with #<number> and containing INITED or NEW or REDUCE
pattern = re.compile(r'^#(\d+)\s+(INITED|NEW|REDUCE).*?cov:\s*(\d+)\s+ft:\s*(\d+)\s+corp:\s*(\d+)/\d+b', re.MULTILINE)

data = []
for match in pattern.finditer(log_content):
    exec_count = int(match.group(1))
    ft_count = int(match.group(4))
    corp_size = int(match.group(5))
    data.append((exec_count, corp_size, ft_count))

print("| Execution Count | Corpus Size | Coverage Features (ft) | Gap to Next (Execs) |")
print("| :--- | :--- | :--- | :--- |")

gaps = []
for i in range(len(data)):
    exec_count, corp_size, ft_count = data[i]
    if i == 0:
        gap = exec_count # from 0 to first INITED
    else:
        gap = exec_count - data[i-1][0]
    gaps.append(gap)
    print(f"| {exec_count} | {corp_size} | {ft_count} | {gap} |")

print()
if len(gaps) > 1:
    avg_gap = sum(gaps[1:]) / (len(gaps) - 1)
    max_gap = max(gaps[1:])
    print(f"Average time-to-new-path (after INITED): {avg_gap:.1f} executions")
    print(f"Maximum time-to-new-path (after INITED): {max_gap} executions")
else:
    print("Not enough NEW events to compute gaps.")
print("\nNote: libFuzzer does not reliably log per-event wall-clock timestamps in its standard stdout formatting. Thus, time-to-new-path is strictly measured in execution iterations.")

with open('corpus_growth_analysis.md', 'w') as f:
    f.write("# Corpus Growth and Time-to-New-Path Analysis\n\n")
    f.write("Extracted from the `fuzz_pl011_isr` coverage fuzzing session (Task 2).\n\n")
    
    f.write("## Event Log\n")
    f.write("| Execution Count | Corpus Size | Coverage Features (ft) | Gap to Previous Event (Execs) |\n")
    f.write("| :--- | :--- | :--- | :--- |\n")
    for i in range(len(data)):
        exec_count, corp_size, ft_count = data[i]
        gap = gaps[i]
        f.write(f"| {exec_count} | {corp_size} | {ft_count} | {gap} |\n")
    
    f.write("\n## Time-to-New-Path Statistics\n")
    if len(gaps) > 1:
        f.write(f"* **Average gap between discoveries:** {avg_gap:.1f} executions\n")
        f.write(f"* **Maximum gap (longest dry spell):** {max_gap} executions\n")
        
    f.write("\n*Limitation Note: libFuzzer does not output precise wall-clock timestamps per NEW event in standard logs. Thus, time-to-new-path is fundamentally measured in execution units rather than wall-clock seconds. Given the execution rate of ~730,000 execs/sec in this run, the maximum gap of 36 executions translates to approximately 0.05 milliseconds of wall-clock time.*")
