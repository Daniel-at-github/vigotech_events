#!/usr/bin/env -S uv run

# /// script
# requires-python = ">=3.9"
# dependencies = [
#     "ics",
# ]
# ///

"""
json_to_ics.py

Reads JSON event files and converts them to standard iCalendar (.ics) files.
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ics import Calendar, Event

INPUT_DIR = Path("calendars")


def convert_ms_to_datetime(ms_timestamp: int) -> datetime:
    """Converts a millisecond timestamp to a UTC datetime object."""
    return datetime.fromtimestamp(ms_timestamp / 1000, tz=timezone.utc)


def process_json_file(json_path: Path):
    """Reads a single JSON file and writes a corresponding .ics file."""
    try:
        try:
            content = json_path.read_text(encoding="utf-8")
            events_data = json.loads(content)
        except (IOError, json.JSONDecodeError) as e:
            print(f"Error reading or parsing {json_path.name}: {e}", file=sys.stderr)
            return

        if not isinstance(events_data, list):
            print(
                f"Skipping {json_path.name}: Expected a list of events, got {type(events_data)}.",
                file=sys.stderr,
            )
            return

        calendar = Calendar()

        for item in events_data:
            try:
                title = item.get("title", "Untitled Event")
                url = item.get("url", "")
                date_ms = item.get("date")
                duration_minutes = item.get("duration")

                if date_ms is None:
                    print(
                        f"Skipping item in {json_path.name}: Missing 'date' field.",
                        file=sys.stderr,
                    )
                    continue

                event_date = convert_ms_to_datetime(date_ms)

                event = Event()
                event.name = title
                event.begin = event_date
                event.description = url
                event.url = url

                # Preserve duration from JSON, default to 2 hours if missing
                if duration_minutes and isinstance(duration_minutes, (int, float)):
                    event.duration = timedelta(minutes=duration_minutes)
                else:
                    event.duration = timedelta(hours=2)

                calendar.events.add(event)

            except Exception as e:
                print(
                    f"Error processing item in {json_path.name}: {e}",
                    file=sys.stderr,
                )
                continue

        output_path = json_path.with_suffix(".ics")
        try:
            with output_path.open("w", encoding="utf-8") as f:
                f.writelines(calendar)
            print(f"Successfully created {output_path.name}")
        except IOError as e:
            print(f"Error writing {output_path.name}: {e}", file=sys.stderr)

    except Exception as e:
        print(f"Unexpected error processing {json_path.name}: {e}", file=sys.stderr)


def main():
    if not INPUT_DIR.exists():
        print(f"Directory '{INPUT_DIR}' does not exist.", file=sys.stderr)
        sys.exit(1)

    json_files = list(INPUT_DIR.glob("*.json"))
    if not json_files:
        print(f"No JSON files found in '{INPUT_DIR}'.", file=sys.stderr)
        return

    for json_file in json_files:
        process_json_file(json_file)


if __name__ == "__main__":
    main()
