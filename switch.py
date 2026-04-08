import asyncio
import os
import argparse
from asyncio import Queue

import yaml
from aiohttp import web

import serial_asyncio
from serial.tools import list_ports
import evdev
from evdev import ecodes

write_queue = Queue()
cam_transports = {}

VISCA_PORT = 52381


class ViscaOverIP:
    def __init__(self, ip, port):
        self.ip = ip
        self.port = port
        self.sequence_number = 1
        self.transport = None

    async def connect(self, loop):
        class ViscaProtocol(asyncio.DatagramProtocol):
            def connection_made(self, transport):
                pass

        self.transport, _ = await loop.create_datagram_endpoint(
            ViscaProtocol, remote_addr=(self.ip, self.port)
        )

    def write(self, visca_payload):
        if not self.transport:
            print(f"[ERROR] No transport for {self.ip}")
            return

        header = bytearray([0x01, 0x00])  # Payload type: VISCA command
        header += len(visca_payload).to_bytes(2, "big")
        header += self.sequence_number.to_bytes(4, "big")

        packet = header + visca_payload
        self.transport.sendto(packet)
        self.sequence_number = (self.sequence_number + 1) & 0xFFFFFFFF


def translate_pelco_to_visca(packet):
    """
    Translates a 7-byte Pelco-D packet to a VISCA command.
    """
    if len(packet) < 7:
        return None

    cmd1 = packet[2]
    cmd2 = packet[3]
    pan_speed = packet[4]
    tilt_speed = packet[5]

    # Map speeds (Pelco 00-3F to VISCA 01-18/17)
    v_pan_speed = max(1, min(0x18, int(pan_speed * 0x18 / 0x3F)))
    v_tilt_speed = max(1, min(0x17, int(tilt_speed * 0x17 / 0x3F)))

    # Pan/Tilt Drive
    # 81 01 06 01 VV WW 0x 0y FF
    # x: 01=left, 02=right, 03=stop
    # y: 01=up, 02=down, 03=stop

    pan_dir = 0x03
    if cmd2 & 0x02:  # Right
        pan_dir = 0x02
    elif cmd2 & 0x04:  # Left
        pan_dir = 0x01

    tilt_dir = 0x03
    if cmd2 & 0x08:  # Up
        tilt_dir = 0x01
    elif cmd2 & 0x10:  # Down
        tilt_dir = 0x02

    if pan_dir != 0x03 or tilt_dir != 0x03:
        return bytearray(
            [
                0x81,
                0x01,
                0x06,
                0x01,
                v_pan_speed,
                v_tilt_speed,
                pan_dir,
                tilt_dir,
                0xFF,
            ]
        )

    # Zoom
    # 81 01 04 07 0p FF (0p: 00=Stop, 02=Tele/In, 03=Wide/Out)
    if cmd2 & 0x20:  # Zoom In (Tele)
        return bytearray([0x81, 0x01, 0x04, 0x07, 0x02, 0xFF])
    if cmd2 & 0x40:  # Zoom Out (Wide)
        return bytearray([0x81, 0x01, 0x04, 0x07, 0x03, 0xFF])

    # Focus
    # 81 01 04 08 0p FF (02=Far, 03=Near)
    if cmd1 & 0x01:  # Focus Near
        return bytearray([0x81, 0x01, 0x04, 0x08, 0x03, 0xFF])
    if cmd1 & 0x02:  # Focus Far
        return bytearray([0x81, 0x01, 0x04, 0x08, 0x02, 0xFF])

    # If it's a stop packet (cmd1=0, cmd2=0) or we don't recognize it
    if cmd1 == 0 and cmd2 == 0:
        # General stop for Pan/Tilt and Zoom
        # Note: VISCA Zoom stop is separate but we'll prioritize P/T stop
        return bytearray([0x81, 0x01, 0x06, 0x01, 0x00, 0x00, 0x03, 0x03, 0xFF])

    return None


async def writer_task():
    while True:
        cam_name, packet = await write_queue.get()
        visca_obj = cam_transports.get(cam_name)
        if visca_obj:
            try:
                visca_obj.write(packet)
            except Exception as e:
                print(f"[ERROR] Write failed for {cam_name}: {e}")
        else:
            print(f"[WARN] No transport for {cam_name}")
        write_queue.task_done()


def enqueue_write(cam_name, packet):
    write_queue.put_nowait((cam_name, packet))


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


def load_config():
    config_file = get_config_path()
    if not os.path.exists(config_file):
        raise FileNotFoundError(f"Config file not found at: {config_file}")
    with open(config_file, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return config


config = load_config()
location_roles = config.get("location_roles", {})
camera_ips = config.get("cameras", {})
joystick_type = config.get("joystick_type", "pelco_serial")

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
BAUDRATE = 2400

CURRENT_TARGET = "cam1"  # Default
CURRENT_MODE = "preview"  # Default


async def evdev_joystick_task(forward_func):
    devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
    target_device = None
    for device in devices:
        if "shenzhenxiaolong" in device.name.lower():
            target_device = device
            break

    if not target_device:
        print("[WARN] Sony/Anxinshi USB joystick not found.")
        return

    print(f"[INFO] Using USB joystick: {target_device.name}")

    x_val = 512
    y_val = 512
    z_val = 512
    deadzone = 50

    last_pt_packet = None
    last_z_packet = None

    try:
        async for event in target_device.async_read_loop():
            if event.type == ecodes.EV_ABS:
                if event.code == ecodes.ABS_X:
                    x_val = event.value
                elif event.code == ecodes.ABS_Y:
                    y_val = event.value
                elif event.code == ecodes.ABS_Z:
                    z_val = event.value
            elif event.type == ecodes.EV_SYN:
                pan_dir = 0x03
                pan_speed = 0x00
                if x_val < 512 - deadzone:
                    pan_dir = 0x01  # Left
                    pan_speed = int((512 - x_val) / 512.0 * 0x18)
                elif x_val > 512 + deadzone:
                    pan_dir = 0x02  # Right
                    pan_speed = int((x_val - 512) / 511.0 * 0x18)
                pan_speed = (
                    max(1, min(0x18, pan_speed)) if pan_dir != 0x03 else 0x00
                )

                tilt_dir = 0x03
                tilt_speed = 0x00
                if y_val < 512 - deadzone:
                    tilt_dir = 0x01  # Up
                    tilt_speed = int((512 - y_val) / 512.0 * 0x17)
                elif y_val > 512 + deadzone:
                    tilt_dir = 0x02  # Down
                    tilt_speed = int((y_val - 512) / 511.0 * 0x17)
                tilt_speed = (
                    max(1, min(0x17, tilt_speed)) if tilt_dir != 0x03 else 0x00
                )

                pt_packet = bytearray(
                    [
                        0x81,
                        0x01,
                        0x06,
                        0x01,
                        pan_speed,
                        tilt_speed,
                        pan_dir,
                        tilt_dir,
                        0xFF,
                    ]
                )
                if pt_packet != last_pt_packet:
                    forward_func(pt_packet)
                    last_pt_packet = pt_packet

                zoom_cmd = 0x00
                if z_val < 512 - deadzone:
                    z_speed = int((512 - z_val) / 512.0 * 7)
                    z_speed = max(0, min(7, z_speed))
                    zoom_cmd = 0x30 | z_speed
                elif z_val > 512 + deadzone:
                    z_speed = int((z_val - 512) / 511.0 * 7)
                    z_speed = max(0, min(7, z_speed))
                    zoom_cmd = 0x20 | z_speed

                z_packet = bytearray([0x81, 0x01, 0x04, 0x07, zoom_cmd, 0xFF])
                if z_packet != last_z_packet:
                    forward_func(z_packet)
                    last_z_packet = z_packet
    except Exception as e:
        print(f"[ERROR] USB Joystick loop error: {e}")


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
                f"[Joystick] Pelco packet to addr {address:02X} — "
                f"Cmd1: {cmd1:02X}, Cmd2: {cmd2:02X}, "
                f"Data1: {data1:02X}, Data2: {data2:02X}, "
                f"Target: {CURRENT_TARGET}"
            )

            visca_packet = translate_pelco_to_visca(packet)
            if visca_packet:
                self.forward(visca_packet)


def make_visca_preset_command(cmd2, preset_id):
    if not 0 <= preset_id <= 0xFF:
        raise ValueError("Preset ID must be between 0 and 255")

    # VISCA: 81 01 04 3F 0p pp FF
    # 0p: 01=Set, 02=Recall
    action = 0x02 if cmd2 == 0x07 else 0x01
    return bytearray([0x81, 0x01, 0x04, 0x3F, action, preset_id, 0xFF])


def send_preset_command(cam_name, cmd2, preset_id):
    packet = make_visca_preset_command(cmd2, preset_id)
    print(
        f"[API] Queueing VISCA preset action={cmd2:02X} preset_id={preset_id} for {cam_name}"
    )
    enqueue_write(cam_name, packet)


async def handle_status(request):
    return web.json_response({"current_target": CURRENT_TARGET})


async def handle_set_target(request):
    global CURRENT_TARGET
    target = None
    if request.can_read_body:
        try:
            data = await request.json()
            target = data.get("target")
        except Exception:
            pass
    if not target:
        target = request.query.get("target")

    if target not in cam_transports:
        return web.json_response(
            {"error": f"Invalid target: {target}"}, status=400
        )
    CURRENT_TARGET = target
    print(f"[API] Target set to: {CURRENT_TARGET}")
    return web.json_response({"status": "ok", "target": CURRENT_TARGET})


async def handle_goto_preset(request):
    preset_id = None
    target = None
    if request.can_read_body:
        try:
            data = await request.json()
            preset_id = data.get("preset")
            target = data.get("target")
        except Exception:
            pass

    if preset_id is None:
        preset_id = request.query.get("preset")
    if target is None:
        target = request.query.get("target", CURRENT_TARGET)

    if preset_id is None:
        return web.json_response({"error": "Missing preset"}, status=400)

    try:
        preset_id = int(preset_id)
    except ValueError:
        return web.json_response({"error": "Invalid preset ID"}, status=400)

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
    preset_id = None
    target = None
    if request.can_read_body:
        try:
            data = await request.json()
            preset_id = data.get("preset")
            target = data.get("target")
        except Exception:
            pass

    if preset_id is None:
        preset_id = request.query.get("preset")
    if target is None:
        target = request.query.get("target", CURRENT_TARGET)

    if preset_id is None:
        return web.json_response({"error": "Missing preset"}, status=400)

    try:
        preset_id = int(preset_id)
    except ValueError:
        return web.json_response({"error": "Invalid preset ID"}, status=400)

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
    global CURRENT_MODE
    mode = request.query.get("mode")
    if mode not in ("preview", "program"):
        return web.json_response({"error": "Invalid mode"}, status=400)
    CURRENT_MODE = mode
    return web.json_response({"status": "ok", "mode": CURRENT_MODE})


async def handle_get_mode(request):
    return web.json_response({"mode": CURRENT_MODE})


async def start_http_server():
    app = web.Application()
    app.router.add_get("/target/get", handle_status)
    app.router.add_post("/target/set", handle_set_target)
    app.router.add_post("/preset/goto", handle_goto_preset)
    app.router.add_post("/preset/save", handle_save_preset)
    app.router.add_get("/mode/get", handle_get_mode)
    app.router.add_post("/mode/set", handle_set_mode)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 1423)
    await site.start()


async def main():
    global cam_transports

    loop = asyncio.get_running_loop()

    def forward_packet(packet):
        if CURRENT_TARGET in cam_transports:
            enqueue_write(CURRENT_TARGET, packet)
        else:
            print(f"[WARN] No transport for {CURRENT_TARGET}")

    # Connect to cameras via VISCA over IP
    for cam_name, ip in camera_ips.items():
        if cam_name.startswith("cam"):
            print(f"[INFO] Connecting to {cam_name} at {ip}")
            visca_obj = ViscaOverIP(ip, VISCA_PORT)
            await visca_obj.connect(loop)
            cam_transports[cam_name] = visca_obj

    if not cam_transports:
        print("[WARN] No cameras configured")

    asyncio.create_task(writer_task())

    if joystick_type == "usb_joystick":
        print("[INFO] Starting USB joystick task")
        asyncio.create_task(evdev_joystick_task(forward_packet))
    else:
        if JOYSTICK_PORT:
            await serial_asyncio.create_serial_connection(
                loop,
                lambda: JoystickProtocol(forward_packet),
                JOYSTICK_PORT,
                baudrate=BAUDRATE,
            )
        else:
            print("[WARN] No joystick port found for serial connection")

    asyncio.create_task(start_http_server())

    # Wait forever
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())


if __name__ == "__main__":
    asyncio.run(main())
