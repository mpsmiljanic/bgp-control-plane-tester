# bgp-control-plane-tester - Test Specification (v1.0.0)

## 1. Overview
This document outlines the risk-based test specification for validating the embedded BGP Finite State Machine. The tests are designed to cover both "Happy Path" functional states and negative validation/Error Injection boundary scenarios.

## 2. Test Case Matrix

| Test Case ID | Name / Description | Type | Target State / Expected Behavior | Status |
| :--- | :--- | :--- | :--- | :--- |
| **TC-F-01** | BGP FSM Happy Path Handshake | Functional | Successful transition: IDLE -> CONNECT -> ACTIVE -> OPENSENT -> ESTABLISHED. Target returns `ADI_BGP_SESSION_ESTABLISHED`. | `[Implemented v1.0]` |
| **TC-R-01** | Error Injection: Bad Header Marker | Robustness | Send 19-byte packet with corrupted 16-byte marker. Assert FSM immediately drops TCP, resets to IDLE, and restarts CONNECT. | `[Implemented v1.0]` |
| **TC-R-02** | Error Injection: Oversized BGP Message | Robustness | Send message exceeding maximum RFC length (4096 bytes). Assert target gracefully rejects packet and logs "Header Overflow". | `[Planned v2.0]` |
| **TC-S-01** | Control Plane Policing (CoPP) Stress | Stress | Send high-rate malformed control traffic (1000+ packets/sec). Assert ESP32 control plane remains stable and does not reboot. | `[Planned v2.0]` |
| **TC-F-02** | Wi-Fi Connection Flapping Recovery | Flakiness | Disconnect and reconnect Wi-Fi client. Assert target re-establishes TCP server listening state within 5 seconds of network reconnect. | `[Planned v3.0]` |

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
