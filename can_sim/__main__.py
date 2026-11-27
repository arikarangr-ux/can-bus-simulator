"""Command-line demo: simulate the EV network and print a decoded trace.

    python -m can_sim --duration 2000 --drop INV_Status@500:100 --corrupt BMS_Status@1200

Uses python-can's in-process "virtual" interface by default, so nothing is
needed beyond pip. Pass --interface socketcan --channel vcan0 on Linux to put
the frames on a real (or virtual) SocketCAN bus and watch them in candump.
"""

from __future__ import annotations

import argparse

import can

from . import BusMonitor, build_ev_network, load_dbc


def parse_event(spec: str):
    name, _, rest = spec.partition("@")
    start, _, length = rest.partition(":")
    return name, int(start), int(length or 0)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--duration", type=int, default=2000, help="simulated ms")
    parser.add_argument("--interface", default="virtual")
    parser.add_argument("--channel", default="sim")
    parser.add_argument("--drop", action="append", default=[],
                        help="MSG@start_ms:length_ms - stop sending a message for a while")
    parser.add_argument("--corrupt", action="append", default=[],
                        help="MSG@time_ms - corrupt one frame after its CRC is computed")
    parser.add_argument("--print-every", type=int, default=500, help="ms between snapshots")
    args = parser.parse_args()

    db = load_dbc()
    tx_bus = can.Bus(interface=args.interface, channel=args.channel, receive_own_messages=False)
    rx_bus = can.Bus(interface=args.interface, channel=args.channel)
    ecu = build_ev_network(db, tx_bus)
    monitor = BusMonitor(db)

    drops = [parse_event(s) for s in args.drop]
    corrupts = [parse_event(s) for s in args.corrupt]
    reported = 0

    try:
        for now in range(0, args.duration + 1):
            for name, start, length in drops:
                ecu.message(name).enabled = not (start <= now < start + length)
            for name, at, _ in corrupts:
                if now == at:
                    ecu.message(name).corrupt_next = True

            ecu.run_until(now)
            while (frame := rx_bus.recv(timeout=0)) is not None:
                monitor.on_frame(frame, now)
            monitor.check_timeouts(now)

            for event in monitor.faults[reported:]:
                print(f"[{event.time_ms:6d} ms] FAULT {event.message:<16} "
                      f"{event.fault.value:<12} {event.detail}")
            reported = len(monitor.faults)

            if now % args.print_every == 0 and monitor.latest:
                bms = monitor.latest.get("BMS_Status", {})
                inv = monitor.latest.get("INV_Status", {})
                print(f"[{now:6d} ms] BMS {bms.get('BMS_PackVoltage', 0):6.1f} V "
                      f"{bms.get('BMS_PackCurrent', 0):7.1f} A  SOC {bms.get('BMS_SOC', 0):5.1f} % | "
                      f"INV {inv.get('INV_MotorSpeed', 0):6.0f} rpm "
                      f"{inv.get('INV_MotorTorque', 0):6.1f} Nm  {inv.get('INV_State', '')}")
    finally:
        tx_bus.shutdown()
        rx_bus.shutdown()

    print(f"\n{len(monitor.faults)} fault(s) detected")


if __name__ == "__main__":
    main()
