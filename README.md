# CLI Alarm Clock

A persistent command-line alarm clock built in Python. Alarms survive terminal sessions, support daily repeat, snooze, and fire macOS system notifications.

## Features

- Set alarms by absolute time (`--time`) or relative duration (`--in`)
- `once` or `daily` repeat modes
- Snooze any alarm by N minutes
- Rich formatted alarm table with countdown
- macOS system notifications + terminal bell on fire
- JSON-backed persistence at `~/.alarm_clock/alarms.json`
- Foreground watcher loop — no daemons, no background processes

## Requirements

- Python 3.10+
- macOS (notification/sound via `osascript` and `afplay`; terminal bell works everywhere)

## Installation

```bash
git clone https://github.com/Vishal-sikchi-088/Alarm-Clock--Assignment.git
cd Alarm-Clock--Assignment
pip install -r requirements.txt
```

## Usage

### Add an alarm

```bash
# By absolute time (24h)
python alarm.py add --time 07:30 --label "Standup" --repeat daily

# By absolute time (12h)
python alarm.py add --time "2:30 PM" --label "Review"

# By relative duration
python alarm.py add --in 25m --label "Break"
python alarm.py add --in 1h30m --label "Lunch"
```

> `--time` and `--in` are mutually exclusive.  
> A past `--time` automatically schedules for **tomorrow**.

### List alarms

```bash
python alarm.py list
```

```
                          Alarms
┏━━━━┳━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━┓
┃ ID ┃ Label   ┃ Next Fire                    ┃ Repeat ┃ Status ┃
┡━━━━╇━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━┩
│ 1  │ Standup │ 2026-06-05 07:30 (in 7h 28m) │ daily  │ active │
│ 2  │ Break   │ 2026-06-04 14:25 (in 25m)    │  once  │ active │
└────┴─────────┴──────────────────────────────┴────────┴────────┘
```

### Delete an alarm

```bash
python alarm.py delete 2
```

### Snooze an alarm

```bash
python alarm.py snooze 1            # default 5 minutes
python alarm.py snooze 1 --minutes 10
```

### Start the watcher

```bash
python alarm.py run
```

Polls every 5 seconds. Press `Ctrl+C` to stop.  
When an alarm fires, it shows a terminal alert, plays a sound, and sends a macOS notification.  
Daily alarms automatically advance to the next day after firing.

## Storage

Alarms are stored at `~/.alarm_clock/alarms.json` — independent of the project folder. The file is created automatically on first use.

```json
{
  "1": {
    "id": "1",
    "label": "Standup",
    "next_fire": "2026-06-05T07:30:00",
    "base_time": "07:30",
    "repeat": "daily",
    "active": true
  }
}
```

## Running Tests

```bash
python -m unittest test_alarm -v
```

32 focused unit tests covering:
- `parse_duration` edge cases (bare int, hours, minutes, combined, invalid)
- Past `--time` scheduling for tomorrow
- `--time` and `--in` mutual exclusivity
- Daily repeat and `base_time` storage
- Delete (success + unknown ID exits non-zero)
- Snooze (fire time, default duration, reactivation, `base_time` preservation)

## Design Decisions

| Choice | Reason |
|---|---|
| Single file | Fits scope; easy to run and review |
| `click` | Clean decorator-based CLI, good help output |
| `rich` | Formatted table with countdown, no extra complexity |
| Foreground watcher | No daemon complexity; honest about what `run` does |
| `base_time` field | Decouples snooze from daily schedule — snoozing doesn't shift tomorrow's alarm |
| `~/.alarm_clock/` | Persists independently of project location |
