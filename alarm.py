"""One foreground alarm, using only the Python standard library."""

import argparse
from datetime import datetime, timedelta
from pathlib import Path
import shutil
import subprocess
import sys
import time


ALARM_SOUND = "/usr/share/sounds/freedesktop/stereo/alarm-clock-elapsed.oga"


def parse_at(text):
    """Accept only ASCII HH:MM in 24-hour notation."""
    if (
        len(text) != 5
        or text[2] != ":"
        or any(char not in "0123456789" for char in text[:2] + text[3:])
    ):
        raise argparse.ArgumentTypeError("use HH:MM in 24-hour time (00:00–23:59)")
    hour, minute = int(text[:2]), int(text[3:])
    if hour > 23 or minute > 59:
        raise argparse.ArgumentTypeError("time must be between 00:00 and 23:59")
    return hour, minute


def parse_seconds(text):
    """Accept a positive ASCII whole-second countdown of at most one day."""
    message = "seconds must be a whole number from 1 through 86400"
    if not text or any(char not in "0123456789" for char in text):
        raise argparse.ArgumentTypeError(message)
    # Strip leading zeros before conversion, avoiding Python's integer digit limit.
    digits = text.lstrip("0")
    if not digits or len(digits) > 5 or int(digits) > 86400:
        raise argparse.ArgumentTypeError(message)
    return int(digits)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Run one foreground alarm and exit after it fires.",
        allow_abbrev=False,
        epilog=(
            "Keep this process running and the computer awake; Ctrl+C cancels. "
            "An already-started requested minute selects tomorrow. Ambiguous or "
            "nonexistent DST targets are rejected. --at follows wall-clock jumps; "
            "--in uses monotonic time, ignores wall-clock jumps, and pauses during "
            "Linux system suspend. Overdue --at alarms fire after resume. "
            "Timezone changes after scheduling do not move the deadline. "
            "Sound uses pw-play and the installed freedesktop alarm sound, with a "
            "terminal-bell fallback. Audio-service access and an unmuted output "
            "are needed; the visible alert is always printed."
        ),
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--at", type=parse_at, action="append", metavar="HH:MM",
        help="next strictly future local minute, in 24-hour HH:MM format",
    )
    group.add_argument(
        "--in", dest="seconds", type=parse_seconds, action="append", metavar="SECONDS",
        help="count down 1–86400 whole seconds (local target shown as an estimate)",
    )
    args = parser.parse_args(argv)
    if len(args.at or args.seconds) != 1:
        parser.error("supply exactly one scheduling option, without repeats")
    return parser, args


def resolve_at(hour, minute, now_epoch):
    """Resolve a future local minute, rejecting DST gaps and repeated minutes."""
    now = datetime.fromtimestamp(now_epoch)
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)

    timestamps = set()
    for fold in (0, 1):
        timestamp = candidate.replace(fold=fold).timestamp()
        if datetime.fromtimestamp(timestamp) == candidate:
            timestamps.add(timestamp)
    if not timestamps:
        raise ValueError("requested local minute does not exist due to a timezone transition")
    if len(timestamps) != 1:
        raise ValueError("requested local minute is ambiguous due to a timezone transition")
    return timestamps.pop()


def resolve_countdown(seconds, wall_now, monotonic_now):
    """Return the controlling deadline and a separate local-display estimate."""
    return monotonic_now + seconds, wall_now + seconds


def format_target(target_epoch):
    target = datetime.fromtimestamp(target_epoch).astimezone()
    offset = target.strftime("%z")
    offset = offset[:3] + ":" + offset[3:]
    return f"{target:%Y-%m-%d %H:%M:%S} {target.tzname() or 'local'} UTC{offset}"


def wait_until(deadline, clock, sleep):
    """Return as soon as the selected clock reaches or passes the deadline."""
    while True:
        remaining = deadline - clock()
        if remaining <= 0:
            return
        sleep(min(1.0, remaining))


def play_sound():
    """Play the installed Ubuntu alarm; return a failure reason or None."""
    player = shutil.which("pw-play")
    if player is None:
        return "pw-play is not installed or is not on PATH"
    if not Path(ALARM_SOUND).is_file():
        return f"alarm sound file is unavailable: {ALARM_SOUND}"
    try:
        subprocess.run(
            [player, ALARM_SOUND], check=True, timeout=10,
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
        )
    except subprocess.TimeoutExpired:
        return "pw-play timed out after 10 seconds"
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or "").strip()
        return f"pw-play exited {error.returncode}: {detail or 'no diagnostic output'}"
    except OSError as error:
        return f"could not run pw-play: {error}"
    return None


def notify():
    """Print the alert first; try PipeWire playback, then a bell on failure."""
    print("\n*** ALARM: target time reached ***", flush=True)
    failure = play_sound()
    if failure is None:
        print("Sound: pw-play completed. Audibility is unverified.",
              file=sys.stderr, flush=True)
        return
    print(f"Audio playback unavailable: {failure}. Falling back to a terminal bell. "
          "Check audio-service access (including sandbox permissions), output device, "
          "and mute/volume settings.", file=sys.stderr, flush=True)
    try:
        sys.stdout.write("\a")
        sys.stdout.flush()
    except OSError as error:
        print(f"Sound attempt failed: {error}. The terminal alert remains above.",
              file=sys.stderr, flush=True)
    else:
        if sys.stdout.isatty():
            detail = "your terminal may mute it or use a visual bell"
        else:
            detail = "output is not a terminal; a captured bell byte may produce no sound"
        print(f"Sound: terminal bell attempted; {detail}. Audibility is unverified.",
              file=sys.stderr, flush=True)


def main(argv=None, *, wall_clock=time.time, monotonic_clock=time.monotonic,
         sleep=time.sleep, notify_fn=notify):
    try:
        parser, args = parse_args(argv)
        try:
            if args.at:
                deadline = resolve_at(*args.at[0], wall_clock())
                target = deadline
                clock = wall_clock
                label = "Scheduled local target (--at)"
            else:
                deadline, target = resolve_countdown(
                    args.seconds[0], wall_clock(), monotonic_clock()
                )
                clock = monotonic_clock
                label = "Estimated local target (--in, monotonic countdown)"
            target_text = format_target(target)
        except (ValueError, OverflowError, OSError) as error:
            parser.error(f"cannot resolve target: {error}")

        print(f"{label}: {target_text}", flush=True)
        print("Keep this process running; Ctrl+C cancels. Keep the computer awake.",
              flush=True)
        wait_until(deadline, clock, sleep)
        notify_fn()
        return 0
    except KeyboardInterrupt:
        print("\nAlarm cancelled.", flush=True)
        return 130


if __name__ == "__main__":
    sys.exit(main())
