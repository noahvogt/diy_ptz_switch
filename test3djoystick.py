import evdev
from evdev import ecodes


def test_joystick():
    # find the Anxinshi device
    target_device = None
    devices = [evdev.InputDevice(path) for path in evdev.list_devices()]

    for device in devices:
        if "shenzhenxiaolong" in device.name.lower():
            target_device = device
            break

    if not target_device:
        print("Anxinshi device not found. You may not have the permissions.")
        return

    print(f"Testing Device: {target_device.name}")

    # check capabilities
    caps = target_device.capabilities()
    if ecodes.EV_ABS in caps:
        abs_axes = caps[ecodes.EV_ABS]
        print(f"Detected {len(abs_axes)} absolute axes.")
        for axis in abs_axes:
            axis_code = axis[0]
            print(f" - Axis found: {ecodes.ABS[axis_code]}")

    print("\n--- Monitoring Movements (Ctrl+C to exit) ---")
    try:
        for event in target_device.read_loop():
            if event.type == ecodes.EV_ABS:
                axis_name = ecodes.ABS.get(event.code, f"Unknown({event.code})")
                print(f"Event: {axis_name:<10} Value: {event.value:<5}")
    except KeyboardInterrupt:
        print("\nTest finished.")


if __name__ == "__main__":
    test_joystick()
