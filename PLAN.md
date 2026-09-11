# Python CLI alarm clock plan

Implemented in `alarm.py`, with deterministic tests in `test_alarm.py` and usage in `README.md`. Countdown mode uses a monotonic deadline; scheduled-time mode uses a local wall-clock target. This supersedes the earlier proposal to use wall-clock deadlines for both modes. Checked items are implemented and supported by the recorded verification; physical keyboard cancellation remains explicitly pending. Historical runs are retained below.

## Inspected environment

- OS: Ubuntu 24.04.3 LTS, Linux 7.0.0-31-generic, x86_64.
- Python: `python3 --version` reports Python 3.12.3.
- Local timezone at inspection: IST, UTC+05:30. Use the host's local timezone, not a hard-coded zone.
- At initial inspection the project folder was empty and audio was unverified. Later local playback was confirmed by the user; see the notification acceptance review below.

## Requirements and observable acceptance checklist

- [x] **Small foreground CLI:** implement one `alarm.py` using the Python standard library. No GUI, database, daemon, persistence, or third-party Python packages; audio uses the existing optional system player. Each invocation schedules one alarm and exits after it fires or is cancelled. Separate invocations are independent; no global singleton lock.
- [x] **Arguments:** require exactly one of `--at HH:MM` and `--in SECONDS`. `--help` explains formats, time policies, audio limitations, and the need to keep the process running; it exits 0 without scheduling.
- [x] **Invalid input:** `--at` accepts exactly five ASCII characters in 24-hour form, `00:00` through `23:59`. Reject `9:05`, `24:00`, `12:60`, seconds, and whitespace. For a bounded demonstration countdown, accept ASCII decimal integers from 1 through 86400 seconds inclusive (leading zeros allowed). Reject zero, negatives, fractions, nonnumeric values, and larger values. Missing values, neither/both options, repeated scheduling options, and unknown arguments produce a useful error on stderr and exit 2 without waiting or alerting.
- [x] **Requested minute:** resolve `--at` to second zero of that local minute. Today's candidate must be strictly later than the scheduling instant; otherwise use tomorrow. At 09:29:59, `--at 09:30` selects today; at 09:30:00 or 09:30:20 it selects tomorrow. No immediate alert or grace period for an already-started minute.
- [x] **Midnight rollover:** advance the calendar date correctly across month, year, and leap-day boundaries. At December 31, 23:59:30, `--at 00:00` selects January 1, 00:00:00. At 00:00:01, `--at 00:00` selects the following day.
- [x] **Countdown:** `--in 3` sets a monotonic deadline three seconds after scheduling. With an awake, normally scheduled process, it alerts once at or shortly after that deadline, even if the wall clock jumps. Verify that a countdown crossing midnight shows the next date in its estimated local target.
- [x] **Visible target:** before waiting, flush a scheduling message containing the mode, resolved local date, time including seconds, timezone abbreviation when available, and numeric UTC offset (for example, `2026-09-12 09:30:00 IST UTC+05:30`). Label the countdown's date/time as an estimate calculated at startup, not its controlling deadline. Include “Keep this process running; Ctrl+C cancels.” Preserve this message in redirected output too.
- [x] **Notification:** at the deadline, flush `*** ALARM: target time reached ***`, play the installed alarm sound through `pw-play`, then exit 0. Bound playback to 10 seconds; on missing player/file, timeout, or playback failure, report the reason and attempt one terminal bell (`\a`). Verify the visible alert survives failure. Human confirmation of audibility is separate from player completion; silence does not fail the alarm or trigger an installation prompt.
- [ ] **Cancellation (physical keyboard check pending):** Ctrl+C while waiting prints a short cancellation message, exits 130, and produces no traceback or alarm. Once notification has begun, cancellation cannot retract it. Fake interruption in both modes and direct SIGINT passed; the physical keyboard check is not yet verified.

## Clock, sleep, and timezone policy

- [x] **Two clocks, one waiting loop:** `--in` uses `time.monotonic() + seconds`; `--at` resolves the local target once to an epoch timestamp and compares it with `time.time()`. The loop checks the selected clock, returns when `now >= deadline`, and otherwise sleeps for `min(1.0, deadline - now)` seconds before checking again. Never require exact equality. Under ordinary awake, unloaded conditions, accept no early alert and delivery within roughly two seconds; this is not a real-time guarantee.
- [x] **Clock changes:** wall-clock jumps do not change the countdown's monotonic deadline, though its printed local estimate can become stale. For `--at`, a forward jump past the target fires on the next check; a backward jump delays firing until the fixed target is reached again. Verify both directions with independently controlled clocks. Python documents the clock distinction in its [time reference](https://docs.python.org/3.12/library/time.html#time.monotonic).
- [x] **System sleep:** neither mode wakes the computer or alerts while suspended. An overdue `--at` fires on the first check after resume if the process survives. Here, `time.get_clock_info('monotonic')` reports `clock_gettime(CLOCK_MONOTONIC)`, which excludes system suspend time on Linux: `--in` resumes with its remaining countdown, rather than counting the suspended interval. Ordinary process descheduling while the OS remains awake still counts. Simulate both kinds of gap; optionally check actual suspend/resume manually. This is a documented platform limit, not a reason to add suspend detection or another clock backend. See the [Linux clock documentation](https://www.man7.org/linux/man-pages/man2/clock_gettime.2.html).
- [x] **Timezone/DST limits:** select today's or tomorrow's local calendar date before converting the target. Reject a selected nonexistent or ambiguous minute with a clear error and exit 2; do not silently normalize it or select a repeated occurrence. Use the host's timezone rules at startup, including the offset applicable on the target date. Later timezone/rule changes do not move either deadline or rewrite the printed target. Countdown display is an estimate converted from a unique epoch timestamp, so it can show a repeated local minute with its offset. Verify transition cases on Ubuntu; other platforms and leap-second accuracy are not guaranteed.

## Agreed design

One application file, `alarm.py`, using standard-library Python modules only. The audio fix adds `pathlib`, `shutil`, and `subprocess` to locate an existing sound/player and invoke playback safely. Use ordinary values and functions; no scheduler objects, threads, plugins, Docker, GUI, database, daemon, or background scheduling. Tests live in `test_alarm.py` using `unittest` and `unittest.mock`.

| Function | Responsibility |
| --- | --- |
| `parse_at(text)` / `parse_seconds(text)` | Validate the exact formats and bounds above; return an hour/minute pair or integer. Raise `argparse.ArgumentTypeError` for invalid values, including numeric conversion failures. |
| `parse_args(argv)` | Use `ArgumentParser(allow_abbrev=False)` and a required mutually exclusive group. Use `action='append'` for each scheduling option, then require exactly one supplied value so repeated options also fail. Preserve normal argparse help/errors and exit codes. |
| `resolve_at(hour, minute, now_epoch)` | Convert the supplied instant to host-local calendar fields. Choose today only if the requested minute's start is strictly later in those fields; otherwise advance the calendar date by one day. Validate the selected local minute and return its unique epoch timestamp. |
| `resolve_countdown(seconds, wall_now, monotonic_now)` | Return a monotonic deadline and a separate estimated epoch target for display. Take the two startup clock readings close together; never compare values from different clock domains. |
| `format_target(target_epoch)` | Convert the target instant to local time and format its date, seconds, timezone name, and numeric offset. Use the target date's offset rather than copying today's offset. |
| `wait_until(deadline, clock, sleep)` | Run the sleeping/checking loop above using injected callables. Return when due; let `KeyboardInterrupt` propagate to the entry point. |
| `play_sound()` | Locate `pw-play`, check the installed alarm file, and run playback with an argument list and 10-second timeout. Return a failure explanation or `None` on successful completion. |
| `notify()` | Flush the visible alert first, then attempt playback. On failure, explain the reason and attempt one BEL character. Player completion is not a claim of audibility. |
| `main(argv, *, wall_clock, monotonic_clock, sleep, notify_fn)` | Supply production defaults (`time.time`, `time.monotonic`, `time.sleep`, `notify`); parse, resolve, print, wait, notify exactly once, and return 0. Convert target-resolution errors to parser errors (2). Catch Ctrl+C around the foreground flow, print cancellation, and return 130. |

For local-time validation, keep one small helper within target resolution: try the selected naive local datetime with `fold=0` and `fold=1`, convert each to a timestamp, and round-trip through local `datetime.fromtimestamp`. Retain only timestamps whose calendar fields exactly match the requested minute, then deduplicate. Zero matches means nonexistent; two means ambiguous; one is valid. Conversion failures become clear CLI errors. This uses the standard library's [local timestamp and fold support](https://docs.python.org/3.12/library/datetime.html#datetime.datetime.timestamp), without discovering an IANA zone name or adding timezone packages. Test this behavior on the detected platform before relying on it.

## Ubuntu notification and verification

Following the user's report of a silent terminal bell, use the existing `pw-play` and `/usr/share/sounds/freedesktop/stereo/alarm-clock-elapsed.oga` for playback. No installation or volume changes are needed. Keep the unconditional flushed text alert and use BEL only as a fallback. A terminal can translate BEL into sound, a visual bell, or nothing according to its settings; redirected output merely captures the character. The [xterm control-sequence reference](https://invisible-island.net/xterm/ctlseqs/ctlseqs.html) documents BEL as the bell control character.

- [x] Capture output and verify that the readable alert precedes playback, and that failure preserves the alert and emits one BEL byte. This verifies attempted notification only, not speaker output.
- [x] Run a real `--in 3` and record playback completion separately from audibility. The user confirmed hearing the direct `pw-play` diagnostic; the integrated countdown also completed playback outside the sandbox. The application itself must not claim that audio was verified.
- [x] With injected clocks/sleep, cover exact deadline, overshoot, positive bounded sleeps, immediate return when overdue, wall-clock jumps in each mode, and different suspend behavior. Verify one notification on completion and none when waiting is interrupted. No real delays are needed.
- [x] Cover date rollover and DST gaps/folds using fixed instants and process-local test timezone settings, restoring them afterward; do not change the host timezone. Also verify a valid target across a DST transition prints the target's correct offset.

## Risks and implementation sequence

- Terminal bells may be muted, disabled, visual-only, or inaudible in IDE terminals, SSH sessions, containers, and redirected output. PipeWire playback also requires access to the user's audio service and an audible output. Neither emitting a bell nor a successful player exit proves sound was heard.
- Closing the terminal, stopping the process, logging out, shutting down, or losing power may discard the alarm. There is no recovery or background service; users must leave the process running and the computer awake for an on-time alert.
- Clock corrections, CPU scheduling, and sleep can change delivery timing. DST validation and local timezone conversion need explicit verification on the supported Ubuntu/Python environment before claiming portability elsewhere.
- [x] Build argument validation, target resolution, waiting, and notification as a few small functions in `alarm.py`.
- [x] Verify parsing and date/clock edge cases with controlled clocks using standard-library tests; avoid overnight waits and changes to the host clock.
- [x] Run real `--in 3`, invalid-input, and Ctrl+C smoke checks. Record audio separately and write concise usage documentation covering the policies above.

## Initial implementation verification (before the audio fix)

Commands run from `python-cli-alarm-clock/` on the inspected Ubuntu/Python environment:

| Command | Observed outcome |
| --- | --- |
| `python3 -B -m unittest -v` | All 11 tests passed, including parameterized input/date/clock cases and simulated bell failure. |
| `python3 alarm.py --help` | Exit 0; displayed options and operational limitations without scheduling. |
| `python3 alarm.py --in 3` | Exit 0 after approximately three seconds; printed estimated local target `2026-09-11 06:08:41 IST UTC+05:30`, one alarm message, and one bell character. Explained that output was not a terminal and audibility was unverified. |
| `python3 alarm.py --at 24:00` | Exit 2 with a useful range error; no alarm. |
| `python3 alarm.py --in 60`, then SIGINT from a Python subprocess harness after reading the startup output | Child exited 130 with `Alarm cancelled.`; stderr was empty and no alarm fired. The harness exited 0. SIGINT is the signal normally sent by Ctrl+C. |

The initial PTY Ctrl+C attempt returned only `^C` and tool exit 1, so it did not establish clean application cancellation; the direct SIGINT check above did. At this initial stage no speaker playback was verified and the application did not launch subprocesses. The import smoke test and SIGINT harness used subprocess argument lists without a shell.

## Audio investigation and fix verification

- Before editing, confirmed `pw-play` 1.0.5, `aplay`, `wpctl`, and the freedesktop alarm sound were present. `paplay` and `pactl` were absent. `/dev/snd` was not exposed in the sandbox, but user audio-service sockets were visible; visibility alone did not grant connection access.
- `timeout 10s pw-play /usr/share/sounds/freedesktop/stereo/alarm-clock-elapsed.oga`: sandbox exit 1, `pw_context_connect() failed: Operation not permitted`. The same command with approved access outside the sandbox exited 0. The user explicitly confirmed hearing this diagnostic sound.
- `wpctl status` and `wpctl get-volume @DEFAULT_AUDIO_SINK@` could not connect inside the sandbox. Approved inspection outside it showed Speaker + Headphones as default, volume 0.24, not muted. No device, permission, or volume settings were modified.
- Implemented the existing PipeWire player as the primary audio path; retained a visible alert and diagnostic bell fallback. No shell, package installation, or automatic privilege escalation is used by the application.
- `python3 -B -m unittest -v`: all 15 tests passed, including missing player/file, successful playback, timeout, denied access, and bell failure. Unit tests do not play real audio.
- `python3 alarm.py --in 1` inside the sandbox: exit 0; one visible alarm, playback permission error, and terminal-bell fallback.
- `python3 alarm.py --in 3` with approved access outside the sandbox: exit 0; one visible alarm and `pw-play completed`. The process took approximately nine seconds including the three-second countdown and sound playback. Actual audibility of this integrated run was not separately confirmed; direct diagnostic playback was confirmed by the user.

## Focused test review and live checklist

- Follow-up review extended existing tests rather than duplicating them: cancellation now covers both scheduling modes with empty stderr and no notification; missing-player/file cases now exercise `notify()` and verify the visible alert and bell fallback without launching a process. Latest requested run: `python3 -B -m unittest -v` — **17 tests passed in 0.655 seconds**, no failures or skips. No application defects were discovered; `alarm.py` and the retained audible-playback evidence remain unchanged.
- Reviewed existing parsing, positive-countdown, calendar rollover, already-started-minute, cancellation, and audio-failure coverage; retained it without duplicating the cases.
- Added an entry-point subprocess check for `--help`, missing scheduling arguments, and conflicting options, verifying real exit codes, output streams, and absence of tracebacks/alarms.
- Added a full `main` path check for both scheduling modes using actual target resolution, explicit expected timestamps, fake clocks/sleep, and a mocked notifier. It asserts no notification before the deadline and exactly one notification at the deadline or after a late wake-up. Existing audio tests mock OS playback calls.
- `python3 -B -m unittest -v`: **17 tests passed in 0.877 seconds**, with no skips or failures, on the inspected Ubuntu/Python environment. No concrete application defects were found; application code was unchanged during this test review.
- Live commands, expected/actual results, and remaining interactive checks are recorded in [MANUAL_TESTS.md](MANUAL_TESTS.md). The five-second countdown and upcoming-minute alarm both completed; tomorrow's target was inspected and cancelled by SIGINT without waiting overnight.

## Notification acceptance review

Reviewed on 2026-09-11 using the existing evidence. `play_sound()` and `notify()` are unchanged since the audio fix; subsequent work added tests and documentation only. No tests or sound playback were repeated for this review, and no desktop popup was added.

| Acceptance criterion | Evidence and scope | Status |
| --- | --- | --- |
| Terminal alert appears when due | Live `--in 5` printed one alert after five seconds; live `--at 06:21` printed it at `2026-09-11 06:21:00.000471 IST`. Fake-clock tests cover exact and late deadlines without early notification. | PASS |
| Sound is audible on the local machine | User answered **“Yes, I heard it”** for direct playback of the same installed alarm file through `pw-play` outside the sandbox. Retain this human confirmation for the unchanged playback path. It was not a separate listening confirmation for the integrated CLI run. | PASS — retained user confirmation of local playback |
| Alarm fires once | Both live checks displayed exactly one alarm; automated tests assert one notifier call for both modes at exact or exceeded deadlines and one player invocation on successful notification. | PASS |
| Process completes as designed | Integrated `--in 3` outside the sandbox printed the alert, completed `pw-play`, and exited 0 after about nine seconds including countdown and playback. Sandboxed countdown/scheduled runs also exited 0 after reporting fallback. Playback has a 10-second timeout covered by a mocked failure test. | PASS |
| Audio failures preserve visible notification | Real sandbox denial left the alert visible and reported the reason plus bell fallback. Automated tests cover failed execution, denied access, timeout, missing player/file, and bell failure. | PASS |

Evidence types remain distinct: the latest automated suite passed **17 tests** with fake clocks and mocked audio; successful player execution proves completion, not hearing; the user's confirmation establishes audible local playback. The application still correctly prints `Audibility is unverified` because it cannot detect what the user hears. No additional audible confirmation is required for this unchanged implementation.

Verified environment: **Ubuntu 24.04.3 LTS, Linux x86_64, Python 3.12.3**, local timezone IST (UTC+05:30). Playback dependencies are the installed **`pw-play` 1.0.5**, a reachable user **PipeWire** audio service, and **`/usr/share/sounds/freedesktop/stereo/alarm-clock-elapsed.oga`**. Speaker + Headphones was the default output, unmuted at 24% when inspected. `wpctl` was diagnostic only; `aplay`, `paplay`, and `pactl` are not runtime dependencies. No Python packages, root access, audio setting changes, or desktop notification service are required by the application.

The sandbox could see audio sockets but connections were denied with `Operation not permitted`; approved execution outside it succeeded. Sandboxed output therefore verifies fallback behavior, not audible sound. Remote sessions, other operating systems, physical suspend/resume, and overnight operation were not verified. These limits do not invalidate the recorded local audio confirmation.


## Interview submission preparation

- README now documents prerequisites, exact usage, time rules, cancellation, notification dependencies, clock/suspend limits, engineering rationale without Docker, verification distinctions, and a proposed 60-second demo.
- Clarified that the original silent terminal bell has no established specific root cause; the separately demonstrated sandbox denial affects PipeWire access. User-confirmed local playback remains valid; no audio retest was needed.
- Application and tests are unchanged in this documentation pass. Retained the latest 17-test result (0.655 seconds); no redundant suite run.
- Submission file list: `alarm.py`, `test_alarm.py`, `README.md`, `PLAN.md`, `MANUAL_TESTS.md`, `.gitignore`. Exclude sibling requirement drafts and environment metadata. No unrelated files were removed.
- This workspace is not a usable Git repository (`git status` reports “not a git repository”). Documentation changes were reviewed against pre-edit copies and `.gitignore` was inspected directly; no Git baseline diff is claimed.
- Submission inspection found exactly the six intended files, no symlinks, environments, or caches, and no matches for the checked common credential patterns. Local Markdown file links resolve. `.gitignore` adds exclusions for future local artifacts; the ZIP is built from the explicit file list, not from ignore rules.
