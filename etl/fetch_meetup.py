#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.9"
# dependencies = [
#     "requests>=2.32.0",
# ]
# ///

"""
Fetch Meetup Events without Authentication.

This script reads a list of Meetup groups from 'meetup.json' (located at project root),
fetches all past events for each group via the public GraphQL API,
and saves the results to the 'calendars/' directory.

Usage (from project root):
    uv run etl/fetch_meetup.py
"""

import json
import sys
import time
import datetime
import requests
from pathlib import Path
from typing import List, Dict, Any

# --- Paths Configuration ---
# Try to locate meetup.json in the current directory or the parent directory
# to allow running the script from the project root or from inside etl/
CONFIG_PATH = Path("etl") / "meetup.json"
if not CONFIG_PATH.exists():
    CONFIG_PATH = Path(__file__).parent.parent / "meetup.json"

OUTPUT_DIR = Path("calendars")

# --- API Constants ---
API_URL = "https://www.meetup.com/gql2"
PAGINATION_DELAY = 0.5
PERSISTED_QUERY_HASH = "9463f7c9ab5b08db3f2172223c806fb48993508781cd939184d9151c75214e3a"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:147.0) Gecko/20100101 Firefox/147.0',
    'Accept': '*/*',
    'Accept-Language': 'en-US,en;q=0.5',
    'content-type': 'application/json',
    'apollographql-client-name': 'nextjs-web',
    'Referer': 'https://www.meetup.com/',
    'Origin': 'https://www.meetup.com',
    'Connection': 'keep-alive',
}


def load_config() -> List[str]:
    """Loads the list of group usernames from meetup.json."""
    if not CONFIG_PATH.exists():
        print(f"Error: Configuration file '{CONFIG_PATH}' not found.", file=sys.stderr)
        sys.exit(1)

    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            groups = json.load(f)

            if not isinstance(groups, list):
                print(f"Error: {CONFIG_PATH} must contain a JSON list.", file=sys.stderr)
                sys.exit(1)

            return groups
    except json.JSONDecodeError as e:
        print(f"Error: Failed to parse {CONFIG_PATH}. {e}", file=sys.stderr)
        sys.exit(1)


def fetch_events_for_group(group_urlname: str) -> List[Dict[str, Any]]:
    """
    Fetches all past events for a specific group.
    """
    events = []
    cursor = None
    has_next_page = True

    # Set a future date to ensure we capture all "past" events relative to now
    before_date = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=365)).isoformat().replace('+00:00', 'Z')

    print(f"Fetching events for: {group_urlname}")

    while has_next_page:
        variables = {
            "urlname": group_urlname,
            "beforeDateTime": before_date
        }
        if cursor:
            variables["after"] = cursor

        payload = {
            "operationName": "getPastGroupEvents",
            "variables": variables,
            "extensions": {
                "persistedQuery": {
                    "version": 1,
                    "sha256Hash": PERSISTED_QUERY_HASH
                }
            }
        }

        try:
            response = __make_request(payload)

            if not response:
                break

            if response.status_code != 200:
                print(f"Error fetching {group_urlname}: HTTP {response.status_code}", file=sys.stderr)
                try:
                    print(f"Response body: {response.text[:200]}", file=sys.stderr)
                except:
                    pass
                break

            data = response.json()
            group_data = data.get('data', {}).get('groupByUrlname')

            if not group_data:
                print(f"No data found for {group_urlname}. The group might not exist or be private.", file=sys.stderr)
                break

            events_data = group_data.get('events', {})
            edges = events_data.get('edges', [])
            page_info = events_data.get('pageInfo', {})

            for edge in edges:
                node = edge.get('node', {})
                events.append(__transform_event(node))

            has_next_page = page_info.get('hasNextPage', False)
            cursor = page_info.get('endCursor')

            if has_next_page:
                time.sleep(PAGINATION_DELAY)

        except Exception as e:
            print(f"Unexpected error processing {group_urlname}: {e}", file=sys.stderr)
            break

    print(f"  -> Found {len(events)} events.")
    return events


def __make_request(payload: Dict) -> Any:
    """Internal helper to perform the HTTP POST request safely."""
    try:
        return requests.post(API_URL, json=payload, headers=HEADERS, timeout=10)
    except requests.exceptions.RequestException as e:
        print(f"Network error: {e}", file=sys.stderr)
        return None


def __transform_event(event_node: Dict[str, Any]) -> Dict[str, Any]:
    """Transforms the raw event node into the required output schema."""
    title = event_node.get('title', 'Unknown Title')
    event_url = event_node.get('eventUrl', '')
    date_str = event_node.get('dateTime')

    timestamp_ms = 0
    if date_str:
        try:
            dt_obj = datetime.datetime.fromisoformat(date_str)
            timestamp_ms = int(dt_obj.timestamp() * 1000)
        except (ValueError, TypeError):
            pass

    return {
        "title": title,
        "date": timestamp_ms,
        "url": event_url
    }


def save_output(group_name: str, events: List[Dict[str, Any]]) -> None:
    """Saves the list of events to a JSON file inside the calendars/ directory."""
    if not events:
        print(f"  -> No events to save for {group_name}.")
        return

    # Ensure the output directory exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    filename = OUTPUT_DIR / f"{group_name}.json"

    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(events, f, indent=4)
        print(f"  -> Saved to {filename}")
    except IOError as e:
        print(f"Error writing to file {filename}: {e}", file=sys.stderr)


def main():
    print("--- Meetup Event Fetcher ---")

    # Resolve paths relative to where the script is being called usually
    # The CONFIG_PATH logic handles finding meetup.json regardless of CWD

    groups = load_config()

    for group in groups:
        if not isinstance(group, str) or not group:
            print(f"Skipping invalid group entry: {group}", file=sys.stderr)
            continue

        try:
            events = fetch_events_for_group(group)
            save_output(group, events)
        except KeyboardInterrupt:
            print("\nProcess interrupted by user.", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"Failed to process group {group}: {e}", file=sys.stderr)

    print("--- Done ---")

if __name__ == "__main__":
    main()
