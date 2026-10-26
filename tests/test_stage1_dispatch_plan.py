"""Tests for stage1_dispatch_plan.py (work plan item 11): Stage 1 ordering edges -> dispatcher plan."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import stage1_dispatch_plan as sdp  # noqa: E402

DRIVER = ROOT / "zephyr-src" / "drivers" / "serial" / "uart_pl011.c"


def _fake_ast():
    dev = {"name": "dev", "type": "const struct device *", "is_pointer": True}
    byte = {"name": "c", "type": "unsigned char", "is_pointer": False}
    ptr = {"name": "c", "type": "unsigned char *", "is_pointer": True}
    arr = {"name": "t", "type": "const int *", "is_pointer": True}
    return {
        "functions": {
            "drv_init": {"params": [dev], "mmio_accesses": []},
            "drv_out": {"params": [dev, byte], "mmio_accesses": [{"register": "fr", "access_type": "read"}]},
            "drv_in": {"params": [dev, ptr], "mmio_accesses": [{"register": "dr", "access_type": "read"}]},
            "drv_fill": {"params": [dev, arr], "mmio_accesses": []},
            "drv_other": {"params": [dev], "mmio_accesses": []},
        },
        "ordering_edges": [
            {"before": "drv_init", "after": n, "kind": "framework_init_before_api", "evidence": f"{n} in API table"}
            for n in ("drv_out", "drv_in", "drv_fill")
        ] + [{"before": "drv_out", "after": "drv_in", "kind": "register_dataflow", "via_registers": ["dr"]}],
    }


def test_plan_gates_only_on_framework_edges_and_reports_skips():
    plan = sdp.build_plan(_fake_ast(), ["drv_out", "drv_in", "drv_fill", "drv_other", "missing"])
    assert plan["prerequisite"] == "drv_init"
    assert [g["name"] for g in plan["gated"]] == ["drv_out", "drv_in"]
    reasons = {s["name"]: s["reason"] for s in plan["skipped"]}
    assert "unsupported parameter" in reasons["drv_fill"]
    assert "no framework edge" in reasons["drv_other"]
    assert "not in Stage 1" in reasons["missing"]


def test_register_dataflow_edges_do_not_create_a_prerequisite():
    ast = _fake_ast()
    ast["ordering_edges"] = [e for e in ast["ordering_edges"] if e["kind"] == "register_dataflow"]
    with pytest.raises(SystemExit):
        sdp.build_plan(ast, ["drv_out"])


def test_chain_gates_calls_on_init_and_skips_scaffold_registers():
    plan = sdp.build_plan(_fake_ast(), ["drv_out", "drv_in"])
    chain = sdp.emit_chain(plan, skip_regs=frozenset({"fr"}))
    assert "if (cmd == 0) {" in chain and "drv_init(&dev);" in chain
    assert chain.count("&& is_initialized") == 2
    assert "regs.fr" not in chain          # scaffold already seeds (and constrains) fr
    assert "regs.dr = data[i+1];" in chain  # not seeded by the scaffold in this case
    assert "drv_out(&dev, data[++i]);" in chain
    assert "drv_in(&dev, &out1);" in chain


@pytest.mark.skipif(not DRIVER.exists(), reason="vendored zephyr-src not present")
def test_real_pl011_plan(tmp_path):
    pytest.importorskip("clang.cindex")
    r = subprocess.run([sys.executable, str(ROOT / "stage1_ast_parser.py"), str(DRIVER)],
                       cwd=tmp_path, capture_output=True, text=True)
    if r.returncode != 0 or not (tmp_path / "ast_output.json").exists():
        pytest.skip("Stage 1 could not run here: " + r.stderr[-200:])
    import json
    ast = json.load(open(tmp_path / "ast_output.json"))
    plan = sdp.build_plan(ast, ["pl011_poll_out", "pl011_poll_in", "pl011_isr"])
    assert plan["prerequisite"] == "pl011_init"
    assert [g["name"] for g in plan["gated"]] == ["pl011_poll_out", "pl011_poll_in", "pl011_isr"]
    isr = next(g for g in plan["gated"] if g["name"] == "pl011_isr")
    assert set(isr["seed_registers"]) == {"imsc", "mis"}
    assert not plan["skipped"]
