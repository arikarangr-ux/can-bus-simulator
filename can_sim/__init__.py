"""DBC-driven EV powertrain CAN simulator with E2E checks."""

from pathlib import Path

import cantools

from .ecu import CyclicMessage, SimulatedEcu, build_ev_network
from .monitor import BusMonitor, Fault, FaultEvent

DEFAULT_DBC = Path(__file__).resolve().parent.parent / "dbc" / "ev_powertrain.dbc"


def load_dbc(path: Path = DEFAULT_DBC) -> cantools.database.Database:
    return cantools.database.load_file(str(path))


__all__ = [
    "BusMonitor",
    "CyclicMessage",
    "DEFAULT_DBC",
    "Fault",
    "FaultEvent",
    "SimulatedEcu",
    "build_ev_network",
    "load_dbc",
]
