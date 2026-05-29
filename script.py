import requests
import json
import time

TEAM_ID = "--elite-chess-players-union--"

session = requests.Session()

session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/x-ndjson"
})

results = []

total_checked = 0
page = 1

print("Fetching ALL historical arenas...\n")

while True:

    print(f"PAGE {page}")

    url = f"https://lichess.org/api/team/{TEAM_ID}/arena?page={page}"

    r = session.get(url, stream=True, timeout=60)

    if r.status_code != 200:
        print("Failed page:", page)
        break

    found_any = False

    for line in r.iter_lines():

        if not line:
            continue

        found_any = True

        try:

            data = json.loads(line)

            tid = data.get("id")

            if not tid:
                continue

            total_checked += 1

            print("Checking:", tid)

            # Full tournament API
            api_url = f"https://lichess.org/api/tournament/{tid}"

            rr = session.get(api_url, timeout=30)

            if rr.status_code != 200:
                continue

            tdata = rr.json()

            # Some responses are weird arrays
            if not isinstance(tdata, dict):
                continue

            clock = tdata.get("clock", {})

            # 3+0 only
            if clock.get("limit") != 180:
                continue

            if clock.get("increment") != 0:
                continue

            # 12h only
            if tdata.get("minutes") != 720:
                continue

            battle = tdata.get("teamBattle")

            if not battle:
                continue

            teams = None

            # teamBattle may itself be list
            if isinstance(battle, list):
                teams = battle

            # or normal dict
            elif isinstance(battle, dict):
                teams = battle.get("teams")

            if not teams:
                continue

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

            # Must be first place
            if rank != 1:
                continue

            score = (
                our_team.get("nbPoints")
                or our_team.get("score")
                or 0
            )

            # Must be 2000+
            if score < 2000:
                continue

            result = (
                f"{tdata.get('fullName')} | "
                f"Score: {score} | "
                f"https://lichess.org/tournament/{tid}"
            )

            results.append(result)

            print("MATCH FOUND!")

            time.sleep(0.5)

        except Exception as e:

            print("ERROR:", e)

    # No more arenas
    if not found_any:
        print("No more arenas found")
        break

    print(f"Finished page {page}\n")

    page += 1

    time.sleep(1)

print("\n========================")
print("TOTAL ARENAS CHECKED:", total_checked)
print("========================\n")

if not results:

    print("No matching tournaments found")

else:

    print("MATCHES:\n")

    for r in results:
        print(r)
