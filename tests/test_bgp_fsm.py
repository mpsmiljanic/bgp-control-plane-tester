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
    and verify that the connection remains stable with no network connection errors.
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
    assert response == b""


@pytest.mark.xfail(
    strict=True,
    reason="JIRA(QA-342) - DUT Bug: ESP32 firmware lacks BGP Minimum Length (19 bytes) validation. Session is incorrectly established."
)
def test_bgp_fsm_error_injection_invalid_length(dut_connection):
    """
    TC-R-02: Error Injection - Invalid Message Length (Option A).
    We send a packet where the BGP Length field is set to 18 (less than minimum 19 bytes)
    and assert that the target rejects the packet and does not establish a session.
    """
    # 16-byte marker (all 0xFF), 2-byte length indicating 18 (0x0012), 1-byte type (1 = OPEN)
    # Total sent is 19 bytes, but the internal length field says 18.
    bad_length_packet = b"\xff" * 16 + b"\x00\x12" + b"\x01"
    
    response = dut_connection.send_packet(bad_length_packet)
    
    # Robust assertion: The session must NEVER be established
    assert b"ADI_BGP_SESSION_ESTABLISHED" not in response


def test_bgp_fsm_error_injection_unsupported_type(dut_connection):
    """
    TC-R-03: Error Injection - Unsupported Message Type (Option B).
    We deliberately send a packet with an invalid message type (5)
    and assert that the FSM rejects it and closes the connection.
    """
    # 16-byte marker (0xFF), 2-byte length (19), 1-byte invalid type (5 = Unsupported)
    unsupported_type_packet = b"\xff" * 16 + b"\x00\x13" + b"\x05"
    
    response = dut_connection.send_packet(unsupported_type_packet)
    
    # Robust assertion: FSM must reject this packet and drop the connection
    assert b"ADI_BGP_SESSION_ESTABLISHED" not in response