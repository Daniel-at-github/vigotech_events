#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.9"
# dependencies = [
#     "requests>=2.32.0",
#     "tenacity>=8.0.0",
# ]
# ///

"""
Fetch Meetup Events without Authentication.

This script reads configuration from 'meetup.json', fetches events
from the public GraphQL API, and saves the results to 'calendars/'.

Usage (from project root):
    uv run etl/fetch_meetup.py
"""

import datetime
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

# --- Paths Configuration ---
CONFIG_PATH = Path("etl") / "meetup.json"
if not CONFIG_PATH.exists():
    CONFIG_PATH = Path(__file__).parent.parent / "meetup.json"

OUTPUT_DIR = Path("calendars")

# --- API Constants ---
API_URL = "https://www.meetup.com/gql2"
PAGINATION_DELAY = 0.5

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:147.0) Gecko/20100101 Firefox/147.0",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.5",
    "content-type": "application/json",
    "apollographql-client-name": "nextjs-web",
    "Referer": "https://www.meetup.com/",
    "Origin": "https://www.meetup.com",
    "Connection": "keep-alive",
}


def load_config() -> Dict[str, Any]:
    """Loads the configuration (groups and hash) from meetup.json."""
    if not CONFIG_PATH.exists():
        print(f"Error: Configuration file '{CONFIG_PATH}' not found.", file=sys.stderr)
        sys.exit(1)

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)

            if not isinstance(config, dict):
                print(
                    f"Error: {CONFIG_PATH} must be a JSON object with 'groups' and 'graphql_hash'.",
                    file=sys.stderr,
                )
                sys.exit(1)

            if "groups" not in config or "graphql_hash" not in config:
                print(
                    f"Error: {CONFIG_PATH} missing 'groups' or 'graphql_hash'.",
                    file=sys.stderr,
                )
                sys.exit(1)

            return config
    except json.JSONDecodeError as e:
        print(f"Error: Failed to parse {CONFIG_PATH}. {e}", file=sys.stderr)
        sys.exit(1)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception_type(requests.exceptions.RequestException),
    reraise=True,
)
def __make_request(payload: Dict) -> requests.Response:
    """Internal helper to perform the HTTP POST request with retries."""
    return requests.post(API_URL, json=payload, headers=HEADERS, timeout=15)


def fetch_events_for_group(
    group_urlname: str, graphql_hash: str
) -> List[Dict[str, Any]]:
    """
    Fetches events.
    Logic: Fetch 'past' events up to a date far in the future to get everything,
    then filter locally to keep last 1.5 years + all future.
    """
    events = []
    cursor = None
    has_next_page = True

    # We set the horizon to 1 year in the future to ensure we catch all future events
    # using the 'past' events endpoint (which essentially acts as 'all events' if before is far away).
    future_horizon = (
        (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=365))
        .isoformat()
        .replace("+00:00", "Z")
    )

    # Calculate cutoff date (1.5 years ago)
    cutoff_date = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
        days=540
    )  # 18 months

    print(f"Fetching events for: {group_urlname}")

    while has_next_page:
        variables = {"urlname": group_urlname, "beforeDateTime": future_horizon}
        if cursor:
            variables["after"] = cursor

        payload = {
            "operationName": "getPastGroupEvents",
            "variables": variables,
            "extensions": {
                "persistedQuery": {"version": 1, "sha256Hash": graphql_hash}
            },
        }

        try:
            response = __make_request(payload)

            if response.status_code != 200:
                print(
                    f"Error fetching {group_urlname}: HTTP {response.status_code}",
                    file=sys.stderr,
                )
                try:
                    err_data = response.json()
                    print(f"API Error: {err_data}", file=sys.stderr)
                except:
                    print(f"Response body: {response.text[:200]}", file=sys.stderr)
                break

            data = response.json()
            group_data = data.get("data", {}).get("groupByUrlname")

            if not group_data:
                print(
                    f"No data found for {group_urlname}. The group might not exist.",
                    file=sys.stderr,
                )
                break

            events_data = group_data.get("events", {})
            edges = events_data.get("edges", [])
            page_info = events_data.get("pageInfo", {})

            for edge in edges:
                node = edge.get("node", {})

                # Transform immediately
                transformed = __transform_event(node)

                # Filter logic: Keep events starting after cutoff OR keep it if it's very recent
                # (Since 'past' query usually returns newest first, we stop if we go too far back)

                # 1. Parse date from the transformed event (or raw node) to check cutoff
                dt_obj = None
                date_str = node.get("dateTime")
                if date_str:
                    try:
                        dt_obj = datetime.datetime.fromisoformat(date_str)
                    except ValueError:
                        pass

                # If date is valid
                if dt_obj:
                    if dt_obj >= cutoff_date:
                        events.append(transformed)
                    else:
                        # Optimization: Since API returns descending (newest first),
                        # if we hit a date older than cutoff, we are done for this page.
                        # Note: Some APIs return mixed pagination, but Meetup GQL is usually chronological.
                        # We'll rely on the logic: append if valid, loop continues until pagination ends.
                        pass

            has_next_page = page_info.get("hasNextPage", False)
            cursor = page_info.get("endCursor")

            if has_next_page:
                time.sleep(PAGINATION_DELAY)

        except Exception as e:
            print(f"Unexpected error processing {group_urlname}: {e}", file=sys.stderr)
            break

    print(f"  -> Found {len(events)} events within the last 1.5 years and future.")
    return events


def __transform_event(event_node: Dict[str, Any]) -> Dict[str, Any]:
    """Transforms the raw event node into the required output schema."""
    title = event_node.get("title", "Unknown Title")
    event_url = event_node.get("eventUrl", "")
    date_str = event_node.get("dateTime")

    # Meetup usually returns duration in minutes
    duration_minutes = event_node.get("duration")

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
        "url": event_url,
        "duration": duration_minutes,
    }


def save_output(group_name: str, events: List[Dict[str, Any]]) -> None:
    """Saves the list of events to a JSON file."""
    if not events:
        print(f"  -> No events to save for {group_name}.")
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    filename = OUTPUT_DIR / f"{group_name}.json"

    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(events, f, indent=4)
        print(f"  -> Saved to {filename}")
    except IOError as e:
        print(f"Error writing to file {filename}: {e}", file=sys.stderr)


def main():
    print("--- Meetup Event Fetcher ---")

    config = load_config()
    groups = config.get("groups", [])
    graphql_hash = config.get("graphql_hash", "")

    if not graphql_hash:
        print("Error: graphql_hash is missing in config.", file=sys.stderr)
        sys.exit(1)

    for group in groups:
        if not isinstance(group, str) or not group:
            print(f"Skipping invalid group entry: {group}", file=sys.stderr)
            continue

        try:
            events = fetch_events_for_group(group, graphql_hash)
            save_output(group, events)
        except KeyboardInterrupt:
            print("\nProcess interrupted by user.", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"Failed to process group {group}: {e}", file=sys.stderr)

    print("--- Done ---")


if __name__ == "__main__":
    main()
