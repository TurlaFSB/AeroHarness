import os
import sys
from pathlib import Path
sys.path.insert(0, r"D:\aeroharness")

from src.analyzer.c_ast_extractor import CASTExtractor
from src.analyzer.call_graph import CallGraphBuilder
from src.analyzer.dict_generator import DictionaryGenerator
from src.synthesizer.agent import HarnessSynthesizerAgent, SynthesisCandidate
from src.synthesizer.mmio_stubber import MMIOStubber, MockStubConfig
from src.oracle.compiler_oracle import CompilerOracle
from src.oracle.repair_loop import SelfRepairOrchestrator
from src.fuzzer.runner import FuzzingCampaignRunner
from src.fuzzer.triager import CrashTriager, CrashStackFrame
from benchmarks.eval_metrics import BenchmarkMetrics

# 1. AST Parser
dummy_c = Path("dummy.c")
dummy_c.write_text("""
#define MAGIC 0xA55A
#define REG_STATUS 0x40001000
typedef struct { int a; } my_ctx;
void target_func(my_ctx *ctx, uint8_t *data, size_t len) {
    memcpy(ctx, data, len);
}
""")
extractor = CASTExtractor()
ctx = extractor.extract_from_header(dummy_c)
print("--- 1,3 AST ---")
print("Funcs:", [f.name for f in ctx.functions])
print("Magic:", ctx.magic_constants)
print("MMIO:", [(r.name, r.address) for r in ctx.mmio_registers])

# 2. Risk
cg = CallGraphBuilder()
risk = cg.analyze_source_file(dummy_c, ["target_func"])
print("--- 2 RISK ---")
print(risk.get("target_func"))

# 4. Dict
dg = DictionaryGenerator()
d = dg.generate_dictionary_from_files([dummy_c], Path("dummy.dict"))
print("--- 4 DICT ---")
print(d.tokens)

# 6. MMIO Stubber
stubber = MMIOStubber()
print("--- 6 MMIO ---")
print(stubber.generate_mmio_stubs(ctx.mmio_registers))

# 11. Triager Dedup
t = CrashTriager()
hash = t.compute_crash_hash("heap-buffer-overflow", [CrashStackFrame(frame_index=0, function_name="foo", line_number=10)])
print("--- 11 DEDUP ---")
print(hash)

# 13. Metrics
m = BenchmarkMetrics()
print("--- 13 METRICS ---")
print(m.compute_summary([]))
