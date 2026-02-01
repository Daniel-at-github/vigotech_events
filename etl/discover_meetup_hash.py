#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.9"
# dependencies = [
#     "playwright>=1.40.0",
# ]
# ///

"""
discover_meetup_hash.py

Launches a headless browser to intercept the GraphQL network requests made by Meetup,
extracts the sha256Hash used for 'getPastGroupEvents', and updates meetup.json.
"""

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

# Configuration
# We use a popular group from the list to force the API call
# Using the "past events" view ensures the specific query we want is triggered.
TARGET_URL = "https://www.meetup.com/sysarmy-galicia/events/past/"
CONFIG_PATH = Path("etl") / "meetup.json"

# Fallback to project root if running from elsewhere
if not CONFIG_PATH.exists():
    CONFIG_PATH = Path(__file__).parent.parent / "meetup.json"


def discover_hash():
    """Runs the headless browser and extracts the hash."""
    print("Launching headless browser to discover GraphQL hash...")

    with sync_playwright() as p:
        # Launch browser
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/115.0"
        )
        page = context.new_page()

        found_hash = None

        def handle_response(response):
            """Intercepts network responses looking for the specific GQL query."""
            nonlocal found_hash

            # Filter for the GraphQL endpoint
            if "gql2" in response.url:
                try:
                    # Access the request object associated with this response
                    request = response.request
                    post_data = request.post_data_json

                    # Check if this is the operation we care about
                    if post_data.get("operationName") == "getPastGroupEvents":
                        hash_val = (
                            post_data.get("extensions", {})
                            .get("persistedQuery", {})
                            .get("sha256Hash")
                        )
                        if hash_val:
                            found_hash = hash_val
                            print(f"  -> Intercepted Hash: {hash_val}")
                except Exception:
                    # Ignore JSON parsing errors for non-JSON requests
                    pass

        # Attach the listener
        page.on("response", handle_response)

        # Go to the page
        page.goto(TARGET_URL, timeout=15000)

        # Wait a moment for the lazy loading/XHR to trigger
        # We wait for a selector that likely appears after data loads, or just a fixed timeout
        # Here we wait for any event card to appear in the DOM
        try:
            page.wait_for_selector("div[data-event-id]", timeout=10000)
        except:
            # If selector not found, we might still have caught the network request during loading
            pass

        browser.close()

        return found_hash


def update_config(new_hash):
    """Updates the meetup.json file with the new hash."""
    if not CONFIG_PATH.exists():
        print(f"Error: {CONFIG_PATH} not found.", file=sys.stderr)
        return False

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)

        old_hash = config.get("graphql_hash", "")
        if old_hash == new_hash:
            print("Hash is already up to date.")
            return False

        config["graphql_hash"] = new_hash

        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)

        print(f"Updated {CONFIG_PATH} with new hash.")
        return True
    except Exception as e:
        print(f"Failed to update config: {e}", file=sys.stderr)
        return False


def main():
    hash_val = discover_hash()

    if hash_val:
        update_config(hash_val)
    else:
        print(
            "Failed to discover hash. The site structure might have changed.",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
