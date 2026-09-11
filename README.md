# Python CLI alarm clock

A small foreground CLI that schedules one alarm, prints its resolved local target, waits without busy-waiting, and displays an unmistakable terminal alert with best-effort sound. Each invocation fires once and exits. There is no saved schedule or background service.

## Prerequisites and usage

Verified on **Ubuntu 24.04.3 LTS (x86_64), Python 3.12.3**. Use Python 3.12 for the verified setup; other versions and operating systems have not been validated. Python dependencies are standard-library only: no pip install, virtual environment, or database is needed.

For audible playback, the Ubuntu desktop session needs `pw-play` (verified version 1.0.5), access to its user PipeWire service, an unmuted output, and `/usr/share/sounds/freedesktop/stereo/alarm-clock-elapsed.oga`. These were already installed on the tested machine. Missing audio prerequisites preserve the visible alert and produce a terminal-bell fallback. Run as your normal desktop user; root is not required.

From the project directory:

```bash
python3 --version
python3 alarm.py --help
python3 alarm.py --at 09:30
python3 alarm.py --in 5
```

The last two commands are alternatives; each runs in the foreground until completion. Supply exactly one scheduling option, once:

- `--at HH:MM`: exactly five ASCII characters, 24-hour time from `00:00` through `23:59`.
- `--in SECONDS`: ASCII whole seconds from 1 through 86400 inclusive; leading zeros are allowed. Zero, negatives, fractions, and nonnumeric values are rejected.

Missing, repeated, conflicting, unknown, or invalid arguments exit **2**. **Ctrl+C** while waiting prints `Alarm cancelled.` and exits **130** without a traceback. Completed alarms exit **0**, including when audio is unavailable.

## Local time and timing policy

The startup message includes the resolved date, time, timezone name, and UTC offset. `--at` selects second zero of the requested local minute only if it is strictly in the future today; otherwise it selects tomorrow. At 09:29:59, `--at 09:30` selects today. At 09:30:00 or 09:30:20, it selects tomorrow. Calendar arithmetic handles month, year, and leap-day rollover. A selected local minute that is ambiguous or nonexistent during a daylight-saving transition is rejected.

**Keep the process running and the computer awake.** Closing the terminal, logging out, stopping the process, shutdown, or power loss can discard the alarm. It cannot wake the computer or recover a lost schedule.

| Mode | Clock changes | System suspend on the verified Linux environment |
| --- | --- | --- |
| `--at` | A fixed epoch target is compared with wall-clock time. A forward jump past it fires on the next check; a backward jump delays it. Later timezone changes do not move it. | An overdue target fires on the first check after resume, if the process survived. |
| `--in` | A monotonic deadline ignores wall-clock jumps. The printed local target is only a startup estimate and can become stale. | Linux monotonic time excludes suspend, so the remaining countdown continues after resume. Ordinary process descheduling while the OS is awake still counts. |

The waiting loop sleeps for up to one second and fires when the deadline is reached **or passed**. Timing is not a real-time guarantee. Other platforms, leap-second precision, and physical suspend/resume have not been verified.

## Notification and engineering note

The original terminal alert worked, but the user did not hear its BEL character. The investigation did **not** establish which terminal setting or component suppressed that bell. BEL emission alone does not establish audible playback.

The machine already had a usable PipeWire player and alarm sound. A separate limitation was demonstrated: sandboxed `pw-play` failed with `Operation not permitted`, while approved execution outside the sandbox succeeded. This establishes an audio-access restriction in the test sandbox; it does not prove that the sandbox caused the original terminal-bell silence. The default Speaker + Headphones output was unmuted at 24% when inspected. No audio settings or packages were changed.

The fix prints and flushes `*** ALARM: target time reached ***` first, then invokes:

```bash
pw-play /usr/share/sounds/freedesktop/stereo/alarm-clock-elapsed.oga
```

The application uses a subprocess argument list without a shell and a 10-second playback timeout. It exits after the sound finishes, so a five-second countdown can take longer than five seconds to return to the prompt. Missing player/file, execution errors, permission denial, and timeout are reported; one terminal bell is then attempted. The visible alert is preserved even if both sound approaches fail. No desktop popup is used.

The user confirmed hearing direct playback of this same sound through `pw-play`. The integrated CLI subsequently completed playback and exited 0, but that run did not receive a separate listening confirmation. This evidence is retained because the notification code has not changed. The application still reports `Audibility is unverified`: it cannot detect what a listener hears.

## Tests and actual verification

```bash
# Run the complete test suite
python3 -B -m unittest -v

# Example: run one focused test case
python3 -B -m unittest -v test_alarm.WaitingTests.test_cancellation_does_not_notify
```

Latest run: **17 tests passed in 0.655 seconds**, with no failures or skips. Fake clocks and sleep keep tests fast; OS playback is mocked. Coverage includes strict parsing, positive countdowns, today/tomorrow and calendar boundaries, already-started minutes, exact/late deadlines, once-only notification, cancellation in both modes, audio failures, import safety, and a small subprocess check of actual CLI help/error exits. Expected dates and times are explicit, rather than recalculated with the application's algorithm.

| Evidence | Actual result |
| --- | --- |
| Automated regression suite | 17 passing tests; proves checked behavior, not audible sound. |
| Live CLI checks | Help and invalid-input exits passed. `--in 5` showed one alarm and exited 0; an upcoming `--at 06:21` fired once at 06:21 local time. These sandbox runs exercised audio-denial fallback. |
| Tomorrow target and cancellation | Printed tomorrow's date, then cancelled by direct SIGINT with exit 130; no overnight wait. |
| Audio-player execution | Integrated `--in 3` outside the sandbox completed playback and exited 0 in about nine seconds including sound duration. |
| Human audio confirmation | User confirmed hearing the direct local `pw-play` diagnostic. Retained for the unchanged playback path; no repeat requested. |
| Remaining limits | Physical keyboard Ctrl+C was not conclusively verified; direct SIGINT and fake interruption were. No overnight or physical suspend/resume check, remote-session audio guarantee, or broader platform coverage. |

See [MANUAL_TESTS.md](MANUAL_TESTS.md) for commands, expected/actual outcomes, and exact remaining local checks. [PLAN.md](PLAN.md) records design decisions and verification history.

## Why a local CLI, without Docker

A foreground alarm needs a clock, a sleeping loop, and access to the user's terminal/audio session. Small functions with injectable clocks, sleep, and notification keep the implementation easy to review and test. Docker would add setup and audio/session access configuration without solving a requirement. No web UI, database, daemon, or background scheduler is needed for one foreground alarm.

## 60-second interview demo

Run from this directory in the normal Ubuntu terminal. Times are approximate; allow the alarm sound to finish.

| Time | Action and explanation |
| --- | --- |
| 0–10 s | `python3 alarm.py --help` — explain the two exclusive modes and foreground lifetime. |
| 10–25 s | `python3 alarm.py --in 5` — show the target, one alert, sound attempt, and return to the prompt. |
| 25–35 s | `python3 alarm.py --at 25:00` — show validation and exit 2 (`echo $?`). |
| 35–45 s | `python3 alarm.py --at "$(date +%H:%M)"` — the current minute has begun, so inspect tomorrow's printed target; press Ctrl+C, then `echo $?` (expect 130). |
| 45–60 s | `python3 -B -m unittest -v` — show 17 passing tests and summarize monotonic countdown versus wall-clock scheduling. |

This is a proposed live presentation sequence, not a claim that physical keyboard interaction was already verified.

## Submission contents

Submit only `alarm.py`, `test_alarm.py`, `README.md`, `PLAN.md`, `MANUAL_TESTS.md`, and `.gitignore`. The prepared ZIP uses this explicit file list. `.gitignore` excludes credential/config files, virtual environments, bytecode, caches, and build artifacts from future Git additions; ignore rules alone do not remove already tracked files or filter arbitrary ZIP commands. No credentials or runtime environments are required.
