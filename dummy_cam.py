import socket
import argparse

def main():
    parser = argparse.ArgumentParser(description="Dummy VISCA PTZ Camera")
    parser.add_argument("--ip", type=str, default="127.0.0.1", help="IP to bind to")
    parser.add_argument("--port", type=int, default=52381, help="UDP port to bind to")
    parser.add_argument("--name", type=str, default="Cam", help="Name for log outputs")
    args = parser.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((args.ip, args.port))
    
    print(f"[{args.name}] Listening for VISCA UDP packets on {args.ip}:{args.port}...")

    try:
        while True:
            data, addr = sock.recvfrom(1024)
            # Format the output as spaced hex for easy reading (e.g., 81 01 06 01 ...)
            hex_data = ' '.join(f'{b:02X}' for b in data)
            print(f"[{args.name}] Received from {addr}: {hex_data}")
    except KeyboardInterrupt:
        print(f"\n[{args.name}] Shutting down.")

if __name__ == "__main__":
    main()
