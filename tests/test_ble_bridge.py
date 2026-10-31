import pytest

from pulse_data.ble_bridge import parse_hrm, rmssd


@pytest.mark.parametrize("data, expected", [
    ([0x00, 72], (72, [])),                                   # uint8 heart rate
    ([0x01, 72, 0], (72, [])),                                # uint16 heart rate
    ([0x01, 0x2C, 0x01], (300, [])),                          # uint16 above 255
    ([0x18, 60, 0x10, 0, 0, 4, 0, 4], (60, [1000.0, 1000.0])),  # energy skipped, two RR of 1024/1024 s
    ([0x16, 60, 0, 4], (60, [1000.0])),                       # contact detected, RR
    ([0x04, 72], (None, [])),                                 # contact supported but not detected
    ([0x00, 0], (None, [])),                                  # 0 bpm is no reading
])
def test_parse_hrm(data, expected):
    assert parse_hrm(bytes(data)) == expected


def test_rmssd():
    assert rmssd([800, 810] * 15) == 10.0
    assert rmssd([800, 810] * 14) is None                    # fewer than 30 intervals
    assert rmssd([800, 810] * 15 + [100, 5000]) == 10.0      # implausible beats dropped
