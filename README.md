# diy_ptz_switch

For a typical livestream production environment consisting of 2 ptz cameras and one joystick / controller board, most commercial options like the [Skaarhoj PTZ Fly](https://shop.skaarhoj.com/products/ptz-fly-w-blue-pill-inside) are
- expensive
- offering no API
- nearly impossible to automate

To fix this, I built a Python-based PTZ router that connects a traditional Pelco-D serial joystick to modern IP-based PTZ cameras. This server selects which camera receives the joystick input and provides a HTTP API for selecting the target camera and managing presets.

The router receives Pelco-D packets from the joystick via a USB-to-RS485 converter and translates them into VISCA-over-IP commands, which are sent to the cameras over the network (UDP port 52381).

See the following ascii diagram for the architecture.

                            +------------------------+
                            |      PTZ Joystick      |
                            |  (Pelco-D via RS-485)  |
                            +------------------------+
                                         |
                                         v
                         +--------------------------------+
                         |  /dev/ttyUSBX (JOYSTICK_PORT)  |
                         |  [async serial reader]         |
                         +--------------------------------+
                                         |
                                         v
                          +------------------------------+
                          |  Python asyncio PTZ Router   |
                          |------------------------------|
                          | - Parse Pelco-D packets      |
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
location_roles:
  "1-4.4": joystick
  "1-4.1": cam1 # Optional if using IP
  "1-4.2": cam2 # Optional if using IP

cameras:
  cam1: "192.168.1.3"
  cam2: "192.168.1.4"
```

- `location_roles`: Maps USB port locations to roles (like `joystick`).
- `cameras`: Maps camera names to their IP addresses for VISCA-over-IP communication.

