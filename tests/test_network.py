import itertools

import can
import pytest

from can_sim import BusMonitor, Fault, build_ev_network, load_dbc

_channels = itertools.count()


@pytest.fixture
def setup():
    db = load_dbc()
    channel = f"test{next(_channels)}"
    tx = can.Bus(interface="virtual", channel=channel)
    rx = can.Bus(interface="virtual", channel=channel)
    ecu = build_ev_network(db, tx)
    monitor = BusMonitor(db)
    yield db, ecu, rx, monitor
    tx.shutdown()
    rx.shutdown()


def run(ecu, rx, monitor, until_ms, before_step=None):
    for now in range(ecu.now_ms, until_ms + 1):
        if before_step:
            before_step(now)
        ecu.run_until(now)
        while (frame := rx.recv(timeout=0)) is not None:
            monitor.on_frame(frame, now)
        monitor.check_timeouts(now)


def test_dbc_has_expected_messages(setup):
    db, *_ = setup
    names = {m.name for m in db.messages}
    assert names == {"BMS_Status", "BMS_Temperatures", "INV_Status", "DCDC_Status"}
    assert db.get_message_by_name("BMS_Status").cycle_time == 10


def test_cycle_times_are_respected(setup):
    _, ecu, rx, monitor = setup
    counts = {}

    def count(frame):
        counts[frame.arbitration_id] = counts.get(frame.arbitration_id, 0) + 1

    ecu.run_until(999, on_send=count)
    assert counts[0x100] == 100   # 10 ms
    assert counts[0x101] == 10    # 100 ms
    assert counts[0x200] == 100   # 10 ms
    assert counts[0x300] == 50    # 20 ms


def test_clean_run_has_no_faults_and_sane_values(setup):
    _, ecu, rx, monitor = setup
    run(ecu, rx, monitor, 3000)
    assert monitor.faults == []

    bms = monitor.latest["BMS_Status"]
    assert 330 < bms["BMS_PackVoltage"] < 420
    assert 0 <= bms["BMS_SOC"] <= 100
    assert str(bms["BMS_State"]) == "Ready"
    assert str(monitor.latest["INV_Status"]["INV_State"]) == "Torque"


def test_dropped_frames_cause_lost_frames_and_timeout(setup):
    _, ecu, rx, monitor = setup

    def drop_inverter(now):
        ecu.message("INV_Status").enabled = not (500 <= now < 600)

    run(ecu, rx, monitor, 1000, before_step=drop_inverter)

    timeouts = monitor.faults_of(Fault.TIMEOUT)
    assert [f.message for f in timeouts] == ["INV_Status"]
    # Last frame before the gap is at 490 ms; timeout fires once > 3 x 10 ms pass.
    assert timeouts[0].time_ms == 521

    lost = monitor.faults_of(Fault.LOST_FRAMES)
    assert [f.message for f in lost] == ["INV_Status"]
    assert "10 frame(s) missing" in lost[0].detail


def test_corrupted_frame_is_rejected(setup):
    _, ecu, rx, monitor = setup

    def corrupt(now):
        if now == 200:
            ecu.message("BMS_Status").corrupt_next = True

    run(ecu, rx, monitor, 400, before_step=corrupt)
    crc_errors = monitor.faults_of(Fault.CRC_ERROR)
    assert len(crc_errors) == 1 and crc_errors[0].message == "BMS_Status"
    # The frame after the corrupted one shows a counter gap of one.
    assert len(monitor.faults_of(Fault.LOST_FRAMES)) == 1


def test_repeated_frame_is_detected(setup):
    db, ecu, rx, monitor = setup
    ecu.run_until(20)
    frames = []
    while (frame := rx.recv(timeout=0)) is not None:
        frames.append(frame)
    inv = [f for f in frames if f.arbitration_id == 0x200]
    monitor.on_frame(inv[0], 0)
    monitor.on_frame(inv[0], 10)  # replay
    assert len(monitor.faults_of(Fault.REPEATED)) == 1
