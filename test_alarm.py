"""Unit tests for alarm.py — focused on pure logic and CLI commands."""

import json
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import click
from click.testing import CliRunner

# ---------------------------------------------------------------------------
# Helpers to import the module with a patched ALARMS_FILE so tests never
# touch ~/.alarm_clock/alarms.json.
# ---------------------------------------------------------------------------
import importlib
import alarm  # noqa: E402  (imported after path setup)


class AlarmTestBase(unittest.TestCase):
    """Sets up an isolated temp JSON file for each test."""

    def setUp(self):
        self.runner = CliRunner()
        # Each test gets its own fresh in-memory filesystem via CliRunner's
        # isolated filesystem, but we also patch ALARMS_FILE directly so
        # load/save in alarm.py always hits the temp file.
        self._fs_ctx = self.runner.isolated_filesystem()
        self._fs_ctx.__enter__()
        self.tmp_file = Path("alarms.json")
        self.tmp_file.write_text("{}")
        # Redirect alarm module's storage to the temp file.
        self._orig_file = alarm.ALARMS_FILE
        alarm.ALARMS_FILE = self.tmp_file

    def tearDown(self):
        alarm.ALARMS_FILE = self._orig_file
        self._fs_ctx.__exit__(None, None, None)

    # Convenience ---------------------------------------------------------

    def _load(self) -> dict:
        return json.loads(self.tmp_file.read_text())

    def _seed(self, data: dict):
        self.tmp_file.write_text(json.dumps(data))


# ===========================================================================
# parse_duration
# ===========================================================================

class TestParseDuration(unittest.TestCase):

    def test_minutes_only(self):
        self.assertEqual(alarm.parse_duration("5m"), timedelta(minutes=5))

    def test_hours_only(self):
        self.assertEqual(alarm.parse_duration("2h"), timedelta(hours=2))

    def test_seconds_only(self):
        self.assertEqual(alarm.parse_duration("90s"), timedelta(seconds=90))

    def test_combined_hours_and_minutes(self):
        self.assertEqual(alarm.parse_duration("1h30m"), timedelta(hours=1, minutes=30))

    def test_combined_all_three(self):
        self.assertEqual(alarm.parse_duration("2h15m10s"), timedelta(hours=2, minutes=15, seconds=10))

    def test_whitespace_stripped(self):
        self.assertEqual(alarm.parse_duration("  10m  "), timedelta(minutes=10))

    def test_bare_integer_raises(self):
        with self.assertRaises(click.BadParameter):
            alarm.parse_duration("30")

    def test_letters_only_raises(self):
        with self.assertRaises(click.BadParameter):
            alarm.parse_duration("badformat")

    def test_empty_string_raises(self):
        with self.assertRaises(click.BadParameter):
            alarm.parse_duration("")


# ===========================================================================
# parse_alarm_time — past time schedules tomorrow
# ===========================================================================

class TestParseAlarmTime(unittest.TestCase):

    def _fixed_now(self, hour=12, minute=0):
        return datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0)

    def test_future_time_stays_today(self):
        now = self._fixed_now(hour=8, minute=0)
        with patch("alarm.datetime") as mock_dt:
            mock_dt.now.return_value = now
            mock_dt.strptime = datetime.strptime
            result = alarm.parse_alarm_time("09:00")
        self.assertEqual(result.date(), now.date())
        self.assertEqual(result.hour, 9)

    def test_past_time_schedules_tomorrow(self):
        now = self._fixed_now(hour=14, minute=0)
        with patch("alarm.datetime") as mock_dt:
            mock_dt.now.return_value = now
            mock_dt.strptime = datetime.strptime
            result = alarm.parse_alarm_time("08:00")
        self.assertEqual(result.date(), (now + timedelta(days=1)).date())
        self.assertEqual(result.hour, 8)

    def test_same_minute_schedules_tomorrow(self):
        now = self._fixed_now(hour=10, minute=30)
        with patch("alarm.datetime") as mock_dt:
            mock_dt.now.return_value = now
            mock_dt.strptime = datetime.strptime
            result = alarm.parse_alarm_time("10:30")
        self.assertEqual(result.date(), (now + timedelta(days=1)).date())

    def test_12h_am_format(self):
        now = self._fixed_now(hour=6, minute=0)
        with patch("alarm.datetime") as mock_dt:
            mock_dt.now.return_value = now
            mock_dt.strptime = datetime.strptime
            result = alarm.parse_alarm_time("07:30 AM")
        self.assertEqual(result.hour, 7)

    def test_12h_pm_format(self):
        now = self._fixed_now(hour=6, minute=0)
        with patch("alarm.datetime") as mock_dt:
            mock_dt.now.return_value = now
            mock_dt.strptime = datetime.strptime
            result = alarm.parse_alarm_time("2:30 PM")
        self.assertEqual(result.hour, 14)

    def test_invalid_time_raises(self):
        with self.assertRaises(click.BadParameter):
            alarm.parse_alarm_time("99:99")

    def test_garbage_raises(self):
        with self.assertRaises(click.BadParameter):
            alarm.parse_alarm_time("not-a-time")


# ===========================================================================
# add command — mutual exclusivity and daily repeat storage
# ===========================================================================

class TestAddCommand(AlarmTestBase):

    def test_both_flags_rejected(self):
        result = self.runner.invoke(alarm.cli, ["add", "--time", "09:00", "--in", "5m"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("mutually exclusive", result.output)

    def test_neither_flag_rejected(self):
        result = self.runner.invoke(alarm.cli, ["add", "--label", "oops"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("--time or --in", result.output)

    def test_add_with_duration_succeeds(self):
        result = self.runner.invoke(alarm.cli, ["add", "--in", "30m", "--label", "break"])
        self.assertEqual(result.exit_code, 0)
        alarms = self._load()
        self.assertEqual(len(alarms), 1)
        a = next(iter(alarms.values()))
        self.assertEqual(a["label"], "break")
        self.assertEqual(a["repeat"], "once")
        self.assertTrue(a["active"])

    def test_add_daily_repeat_stored(self):
        result = self.runner.invoke(alarm.cli, ["add", "--in", "1h", "--repeat", "daily"])
        self.assertEqual(result.exit_code, 0)
        alarms = self._load()
        a = next(iter(alarms.values()))
        self.assertEqual(a["repeat"], "daily")

    def test_daily_base_time_stored(self):
        result = self.runner.invoke(alarm.cli, ["add", "--in", "1h", "--repeat", "daily"])
        self.assertEqual(result.exit_code, 0)
        alarms = self._load()
        a = next(iter(alarms.values()))
        # base_time must be HH:MM
        self.assertRegex(a["base_time"], r"^\d{2}:\d{2}$")

    def test_add_increments_id(self):
        self.runner.invoke(alarm.cli, ["add", "--in", "5m"])
        self.runner.invoke(alarm.cli, ["add", "--in", "10m"])
        alarms = self._load()
        self.assertIn("1", alarms)
        self.assertIn("2", alarms)

    def test_invalid_repeat_value_rejected(self):
        result = self.runner.invoke(alarm.cli, ["add", "--in", "5m", "--repeat", "weekly"])
        self.assertNotEqual(result.exit_code, 0)


# ===========================================================================
# delete command
# ===========================================================================

class TestDeleteCommand(AlarmTestBase):

    def _add_alarm(self, alarm_id="1"):
        self._seed({
            alarm_id: {
                "id": alarm_id,
                "label": "test",
                "next_fire": (datetime.now() + timedelta(hours=1)).isoformat(),
                "base_time": "09:00",
                "repeat": "once",
                "active": True,
            }
        })

    def test_delete_existing_alarm(self):
        self._add_alarm("1")
        result = self.runner.invoke(alarm.cli, ["delete", "1"])
        self.assertEqual(result.exit_code, 0)
        self.assertNotIn("1", self._load())

    def test_delete_removes_only_target(self):
        self._seed({
            "1": {"id": "1", "label": "a", "next_fire": (datetime.now() + timedelta(hours=1)).isoformat(),
                  "base_time": "08:00", "repeat": "once", "active": True},
            "2": {"id": "2", "label": "b", "next_fire": (datetime.now() + timedelta(hours=2)).isoformat(),
                  "base_time": "09:00", "repeat": "once", "active": True},
        })
        self.runner.invoke(alarm.cli, ["delete", "1"])
        alarms = self._load()
        self.assertNotIn("1", alarms)
        self.assertIn("2", alarms)

    def test_delete_unknown_id_exits_nonzero(self):
        result = self.runner.invoke(alarm.cli, ["delete", "999"])
        self.assertNotEqual(result.exit_code, 0)

    def test_delete_unknown_id_prints_error(self):
        result = self.runner.invoke(alarm.cli, ["delete", "999"])
        self.assertIn("999", result.output)


# ===========================================================================
# snooze command
# ===========================================================================

class TestSnoozeCommand(AlarmTestBase):

    def _add_alarm(self, alarm_id="1", fire_offset_hours=1):
        self._seed({
            alarm_id: {
                "id": alarm_id,
                "label": "test",
                "next_fire": (datetime.now() + timedelta(hours=fire_offset_hours)).isoformat(),
                "base_time": "09:00",
                "repeat": "once",
                "active": True,
            }
        })

    def test_snooze_pushes_fire_time_forward(self):
        self._add_alarm("1", fire_offset_hours=1)
        before = datetime.now()
        result = self.runner.invoke(alarm.cli, ["snooze", "1", "--minutes", "10"])
        self.assertEqual(result.exit_code, 0)
        new_fire = datetime.fromisoformat(self._load()["1"]["next_fire"])
        # new_fire should be ~10 minutes from now, not 1 hour
        self.assertGreater(new_fire, before + timedelta(minutes=9))
        self.assertLess(new_fire, before + timedelta(minutes=11))

    def test_snooze_default_five_minutes(self):
        self._add_alarm("1")
        before = datetime.now()
        self.runner.invoke(alarm.cli, ["snooze", "1"])
        new_fire = datetime.fromisoformat(self._load()["1"]["next_fire"])
        self.assertGreater(new_fire, before + timedelta(minutes=4))
        self.assertLess(new_fire, before + timedelta(minutes=6))

    def test_snooze_reactivates_inactive_alarm(self):
        self._seed({
            "1": {
                "id": "1", "label": "done",
                "next_fire": (datetime.now() - timedelta(hours=1)).isoformat(),
                "base_time": "07:00", "repeat": "once", "active": False,
            }
        })
        self.runner.invoke(alarm.cli, ["snooze", "1", "--minutes", "5"])
        self.assertTrue(self._load()["1"]["active"])

    def test_snooze_unknown_id_exits_nonzero(self):
        result = self.runner.invoke(alarm.cli, ["snooze", "999"])
        self.assertNotEqual(result.exit_code, 0)

    def test_snooze_preserves_base_time(self):
        self._add_alarm("1")
        self.runner.invoke(alarm.cli, ["snooze", "1", "--minutes", "5"])
        self.assertEqual(self._load()["1"]["base_time"], "09:00")


if __name__ == "__main__":
    unittest.main(verbosity=2)
