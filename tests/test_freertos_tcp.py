"""
Unit tests for FreeRTOS-Plus-TCP Target Extraction and Ingestion
"""
from pathlib import Path
from src.analyzer.c_ast_extractor import CASTExtractor
from src.analyzer.call_graph import CallGraphBuilder


def test_freertos_ip_extraction():
    ip_header = Path("D:/aeroharness/targets/freertos_tcp/include/FreeRTOS_IP.h")
    extractor = CASTExtractor()
    context = extractor.extract_from_header(ip_header)

    func_names = [f.name for f in context.functions]
    assert "FreeRTOS_IPInit" in func_names
    assert "prvProcessIPPacket" in func_names
    assert "xProcessReceivedUDPPacket" in func_names

    struct_names = [s.name for s in context.structs]
    assert "IPPacket_t" in struct_names
    assert "NetworkBufferDescriptor_t" in struct_names


def test_freertos_dns_extraction_and_risk():
    dns_header = Path("D:/aeroharness/targets/freertos_tcp/include/FreeRTOS_DNS.h")
    dns_source = Path("D:/aeroharness/targets/freertos_tcp/source/FreeRTOS_DNS.c")

    extractor = CASTExtractor()
    context = extractor.extract_from_header(dns_header)

    func_names = [f.name for f in context.functions]
    assert "prvParseDNSReply" in func_names

    cg_builder = CallGraphBuilder()
    risk_scores = cg_builder.analyze_source_file(dns_source, func_names)

    assert "prvParseDNSReply" in risk_scores
    score = risk_scores["prvParseDNSReply"]
    assert score.risk_score > 5.0  # DNS parsing contains complex loops and memcpy
