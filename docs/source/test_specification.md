# bgp-control-plane-tester - Test Specification (v1.0.0)

## 1. Overview
This document outlines the risk-based test specification for validating the embedded BGP Finite State Machine. The tests are designed to cover both "Happy Path" functional states and negative validation/Error Injection boundary scenarios.

## 2. Test Case Matrix

| Test Case ID | Name / Description | Type | Target State / Expected Behavior | Status |
| :--- | :--- | :--- | :--- | :--- |
| **TC-F-01** | BGP FSM Happy Path Handshake | Functional | Successful transition: IDLE -> CONNECT -> ACTIVE -> OPENSENT -> ESTABLISHED. Target returns `ADI_BGP_SESSION_ESTABLISHED`. | `[Implemented v1.0]` |
| **TC-R-01** | Error Injection: Bad Header Marker | Robustness | Send 19-byte packet with corrupted 16-byte marker. Assert FSM immediately drops TCP, resets to IDLE, and restarts CONNECT. | `[Implemented v1.0]` |
| **TC-F-02** | BGP Keepalive Packet Validation | Functional | Establish session, then send Keepalive (Type 4). Assert connection remains stable and ESP32 processes it silently. | `[Implemented v1.1]` |
| **TC-R-02** | Error Injection: Invalid Message Length | Robustness | Send packet with declared length 18 (< 19). Assert target rejects packet and drops session. | `[Implemented v1.1 - xfail (JIRA-1042 / QA-342)]` |
| **TC-R-03** | Error Injection: Unsupported Message Type | Robustness | Send packet with invalid type byte (5). Assert FSM rejects it, prevents transition, and tears down socket. | `[Implemented v1.1]` |
| **TC-R-04** | Error Injection: Oversized BGP Message | Robustness | Send message exceeding maximum RFC length (4096 bytes). Assert target gracefully rejects packet and logs "Header Overflow". | `[Planned v2.0]` |
| **TC-S-01** | Control Plane Policing (CoPP) Stress | Stress | Send high-rate malformed control traffic (1000+ packets/sec). Assert ESP32 control plane remains stable and does not reboot. | `[Planned v2.0]` |
| **TC-F-03** | Wi-Fi Connection Flapping Recovery | Flakiness | Disconnect and reconnect Wi-Fi client. Assert target re-establishes TCP server listening state within 5 seconds of network reconnect. | `[Planned v3.0]` |



---

## 3. Detailed Test Design (v1.0.0 MVP Implementation)

### TC-F-01: BGP FSM Happy Path Handshake
* **Objective**: Ensure the embedded TCP BGP server correctly handles a standard peer session establishment.
* **Pre-conditions**: ESP32 is powered, Wi-Fi connected, IP allocated, listening on port 179.
* **Stimulus (Python Test-Runner)**:
  1. Open TCP Socket to `target_ip:179`.
  2. Send standard 19-byte valid BGP OPEN header:
     * `Marker`: 16 bytes of `0xFF`
     * `Length`: 2 bytes of `0x0013` (19 bytes decimal)
     * `Type`: 1 byte of `0x01` (OPEN Message Type)
* **Verifications**:
  1. Read TCP socket stream: Assert receipt of `ACK_OPEN` followed by `ADI_BGP_SESSION_ESTABLISHED`.
  2. Read Serial UART output: Assert FSM state prints:
     `[BGP_FSM] STATE: ACTIVE` -> `[BGP_FSM] STATE: OPENSENT` -> `[BGP_FSM] STATE: ESTABLISHED`.

### TC-R-01: Error Injection - Bad Header Marker
* **Objective**: Validate the robustness of the embedded parser when receiving corrupted header structures (protection against malformed packet crashes).
* **Pre-conditions**: ESP32 is powered and mrežni link is stable.
* **Stimulus (Python Test-Runner)**:
  1. Open TCP Socket to `target_ip:179`.
  2. Send standard 19-byte header with a corrupted marker:
     * `Marker`: 4 bytes of `0x00` followed by 12 bytes of `0xFF` (Corrupted)
     * `Length`: `0x0013`
     * `Type`: `0x01`
* **Verifications**:
  1. Read TCP socket stream: Assert receipt of error message `ERR_BAD_MARKER`.
  2. Assert socket connection is forcibly closed by the target.
  3. Read Serial UART output: Assert target FSM prints:
     `[ERROR_INJECTION] Invalid Marker received!` -> `[BGP_FSM] Resetting FSM connection to IDLE` -> `[BGP_FSM] STATE: CONNECT`.

### TC-F-02: BGP Keepalive Packet Validation
* **Objective**: Verify that the embedded BGP parser correctly validates and processes standard BGP KEEPALIVE (Type 4) packets without hanging or crashing the session.
* **Pre-conditions**: ESP32 is powered, Wi-Fi connected, BGP session has been established via standard OPEN handshake (TC-F-01).
* **Stimulus (Python Test-Runner)**:
  1. Inject standard 19-byte valid BGP OPEN header to establish the session.
  2. Send standard 19-byte BGP KEEPALIVE header:
     * `Marker`: 16 bytes of `0xFF`
     * `Length`: 2 bytes of `0x0013` (19 bytes decimal)
     * `Type`: 1 byte of `0x04` (KEEPALIVE Message Type)
* **Verifications**:
  1. Read HIL Adapter Response: Assert that the connection is closed cleanly with an empty response (`b""`), as ESP32 does not send TCP-level payload ACKs for Keepalive.
  2. Read Serial UART output (when accessible): Assert FSM logs print:
     `[BGP_FSM] Valid BGP Header. Length: 19, Type: 4`
  3. Ensure no network sockets hang or crash.

### TC-R-02: Error Injection - Invalid Message Length (Option A)
* **Objective**: Validate the robustness of the embedded parser when receiving structurally malformed packets where the internal Length field is set to a value below the RFC-mandated minimum of 19 bytes.
* **Pre-conditions**: ESP32 is powered and the network link is stable.
* **Stimulus (Python Test-Runner)**:
  1. Open TCP Socket to `target_ip:179`.
  2. Send a 19-byte packet where the internal length field is set to 18:
     * `Marker`: 16 bytes of `0xFF`
     * `Length`: 2 bytes of `0x0012` (18 bytes decimal)
     * `Type`: 1 byte of `0x01` (OPEN Message Type)
* **Verifications**:
  1. Read TCP socket stream: Assert that the session is **NEVER** established (token `ADI_BGP_SESSION_ESTABLISHED` is absent from response).
  2. Read Serial UART output: Assert FSM logs indicate rejection of the invalid message length.
* **Current Status / Bug Note**: **FAILED (Known Firmware Bug)**. The current ESP32 firmware lacks validation for minimum message length. It accepts the 18-byte length field and incorrectly establishes the session anyway. This test is decorated with `@pytest.mark.xfail(strict=True)` (tracked under ticket `JIRA-1042 / QA-342`) to keep the CI/CD pipeline green while awaiting a firmware fix.

### TC-R-03: Error Injection - Unsupported Message Type (Option B)
* **Objective**: Validate that the embedded BGP parser and state machine gracefully reject unrecognized/reserved BGP message types without crashing or locking up the control plane.
* **Pre-conditions**: ESP32 is powered and the network link is stable.
* **Stimulus (Python Test-Runner)**:
  1. Open TCP Socket to `target_ip:179`.
  2. Send a 19-byte packet with an unsupported message type byte:
     * `Marker`: 16 bytes of `0xFF`
     * `Length`: 2 bytes of `0x0013` (19 bytes decimal)
     * `Type`: 1 byte of `0x05` (Reserved/Unsupported Type)
* **Verifications**:
  1. Read TCP socket stream: Assert that the session is **NEVER** established (token `ADI_BGP_SESSION_ESTABLISHED` is absent from response).
  2. Assert that the socket connection is torn down by the target.
  3. Read Serial UART output: Assert target FSM prints:
     `[ERROR_INJECTION] Unsupported Message Type: 5!` -> `[BGP_FSM] STATE: IDLE`.
