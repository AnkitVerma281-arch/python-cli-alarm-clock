"""Deterministic behavioral tests; no real waiting or host clock changes."""

from contextlib import contextmanager, redirect_stderr, redirect_stdout
from datetime import datetime
import io
import os
import subprocess
import sys
import time
import unittest
from unittest.mock import Mock, patch

import alarm


@contextmanager
def local_zone(zone):
    try:
        with patch.dict(os.environ, {"TZ": zone}):
            time.tzset()
            yield
    finally:
        time.tzset()


class ParsingTests(unittest.TestCase):
    def test_valid_values(self):
        for text, expected in (("00:00", (0, 0)), ("23:59", (23, 59))):
            self.assertEqual(alarm.parse_args(["--at", text])[1].at, [expected])
        for text, expected in (("1", 1), ("0003", 3), ("86400", 86400)):
            self.assertEqual(alarm.parse_args(["--in", text])[1].seconds, [expected])

    def test_invalid_arguments_exit_two_without_scheduling(self):
        cases = [[], ["--at"], ["--in"], ["--at", "12:00", "--in", "1"],
                 ["--in", "1", "--in", "2"], ["--at", "12:00", "--at", "13:00"],
                 ["--unknown"], ["--a", "12:00"]]
        cases += [["--at", text] for text in
                  ("9:05", "24:00", "12:60", "12:00:00", " 12:00", "１２:００", "ab:cd", "")]
        cases += [["--in", text] for text in
                  ("0", "-1", "1.5", "+1", "nan", "inf", " 3", "３", "86401", "9" * 5000, "")]
        for args in cases:
            with self.subTest(args=str(args)[:80]), redirect_stdout(io.StringIO()) as out, \
                    redirect_stderr(io.StringIO()) as err:
                clock, notify = Mock(), Mock()
                with self.assertRaises(SystemExit) as result:
                    alarm.main(args, wall_clock=clock, notify_fn=notify)
                self.assertEqual(result.exception.code, 2)
                self.assertIn("error:", err.getvalue())
                self.assertEqual(out.getvalue(), "")
                clock.assert_not_called()
                notify.assert_not_called()

    def test_import_has_no_output_or_waiting(self):
        result = subprocess.run(
            [sys.executable, "-B", "-c", "import alarm"],
            cwd=os.path.dirname(__file__), capture_output=True, text=True, timeout=5,
        )
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))

    def test_cli_process_help_and_argument_error_exits(self):
        # A small entry-point check complements the broader in-process matrix.
        cases = (
            (["--help"], 0, None),
            ([], 2, "required"),
            (["--at", "12:00", "--in", "5"], 2, "not allowed"),
        )
        for args, expected_exit, error_text in cases:
            with self.subTest(args=args):
                result = subprocess.run(
                    [sys.executable, "-B", "alarm.py", *args],
                    cwd=os.path.dirname(__file__), capture_output=True, text=True, timeout=5,
                )
                self.assertEqual(result.returncode, expected_exit)
                if error_text is None:
                    self.assertIn("--at HH:MM", result.stdout)
                    self.assertIn("--in SECONDS", result.stdout)
                    self.assertEqual(result.stderr, "")
                else:
                    self.assertEqual(result.stdout, "")
                    self.assertIn(error_text, result.stderr)
                self.assertNotIn("*** ALARM", result.stdout)
                self.assertNotIn("Traceback", result.stderr)


@unittest.skipUnless(hasattr(time, "tzset"), "requires process-local Unix timezone support")
class TargetTests(unittest.TestCase):
    def test_minute_and_calendar_rollovers(self):
        cases = [
            ("2026-01-01 09:29:59", (9, 30), "2026-01-01 09:30:00"),
            ("2026-01-01 09:30:00", (9, 30), "2026-01-02 09:30:00"),
            ("2026-01-01 09:30:20", (9, 30), "2026-01-02 09:30:00"),
            ("2026-12-31 23:59:30", (0, 0), "2027-01-01 00:00:00"),
            ("2026-01-31 23:59:59", (0, 0), "2026-02-01 00:00:00"),
            ("2028-02-28 23:59:59", (0, 0), "2028-02-29 00:00:00"),
            ("2028-02-29 23:59:59", (0, 0), "2028-03-01 00:00:00"),
            ("2026-01-01 00:00:01", (0, 0), "2026-01-02 00:00:00"),
        ]
        with local_zone("UTC0"):
            for start, requested, expected in cases:
                with self.subTest(start=start):
                    target = alarm.resolve_at(*requested, datetime.fromisoformat(start).timestamp())
                    self.assertEqual(datetime.fromtimestamp(target), datetime.fromisoformat(expected))

    def test_dst_gap_fold_and_target_offset(self):
        with local_zone("EST5EDT,M3.2.0,M11.1.0"):
            for start, requested, message in (
                ("2026-03-08 00:00:00", (2, 30), "does not exist"),
                ("2026-11-01 00:00:00", (1, 30), "ambiguous"),
            ):
                with self.assertRaisesRegex(ValueError, message):
                    alarm.resolve_at(*requested, datetime.fromisoformat(start).timestamp())
            target = alarm.resolve_at(3, 30, datetime(2026, 3, 8).timestamp())
            self.assertEqual(alarm.format_target(target), "2026-03-08 03:30:00 EDT UTC-04:00")

    def test_countdown_display_midnight_and_timezone_offset(self):
        with local_zone("IST-5:30"):
            deadline, target = alarm.resolve_countdown(3, datetime(2026, 12, 31, 23, 59, 59).timestamp(), 100)
            self.assertEqual(deadline, 103)
            self.assertEqual(alarm.format_target(target), "2027-01-01 00:00:02 IST UTC+05:30")


class WaitingTests(unittest.TestCase):
    @unittest.skipUnless(hasattr(time, "tzset"), "requires process-local Unix timezone support")
    def test_main_notifies_only_when_due_with_real_target_resolution(self):
        # Exercise parsing -> target calculation -> waiting -> notification together.
        # Explicit wake-up offsets cover reaching the deadline and missing it.
        with local_zone("UTC0"):
            start = datetime(2026, 1, 1, 9, 29, 58).timestamp()
            for args in (["--at", "09:30"], ["--in", "2"]):
                for wake_offsets in ((1, 2), (7,)):
                    with self.subTest(args=args, wake_offsets=wake_offsets):
                        state = {"elapsed": 0}
                        wakes = iter(wake_offsets)

                        def on_notify():
                            self.assertGreaterEqual(state["elapsed"], 2)

                        notify = Mock(side_effect=on_notify)

                        def sleep(seconds):
                            notify.assert_not_called()
                            self.assertTrue(0 < seconds <= 1)
                            state["elapsed"] = next(wakes)

                        with redirect_stdout(io.StringIO()) as out:
                            result = alarm.main(
                                args, wall_clock=lambda: start + state["elapsed"],
                                monotonic_clock=lambda: 100 + state["elapsed"],
                                sleep=sleep, notify_fn=notify,
                            )
                        self.assertEqual(result, 0)
                        notify.assert_called_once_with()
                        self.assertEqual(state["elapsed"], wake_offsets[-1])
                        self.assertIn("2026-01-01 09:30:00 UTC UTC+00:00", out.getvalue())

    def test_exact_overshot_and_already_due(self):
        for ticks, expected_sleeps in (([9, 10], [1]), ([9.75, 12], [0.25]), ([10], []), ([11], [])):
            sleep = Mock()
            alarm.wait_until(10, Mock(side_effect=ticks), sleep)
            self.assertEqual([call.args[0] for call in sleep.call_args_list], expected_sleeps)

    def test_wall_clock_changes_and_linux_suspend(self):
        for mode in ("--at", "--in"):
            for change in ("forward", "backward", "suspend", "descheduled"):
                with self.subTest(mode=mode, change=change):
                    state = {"wall": 100.0, "mono": 20.0}
                    sleeps = []

                    def sleep(seconds):
                        sleeps.append(seconds)
                        self.assertTrue(0 < seconds <= 1)
                        self.assertLess(len(sleeps), 20, "loop failed to complete")
                        if len(sleeps) == 1:
                            state["wall"] += {"forward": 100, "backward": -5,
                                              "suspend": 100, "descheduled": 100}[change]
                            if change == "suspend":
                                return
                            if change == "descheduled":
                                state["mono"] += 100
                                return
                        state["wall"] += seconds
                        state["mono"] += seconds

                    notify = Mock()
                    with patch.object(alarm, "resolve_at", return_value=103), \
                            redirect_stdout(io.StringIO()):
                        result = alarm.main(
                            [mode, "00:01" if mode == "--at" else "3"],
                            wall_clock=lambda: state["wall"], monotonic_clock=lambda: state["mono"],
                            sleep=sleep, notify_fn=notify,
                        )
                    self.assertEqual(result, 0)
                    notify.assert_called_once_with()
                    if mode == "--in":
                        self.assertEqual(len(sleeps), {"forward": 3, "backward": 3,
                                                      "suspend": 4, "descheduled": 1}[change])
                    else:
                        self.assertEqual(len(sleeps), 8 if change == "backward" else 1)

    @unittest.skipUnless(hasattr(time, "tzset"), "requires process-local Unix timezone support")
    def test_cancellation_does_not_notify(self):
        with local_zone("UTC0"):
            for args in (["--in", "3"], ["--at", "00:02"]):
                with self.subTest(args=args):
                    notify = Mock()
                    sleep = Mock(side_effect=KeyboardInterrupt)
                    with redirect_stdout(io.StringIO()) as output, \
                            redirect_stderr(io.StringIO()) as error:
                        result = alarm.main(args, wall_clock=lambda: 100,
                                            monotonic_clock=lambda: 20,
                                            sleep=sleep, notify_fn=notify)
                    self.assertEqual(result, 130)
                    self.assertIn("Alarm cancelled.", output.getvalue())
                    self.assertNotIn("*** ALARM", output.getvalue())
                    self.assertEqual(error.getvalue(), "")
                    sleep.assert_called_once_with(1.0)
                    notify.assert_not_called()


class NotificationTests(unittest.TestCase):
    @patch.object(alarm, "play_sound", return_value="pw-play is unavailable")
    def test_visible_alert_and_one_bell_without_claiming_audibility(self, play):
        with redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()) as err:
            alarm.notify()
        self.assertEqual(out.getvalue().count("*** ALARM"), 1)
        self.assertEqual(out.getvalue().count("\a"), 1)
        self.assertLess(out.getvalue().index("*** ALARM"), out.getvalue().index("\a"))
        self.assertIn("not a terminal", err.getvalue())
        self.assertIn("Audibility is unverified", err.getvalue())
        self.assertIn("Audio playback unavailable", err.getvalue())

    @patch.object(alarm, "play_sound", return_value="pw-play is unavailable")
    def test_bell_failure_preserves_alert(self, play):
        class BrokenBell(io.StringIO):
            def write(self, text):
                if text == "\a":
                    raise OSError("bell output unavailable")
                return super().write(text)

        with redirect_stdout(BrokenBell()) as out, redirect_stderr(io.StringIO()) as err:
            alarm.notify()
        self.assertIn("*** ALARM", out.getvalue())
        self.assertIn("Sound attempt failed", err.getvalue())

    def test_successful_playback_follows_alert_without_extra_bell(self):
        with redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()) as err:
            def play():
                self.assertIn("*** ALARM", out.getvalue())
                return None

            with patch.object(alarm, "play_sound", side_effect=play) as playback:
                alarm.notify()
        playback.assert_called_once_with()
        self.assertEqual(out.getvalue().count("*** ALARM"), 1)
        self.assertNotIn("\a", out.getvalue())
        self.assertIn("pw-play completed", err.getvalue())
        self.assertIn("Audibility is unverified", err.getvalue())

    def test_missing_player_or_sound_preserves_alert_without_launching_process(self):
        for player, exists, reason in ((None, True, "not installed"),
                                       ("/usr/bin/pw-play", False, "sound file is unavailable")):
            with self.subTest(reason=reason), \
                    patch.object(alarm.shutil, "which", return_value=player), \
                    patch.object(alarm.Path, "is_file", return_value=exists), \
                    patch.object(alarm.subprocess, "run") as run, \
                    redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()) as err:
                alarm.notify()
                self.assertIn(reason, err.getvalue())
                self.assertEqual(out.getvalue().count("*** ALARM"), 1)
                self.assertEqual(out.getvalue().count("\a"), 1)
                run.assert_not_called()

    def test_player_uses_argument_list_and_timeout(self):
        with patch.object(alarm.shutil, "which", return_value="/usr/bin/pw-play"), \
                patch.object(alarm.Path, "is_file", return_value=True), \
                patch.object(alarm.subprocess, "run") as run:
            self.assertIsNone(alarm.play_sound())
        run.assert_called_once_with(
            ["/usr/bin/pw-play", alarm.ALARM_SOUND], check=True, timeout=10,
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
        )

    def test_player_failures_preserve_alert_and_fall_back(self):
        errors = [
            (subprocess.CalledProcessError(1, "pw-play", stderr="Operation not permitted"),
             "Operation not permitted"),
            (subprocess.TimeoutExpired("pw-play", 10), "timed out"),
            (PermissionError("execution denied"), "execution denied"),
        ]
        for error, expected in errors:
            with self.subTest(error=expected), \
                    patch.object(alarm.shutil, "which", return_value="/usr/bin/pw-play"), \
                    patch.object(alarm.Path, "is_file", return_value=True), \
                    patch.object(alarm.subprocess, "run", side_effect=error), \
                    redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()) as err:
                alarm.notify()
            self.assertEqual(out.getvalue().count("*** ALARM"), 1)
            self.assertEqual(out.getvalue().count("\a"), 1)
            self.assertIn(expected, err.getvalue())


if __name__ == "__main__":
    unittest.main()
