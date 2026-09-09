"""The safety properties of ``scripts/probe.py`` that must hold before any run.

These read the script as text or drive its seams against an in-memory panel;
nothing here opens a socket. The register parser and the CI gate are covered in
``test_check_conformance.py``.
"""

import ast
import json
import re
import sys
from pathlib import Path
from typing import Any, cast

import probe
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PROBE_SOURCE = REPO_ROOT / "scripts" / "probe.py"

#: The wire shape of a real status at firmware 1.21, identifying values replaced
#: by the fixture placeholders of the spec's §8.3.
STATUS_DOC: dict[str, Any] = {
    "id": "FIXTUREFIXTUREFIXTUREX",
    "room": "Bedroom",
    "name": "Näytehuone 1",
    "state": "Idle",
    "currentPower": 0,
    "totalConsumption": 0.0,
    "roomTemperature": 23.0,
    "parameters": {
        "panelMode": 1,
        "sensorCalibration": 0.0,
        "temperatureDisplay": True,
        "sensorMode": False,
        "activeDisplayBrightness": 10,
        "standbyDisplayBrightness": 0,
        "ecoSetpoint": 18.0,
        "heatingSetpoint": 19.0,
        "minimumTemperatureLimit": 5.0,
        "maximumTemperatureLimit": 40.0,
        "OWD": {"openWindowDetection": False, "activeNow": False, "activeTime": 0},
        "loadLimit": 6,
        "maxLoad": 6,
        "disableButtons": 1,
    },
    "Network": {
        "SSID": "SSID-REDACTED",
        "mac": "02:00:00:00:00:01",
        "ipAddress": "10.0.0.2",
        "wifiSignalStrength": "-66dBm",
        "status": "ok",
    },
    "firmware": "1.21",
    "model": "Heatit WiFi Panel Heater",
}


class FakePanel:
    """A panel that applies writes to a status document, honestly or not."""

    def __init__(self, *, honest: bool = True) -> None:
        """Start from the reference status; ``honest=False`` echoes but ignores."""
        self.doc = json.loads(json.dumps(STATUS_DOC))
        self.honest = honest
        self.writes: list[tuple[str, str]] = []
        self.host = "panel.test"
        self.port = 80

    def status(self) -> probe.Status:
        """Return the current document as a status read would."""
        raw = json.dumps(self.doc).encode()
        return probe.Status(raw=raw, headers={}, doc=json.loads(raw))

    def write(self, name: str, value: str) -> probe.Response:
        """Acknowledge a write, applying it only when honest."""
        self.writes.append((name, value))
        if self.honest:
            probe.apply_wire_value(self.doc["parameters"], name, value)
        body = json.dumps({"status": "Success", name: value}).encode()
        return probe.Response(
            status=200, reason="OK", headers={}, body=body, raw_headers=b""
        )


def no_sleep(_seconds: float) -> None:
    """Stand in for ``time.sleep`` so a test never waits."""


def test_factory_reset_path_is_absent_from_the_source() -> None:
    """The path is structurally absent: not a flag, not a string, nowhere."""
    source = PROBE_SOURCE.read_text(encoding="utf-8")
    assert "reset/factory" not in source
    assert set(re.findall(r"reset/(\w+)", source)) == {"kwh", "settings"}


def test_probe_imports_only_the_standard_library() -> None:
    """A stranger with a second panel needs nothing but Python."""
    tree = ast.parse(PROBE_SOURCE.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.partition(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "no relative imports in a standalone script"
            assert node.module is not None
            imported.add(node.module.partition(".")[0])
    assert imported
    assert imported <= sys.stdlib_module_names
    assert "custom_components" not in imported


def test_every_registered_check_carries_a_known_tier() -> None:
    """Checks register an id and a tier only; the tier must be a probe tier."""
    assert probe.registered_ids()
    for row_id, entry in probe.CHECKS.items():
        assert entry.tier in probe.TIERS, row_id
        assert entry.row_id == row_id


def test_thermal_target_refuses_more_than_two_degrees_above_room() -> None:
    """No thermal check may raise a setpoint more than 2 °C above the room."""
    assert probe.thermal_target(23.0, maximum_limit=40.0) == pytest.approx(24.0)
    with pytest.raises(probe.ThermalRefusedError):
        probe.assert_thermal_setpoint(room_temperature=23.0, target=25.5)
    probe.assert_thermal_setpoint(room_temperature=23.0, target=25.0)
    assert probe.THERMAL_MAX_ABOVE_ROOM == 2.0
    assert 0 < probe.THERMAL_MAX_RELAY_SECONDS <= 60


def test_thermal_target_refuses_when_the_limit_blocks_it() -> None:
    """A maximum limit below room + 1 leaves no lawful target, so refuse."""
    with pytest.raises(probe.ThermalRefusedError):
        probe.thermal_target(23.0, maximum_limit=23.5)


@pytest.mark.parametrize(
    "body",
    [
        b'{"status":"Success","id":"FU2yTQsAVW8cYBgrehc2z4"}',
        b'{"status":"Success","name":"x"}',
        b'{"status":"Success","SSID":"x"}',
        b'{"status":"Success","mac":"x"}',
        b'{"status":"Success","ipAddress":"x"}',
        b'{"status":"Success","heatingSetpoint":19,"where":"Bedroom-Secret"}',
    ],
)
def test_fixture_saving_fails_closed_on_a_scrub_key_or_a_known_value(
    tmp_path: Path, body: bytes
) -> None:
    """A response carrying a scrub key or a known identifying value is refused."""
    response = probe.Response(
        status=200,
        reason="OK",
        headers={"Content-Type": "application/json"},
        body=body,
        raw_headers=b"Content-Type: application/json\r\n",
    )
    store = probe.FixtureStore(tmp_path, secrets=("Bedroom-Secret",))
    with pytest.raises(probe.ScrubViolationError):
        store.save("write-echo-test", response)
    assert list(tmp_path.iterdir()) == []


def test_fixture_saving_writes_raw_bytes_and_headers(tmp_path: Path) -> None:
    """A clean echo lands byte-for-byte, its headers beside it."""
    body = b'{"status":"Success","heatingSetpoint":19}'
    response = probe.Response(
        status=200,
        reason="OK",
        headers={"Content-Type": "application/json"},
        body=body,
        raw_headers=b"Content-Type: application/json\r\nContent-Length: 41\r\n",
    )
    store = probe.FixtureStore(tmp_path, secrets=())
    saved = store.save("write-echo-heatingSetpoint", response)
    assert saved.read_bytes() == body
    assert saved.with_suffix(".headers").read_bytes() == response.raw_headers
    assert saved.suffix == ".json"


def test_ledger_snapshots_before_the_first_write_and_restores_verified(
    tmp_path: Path,
) -> None:
    """Touching a parameter snapshots status once; restore rewrites and verifies."""
    panel = FakePanel()
    ledger = probe.Ledger(panel, snapshot_dir=tmp_path, sleep=no_sleep)
    assert ledger.snapshot_path is None

    ledger.touch("heatingSetpoint")
    ledger.touch("openWindowDetection")
    assert ledger.snapshot_path is not None
    snapshot = json.loads(ledger.snapshot_path.read_text(encoding="utf-8"))
    assert snapshot["touched"] == ["heatingSetpoint", "openWindowDetection"]
    assert snapshot["status"]["parameters"]["heatingSetpoint"] == 19.0

    panel.write("heatingSetpoint", "18.5")
    panel.write("openWindowDetection", "true")
    failures = ledger.restore()

    assert failures == []
    assert panel.writes[-2:] == [
        ("heatingSetpoint", "19.0"),
        ("openWindowDetection", "false"),
    ]
    assert panel.doc["parameters"]["heatingSetpoint"] == 19.0
    assert ledger.pending == ()


def test_ledger_reports_a_restore_the_status_does_not_confirm(
    tmp_path: Path,
) -> None:
    """The echo is never trusted: a silent undo on restore is a failure."""
    panel = FakePanel()
    ledger = probe.Ledger(panel, snapshot_dir=tmp_path, sleep=no_sleep)
    ledger.touch("sensorMode")
    panel.write("sensorMode", "true")
    panel.honest = False

    failures = ledger.restore()

    assert [failure.parameter for failure in failures] == ["sensorMode"]
    assert failures[0].original == "false"
    assert failures[0].observed == "true"
    banner = probe.restore_banner(panel.host, panel.port, failures)
    assert "sensorMode" in banner
    assert "curl -X POST 'http://panel.test:80/api/parameters?sensorMode=false'" in (
        banner
    )


def test_replaying_a_snapshot_restores_only_the_touched_parameters(
    tmp_path: Path,
) -> None:
    """``--restore <file>`` rewrites what the run touched and nothing else."""
    panel = FakePanel()
    ledger = probe.Ledger(panel, snapshot_dir=tmp_path, sleep=no_sleep)
    ledger.touch("standbyDisplayBrightness")
    assert ledger.snapshot_path is not None
    panel.write("standbyDisplayBrightness", "5")
    panel.write("ecoSetpoint", "17.0")
    panel.writes.clear()

    failures = probe.replay_snapshot(ledger.snapshot_path, panel, sleep=no_sleep)

    assert failures == []
    assert panel.writes == [("standbyDisplayBrightness", "0")]
    assert panel.doc["parameters"]["ecoSetpoint"] == 17.0


def make_run(panel: FakePanel, tmp_path: Path) -> probe.Run:
    """Build a run context over the fake panel that never sleeps or waits."""
    ledger = probe.Ledger(panel, snapshot_dir=tmp_path, sleep=no_sleep)
    ticks = iter(range(10_000))
    return probe.Run(
        panel=cast("probe.Panel", panel),
        ledger=ledger,
        fixtures=None,
        sleep=no_sleep,
        clock=lambda: float(next(ticks)),
    )


def test_a_check_s_writes_are_restored_before_the_next_check(
    tmp_path: Path,
) -> None:
    """Every check hands the panel back as it found it, verified, before the next."""
    panel = FakePanel()
    run = make_run(panel, tmp_path)
    seen_at_second: dict[str, object] = {}

    def first(run: probe.Run) -> str | None:
        run.write("standbyDisplayBrightness", "7")
        return None

    def second(run: probe.Run) -> str | None:
        seen_at_second.update(run.panel.status().parameters)
        return None

    checks = [
        probe.Check("Q8", probe.WRITE, first),
        probe.Check("Q31", probe.WRITE, second),
    ]
    results = probe.run_checks(checks, {}, run, frozenset({probe.WRITE}))

    assert [result.verdict for result in results] == ["PASS", "PASS"]
    assert seen_at_second["standbyDisplayBrightness"] == 0
    assert run.ledger.pending == ()


def test_a_revert_the_status_denies_stops_the_run(tmp_path: Path) -> None:
    """A check whose restore is not confirmed is the last check that runs."""
    panel = FakePanel()
    run = make_run(panel, tmp_path)

    def lying(run: probe.Run) -> str | None:
        run.write("sensorMode", "true")
        panel.honest = False
        return None

    checks = [
        probe.Check("Q58", probe.WRITE, lying),
        probe.Check("Q6", probe.WRITE, lying),
    ]
    with pytest.raises(probe.RevertFailedError):
        probe.run_checks(checks, {}, run, frozenset({probe.WRITE}))
    assert run.ledger.pending == ("sensorMode",)


def test_the_reflect_poll_compares_like_the_panel_stores(tmp_path: Path) -> None:
    """``0`` written to a boolean and ``18`` to a float both count as reflected."""
    panel = FakePanel()
    run = make_run(panel, tmp_path)
    panel.write("temperatureDisplay", "0")
    assert run.reflect("temperatureDisplay", "0")[1] is not None
    panel.write("heatingSetpoint", "18")
    assert run.reflect("heatingSetpoint", "18")[1] is not None
    assert run.reflect("heatingSetpoint", "17.5")[1] is None


def test_wire_serialisation_matches_what_the_panel_stores() -> None:
    """Floats carry one decimal, booleans are lowercase, integers are bare."""
    assert probe.serialise(19.0) == "19.0"
    assert probe.serialise(-1.0) == "-1.0"
    assert [probe.serialise(flag) for flag in (True, False)] == ["true", "false"]
    assert probe.serialise(6) == "6"


def test_a_settings_reset_touches_every_writable_parameter() -> None:
    """The restore surface of a settings reset is the whole writable set."""
    assert len(probe.WRITABLE_PARAMETERS) == 13
    assert "openWindowDetection" in probe.WRITABLE_PARAMETERS
    assert "maxLoad" not in probe.WRITABLE_PARAMETERS


def test_exit_codes_are_the_spec_s_four() -> None:
    """0 all passed, 1 a check failed, 2 a revert failed, 3 usage or connectivity."""
    assert (probe.EXIT_OK, probe.EXIT_FAILED, probe.EXIT_REVERT, probe.EXIT_USAGE) == (
        0,
        1,
        2,
        3,
    )
    assert probe.exit_code_for(["PASS", "INCONCLUSIVE", "SKIPPED"]) == probe.EXIT_OK
    assert probe.exit_code_for(["PASS", "FAIL"]) == probe.EXIT_FAILED


def test_enabled_tiers_ascend_with_the_flags() -> None:
    """Each flag enables its tier and every tier below it."""
    assert probe.enabled_tiers() == frozenset({"read"})
    assert probe.enabled_tiers(writes=True) == frozenset({"read", "write"})
    assert probe.enabled_tiers(destructive=True) == frozenset(
        {"read", "write", "destructive"}
    )
    assert probe.enabled_tiers(thermal=True) == frozenset(probe.TIERS)
