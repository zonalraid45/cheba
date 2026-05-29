import requests
from bs4 import BeautifulSoup
import re
import json
import time

TEAM_ID = "--elite-chess-players-union--"

headers = {
    "User-Agent": "Mozilla/5.0"
}

# Step 1: Get team tournaments page
url = f"https://lichess.org/team/{TEAM_ID}/arena"

resp = requests.get(url, headers=headers)

if resp.status_code != 200:
    print("Failed to fetch team page")
    exit()

html = resp.text

# Find tournament IDs
# Tournament links look like /tournament/xxxxxxx
ids = set(re.findall(r'/tournament/([a-zA-Z0-9]{8})', html))

print(f"Found {len(ids)} tournaments")

results = []

for tid in ids:
    try:
        api_url = f"https://lichess.org/api/tournament/{tid}"

        r = requests.get(api_url, headers=headers)

        if r.status_code != 200:
            continue

        data = r.json()

        # Filter 3+0
        clock = data.get("clock", {})
        if clock.get("limit") != 180:
            continue

        if clock.get("increment") != 0:
            continue

        # Filter 12h duration
        minutes = data.get("minutes")

        if minutes != 720:
            continue

        # Must be team battle
        standing = data.get("teamBattle")

        if not standing:
            continue

        teams = standing.get("teams", [])

        if not teams:
            continue

        # Find our team
        our_team = None

        for t in teams:
            if t.get("id") == TEAM_ID:
                our_team = t
                break

        if not our_team:
            continue

        # Must be 1st place
        if our_team.get("rank") != 1:
            continue

        # Must have 2000+ points
        score = our_team.get("score", 0)

        if score < 2000:
            continue

        results.append({
            "name": data.get("fullName"),
            "id": tid,
            "score": score,
            "date": data.get("startsAt"),
            "url": f"https://lichess.org/tournament/{tid}"
        })

        time.sleep(1)

    except Exception as e:
        print("Error:", tid, e)

# Print results
print("\nMATCHES FOUND:\n")

for r in results:
    print(json.dumps(r, indent=2))
