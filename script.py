import requests
import re
import time

TEAM_ID = "--elite-chess-players-union--"

session = requests.Session()

session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9"
})

# Better URL
url = f"https://lichess.org/team/{TEAM_ID}"

resp = session.get(url, timeout=20)

print("STATUS:", resp.status_code)

if resp.status_code != 200:
    print(resp.text[:500])
    raise SystemExit("Failed to fetch team page")

html = resp.text

# Extract tournament IDs
ids = set(re.findall(r'/tournament/([a-zA-Z0-9]{8})', html))

print(f"Found {len(ids)} tournaments")

results = []

for tid in ids:
    try:
        api_url = f"https://lichess.org/api/tournament/{tid}"

        r = session.get(api_url, timeout=20)

        if r.status_code != 200:
            print("Skipped:", tid)
            continue

        data = r.json()

        clock = data.get("clock", {})

        # 3+0
        if clock.get("limit") != 180:
            continue

        if clock.get("increment") != 0:
            continue

        # 12 hours
        if data.get("minutes") != 720:
            continue

        battle = data.get("teamBattle")

        if not battle:
            continue

        teams = battle.get("teams", [])

        our_team = None

        for t in teams:
            if t.get("id") == TEAM_ID:
                our_team = t
                break

        if not our_team:
            continue

        # first place
        if our_team.get("rank") != 1:
            continue

        score = our_team.get("score", 0)

        # 2000+
        if score < 2000:
            continue

        results.append(
            f"{data.get('fullName')} | "
            f"Score: {score} | "
            f"https://lichess.org/tournament/{tid}"
        )

        time.sleep(0.5)

    except Exception as e:
        print("ERROR:", tid, e)

print("\n=== RESULTS ===\n")

if not results:
    print("No matching tournaments found")

for x in results:
    print(x)
