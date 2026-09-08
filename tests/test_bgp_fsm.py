import pytest

def test_bgp_fsm_happy_path(dut_connection):
    """
    TC-F-01: Verify BGP FSM successful transition up to ESTABLISHED state.
    Sends a standard valid BGP OPEN packet and asserts session establishment.
    """
    # Standard 19-byte valid BGP OPEN header:
    # 16-byte marker (all 0xFF), 2-byte length (19), 1-byte type (1 = OPEN)
    valid_header = b"\xff" * 16 + b"\x00\x13" + b"\x01"
    response = dut_connection.send_packet(valid_header)
    
    # Assert successful BGP handshake
    assert b"ACK_OPEN" in response
    assert b"ADI_BGP_SESSION_ESTABLISHED" in response


def test_bgp_fsm_keepalive_validation(dut_connection):
    """
    TC-F-02: Verify BGP KEEPALIVE Packet Validation.
    After establishing a session, injects a KEEPALIVE message (Type 4)
    and verifies the connection remains stable with no network errors.
    """
    # 1. Establish session first by sending a standard BGP OPEN packet
    valid_open = b"\xff" * 16 + b"\x00\x13" + b"\x01"
    response = dut_connection.send_packet(valid_open)
    assert b"ADI_BGP_SESSION_ESTABLISHED" in response

    # 2. Create and send Keepalive message (Type 4)
    # 16-byte marker (0xFF), 2-byte length (19), 1-byte type (4 = KEEPALIVE)
    keepalive_msg = b"\xff" * 16 + b"\x00\x13" + b"\x04"
    response = dut_connection.send_packet(keepalive_msg)

    # 3. Assert that the DUT accepted the keepalive (empty response b"" due to adapter closing socket)
    assert response == b""

@pytest.mark.parametrize(
    "packet, expected_token, should_be_present",
    [
        # TC-R-01: Corrupt Marker - Expect ERR_BAD_MARKER in response
        pytest.param(
            b"\x00" * 4 + b"\xff" * 12 + b"\x00\x13" + b"\x01",
            b"ERR_BAD_MARKER",
            True,
            id="TC-R-01: Corrupt Marker"
        ),
        
        # TC-R-02: Invalid Message Length (< 19 bytes)
        # Use pytest.param to apply xfail(strict=True) EXCLUSIVELY to this test case
        pytest.param(
            b"\xff" * 16 + b"\x00\x12" + b"\x01",
            b"ADI_BGP_SESSION_ESTABLISHED",
            False,
            id="TC-R-02: Invalid Length",
            marks=pytest.mark.xfail(
                strict=True, 
                reason="JIRA QA-342/1042: ESP32 firmware bug - lacks BGP Minimum Length (19 bytes) validation."
            )
        ),
        
        # TC-R-03: Unsupported Message Type (Type 5) - Session must not be established
        pytest.param(
            b"\xff" * 16 + b"\x00\x13" + b"\x05",
            b"ADI_BGP_SESSION_ESTABLISHED",
            False,
            id="TC-R-03: Unsupported Type"
        )
    ]
)
def test_bgp_fsm_error_injection(dut_connection, packet, expected_token, should_be_present):
    """
    TC-R-Param: Unified Parameterized Error Injection (Negative Testing).
    Deliberately sends malformed packets to verify DUT parser robustness and connection teardown.
    """
    response = dut_connection.send_packet(packet)
    
    if should_be_present:
        assert expected_token in response
    else:
        assert expected_token not in response