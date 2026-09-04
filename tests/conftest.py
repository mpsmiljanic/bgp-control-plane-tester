import os
import yaml
import pytest
import socket

@pytest.fixture(scope="session")
def topology_config():
    """
    Session-scoped fixture to load topology configuration.
    Prioritizes local 'config/topology.yaml'.
    Falls back to 'config/topology.yaml.example' in CI/Docker environments.
    """
    base_dir = os.path.dirname(__file__)
    primary_config = os.path.abspath(os.path.join(base_dir, "../config/topology.yaml"))
    fallback_config = os.path.abspath(os.path.join(base_dir, "../config/topology.yaml.example"))

    if os.path.exists(primary_config):
        target_file = primary_config
    elif os.path.exists(fallback_config):
        target_file = fallback_config
    else:
        pytest.fail("Neither 'config/topology.yaml' nor 'config/topology.yaml.example' was found!")

    with open(target_file, "r") as f:
        return yaml.safe_load(f)


class MockDUT:
    def __init__(self):
        self.state = "BGP_CONNECT"
        self.logs = [
            "[BGP_FSM] STATE: BGP_CONNECT",
            "HIL-NetLink: BGP FSM Target Online",
            "[WIFI] Connected. IP Address: 192.168.1.105"
        ]

    def get_serial_log(self):
        return "\n".join(self.logs)

    def send_packet(self, data):
        # Structured header byte indexes
        LENGTH_HIGH_BYTE = 16
        LENGTH_LOW_BYTE = 17
        MSG_TYPE_BYTE = 18

        # Validate BGP sync marker (first 16 bytes)
        if len(data) >= 19:
            marker = data[:16]
            if marker != b"\xff" * 16:
                self.state = "BGP_IDLE"
                self.logs.append("[ERROR_INJECTION] Invalid Marker received! Expected 16 bytes of 0xFF.")
                self.logs.append("[BGP_FSM] STATE: IDLE")
                return b"ERR_BAD_MARKER\n"
            
            # Extract length and message type using structured constants
            length = (data[LENGTH_HIGH_BYTE] << 8) | data[LENGTH_LOW_BYTE]
            msg_type = data[MSG_TYPE_BYTE]
            
            # Simulate serial output before checking message type (identical to ESP32 behavior)
            self.logs.append(f"[BGP_FSM] Valid BGP Header. Length: {length}, Type: {msg_type}")
            
            if msg_type == 1:
                self.state = "BGP_ESTABLISHED"
                self.logs.append("[BGP_FSM] STATE: OPENSENT")
                self.logs.append("[BGP_FSM] STATE: ESTABLISHED")
                return b"ACK_OPEN\nADI_BGP_SESSION_ESTABLISHED\n"
            elif msg_type == 4:
                # Keepalive message accepted, state remains ESTABLISHED, no response payload expected over TCP
                return b""
        return b"ERR_UNKNOWN\n"


@pytest.fixture(scope="session")
def dut_connection(topology_config):
    """
    Establishes connection to the DUT. Supports both old and new config schemas.
    Falls back gracefully to MockDUT if hardware or network configuration is unreachable.
    """
    if "connections" in topology_config:
        conn_cfg = topology_config["connections"]
        port = conn_cfg.get("serial", {}).get("port", "/dev/ttyACM0")
        baud = conn_cfg.get("serial", {}).get("baud_rate", 115200)
        target_ip = conn_cfg.get("network", {}).get("target_ip", "192.168.1.8")
        target_port = conn_cfg.get("network", {}).get("target_port", 179)
    else:
        device_cfg = topology_config.get("device", {})
        port = device_cfg.get("serial_port", "/dev/ttyACM0")
        baud = device_cfg.get("baud_rate", 115200)
        target_ip = device_cfg.get("target_ip", "192.168.1.8")
        target_port = device_cfg.get("bgp_port", 179)

    if os.path.exists(port):
        class HILDUT:
            def __init__(self, port, baud, ip, target_port):
                self.port = port
                self.baud = baud
                self.ip = ip
                self.target_port = target_port
                self.ser = None  # Lazy initialization

            def get_serial_log(self):
                if self.ser is None:
                    import serial
                    self.ser = serial.Serial(self.port, self.baud, timeout=2)
                self.ser.write(b"\n")
                return self.ser.read(4000).decode("utf-8", errors="replace")

            def send_packet(self, data):
                MSG_TYPE_BYTE = 18
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(5)
                try:
                    s.connect((self.ip, self.target_port))
                    s.sendall(data)
                    
                    # If sending Keepalive (Type 4), do not wait for TCP response payload (ESP32 does not ACK over TCP)
                    if len(data) >= 19 and data[MSG_TYPE_BYTE] == 4:
                        s.close()
                        return b""
                        
                    response = b""
                    while True:
                        chunk = s.recv(1024)
                        if not chunk:
                            break
                        response += chunk
                        if b"ADI_BGP_SESSION_ESTABLISHED" in response or b"ERR_BAD_MARKER" in response:
                            break
                    s.close()
                    return response
                except Exception as e:
                    return f"CONN_ERR: {str(e)}".encode()

            def close(self):
                if hasattr(self, "ser") and self.ser is not None and self.ser.is_open:
                    self.ser.close()

        dut = HILDUT(port, baud, target_ip, target_port)
        yield dut
        dut.close()
    else:
        print("\n[TOPOLOGY WARNING] Hardware target not found. Initializing Automated Emulated-HIL Session.")
        yield MockDUT()