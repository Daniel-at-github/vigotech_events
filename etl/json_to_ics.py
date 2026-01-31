#!/usr/bin/env -S uv run

# /// script
# requires-python = ">=3.9"
# dependencies = [
#     "ics",
# ]
# ///

"""
json_to_ics.py

This script reads JSON event files from a specific directory and converts them
into standard iCalendar (.ics) files.

Usage:
    uv run json_to_ics.py

JSON Format Expected:
    [
        {
            "title": "Event Title",
            "date": 1764961200000,  # Milliseconds since epoch
            "url": "https://example.com/event"
        },
        ...
    ]
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from ics import Calendar, Event

# Configuration
INPUT_DIR = Path("calendars")


def convert_ms_to_datetime(ms_timestamp: int) -> datetime:
    """
    Converts a millisecond timestamp to a UTC datetime object.
    """
    return datetime.fromtimestamp(ms_timestamp / 1000, tz=timezone.utc)


def process_json_file(json_path: Path):
    """
    Reads a single JSON file and writes a corresponding .ics file.
    Handles errors specific to this file without stopping the whole script.
    """
    try:
        # Read JSON data
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

        # Create Calendar
        calendar = Calendar()

        # Populate Events
        for item in events_data:
            try:
                # Extract data safely
                title = item.get("title", "Untitled Event")
                url = item.get("url", "")
                date_ms = item.get("date")

                if date_ms is None:
                    print(
                        f"Skipping item in {json_path.name}: Missing 'date' field.",
                        file=sys.stderr,
                    )
                    continue

                event_date = convert_ms_to_datetime(date_ms)

                # Create ICS Event
                event = Event()
                event.name = title
                event.begin = event_date
                # Using URL as the description if no other text is provided
                event.description = url
                event.url = url

                calendar.events.add(event)

            except Exception as e:
                # Log error for a specific event item but continue processing the file
                print(
                    f"Error processing item in {json_path.name}: {e}",
                    file=sys.stderr,
                )
                continue

        # Write .ics file
        output_path = json_path.with_suffix(".ics")
        try:
            with output_path.open("w", encoding="utf-8") as f:
                f.writelines(calendar)
            print(f"Successfully created {output_path.name}")
        except IOError as e:
            print(f"Error writing {output_path.name}: {e}", file=sys.stderr)

    except Exception as e:
        # Catch-all for unexpected logic errors within this file's processing
        print(f"Unexpected error processing {json_path.name}: {e}", file=sys.stderr)


def main():
    # Ensure input directory exists
    if not INPUT_DIR.exists():
        print(f"Directory '{INPUT_DIR}' does not exist.", file=sys.stderr)
        sys.exit(1)

    # Find all .json files
    json_files = list(INPUT_DIR.glob("*.json"))

    if not json_files:
        print(f"No JSON files found in '{INPUT_DIR}'.", file=sys.stderr)
        return

    # Process each file
    for json_file in json_files:
        process_json_file(json_file)


if __name__ == "__main__":
    main()
