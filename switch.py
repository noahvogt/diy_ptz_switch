import asyncio
import os
import argparse

import serial_asyncio
from serial.tools import list_ports
import yaml
from aiohttp import web


def get_config_path():
    parser = argparse.ArgumentParser(description="PTZ router")
    parser.add_argument(
        "-c", "--config", type=str, help="Path to config.yml file"
    )
    args = parser.parse_args()

    if args.config:
        return args.config

    xdg_config_home = os.environ.get(
        "XDG_CONFIG_HOME", os.path.expanduser("~/.config")
    )
    return os.path.join(xdg_config_home, "diy_ptz_switch", "config.yml")


def load_location_roles():
    config_file = get_config_path()
    if not os.path.exists(config_file):
        raise FileNotFoundError(f"Config file not found at: {config_file}")
    with open(config_file, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return config.get("location_roles", {})


location_roles = load_location_roles()

port_map = {}
for port in list_ports.comports():
    if "LOCATION=" in port.hwid:
        loc = port.hwid.split("LOCATION=")[-1]
        if loc in location_roles:
            role = location_roles[loc]
            port_map[role] = port.device

print("Port mapping by USB port:")
for role, dev in port_map.items():
    print(f"  {role}: {dev}")

JOYSTICK_PORT = port_map.get("joystick")
CAM1_PORT = port_map.get("cam1")
CAM2_PORT = port_map.get("cam2")
BAUDRATE = 2400

current_target = "cam1"  # Default
current_mode = "preview"  # Default
cam_transports = {}


class JoystickProtocol(asyncio.Protocol):
    def __init__(self, forward_func):
        self.forward = forward_func
        self.buffer = bytearray()

    def data_received(self, data):
        print(f"[DEBUG] Raw data received: {data.hex()}")
        self.buffer += data
        self.parse_pelco_d_packets()

    def parse_pelco_d_packets(self):
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

            print(
                f"[Joystick] Packet to camera addr {address:02X} — "
                f"Cmd1: {cmd1:02X}, Cmd2: {cmd2:02X}, "
                f"Data1: {data1:02X}, Data2: {data2:02X}, "
                f"Target: {current_target}"
            )

            self.forward(packet)


class DummyCamProtocol(asyncio.Protocol):
    def connection_made(self, transport):
        pass


def make_preset_command(cam_address: int, cmd2: int, preset_id: int):
    if not (1 <= preset_id <= 0xFF):
        raise ValueError("Preset ID must be between 1 and 255")

    cmd1 = 0x00
    data1 = 0x00
    data2 = preset_id
    packet = bytearray([0xFF, cam_address, cmd1, cmd2, data1, data2])
    checksum = sum(packet[1:]) % 256
    packet.append(checksum)
    return packet


def send_preset_command(cam_name, cmd2, preset_id):
    transport = cam_transports.get(cam_name)
    if not transport:
        print(f"[WARN] No transport for {cam_name}")
        return
    packet = make_preset_command(
        1, cmd2, preset_id
    )  # Camera address is hardcoded as 1
    print(
        f"[API] Sending preset cmd2={cmd2:02X} preset_id={preset_id} to {cam_name}"
    )
    transport.write(packet)


async def handle_status(request):
    return web.json_response({"current_target": current_target})


async def handle_set_target(request):
    global current_target
    data = await request.json()
    target = data.get("target")
    if target not in cam_transports:
        return web.json_response(
            {"error": f"Invalid target: {target}"}, status=400
        )
    current_target = target
    print(f"[API] Target set to: {current_target}")
    return web.json_response({"status": "ok", "target": current_target})


async def handle_goto_preset(request):
    data = await request.json()
    preset_id = int(data.get("preset"))
    target = data.get("target", current_target)
    if target not in cam_transports:
        return web.json_response(
            {"error": f"Invalid target: {target}"}, status=400
        )
    send_preset_command(target, cmd2=0x07, preset_id=preset_id)
    return web.json_response(
        {
            "status": "ok",
            "action": "goto",
            "preset": preset_id,
            "target": target,
        }
    )


async def handle_save_preset(request):
    data = await request.json()
    preset_id = int(data.get("preset"))
    target = data.get("target", current_target)
    if target == "both":
        for cam in ["cam1", "cam2"]:
            send_preset_command(cam, cmd2=0x03, preset_id=preset_id)
    elif target in cam_transports:
        send_preset_command(target, cmd2=0x03, preset_id=preset_id)
    else:
        return web.json_response(
            {"error": f"Invalid target: {target}"}, status=400
        )

    return web.json_response(
        {
            "status": "ok",
            "action": "save",
            "preset": preset_id,
            "target": target,
        }
    )


async def handle_set_mode(request):
    global current_mode
    mode = request.query.get("mode")
    if mode not in ("preview", "program"):
        return web.json_response({"error": "Invalid mode"}, status=400)
    current_mode = mode
    return web.json_response({"status": "ok", "mode": current_mode})


async def handle_get_mode(request):
    return web.json_response({"mode": current_mode})


def start_http_server():
    app = web.Application()
    app.router.add_get("/target/get", handle_status)
    app.router.add_post("/target/set", handle_set_target)
    app.router.add_post("/preset/goto", handle_goto_preset)
    app.router.add_post("/preset/save", handle_save_preset)
    app.router.add_get("/mode/get", handle_get_mode)
    app.router.add_post("/mode/set", handle_set_mode)
    return web._run_app(app, port=1423)


async def main():
    global cam_transports

    loop = asyncio.get_running_loop()

    def forward_packet(packet):
        transport = cam_transports.get(current_target)
        if transport:
            transport.write(packet)
        else:
            print(f"[WARN] No transport for {current_target}")

    # Connect to cameras
    cam1_transport, _ = await serial_asyncio.create_serial_connection(
        loop, DummyCamProtocol, CAM1_PORT, baudrate=BAUDRATE
    )
    cam2_transport, _ = await serial_asyncio.create_serial_connection(
        loop, DummyCamProtocol, CAM2_PORT, baudrate=BAUDRATE
    )
    cam_transports = {"cam1": cam1_transport, "cam2": cam2_transport}

    # Connect to joystick
    await serial_asyncio.create_serial_connection(
        loop,
        lambda: JoystickProtocol(forward_packet),
        JOYSTICK_PORT,
        baudrate=BAUDRATE,
    )

    # Start HTTP API in a separate task
    asyncio.create_task(start_http_server())

    # Wait forever
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
