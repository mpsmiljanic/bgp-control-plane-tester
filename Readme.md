# HIL Control Plane Tester for BGP Finite State Machine (FSM)

A professional Hardware-in-the-Loop (HIL) automation framework designed to validate the BGP (Border Gateway Protocol) Finite State Machine on physical embedded targets. 

This project establishes a dual-plane testing pipeline:
*   **Control/Logging Plane (UART):** Real-time device state extraction and monitoring via serial.
*   **Data Plane (TCP/IP):** Raw binary packet injection (standard BGP port 179) over Wi-Fi to validate state transitions and error-injection resiliency.

---

## System Architecture

```text
  +-------------------------------------------------+
  |                Raspberry Pi 4                   |
  |               (HIL Test Runner)                 |
  |                                                 |
  |   +-------------------+   +-----------------+   |
  |   |    Pytest Core    |   |  PyYAML Config  |   |
  |   +---------+---------+   +--------+--------+   |
  +-------------|----------------------|------------+
                |                      |
    TCP/IP (Wi-Fi, Port 179)      UART (/dev/ttyACM0)
    BGP Packet Injection          Control & Log Sync
                |                      |
  +-------------v----------------------v------------+
  |                                                 |
  |                 ESP32-S3 DUT                    |
  |            (Target Running ESP-IDF)             |
  |                                                 |
  +-------------------------------------------------+

Directory Layout

bgp-control-plane-tester/
├── config/                  # Topology & network configurations (YAML)
│   └── topology.yaml
├── docs/                    # Architectural & protocol design specifications
├── dut_firmware/            # Target ESP-IDF firmware (C++)
│   └── esp32_bgp_fsm/
│       ├── main/
│       │   ├── CMakeLists.txt
│       │   └── main.cpp     # Clean, modern ESP-IDF C++ implementation
│       └── CMakeLists.txt
├── tests/                   # Pytest automation suite
│   ├── conftest.py          # HILDUT abstraction layer (dual-mode Mock/Real)
│   └── test_bgp_fsm.py      # Automated test cases
├── Dockerfile               # Containerized environment blueprint (TBD)
├── requirements.txt         # Python dependencies
└── Readme.md                # Project documentation

Test Scenarios Supported

    TC-F-01: test_bgp_fsm_happy_path (Functional)
        Objective: Verify standard BGP FSM state transitions up to ESTABLISHED.
        Execution: Injection of a valid 19-byte BGP OPEN packet (16-byte marker 0xFF, 2-byte length, 1-byte type).
        Assertion: Validates receipt of ACK_OPEN and ADI_BGP_SESSION_ESTABLISHED.
    TC-R-01: test_bgp_fsm_error_injection_bad_marker (Robustness)
        Objective: Validate FSM recovery and error handling under corrupt frame inputs.
        Execution: Injection of a BGP packet with a corrupted 16-byte marker (leading zeros).
        Assertion: Verifies target issues ERR_BAD_MARKER, drops the TCP connection, and resets FSM cleanly to IDLE/CONNECT.

Getting Started
Hardware Setup

    Connect the ESP32-S3 board to one of the USB ports of the Raspberry Pi.
    Ensure both the Raspberry Pi and the ESP32-S3 are connected to the same local subnet (via Wi-Fi router).

Software Environment Setup

    Activate the Unified Environment: Initialize the Python environment and export ESP-IDF tools paths:

cd ~/esp/esp-idf && . ./export.sh
cd ~/adi_project/bgp-control-plane-tester

    Build & Flash the Target Firmware:

cd dut_firmware/esp32_bgp_fsm
idf.py set-target esp32s3
idf.py build
idf.py -p /dev/ttyACM0 flash

(Verify the dynamic IP address printed by the target in the logs).

    Configure the HIL Topology: Update config/topology.yaml with your local Wi-Fi credentials and the ESP32 dynamic IP address.
    Run the Automated Pytest Suite:

cd ~/adi_project/bgp-control-plane-tester
pytest -s -v tests/test_bgp_fsm.py


## Automated PCAP & L4/L7 BGP Protocol Validation

Automated network layer verification suite using **Pytest** and **Scapy** to programmatically generate, inspect, and decode packet captures (`.pcap`) against RFC 4271 BGP specifications.

### Key Capabilities
* **L3/L4 Header Inspection:** Validates IP routing endpoints (Source/Destination) and ensures TCP destination port strictly matches standard BGP port `179`.
* **L7 BGP Framing (RFC 4271):** Decodes and verifies the 16-byte `0xFF` Synchronization Marker, BGP Version 4 header payload, Autonomous System (AS65) configuration, and Hold-Time parameters.
* **Automated Capture Lifecycle:** Leverages Pytest module-scoped fixtures (`bgp_pcap_capture_file`) with explicit setup/teardown mechanics to dynamically construct and purge `.pcap` test artifacts.

### Running PCAP Tests

To execute the PCAP packet validation suite:

pytest -s -v tests/test_pcap/test_bgp_pcap_validation.py

# WARNING!
## Critical HIL Architecture Gotcha: The "Bypass Routing" Trap (Testbed Leakage)

During the deployment of this HIL testbed, we encountered and resolved a classic system-level networking loophole. This case study highlights the difference between **logical protocol success** and **physical testbed integrity**.

### The Problem (Logical PASS, Physical FAIL)
During early testing, the Raspberry Pi (Runner) and the ESP32 (DUT) were connected to the same Wi-Fi network. However, the Pi was also physically connected to the Developer's PC via an Ethernet cable for diagnostic/SSH access, with internet/network sharing enabled on the PC.

When executing the BGP suite with the Pi's Wi-Fi interface intentionally disabled, **the tests still passed green!**

+------------------+                   +------------------+ |  Developer PC    | <===[ Wi-Fi ]===> |    ESP32 DUT     | |  (Bridge/Router) |                   |  (192.168.1.8)   | +------------------+                   +------------------+ ^ || [Ethernet LAN (10.42.0.1)] v +------------------+ |  Raspberry Pi    | |  (Wi-Fi OFF!)    | +------------------+


#### Why did this happen?
Because TCP/IP and routing protocols are inherently robust. When the Raspberry Pi's Wi-Fi was off, it had no direct route to the ESP32's IP subnet (`192.168.1.x`). However, its default gateway was set to the Ethernet interface connected to the PC (`10.42.0.1`). 
1. The Pi generated BGP packets and sent them over the **physical Ethernet cable** to the PC.
2. The PC's operating system bridged/routed those packets over its own **active Wi-Fi interface** directly to the ESP32.
3. The ESP32 replied, and the PC routed the response back through the wire to the Pi.

### Why is this a Critical Testbed Failure?
* **False Security:** The test runner reported `PASSED`, masking the fact that **direct Wi-Fi connectivity between the Pi and the ESP32 was completely broken/non-existent**.
* **Environmental Dependency:** The moment the developer disconnects their laptop or locks their screen, the automated CI/CD pipeline on the self-hosted runner will immediately break with `No route to host`.

### The Resolution (How to Ensure 100% Isolated HIL)
To validate that the HIL testbed is truly autonomous and isolated, we implemented a strict **physical-only validation protocol**:

1. **Physical Isolation:** Unplug any direct Ethernet/USB bridges between the Developer PC and the Raspberry Pi.
2. **Routing Table Audit:** Execute `ip route` on the Pi and ensure the *only* active default gateway is the local WLAN router (`wlan0`), with no active Ethernet bridges routing traffic to external gateways.
3. **Negative Testbed Validation:** Disabling the Wi-Fi radio on the Pi via `nmcli radio wifi off` *must* immediately cause the pytest suite to fail with packet-delivery timeouts. 

Only when the tests **fail under Wi-Fi disconnection** and **pass under Wi-Fi activation with NO physical PC-to-Pi bridge** can the testbed run be certified as a **True HIL Pass**.




