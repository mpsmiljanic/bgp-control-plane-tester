# bgp-control-plane-tester - System Architecture (v1.0.0)

## 1. Overview
The BGP Control Plane HIL Tester is a localized Hardware-in-the-Loop (HIL) system designed to validate the stability, state machine transitions, and error-handling capabilities of an embedded network processing system.

By utilizing low-cost, readily available hardware, this setup bridges the gap between theoretical network operation and bare-metal embedded protocol testing.

## 2. Hardware Topology
The HIL system consists of two primary physical nodes:
1. **Device Under Test (DUT)**: An ESP32 microcontroller running a custom lightweight C++ network stack simulation. It simulates a carrier-grade Router Control Plane listening on standard BGP TCP Port 179.
2. **Hardware Test Platform (HTP)**: A Raspberry Pi 3B+ (or PC) executing automated test scripts under the `pytest` framework. It acts as the traffic generator, protocol tester, and test runner.

### Frequencies and Connections
* **Control/Debug Plane (UART)**: Serial connection via USB (baud rate: 115200) linking the RPi directly to the ESP32 for raw log extraction, resource monitoring (heap memory, CPU load), and hard-reset control.
* **Data Plane (TCP/IP)**: Dual wireless or wired Local Area Network (Wi-Fi/Ethernet) linking RPi and ESP32. Real mrežni TCP socket connection is used to transport protocol packets.

   +-------------------------------------------------+
   |         Hardware Test Platform (HTP)            |
   |             Raspberry Pi 3B+                    |
   |  +-------------------------------------------+  |
   |  |  Pytest Framework                         |  |
   |  |  (Test-Runner & Mock Fallback Engine)     |  |
   |  +-------------------------------------------+  |
   +-----------------------+-------------------------+
                           |
        Data Plane         | Control/Debug Plane
        TCP Port 179       | UART via USB (115200)
        (WiFi / Ethernet)  | (Hard Reset, Logs & Telemetry)
                           |
   +-----------------------v-------------------------+
   |             Device Under Test (DUT)             |
   |                  ESP32 MCU                      |
   |  +-------------------------------------------+  |
   |  |  Lightweight Network OS Simulator         |  |
   |  |  BGP Finite State Machine (FSM) Engine    |  |
   |  +-------------------------------------------+  |
   +-------------------------------------------------+


## 3. Finite State Machine (FSM) Implementation
The ESP32 firmware implements a subset of the standard BGP Finite State Machine (RFC 4271):

1. **IDLE**: FSM is uninitialized or has experienced an unrecoverable protocol error.
2. **CONNECT**: The system is listening on TCP port 179 and waiting for an incoming peer connection.
3. **ACTIVE**: An active TCP socket has been established. The target waits for the first BGP message.
4. **OPENSENT**: A valid BGP `OPEN` message header has been parsed. The target responds and waits for confirmation.
5. **ESTABLISHED**: Handshake is complete. The active BGP session is fully operational.

## 4. Software Design Patterns
* **Dual-Mode Test Runner**: `conftest.py` implements an abstraction layer that checks for physical hardware presence. If the configured serial port does not exist, it automatically falls back to an emulated mock environment, allowing headless CI/CD execution.
* **Separation of Concerns**: System parameters are strictly isolated in `config/topology.yaml` so that code never has to be modified when deploying onto different network configurations.
