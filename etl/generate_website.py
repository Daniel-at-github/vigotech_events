#!/usr/bin/env -S uv run

# /// script
# requires-python = ">=3.9"
# dependencies = [
#     "jinja2",
# ]
# ///

"""
generate_website.py

This script scans the 'calendars/' directory and generates an 'index.html'
file that visualizes the events using FullCalendar and provides download links.
"""

import hashlib
import sys
from pathlib import Path

from jinja2 import Template

# Configuration
INPUT_DIR = Path("calendars")
OUTPUT_FILE = Path("index.html")


# Simple pastel color generator
def hash_to_pastel(name: str) -> str:
    hash_hex = hashlib.md5(name.encode()).hexdigest()
    r = (int(hash_hex[0:2], 16) + 255) // 2
    g = (int(hash_hex[2:4], 16) + 255) // 2
    b = (int(hash_hex[4:6], 16) + 255) // 2
    return f"#{r:02x}{g:02x}{b:02x}"


# HTML Template
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang='en'>
<head>
    <meta charset='utf-8' />
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Community Calendar</title>
    <script src='https://cdn.jsdelivr.net/npm/fullcalendar@6.1.10/index.global.min.js'></script>
    <style>
        body { margin: 0; font-family: Arial, sans-serif; padding: 20px; background-color: #f4f4f9; }
        #calendar { max-width: 1200px; margin: 30px auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .container { max-width: 1200px; margin: 0 auto; }
        h1 { text-align: center; color: #333; }

        /* Link List Styling */
        .links-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }
        .calendar-card {
            background: white;
            padding: 15px;
            border-radius: 6px;
            border-left: 5px solid #ccc;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }
        .calendar-card h3 { margin-top: 0; font-size: 1.1em; word-break: break-all; }
        .download-links { margin-top: 10px; font-size: 0.9em; }
        .download-links a { margin-right: 10px; text-decoration: none; color: #0066cc; }
        .download-links a:hover { text-decoration: underline; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Community Events</h1>

        <div class="links-grid">
            {% for cal in calendars %}
            <div class="calendar-card" style="border-left-color: {{ cal.color }};">
                <h3>{{ cal.name }}</h3>
                <div class="download-links">
                    {% if cal.has_json %}
                    <a href="calendars/{{ cal.name }}.json" target="_blank">JSON</a>
                    {% endif %}
                    {% if cal.has_ics %}
                    <a href="calendars/{{ cal.name }}.ics" target="_blank">ICS</a>
                    {% endif %}
                </div>
            </div>
            {% endfor %}
        </div>

        <div id='calendar'></div>
    </div>

    <script>
        document.addEventListener('DOMContentLoaded', function() {
            var calendarEl = document.getElementById('calendar');
            var calendar = new FullCalendar.Calendar(calendarEl, {
                initialView: 'dayGridMonth',
                headerToolbar: {
                    left: 'prev,next today',
                    center: 'title',
                    right: 'dayGridMonth,timeGridWeek,listWeek'
                },
                height: 'auto',
                eventSources: [
                    {% for cal in calendars %}
                    {
                        url: 'calendars/{{ cal.name }}.ics',
                        format: 'ics',
                        color: '{{ cal.color }}',
                        textColor: 'white'
                    },
                    {% endfor %}
                ]
            });
            calendar.render();
        });
    </script>
</body>
</html>
"""


def main():
    # 1. Scan directory
    if not INPUT_DIR.exists():
        print(
            f"Directory '{INPUT_DIR}' does not exist. Cannot generate website.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Collect data
    files_data = {}

    # Find all JSON and ICS files
    for f in INPUT_DIR.glob("*.json"):
        stem = f.stem
        if stem not in files_data:
            files_data[stem] = {"has_json": False, "has_ics": False}
        files_data[stem]["has_json"] = True

    for f in INPUT_DIR.glob("*.ics"):
        stem = f.stem
        if stem not in files_data:
            files_data[stem] = {"has_json": False, "has_ics": False}
        files_data[stem]["has_ics"] = True

    # Prepare list for template
    # Only add to list if we have at least an ICS file (required for FullCalendar view)
    calendars = []
    for name, flags in files_data.items():
        if flags["has_ics"]:
            calendars.append(
                {
                    "name": name,
                    "color": hash_to_pastel(name),
                    "has_json": flags["has_json"],
                    "has_ics": True,
                }
            )

    if not calendars:
        print("No .ics files found to render in calendar.", file=sys.stderr)
        # Create a dummy index.html stating no calendars found
        with open(OUTPUT_FILE, "w") as f:
            f.write("<h1>No calendars available</h1>")
        return

    # 2. Render HTML
    template = Template(HTML_TEMPLATE)
    html_content = template.render(calendars=calendars)

    # 3. Write to file
    try:
        with open(OUTPUT_FILE, "w") as f:
            f.write(html_content)
        print(
            f"Successfully generated {OUTPUT_FILE.name} with {len(calendars)} calendars."
        )
    except IOError as e:
        print(f"Error writing {OUTPUT_FILE.name}: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
