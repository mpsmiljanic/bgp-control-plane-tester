import pytest

def test_bgp_fsm_happy_path(dut_connection):
    """
    TC-F-01: Verify BGP FSM successful transition up to ESTABLISHED.
    We send a standard valid BGP OPEN packet and assert target state update.
    """
    # Standard 19-byte valid BGP OPEN header
    # 16-byte marker (all 0xFF), 2-byte length (19), 1-byte type (1 = OPEN)
    valid_header = b"\xff" * 16 + b"\x00\x13" + b"\x01"
    
    response = dut_connection.send_packet(valid_header)
    
    # Assert successful BGP handshake
    assert b"ACK_OPEN" in response
    assert b"ADI_BGP_SESSION_ESTABLISHED" in response


def test_bgp_fsm_error_injection_bad_marker(dut_connection):
    """
    TC-R-01: Error Injection - Bad Packet Marker.
    We deliberately corrupt the BGP marker and assert FSM resets to IDLE.
    """
    # Corrupting the first 4 bytes of the marker
    bad_marker = b"\x00" * 4 + b"\xff" * 12 + b"\x00\x13" + b"\x01"
    
    response = dut_connection.send_packet(bad_marker)
    
    # Assert proper target error reporting and connection teardown
    assert b"ERR_BAD_MARKER" in response


def test_bgp_fsm_keepalive_validation(dut_connection):
    """
    TC-F-02: Verify BGP KEEPALIVE Packet Validation.
    After establishing session, we inject a KEEPALIVE message (Type 4) 
    and verify that the connection remains stable with no mrežna connection errors.
    """
    # 1. Establish session first by sending a standard BGP OPEN packet
    valid_open = b"\xff" * 16 + b"\x00\x13" + b"\x01"
    response = dut_connection.send_packet(valid_open)
    assert b"ADI_BGP_SESSION_ESTABLISHED" in response

    # 2. Create and send Keepalive message
    # 16-byte marker (0xFF), 2-byte length (19), 1-byte type (4 = KEEPALIVE)
    keepalive_msg = b"\xff" * 16 + b"\x00\x13" + b"\x04"
    response = dut_connection.send_packet(keepalive_msg)

    # 3. Assert that the DUT accepted the keepalive without raising any errors
    # (Since ESP32 does not return any TCP payload for Keepalive, response must be empty)
    assert response == b""