# Copyright © 2025 Noah Vogt <noah@noahvogt.com>

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import asyncio
import serial_asyncio
from serial.tools import list_ports

# TODO: Don't use hardcoded usb port mapping anymore
location_roles = {
    "1-1.4": "joystick",
    "1-1.1": "cam1",
    "1-1.2": "cam2",
}

port_map = {}

for port in list_ports.comports():
    if "LOCATION=" in port.hwid:
        loc = port.hwid.split("LOCATION=")[-1]
        if loc in location_roles:
            role = location_roles[loc]
            port_map[role] = port.device

print("port mapping by usb port:")
print(port_map)

JOYSTICK_PORT = port_map.get("joystick")
CAM1_PORT = port_map.get("cam1")
CAM2_PORT = port_map.get("cam2")
# TODO: Don't hardcore baudrate anymore
BAUDRATE = 2400

DEFAULT_TARGET = "cam1"  # default

# Will hold writeable serial transports
cam_transports = {}


class JoystickProtocol(asyncio.Protocol):
    def __init__(self, forward_func):
        self.forward = forward_func
        self.buffer = bytearray()

    def data_received(self, data):
        print(f"[DEBUG] Raw data received: {data.hex()}")
        self.buffer += data

        self.parse_pelco_d_packets()

    def parse_pelco_d_packets(self) -> None:
        while len(self.buffer) >= 7:
            if self.buffer[0] != 0xFF:
                self.buffer.pop(0)
                continue

            packet = self.buffer[:7]
            self.buffer = self.buffer[7:]

            address = packet[1]
            cmd1 = packet[2]
            cmd2 = packet[3]
            data1 = packet[4]
            data2 = packet[5]
            # checksum = packet[6]

            print(
                f"[Joystick] Packet to camera addr {address:02X} — "
                f"Cmd1: {cmd1:02X}, Cmd2: {cmd2:02X}, "
                f"Data1: {data1:02X}, Data2: {data2:02X}, "
                f"Target: {DEFAULT_TARGET}"
            )

            self.forward(packet)


class DummyCamProtocol(asyncio.Protocol):
    def connection_made(self, transport):
        pass  # We don't need to receive data from the cams


async def main():
    global cam_transports
    loop = asyncio.get_running_loop()

    def forward_packet(packet):
        transport = cam_transports.get(DEFAULT_TARGET)
        if transport:
            transport.write(packet)
        else:
            print(f"[WARN] No transport for {DEFAULT_TARGET}")

    # Open cam1 and cam2 for writing
    cam1_transport, _ = await serial_asyncio.create_serial_connection(
        loop, DummyCamProtocol, CAM1_PORT, baudrate=BAUDRATE
    )
    cam2_transport, _ = await serial_asyncio.create_serial_connection(
        loop, DummyCamProtocol, CAM2_PORT, baudrate=BAUDRATE
    )

    cam_transports = {
        "cam1": cam1_transport,
        "cam2": cam2_transport,
    }

    # Open joystick serial
    await serial_asyncio.create_serial_connection(
        loop,
        lambda: JoystickProtocol(forward_packet),
        JOYSTICK_PORT,
        baudrate=BAUDRATE,
    )

    # Keep the loop running
    await asyncio.Event().wait()


asyncio.run(main())
