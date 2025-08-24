from serial.tools import list_ports

for port in list_ports.comports():
    if "LOCATION=" in port.hwid:
        print(port.hwid)
