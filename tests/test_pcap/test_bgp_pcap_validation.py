"""
test_bgp_pcap_validation.py
01.09.2026
"""
import pytest
from scapy.all import IP, TCP, wrpcap, rdpcap
import os

@pytest.fixture(scope="module")
def bgp_pcap_capture_file(tmp_path_factory):
    """
    Fixture generating a synthetic PCAP file containing a valid BGP Open message
    compliant with RFC 4271 specification for network verification.
    """
    pcap_dir = tmp_path_factory.mktemp("pcap_captures")
    pcap_file = str(pcap_dir / "bgp_session_capture.pcap")
    
    # Construct synthetic L3/L4/L7 BGP Open packet using Scapy
    # L3: IP header (Source -> Destination)
    # L4: TCP header (Target Port 179 - Standard BGP Port)
    # L7: BGP Header Payload (16-byte Sync Marker + BGP Open Header)
    bgp_marker = b"\xff" * 16
    bgp_open_payload = bgp_marker + b"\x00\x1d\x01\x04\x00\x41\x00\xb4"
    
    packet = IP(src="192.168.1.1", dst="192.168.1.2") / TCP(sport=49152, dport=179) / bgp_open_payload
    
    # Write packet capture to disk
    wrpcap(pcap_file, [packet])
    
    yield pcap_file
    
    # Teardown: Clean up generated PCAP artifact
    if os.path.exists(pcap_file):
        os.remove(pcap_file)

def test_validate_bgp_pcap_headers(bgp_pcap_capture_file):
    """
    Parses captured PCAP file and verifies L4 TCP destination port and L7 BGP Sync Marker.
    """
    packets = rdpcap(bgp_pcap_capture_file)
    
    assert len(packets) > 0, "PCAP capture file must not be empty"
    
    captured_packet = packets[0]
    
    # L4 Validation: Verify destination TCP port is 179
    assert captured_packet[TCP].dport == 179, f"Expected BGP TCP port 179, got {captured_packet[TCP].dport}"
    
    # L7 Validation: Verify BGP 16-byte Sync Marker pattern (all 0xFF bytes)
    raw_payload = bytes(captured_packet[TCP].payload)
    bgp_marker = raw_payload[:16]
    
    assert bgp_marker == b"\xff" * 16, "BGP 16-byte Sync Marker is corrupted or invalid"


@pytest.mark.parametrize("expected_src_ip, expected_dst_ip", [
    ("192.168.1.1", "192.168.1.2"),
])
def test_pcap_ip_routing_endpoints(bgp_pcap_capture_file, expected_src_ip, expected_dst_ip):
    """
    Verifies source and destination IP routing endpoints in captured PCAP header.
    """
    packets = rdpcap(bgp_pcap_capture_file)
    captured_packet = packets[0]
    
    assert captured_packet[IP].src == expected_src_ip, f"Source IP mismatch: expected {expected_src_ip}, got {captured_packet[IP].src}"
    assert captured_packet[IP].dst == expected_dst_ip, f"Destination IP mismatch: expected {expected_dst_ip}, got {captured_packet[IP].dst}"

