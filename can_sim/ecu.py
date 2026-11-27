"""Simulated ECUs that transmit cyclic, E2E-protected frames from a DBC."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

import can
import cantools

from .e2e import crc8_sae_j1850, next_counter
from .models import BatteryModel, DriveCycle

SignalProvider = Callable[[float], Dict[str, float]]


@dataclass
class CyclicMessage:
    name: str
    provider: SignalProvider
    counter_signal: str
    crc_signal: str
    cycle_ms: int
    counter: int = 0
    next_due_ms: int = 0
    enabled: bool = True
    corrupt_next: bool = False


@dataclass
class SimulatedEcu:
    """Encodes signals with cantools and sends them on a python-can bus.

    Time is driven explicitly through :meth:`run_until` so tests are
    deterministic and the simulation can run faster than real time.
    """

    db: cantools.database.Database
    bus: can.BusABC
    messages: List[CyclicMessage] = field(default_factory=list)
    now_ms: int = 0

    def add(self, message: CyclicMessage) -> None:
        self.messages.append(message)

    def message(self, name: str) -> CyclicMessage:
        return next(m for m in self.messages if m.name == name)

    def encode(self, msg: CyclicMessage, t_s: float) -> can.Message:
        definition = self.db.get_message_by_name(msg.name)
        signals = msg.provider(t_s)
        signals[msg.counter_signal] = msg.counter
        signals[msg.crc_signal] = 0
        payload = bytearray(definition.encode(signals, strict=False))

        # CRC sits in the last byte and covers bytes 0..6 plus the data ID.
        crc = crc8_sae_j1850(bytes(payload[:7]), data_id=definition.frame_id)
        payload[7] = crc
        if msg.corrupt_next:
            payload[0] ^= 0xFF  # flip bits after the CRC was computed
            msg.corrupt_next = False

        return can.Message(
            arbitration_id=definition.frame_id,
            data=bytes(payload),
            is_extended_id=False,
            timestamp=t_s,
        )

    def run_until(self, end_ms: int, on_send: Optional[Callable[[can.Message], None]] = None) -> int:
        """Advance simulated time in 1 ms steps, sending every due frame."""
        sent = 0
        while self.now_ms <= end_ms:
            for msg in self.messages:
                if msg.next_due_ms <= self.now_ms:
                    msg.next_due_ms = self.now_ms + msg.cycle_ms
                    if msg.enabled:
                        frame = self.encode(msg, self.now_ms / 1000.0)
                        self.bus.send(frame)
                        if on_send:
                            on_send(frame)
                        sent += 1
                    # The counter advances even when a frame is dropped, so
                    # the receiver sees the gap, as with a real lost frame.
                    msg.counter = next_counter(msg.counter)
            self.now_ms += 1
        return sent


def build_ev_network(db: cantools.database.Database, bus: can.BusABC) -> SimulatedEcu:
    """Wire up BMS, inverter and DC-DC providers driven by a drive cycle."""
    battery = BatteryModel()
    cycle = DriveCycle()
    state = {"last_t": 0.0, "current": 0.0}

    def battery_signals(t: float) -> Dict[str, float]:
        dt = max(t - state["last_t"], 0.0)
        state["last_t"] = t
        voltage = battery.terminal_voltage(state["current"])
        state["current"] = cycle.battery_current(t, voltage)
        battery.step(state["current"], dt)
        return {
            "BMS_PackVoltage": round(voltage, 1),
            "BMS_PackCurrent": round(state["current"], 1),
            "BMS_SOC": round(battery.soc * 2) / 2,
            "BMS_State": 3,  # Ready
        }

    def temperature_signals(_t: float) -> Dict[str, float]:
        return {
            "BMS_CellTempMax": round(battery.cell_temp + 1.5),
            "BMS_CellTempMin": round(battery.cell_temp - 1.5),
            "BMS_CoolantTemp": round(battery.coolant_temp),
        }

    def inverter_signals(t: float) -> Dict[str, float]:
        return {
            "INV_MotorSpeed": round(cycle.motor_speed(t)),
            "INV_MotorTorque": round(cycle.motor_torque(t), 1),
            "INV_IgbtTemp": 45 + round(abs(cycle.motor_torque(t)) / 25),
            "INV_State": 2,  # Torque control
        }

    def dcdc_signals(_t: float) -> Dict[str, float]:
        return {"DCDC_OutputVoltage": 14.2, "DCDC_OutputCurrent": 32.5, "DCDC_State": 1}

    ecu = SimulatedEcu(db=db, bus=bus)
    ecu.add(CyclicMessage("BMS_Status", battery_signals, "BMS_AliveCounter", "BMS_CRC", 10))
    ecu.add(CyclicMessage("BMS_Temperatures", temperature_signals,
                          "BMS_TempAliveCounter", "BMS_TempCRC", 100))
    ecu.add(CyclicMessage("INV_Status", inverter_signals, "INV_AliveCounter", "INV_CRC", 10))
    ecu.add(CyclicMessage("DCDC_Status", dcdc_signals, "DCDC_AliveCounter", "DCDC_CRC", 20))
    return ecu
