from can_sim.e2e import counter_delta, crc8_sae_j1850, next_counter


def test_crc8_sae_j1850_known_vectors():
    # Reference values from the AUTOSAR CRC library specification (no data ID).
    def crc_plain(data: bytes) -> int:
        crc = 0xFF
        for byte in data:
            crc ^= byte
            for _ in range(8):
                crc = ((crc << 1) ^ 0x1D) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
        return crc ^ 0xFF

    assert crc_plain(bytes([0x00, 0x00, 0x00, 0x00])) == 0x59
    assert crc_plain(bytes([0xF2, 0x01, 0x83])) == 0x37
    assert crc_plain(bytes([0x0F, 0xAA, 0x00, 0x55])) == 0x79
    assert crc_plain(bytes([0x00, 0xFF, 0x55, 0x11])) == 0xB8
    assert crc_plain(bytes([0x33, 0x22, 0x55, 0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF])) == 0xCB
    assert crc_plain(bytes([0x92, 0x6B, 0x55])) == 0x8C
    assert crc_plain(bytes([0xFF, 0xFF, 0xFF, 0xFF])) == 0x74


def test_data_id_changes_crc():
    payload = bytes(range(7))
    assert crc8_sae_j1850(payload, data_id=0x00) != crc8_sae_j1850(payload, data_id=0x01)


def test_counter_wraps_at_16():
    assert next_counter(14) == 15
    assert next_counter(15) == 0


def test_counter_delta():
    assert counter_delta(3, 4) == 1
    assert counter_delta(15, 0) == 1
    assert counter_delta(5, 5) == 0
    assert counter_delta(14, 2) == 4
