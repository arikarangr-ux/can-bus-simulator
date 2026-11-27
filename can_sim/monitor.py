"""Receiver-side monitor: decodes frames and checks E2E protection and timing."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

import can
import cantools

from .e2e import counter_delta, crc8_sae_j1850


class Fault(str, Enum):
    CRC_ERROR = "CRC_ERROR"
    REPEATED = "REPEATED"
    LOST_FRAMES = "LOST_FRAMES"
    TIMEOUT = "TIMEOUT"


@dataclass
class FaultEvent:
    time_ms: int
    message: str
    fault: Fault
    detail: str = ""


@dataclass
class _Track:
    cycle_ms: int
    last_counter: Optional[int] = None
    last_rx_ms: Optional[int] = None
    timed_out: bool = False


@dataclass
class BusMonitor:
    """Checks every received frame like a gateway or VCU would.

    A message is reported as timed out once nothing valid has arrived for
    ``timeout_factor`` x its cycle time (3x is a common choice).
    """

    db: cantools.database.Database
    timeout_factor: float = 3.0
    faults: List[FaultEvent] = field(default_factory=list)
    latest: Dict[str, Dict[str, object]] = field(default_factory=dict)
    _tracks: Dict[int, _Track] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for msg in self.db.messages:
            cycle = msg.cycle_time or 0
            if cycle:
                self._tracks[msg.frame_id] = _Track(cycle_ms=cycle)

    def on_frame(self, frame: can.Message, now_ms: int) -> None:
        try:
            definition = self.db.get_message_by_frame_id(frame.arbitration_id)
        except KeyError:
            return
        track = self._tracks.get(frame.arbitration_id)
        data = bytes(frame.data)

        if crc8_sae_j1850(data[:7], data_id=definition.frame_id) != data[7]:
            self._fault(now_ms, definition.name, Fault.CRC_ERROR)
            return  # never use data from a corrupted frame

        decoded = definition.decode(data, decode_choices=True)
        counter_name = next(s.name for s in definition.signals if "AliveCounter" in s.name)
        counter = int(decoded[counter_name])

        if track is not None:
            if track.last_counter is not None:
                delta = counter_delta(track.last_counter, counter)
                if delta == 0:
                    self._fault(now_ms, definition.name, Fault.REPEATED)
                    return
                if delta > 1:
                    self._fault(now_ms, definition.name, Fault.LOST_FRAMES,
                                f"{delta - 1} frame(s) missing")
            track.last_counter = counter
            track.last_rx_ms = now_ms
            track.timed_out = False

        self.latest[definition.name] = decoded

    def check_timeouts(self, now_ms: int) -> None:
        for frame_id, track in self._tracks.items():
            if track.last_rx_ms is None or track.timed_out:
                continue
            if now_ms - track.last_rx_ms > track.cycle_ms * self.timeout_factor:
                track.timed_out = True
                name = self.db.get_message_by_frame_id(frame_id).name
                self._fault(now_ms, name, Fault.TIMEOUT,
                            f"no frame for {now_ms - track.last_rx_ms} ms")

    def faults_of(self, fault: Fault) -> List[FaultEvent]:
        return [f for f in self.faults if f.fault == fault]

    def _fault(self, now_ms: int, name: str, fault: Fault, detail: str = "") -> None:
        self.faults.append(FaultEvent(now_ms, name, fault, detail))
