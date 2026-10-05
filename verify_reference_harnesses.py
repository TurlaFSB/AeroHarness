"""Scaffold-solvability check for Ablation G.

Builds one hand-written reference harness per target, appends the target function exactly as
run_ablation_g.py does, compiles with the same clang++ flags, and runs libFuzzer for 1 second.
If all five compile and exit 0, the build scaffold itself is solvable, so a 0% success rate
cannot be blamed on the headers. Run from the repo root: python3 verify_reference_harnesses.py
"""
import sys,re,os,subprocess,tempfile
REPO=os.path.dirname(os.path.abspath(__file__)); os.chdir(REPO)
OUT=tempfile.mkdtemp(prefix='ref_harness_')
sys.argv=['x','--analyze-only']
src=open('run_ablation_g.py').read().split('def evaluate_harness')[0]
g={'__file__':os.path.join(REPO,'run_ablation_g.py'),'__name__':'x'}
try: exec(compile(src,'g','exec'),g)
except SystemExit: pass
T=g['TARGETS']
HDR="""#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <errno.h>
#include <zephyr/device.h>
#include <zephyr/drivers/serial/uart_pl011_registers.h>
"""
R={}
R['pl011_poll_in']=HDR+"""static int pl011_poll_in(const struct device *dev, unsigned char *c);
static struct pl011_regs mock_regs;
extern "C" int LLVMFuzzerTestOneInput(const uint8_t *d, size_t n){
  if(n<sizeof(mock_regs)) return 0;
  memcpy(&mock_regs,d,sizeof(mock_regs));
  struct device dev; dev.config=nullptr; dev.data=nullptr; dev.mmio_base=&mock_regs;
  unsigned char c; pl011_poll_in(&dev,&c); return 0; }
"""
R['pl011_poll_out']=HDR+"""static void pl011_poll_out(const struct device *dev, unsigned char c);
static struct pl011_regs mock_regs;
extern "C" int LLVMFuzzerTestOneInput(const uint8_t *d, size_t n){
  if(n<sizeof(mock_regs)+1) return 0;
  memcpy(&mock_regs,d,sizeof(mock_regs));
  mock_regs.fr &= ~PL011_FR_TXFF;
  struct device dev; dev.config=nullptr; dev.data=nullptr; dev.mmio_base=&mock_regs;
  pl011_poll_out(&dev,d[sizeof(mock_regs)]); return 0; }
"""
R['pl011_isr']="#include <zephyr/kernel.h>\n"+HDR+"""struct pl011_data { void (*irq_cb)(const struct device*, void*); void *irq_cb_data; k_spinlock_t irq_cb_lock; };
static void pl011_isr(const struct device *dev);
static struct pl011_regs mock_regs; static struct pl011_data pd;
static void cb(const struct device*, void*){}
extern "C" int LLVMFuzzerTestOneInput(const uint8_t *d, size_t n){
  if(n<sizeof(mock_regs)+1) return 0;
  memcpy(&mock_regs,d,sizeof(mock_regs));
  pd.irq_cb = (d[sizeof(mock_regs)]&1)? cb : nullptr;
  struct device dev; dev.config=nullptr; dev.data=&pd; dev.mmio_base=&mock_regs;
  pl011_isr(&dev); return 0; }
"""
R['pl011_runtime_configure_internal']="#include <zephyr/drivers/uart.h>\n"+HDR+"""static int pl011_runtime_configure_internal(const struct device *dev, const struct uart_config *cfg);
static void pl011_set_baudrate(const struct device *dev, uint32_t b){(void)dev;(void)b;}
static void pl011_set_flow_control(const struct device *dev, bool e){(void)dev;(void)e;}
static struct pl011_regs mock_regs;
extern "C" int LLVMFuzzerTestOneInput(const uint8_t *d, size_t n){
  struct uart_config cfg;
  if(n<sizeof(cfg)) return 0;
  memcpy(&cfg,d,sizeof(cfg));
  struct device dev; dev.config=nullptr; dev.data=nullptr; dev.mmio_base=&mock_regs;
  pl011_runtime_configure_internal(&dev,&cfg); return 0; }
"""
R['pl011_init']=HDR+"""struct pl011_config { uint32_t sys_clk; };
struct pl011_data { bool sbsa; uint32_t baud_rate; };
static int pl011_init(const struct device *dev);
static void pl011_set_baudrate(const struct device *dev, uint32_t b){(void)dev;(void)b;}
static struct pl011_regs mock_regs; static struct pl011_config pc; static struct pl011_data pd;
extern "C" int LLVMFuzzerTestOneInput(const uint8_t *d, size_t n){
  if(n<9) return 0;
  pc.sys_clk=d[0]; pd.sbsa=d[1]&1; pd.baud_rate=d[2];
  struct device dev; dev.config=&pc; dev.data=&pd; dev.mmio_base=&mock_regs;
  pl011_init(&dev); return 0; }
"""
for k,h in R.items():
    code=h+"\n// === APPENDED TARGET FUNCTION ===\n"+re.search(r'```c\n(.*?)```',T[k],re.S).group(1)
    d=os.path.join(OUT,k); os.makedirs(d,exist_ok=True)
    open(d+'/harness.cpp','w').write(code)
    c=subprocess.run(['clang++','-fsanitize=fuzzer,address','-O1','-fno-inline','-I'+os.path.join(REPO,'harnesses','include'),'-I'+REPO,'harness.cpp','-o','fuzz_bin'],cwd=d,capture_output=True,text=True)
    if c.returncode: print(k,'COMPILE FAIL\n',c.stderr[:1500]); continue
    try:
        r=subprocess.run(['./fuzz_bin','-max_total_time=1','-timeout=2'],cwd=d,capture_output=True,text=True,timeout=10)
        cov=[l for l in r.stderr.split('\n') if 'cov:' in l]
        print(k,'rc',r.returncode, cov[-1][:80] if cov else r.stderr[-300:])
    except Exception as e: print(k,'run exc',e)
