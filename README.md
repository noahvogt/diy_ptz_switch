# diy_ptz_switch

For a typical livestream production environment consisting of 2 ptz cameras and one joystick / controller board, most commercial options like the [Skaarhoj PTZ Fly](https://shop.skaarhoj.com/products/ptz-fly-w-blue-pill-inside) are
- expensive
- offer no API
- nearly impossible to automate
- offer no rs485 serial connection support (basically only IP via RJ45)

To fix this, I thought why not connect the ptz cameras via their rs485 to a rs485 <-> usb serial converter to a computer and use a server that selects which ptz camera is sent the current joystick input. It also has a http api that allows seleting the current camera target and ptz commands like save_preset or goto_preset.

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
                          | - current_target: cam1/cam2  |
                          | - Forward to selected cam    |
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
                    |                                       |
                    v                                       v
      +----------------------------+         +----------------------------+
      |  /dev/ttyUSBY (CAM1_PORT)  |         |  /dev/ttyUSBZ (CAM2_PORT)  |
      |  [async serial writer]     |         |  [async serial writer]     |
      +----------------------------+         +----------------------------+
                    |                                        |
                    v                                        v
        +------------------------+              +------------------------+
        |  PTZ Camera 1          |              |   PTZ Camera 2         |
        |  (Pelco-D via RS-485)  |              |  (Pelco-D via RS-485)  |
        +------------------------+              +------------------------+

