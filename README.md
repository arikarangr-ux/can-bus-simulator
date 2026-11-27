# can-bus-simulator

![CI](https://github.com/arikarangr-ux/can-bus-simulator/actions/workflows/ci.yml/badge.svg)

A **DBC-driven CAN simulator for an EV powertrain** in Python, with receiver-side **E2E checks**: alive counters, SAE J1850 CRC-8 and message timeouts.

Three simulated ECUs (BMS, traction inverter, 12 V DC-DC) send cyclic frames defined in a DBC file. A monitor plays the role of the VCU and flags lost, repeated, corrupted or timed-out messages, the same checks AUTOSAR E2E and a gateway's timeout monitoring do on a real vehicle network.

## What it shows

- **DBC encoding/decoding** with `cantools`: scaling, offsets, signed signals, value tables, `GenMsgCycleTime`
- **Cyclic transmission** at each message's own rate (10 / 20 / 100 ms) on a `python-can` bus
- **E2E protection**: 4-bit alive counter plus CRC-8 SAE J1850 over payload and data ID
- **Fault detection**: CRC errors, repeated frames, lost frames and timeouts (3 × cycle time)
- **Fault injection** from the command line to drop or corrupt frames
- **Plausible signals** from a simple battery model and a 30 s drive cycle (traction and regen)

## Run it

```sh
pip install -r requirements.txt
python -m can_sim --duration 2000 --drop INV_Status@500:100 --corrupt BMS_Status@1200
```

```text
[     0 ms] BMS  394.0 V     8.0 A  SOC  80.0 % | INV      0 rpm  250.0 Nm  Torque
[   500 ms] BMS  390.7 V    42.3 A  SOC  80.0 % | INV    462 rpm  249.7 Nm  Torque
[   521 ms] FAULT INV_Status       TIMEOUT      no frame for 31 ms
[   600 ms] FAULT INV_Status       LOST_FRAMES  10 frame(s) missing
[  1000 ms] BMS  387.9 V    76.6 A  SOC  80.0 % | INV    941 rpm  248.6 Nm  Torque
[  1200 ms] FAULT BMS_Status       CRC_ERROR
[  1210 ms] FAULT BMS_Status       LOST_FRAMES  1 frame(s) missing
[  1500 ms] BMS  385.2 V   110.7 A  SOC  80.0 % | INV   1408 rpm  246.9 Nm  Torque

4 fault(s) detected
```

By default it uses python-can's in-process `virtual` bus, so no hardware is needed. On Linux you can put the traffic on SocketCAN and watch it with `candump`:

```sh
sudo modprobe vcan && sudo ip link add dev vcan0 type vcan && sudo ip link set up vcan0
python -m can_sim --interface socketcan --channel vcan0 --duration 10000 &
candump -td vcan0
```

## Network

| ID | Message | Sender | Cycle | Signals |
|---|---|---|---|---|
| `0x100` | BMS_Status | BMS | 10 ms | Pack voltage, current, SOC, state |
| `0x101` | BMS_Temperatures | BMS | 100 ms | Cell max/min, coolant temp |
| `0x200` | INV_Status | Inverter | 10 ms | Motor speed, torque, IGBT temp, state |
| `0x300` | DCDC_Status | DC-DC | 20 ms | 12 V output voltage and current, state |

Every message carries an alive counter in bits 44–47 and a CRC in byte 7. See [`dbc/ev_powertrain.dbc`](dbc/ev_powertrain.dbc).

## Tests

```sh
pytest -v
```

The tests cover the CRC against the AUTOSAR reference vectors, counter wrap-around, per-message cycle times, fault-free runs with sane values, and each fault type (timeout timing, lost-frame count, CRC rejection, replay detection). Simulated time is driven explicitly, so the tests are deterministic and run in well under a second.

## Layout

```
dbc/ev_powertrain.dbc   Network definition
can_sim/ecu.py          Cyclic transmitter, E2E protection, fault injection
can_sim/monitor.py      Receiver: decode, CRC / counter / timeout checks
can_sim/e2e.py          CRC-8 SAE J1850 and counter helpers
can_sim/models.py       Battery model and drive cycle
can_sim/__main__.py     Command-line demo
tests/                  pytest suite
```
