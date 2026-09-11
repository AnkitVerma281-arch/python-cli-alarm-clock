# Compact manual test checklist

Observed on **2026-09-11**, Ubuntu 24.04.3 LTS, Python 3.12.3, IST (UTC+05:30). Commands below were run from `python-cli-alarm-clock/` through subprocesses with captured output in the sandbox, except explicitly reused evidence. PASS covers the stated check, not physical audibility or other platforms.

| Check / command | Expected result | Actual result | Status |
| --- | --- | --- | --- |
| 1. `python3 alarm.py --help` | Help with both options and limitations; exit 0; no alarm. | Help displayed; exit 0; no alarm. | PASS |
| 2. `python3 alarm.py --in 5` | Target printed first; one alarm after five seconds; exit 0. | Target `2026-09-11 06:20:20 IST UTC+05:30`; one alarm observed at `06:20:20.068`; process finished in 5.243 s, exit 0. Audio access denied; bell fallback reported. | PASS |
| 3. `python3 alarm.py --at 06:21` | Upcoming local minute resolves today; one alarm when due; exit 0. | Target `2026-09-11 06:21:00 IST UTC+05:30`; one alarm observed at `06:21:00.000471`; exit 0. Audio access denied; bell fallback reported. | PASS |
| 4a. `python3 alarm.py --at 25:00` | Range error; exit 2; no waiting or alarm. | Range error; exit 2; stdout empty. | PASS |
| 4b. `python3 alarm.py --at 12:60` | Range error; exit 2; no waiting or alarm. | Range error; exit 2; stdout empty. | PASS |
| 4c. `python3 alarm.py --at abc` | HH:MM format error; exit 2; no alarm. | Format error; exit 2; stdout empty. | PASS |
| 5a. `python3 alarm.py --in 0` | Positive whole-second validation error; exit 2. | Error specifying 1–86400; exit 2; stdout empty. | PASS |
| 5b. `python3 alarm.py --in -1` | Positive whole-second validation error; exit 2. | Error specifying 1–86400; exit 2; stdout empty. | PASS |
| 5c. `python3 alarm.py --in abc` | Numeric validation error; exit 2. | Error specifying 1–86400; exit 2; stdout empty. | PASS |
| 6. `python3 alarm.py --at 12:00 --in 5` | Conflicting options rejected; exit 2; no alarm. | `--in: not allowed with argument --at`; exit 2; stdout empty. | PASS |
| 7. `python3 alarm.py` | Required scheduling option error; exit 2; no alarm. | `one of the arguments --at --in is required`; exit 2; stdout empty. | PASS |
| 8. `python3 alarm.py --in 60`, then keyboard Ctrl+C while waiting | Cancellation message; exit 130; no traceback or alarm. | Physical keyboard Ctrl+C not verified. Prior PTY attempt was inconclusive (`^C`, tool exit 1). See separate SIGINT evidence below. | NOT RUN (keyboard check) |
| 9. `python3 alarm.py --at 06:19`, started at `2026-09-11 06:20:14`, then direct SIGINT after reading startup output | Print tomorrow's target; cancel promptly; exit 130; no alarm. | Printed `2026-09-12 06:19:00 IST UTC+05:30`; `Alarm cancelled.`; exit 130; stderr empty; no alarm. No overnight wait. | PASS (target and signal cancellation) |

## Reused evidence and limits

- Earlier `python3 alarm.py --in 60` with direct SIGINT after startup exited 130, printed cancellation, and produced no traceback/alarm. This verifies signal handling, not physical keyboard interaction. The current passed-time check independently confirmed that behavior.
- During the audio investigation, `pw-play /usr/share/sounds/freedesktop/stereo/alarm-clock-elapsed.oga` completed outside the sandbox and **the user confirmed hearing it**. The updated `python3 alarm.py --in 3` also completed playback outside the sandbox; its audibility was not separately confirmed.
- Current live checks hit the known sandbox error `pw_context_connect() failed: Operation not permitted`. They verified the visible alarm and fallback reporting. No fresh claim of audible playback is made; the earlier successful audio evidence was reused.
- No overnight wait, physical suspend/resume, or broader platform coverage is claimed. Rollover and suspend simulations belong to the automated suite, not these live observations.

## Exact local commands for remaining interactive checks

From your normal Ubuntu terminal:

```bash
cd /home/development/Ankit_Verma_SSE_Role/python-cli-alarm-clock
python3 alarm.py --in 60
```

Press **Ctrl+C after the target appears and before 60 seconds elapse**, then run `echo $?` immediately. Expect `Alarm cancelled.`, status `130`, no alarm, and no traceback.

To repeat tomorrow-target inspection without waiting overnight:

```bash
python3 alarm.py --at "$(date +%H:%M)"
```

The current minute has already begun, so expect tomorrow at that minute. Press Ctrl+C after inspecting the printed date; immediately run `echo $?` and expect `130`.

For an upcoming-minute repeat at the time you run it:

```bash
python3 alarm.py --at "$(date -d '+2 minutes' +%H:%M)"
```

Keep the computer awake until the printed target. Expect one visible alarm and attempted playback. To check the five-second path and listen locally, run `python3 alarm.py --in 5`; record whether sound was actually heard separately from the printed completion message.
