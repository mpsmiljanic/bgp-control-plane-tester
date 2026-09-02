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


