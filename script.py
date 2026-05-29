if not battle:
    continue

teams = battle.get("teams")

our_team = None

# Case 1: dict
if isinstance(teams, dict):
    our_team = teams.get(TEAM_ID)

# Case 2: list
elif isinstance(teams, list):
    for t in teams:
        if isinstance(t, dict) and t.get("id") == TEAM_ID:
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
