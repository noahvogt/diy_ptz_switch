# diy_ptz_switch

For a typical livestream production environment consisting of 2 ptz cameras and one joystick / controller board, most commercial options like the [Skaarhoj PTZ Fly](https://shop.skaarhoj.com/products/ptz-fly-w-blue-pill-inside) are

- expensive
- offering no API
- nearly impossible to automate

To fix this, I built a Python-based PTZ router that enabled a single, simple PTZ Joystick to easily control two modern IP-based PTZ cameras. The server selects which camera receives the joystick input and provides a HTTP API for selecting the target camera and managing presets.

The router receives **a)** Pelco-D packets from the joystick via a USB-to-RS485 converter *OR* **b)** normal packets from a USB Joystick and translates them into VISCA-over-IP commands, which are sent to the cameras over the network (UDP port 52381).

See the following ascii diagram for the architecture.

                            +------------------------+
                            |      PTZ Joystick      |
                            |  (Pelco-D via RS-485)  |
                            |    OR USB Joystick     |
                            +------------------------+
                                         |
                                         v
                         +--------------------------------+
                         |  /dev/ttyUSBX (JOYSTICK_PORT)  |
                         |  [async serial reader]         |
                         |     OR [async evedv reader]    |
                         +--------------------------------+
                                         |
                                         v
                          +------------------------------+
                          |  Python asyncio PTZ Router   |
                          |------------------------------|
                          | - Parse Pelco-D/evdev packets|
                          | - Translate to VISCA commands|
                          | - current_target: cam1/cam2  |
                          | - Forward to selected cam(IP)|
                          | - Handle HTTP API requests   |
                          |                              |
                          |   +----------------------+   |
                          |   |     HTTP API         |   |
                          |   |----------------------|   |
                          |   | POST /target/set     |   |
                          |   | GET  /target/get     |   |
                          |   | POST /preset/goto    |   |
                          |   | POST /preset/save    |   |
                          |   | GET  /mode/get       |   |
                          |   | POST /mode/set       |   |
                          |   +----------------------+   |
                          +------------------------------+
                                         |
                    +--------------------+------------------+
                    | (Network / UDP)                       | (Network / UDP)
                    v                                       v
      +----------------------------+         +----------------------------+
      |  Camera 1 (192.168.1.3)    |         |  Camera 2 (192.168.1.4)    |
      |  [VISCA over IP]           |         |  [VISCA over IP]           |
      +----------------------------+         +----------------------------+

## Configuration

The project uses a YAML configuration file located at `~/.config/diy_ptz_switch/config.yml`.

Example configuration:

```yaml
joystick_type: "usb_joystick" # "usb_joystick" or "pelco_serial" (default)

location_roles:
  "1-4.4": joystick
  "1-4.1": cam1 # Optional if using IP
  "1-4.2": cam2 # Optional if using IP

cameras:
  cam1: "192.168.1.3"
  cam2: "192.168.1.4"
```

- `joystick_type`: Sets the input method.
  - `pelco_serial` (default): Uses a traditional Pelco-D serial joystick via a USB-to-RS485 converter.
  - `usb_joystick`: Uses a modern USB 3D PTZ joystick (HID device) using the `evdev` library.
- `location_roles`: Maps USB port locations to roles (like `joystick`). Required for `pelco_serial`.
- `cameras`: Maps camera names to their IP addresses for VISCA-over-IP communication.

## Easy Testing

You want to test the `switch.py` server, but you don't have two IP-enabled PTZ Cameras in your network? Just run two instances of `dummy_cam.py` like this:

```bash
python3 dummy_cam.py --ip 127.0.0.1 --name "Dummy Cam 1"
python3 dummy_cam.py --ip 127.0.0.2 --name "Dummy Cam 2"
```

Obviously, the camera targets in your `config.yml` need to point to the dummy cam IP's:

```yaml
cameras:
  cam1: "127.0.0.1"
  cam2: "127.0.0.2"
```

## Recommended Hardware

There are basically two technologies to choose from when getting a joystick:

- **Potentiometer Joysticks:**
    - These rely on physical contact. A wiper moves across a resistive element (like a volume knob) to change the voltage based on position.
    - **Precision:** Generally lower. They are prone to "jitter" as the wiper moves, which can cause micro-stutters in your PTZ pans.
    - **Durability:** The resistive track wears down over time due to friction, eventually leading to dead zones or "drifting" (where the camera moves even when the stick is centered).
    - **Cost:** Very affordable; common in budget CCTV controllers.
- **Hall Effect Joysticks:**
    - These are contactless. They use magnets and a sensor to detect position based on magnetic field strength.
    - **Precision:** Extremely high. Because there is no physical friction, the movement is smooth and the signal is very "clean," which is ideal for slow, cinematic camera crawls.
    - **Durability:** Virtually infinite mechanical life. Since nothing is rubbing together, the sensor won't wear out or drift over time.
    - **Cost:** More expensive, but considered the industry standard for professional broadcast production (like the Skaarhoj units mentioned above).

If you ever encountered joystick drift while controlling cameras live using a potentiometer joystick, you will never ever go back to using potentiometer again. The inclusion of the links for the potentiometer hardware is only here for completeness, and not that i would recommend them to anyone.

### Hall Effect Joysticks
|Product|Link|Estimated Cost|
|---|---|---|
|Anxinshi USB PTZ Controller|[https://de.aliexpress.com/item/32825990133.html](https://de.aliexpress.com/item/32825990133.html)|120€|

### Potentiometer Joystick

|Product|Link|Estimated Cost|
|---|---|---|
|Cheapeast PTZ Joystick with RS-485 Output|[https://www.amazon.de/dp/B0DX3BFXM1](https://www.amazon.de/dp/B0DX3BFXM1)|50€|
|RS-485 to USB Converter|[https://de.aliexpress.com/item/1005007539998595.html](https://de.aliexpress.com/item/1005007539998595.html)|2€|

Note that out of 4 RS-485 to USB Converters I bought, only 3 worked.

## Roadmap

Possible changes in future releases:

- Add back the options to output the camera signals over RS-485 (currently fixed to IP/Ethernet/RJ45, but the git history contains working code from the RS-485 days)
- Code Cleanup (especially the globals, don't look at all the pylint warnings)
- API Doc (probably using OpenAPI/swagger by switching to fastapi/uvicorn)
- more RESTful API (use `PUT` instead of `POST` requests)
- less hardcoding of values (ports, baudrate, usb device name), they should be configurable via `config.yml`
- add a testsuite
- a rust rewrite?
