import evdev
from evdev import ecodes


def build_speed_button_map():
    speed_button_map = {}
    joystick_button_names = (
        "BTN_TRIGGER",
        "BTN_THUMB",
        "BTN_THUMB2",
        "BTN_TOP",
        "BTN_TOP2",
        "BTN_PINKIE",
        "BTN_BASE",
        "BTN_BASE2",
    )
    for speed_level in range(1, 9):
        for key_name in (
            f"KEY_{speed_level}",
            f"BTN_{speed_level}",
            f"BTN_TRIGGER_HAPPY{speed_level}",
            joystick_button_names[speed_level - 1],
        ):
            key_code = getattr(ecodes, key_name, None)
            if key_code is not None:
                speed_button_map[key_code] = speed_level
    return speed_button_map


SPEED_BUTTON_MAP = build_speed_button_map()


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

    if ecodes.EV_KEY in caps:
        keys = caps[ecodes.EV_KEY]
        print(f"Detected {len(keys)} button/key codes.")

    print("\n--- Monitoring Movements (Ctrl+C to exit) ---")
    print("Press joystick buttons 1-8 to confirm their event codes.")
    try:
        for event in target_device.read_loop():
            if event.type == ecodes.EV_ABS:
                axis_name = ecodes.ABS.get(event.code, f"Unknown({event.code})")
                print(f"Event: {axis_name:<10} Value: {event.value:<5}")
            elif event.type == ecodes.EV_KEY:
                key_name = ecodes.KEY.get(event.code, f"Unknown({event.code})")
                state = {
                    0: "released",
                    1: "pressed",
                    2: "held",
                }.get(event.value, f"value={event.value}")
                speed_level = SPEED_BUTTON_MAP.get(event.code)
                if speed_level is not None:
                    print(
                        f"Event: {key_name:<25} {state:<8} "
                        f"-> speed level {speed_level}/8 in switch.py"
                    )
                else:
                    print(f"Event: {key_name:<25} {state:<8}")
    except KeyboardInterrupt:
        print("\nTest finished.")


if __name__ == "__main__":
    test_joystick()
