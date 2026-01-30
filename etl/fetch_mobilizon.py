#!/usr/bin/env -S uv run

# /// script
# requires-python = ">=3.8"
# dependencies = [
#     "requests>=2.31.0",
# ]
# ///

"""Fetch ALL Mobilizon events for multiple groups defined in a config file."""

import json
import sys
from datetime import datetime
from pathlib import Path

import requests

# --- Path Resolution ---
# Determine the script directory (etl/) and the project root (.)
SCRIPT_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = SCRIPT_DIR.parent.resolve()

# Configuration file resides in the same directory as the script
CONFIG_FILE = SCRIPT_DIR / "mobilizon.json"

# Output directory resides in the project root
OUTPUT_DIR = PROJECT_ROOT / "calendars"

# GraphQL Query
GRAPHQL_QUERY = """
query FetchGroupEvents($name: String!, $afterDateTime: DateTime, $beforeDateTime: DateTime, $order: EventOrderBy, $orderDirection: SortDirection, $organisedEventsPage: Int, $organisedEventsLimit: Int) {
  group(preferredUsername: $name) {
    organizedEvents(
      afterDatetime: $afterDateTime
      beforeDatetime: $beforeDateTime
      order: $order
      orderDirection: $orderDirection
      page: $organisedEventsPage
      limit: $organisedEventsLimit
    ) {
      elements {
        id
        uuid
        title
        beginsOn
        status
        __typename
      }
      total
      __typename
    }
    __typename
  }
}
"""


def fetch_events(api_url: str, group_username: str) -> list[dict]:
    """Fetch all events for a specific group from a given API URL."""

    # Extract domain from api_url for the Referer header
    base_url = api_url.replace("/api", "")

    payload = {
        "operationName": "FetchGroupEvents",
        "variables": {
            "name": group_username,
            "afterDateTime": None,  # Fetch past events too
            "beforeDateTime": None,
            "order": "BEGINS_ON",
            "orderDirection": "DESC",
            "organisedEventsPage": 1,
            "organisedEventsLimit": 100
        },
        "query": GRAPHQL_QUERY
    }

    headers = {
        "Content-Type": "application/json",
        "Accept": "*/*",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:147.0) Gecko/20100101 Firefox/147.0",
        "Origin": base_url,
        "Referer": f"{base_url}/@{group_username}/events"
    }

    try:
        response = requests.post(api_url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()

        return data.get('data', {}).get('group', {}).get('organizedEvents', {}).get('elements', [])

    except requests.exceptions.RequestException as e:
        print(f"HTTP Request Error for '{group_username}': {e}", file=sys.stderr)
        return []
    except json.JSONDecodeError as e:
        print(f"JSON Decode Error for '{group_username}': {e}", file=sys.stderr)
        return []


def parse_event(event_data: dict, base_url: str) -> dict:
    """Convert raw event data to the desired JSON format."""
    begins_on = event_data.get('beginsOn')
    uuid = event_data.get('uuid')

    timestamp_ms = 0
    if begins_on:
        dt = datetime.fromisoformat(begins_on.replace('Z', '+00:00'))
        timestamp_ms = int(dt.timestamp() * 1000)

    return {
        "title": event_data.get('title'),
        "date": timestamp_ms,
        "url": f"{base_url}/events/{uuid}/"
    }


def main():
    """Main execution function."""
    # Ensure the output directory exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Check if config file exists (located in etl/)
    if not CONFIG_FILE.exists():
        print(f"Error: Configuration file '{CONFIG_FILE}' not found.", file=sys.stderr)
        sys.exit(1)

    # Load configuration
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            groups_config = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error parsing '{CONFIG_FILE}': {e}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(groups_config, list):
        print("Error: Configuration file must contain a list of groups.", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(groups_config)} group(s) to process.\n")

    for group in groups_config:
        api_url = group.get("api_url")
        username = group.get("group_username")

        if not api_url or not username:
            print(f"Skipping invalid entry: {group}")
            continue

        # Derive the base URL (e.g., https://mobilizon.fr) from the API URL
        base_url = api_url.replace("/api", "")

        # Deduce output filename
        output_filename = f"{username}.json"
        output_path = OUTPUT_DIR / output_filename

        print(f"Processing '@{username}' from {api_url}...")

        raw_events = fetch_events(api_url, username)

        if not raw_events:
            print(f"  -> No events found or error occurred.\n")
            continue

        # Pass base_url to parse_event to construct the full URL
        formatted_events = [parse_event(event, base_url) for event in raw_events]

        # Write to JSON file in the calendars/ directory
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(formatted_events, f, indent=4, ensure_ascii=False)
            print(f"  -> Successfully saved {len(formatted_events)} events to 'calendars/{output_filename}'.\n")
        except IOError as e:
            print(f"  -> Error writing file '{output_path}': {e}\n")


if __name__ == "__main__":
    main()
