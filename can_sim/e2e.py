"""End-to-end protection helpers: SAE J1850 CRC-8 and 4-bit alive counters.

This mirrors the idea behind AUTOSAR E2E Profile 1/2: every protected frame
carries a rolling counter and a CRC over its payload, so the receiver can
detect lost, repeated, stale or corrupted messages.
"""

from __future__ import annotations

CRC8_SAE_J1850_POLY = 0x1D
CRC8_SAE_J1850_INIT = 0xFF
CRC8_SAE_J1850_XOR_OUT = 0xFF


def crc8_sae_j1850(data: bytes, data_id: int = 0) -> int:
    """CRC-8 SAE J1850 over a data ID byte followed by the payload.

    Including a data ID (normally the CAN ID's low byte) means a frame that
    ends up on the wrong ID fails the CRC check even if its payload is valid.
    """
    crc = CRC8_SAE_J1850_INIT
    for byte in bytes([data_id & 0xFF]) + data:
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ CRC8_SAE_J1850_POLY) if crc & 0x80 else (crc << 1)
            crc &= 0xFF
    return crc ^ CRC8_SAE_J1850_XOR_OUT


def next_counter(counter: int) -> int:
    """Advance a 4-bit alive counter (0..15, wraps)."""
    return (counter + 1) & 0x0F


def counter_delta(previous: int, current: int) -> int:
    """Number of counter steps from previous to current, modulo 16.

    1 means in sequence, 0 means repeated, >1 means frames were lost.
    """
    return (current - previous) & 0x0F
