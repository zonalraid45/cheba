import requests
import json
import time

TEAM_ID = "--elite-chess-players-union--"

session = requests.Session()

session.headers.update({
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/x-ndjson"
})

# Official API endpoint
url = f"https://lichess.org/api/team/{TEAM_ID}/arena"

print("Fetching full arena history...")

r = session.get(url, stream=True, timeout=60)

if r.status_code != 200:
    print("Failed:", r.status_code)
    exit()

results = []

count = 0

for line in r.iter_lines():

    if not line:
        continue

    try:
        data = json.loads(line)

        count += 1

        tid = data.get("id")

        print("Checking:", tid)

        # Need full tournament details
        api_url = f"https://lichess.org/api/tournament/{tid}"

        rr = session.get(api_url, timeout=20)

        if rr.status_code != 200:
            continue

        tdata = rr.json()

        clock = tdata.get("clock", {})

        # 3+0
        if clock.get("limit") != 180:
            continue

        if clock.get("increment") != 0:
            continue

        # 12h
        if tdata.get("minutes") != 720:
            continue

        battle = tdata.get("teamBattle")

        if not battle:
            continue

        teams = None

        if isinstance(battle, dict):
            teams = battle.get("teams")

        elif isinstance(battle, list):
            teams = battle

        our_team = None

        # dict format
        if isinstance(teams, dict):

            our_team = teams.get(TEAM_ID)

        # list format
        elif isinstance(teams, list):

            for t in teams:

                if not isinstance(t, dict):
                    continue

                tid2 = (
                    t.get("id")
                    or t.get("team")
                    or t.get("teamId")
                )

                if tid2 == TEAM_ID:
                    our_team = t
                    break

        if not our_team:
            continue

        rank = (
            our_team.get("rank")
            or our_team.get("place")
            or 999
        )

        if rank != 1:
            continue

        score = (
            our_team.get("nbPoints")
            or our_team.get("score")
            or 0
        )

        if score < 2000:
            continue

        results.append({
            "name": tdata.get("fullName"),
            "score": score,
            "url": f"https://lichess.org/tournament/{tid}"
        })

        print("MATCH FOUND:", tid)

        time.sleep(0.5)

    except Exception as e:
        print("ERROR:", e)

print("\n========================")
print("TOTAL ARENAS CHECKED:", count)
print("========================\n")

if not results:
    print("No matching tournaments found")

for r in results:

    print(
        f"{r['name']} | "
        f"Score: {r['score']} | "
        f"{r['url']}"
    )
