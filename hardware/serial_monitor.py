#!/usr/bin/env python3
"""
Simple serial monitor for ESP8266 debugging
Reads from serial port and displays output with timestamps
"""

import argparse
import sys
import time
from datetime import datetime


def main():
    parser = argparse.ArgumentParser(description="Timestamp Spoolio serial output")
    parser.add_argument("port", help="serial port, for example /dev/cu.usbserial-0001")
    parser.add_argument("--baud", type=int, default=115200)
    args = parser.parse_args()

    try:
        import serial
    except ImportError:
        parser.error("pyserial is required: python -m pip install pyserial")

    print(f"Opening serial port {args.port} at {args.baud} baud...")
    print("Press Ctrl+C to exit\n")
    print("=" * 80)

    try:
        with serial.Serial(args.port, args.baud, timeout=1) as connection:
            time.sleep(2)  # Wait for connection to stabilize

            print("Connected! Monitoring output...\n")

            while True:
                if connection.in_waiting > 0:
                    line = connection.readline()
                    decoded = line.decode('utf-8', errors='replace').rstrip()
                    timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
                    print(f"[{timestamp}] {decoded}")
                time.sleep(0.01)

    except serial.SerialException as e:
        print(f"Serial error: {e}")
        return 1
    except KeyboardInterrupt:
        print("\n\nStopping monitor...")
        return 0

    return 0

if __name__ == "__main__":
    sys.exit(main())
