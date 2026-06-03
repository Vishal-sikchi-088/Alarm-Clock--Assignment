#!/usr/bin/env python3
"""CLI Alarm Clock — single file, JSON-backed, click + rich."""

import json
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

DATA_DIR = Path.home() / ".alarm_clock"
DATA_DIR.mkdir(exist_ok=True)
ALARMS_FILE = DATA_DIR / "alarms.json"

console = Console()


def load_alarms() -> dict:
    if not ALARMS_FILE.exists():
        return {}
    try:
        return json.loads(ALARMS_FILE.read_text())
    except json.JSONDecodeError:
        return {}


def save_alarms(alarms: dict) -> None:
    ALARMS_FILE.write_text(json.dumps(alarms, indent=2))


def next_id(alarms: dict) -> str:
    int_keys = [int(k) for k in alarms if k.isdigit()]
    return str(max(int_keys) + 1) if int_keys else "1"


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------

def parse_duration(raw: str) -> timedelta:
    m = re.fullmatch(r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?", raw.strip())
    if not m or not any(m.groups()):
        raise click.BadParameter(
            f"Invalid duration '{raw}'. Examples: 5m, 1h, 1h30m, 90s"
        )
    h, mn, s = (int(v or 0) for v in m.groups())
    return timedelta(hours=h, minutes=mn, seconds=s)


def parse_alarm_time(raw: str) -> datetime:
    now = datetime.now()
    normalized = raw.strip().upper()
    for fmt in ("%H:%M", "%I:%M %p", "%I:%M%p"):
        try:
            parsed = datetime.strptime(normalized, fmt)
            target = now.replace(
                hour=parsed.hour, minute=parsed.minute, second=0, microsecond=0
            )
            if target <= now:
                target += timedelta(days=1)
            return target
        except ValueError:
            continue
    raise click.BadParameter(
        f"Invalid time '{raw}'. Use 24h (14:30) or 12h (2:30 PM)."
    )


def fmt_countdown(next_fire_iso: str) -> str:
    nf = datetime.fromisoformat(next_fire_iso)
    delta = nf - datetime.now()
    total = int(delta.total_seconds())
    if total <= 0:
        return f"{nf.strftime('%Y-%m-%d %H:%M')} [red](overdue)[/red]"
    h, rem = divmod(total, 3600)
    m = rem // 60
    parts = [f"{h}h"] if h else []
    parts += [f"{m}m"] if m else []
    if not parts:
        parts = ["<1m"]
    return f"{nf.strftime('%Y-%m-%d %H:%M')} (in {' '.join(parts)})"


# ---------------------------------------------------------------------------
# Notification
# ---------------------------------------------------------------------------

def notify(label: str) -> None:
    msg = label or "Alarm!"
    console.print(f"\n[bold red blink]⏰  {msg}[/bold red blink]\n")
    print("\a\a\a", end="", flush=True)
    try:
        subprocess.run(
            [
                "osascript", "-e",
                f'display notification "{msg}" with title "⏰ Alarm Clock" sound name "Glass"',
            ],
            check=False, capture_output=True, timeout=3,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    try:
        subprocess.run(
            ["afplay", "/System/Library/Sounds/Glass.aiff"],
            check=False, capture_output=True, timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.group()
def cli():
    """Persistent CLI alarm clock."""


@cli.command()
@click.option("--time", "alarm_time", default=None, metavar="HH:MM",
              help="Absolute time, e.g. 07:30 or 2:30 PM")
@click.option("--in", "duration", default=None, metavar="DURATION",
              help="Relative duration, e.g. 5m, 1h30m")
@click.option("--label", "-l", default="", help="Short description")
@click.option(
    "--repeat",
    type=click.Choice(["once", "daily"]),
    default="once",
    show_default=True,
    help="Repeat behaviour",
)
def add(alarm_time, duration, label, repeat):
    """Add a new alarm (--time or --in, not both)."""
    if alarm_time and duration:
        raise click.UsageError("--time and --in are mutually exclusive.")
    if not alarm_time and not duration:
        raise click.UsageError("Provide either --time or --in.")

    if alarm_time:
        next_fire = parse_alarm_time(alarm_time)
    else:
        next_fire = datetime.now() + parse_duration(duration)

    base_time = next_fire.strftime("%H:%M")

    alarms = load_alarms()
    alarm_id = next_id(alarms)
    alarms[alarm_id] = {
        "id": alarm_id,
        "label": label,
        "next_fire": next_fire.isoformat(),
        "base_time": base_time,
        "repeat": repeat,
        "active": True,
    }
    save_alarms(alarms)
    suffix = " [daily]" if repeat == "daily" else ""
    console.print(
        f"[green]✓ Alarm [bold]{alarm_id}[/bold] set for "
        f"{next_fire.strftime('%Y-%m-%d %H:%M')}{suffix}[/green]"
    )


@cli.command("list")
def list_alarms():
    """List all alarms."""
    alarms = load_alarms()
    if not alarms:
        console.print("[yellow]No alarms set.[/yellow]")
        return

    table = Table(title="Alarms", show_lines=True)
    table.add_column("ID", style="cyan", justify="center", no_wrap=True)
    table.add_column("Label", style="magenta")
    table.add_column("Next Fire", style="green")
    table.add_column("Repeat", style="blue", justify="center")
    table.add_column("Status", justify="center")

    for alarm_id, a in sorted(alarms.items(), key=lambda x: x[1]["next_fire"]):
        status = "[green]active[/green]" if a["active"] else "[dim]inactive[/dim]"
        table.add_row(
            alarm_id,
            a["label"] or "[dim]—[/dim]",
            fmt_countdown(a["next_fire"]),
            a["repeat"],
            status,
        )
    console.print(table)


@cli.command()
@click.argument("alarm_id")
def delete(alarm_id):
    """Delete an alarm by ID."""
    alarms = load_alarms()
    if alarm_id not in alarms:
        console.print(f"[red]No alarm with ID {alarm_id!r}.[/red]")
        sys.exit(1)
    removed = alarms.pop(alarm_id)
    save_alarms(alarms)
    tag = f" ({removed['label']})" if removed["label"] else ""
    console.print(f"[green]✓ Deleted alarm {alarm_id}{tag}.[/green]")


@cli.command()
@click.argument("alarm_id")
@click.option("--minutes", "-m", default=5, show_default=True,
              help="Snooze duration in minutes")
def snooze(alarm_id, minutes):
    """Snooze an alarm by ID for N minutes."""
    alarms = load_alarms()
    if alarm_id not in alarms:
        console.print(f"[red]No alarm with ID {alarm_id!r}.[/red]")
        sys.exit(1)
    new_fire = datetime.now() + timedelta(minutes=minutes)
    alarms[alarm_id]["next_fire"] = new_fire.isoformat()
    alarms[alarm_id]["active"] = True
    save_alarms(alarms)
    console.print(
        f"[yellow]💤 Alarm {alarm_id} snoozed until "
        f"{new_fire.strftime('%H:%M')} (+{minutes}m).[/yellow]"
    )


@cli.command()
def run():
    """Start the alarm watcher (foreground). Ctrl+C to stop."""
    console.print("[bold green]⏰ Watcher started. Ctrl+C to exit.[/bold green]")
    try:
        while True:
            alarms = load_alarms()
            now = datetime.now()
            changed = False

            for alarm_id, a in list(alarms.items()):
                if not a["active"]:
                    continue
                if now >= datetime.fromisoformat(a["next_fire"]):
                    notify(a["label"])
                    changed = True
                    if a["repeat"] == "daily":
                        h, m = map(int, a["base_time"].split(":"))
                        next_day = (now + timedelta(days=1)).replace(
                            hour=h, minute=m, second=0, microsecond=0
                        )
                        a["next_fire"] = next_day.isoformat()
                    else:
                        a["active"] = False

            if changed:
                save_alarms(alarms)

            time.sleep(5)

    except KeyboardInterrupt:
        console.print("\n[yellow]Watcher stopped.[/yellow]")


if __name__ == "__main__":
    cli()
