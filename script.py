#!/usr/bin/env python3
"""
Find matching Lichess team battle arenas for Elite Chess Players' Union.

Criteria:
- Team battle arena involving Elite Chess Players' Union
- Finished tournament
- 3+0 time control
- 12 hour duration
- Elite Chess Players' Union ranked 1st
- Elite Chess Players' Union scored at least 2000 points
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BASE_URL = "https://lichess.org"
DEFAULT_TEAM_ID = "--elite-chess-players-union--"
DEFAULT_TEAM_NAME = "Elite Chess Players' Union"
DEFAULT_MAX_TOURNAMENTS = 100_000
DEFAULT_SLEEP_SECONDS = 1.0


@dataclass(frozen=True)
class Match:
    started_at: datetime
    tournament_id: str
    name: str
    url: str
    score: int
    rank: int
    players: int | None
    nb_leaders: int | None


def utc_from_millis(value: int) -> datetime:
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc)


def request_json_or_text(
    url: str,
    *,
    token: str | None,
    accept: str,
    retries: int,
    timeout: int,
) -> str:
    headers = {
        "Accept": accept,
        "User-Agent": "ecpu-team-battle-scanner/1.0 (+https://lichess.org/api)",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    for attempt in range(retries + 1):
        request = Request(url, headers=headers)
        try:
            with urlopen(request, timeout=timeout) as response:
                return response.read().decode("utf-8")
        except HTTPError as error:
            if error.code == 429 and attempt < retries:
                retry_after = error.headers.get("Retry-After")
                delay = int(retry_after) if retry_after and retry_after.isdigit() else 60
                print(f"Rate limited by Lichess; sleeping {delay}s", file=sys.stderr)
                time.sleep(delay)
                continue
            raise
        except URLError:
            if attempt >= retries:
                raise
            delay = min(60, 2 ** attempt)
            print(f"Network error; retrying in {delay}s", file=sys.stderr)
            time.sleep(delay)

    raise RuntimeError(f"Exhausted retries for {url}")


def fetch_team_arenas(
    team_id: str,
    *,
    max_tournaments: int,
    token: str | None,
    retries: int,
    timeout: int,
) -> list[dict[str, Any]]:
    params = urlencode({"max": max_tournaments})
    url = f"{BASE_URL}/api/team/{team_id}/arena?{params}"
    body = request_json_or_text(
        url,
        token=token,
        accept="application/x-ndjson",
        retries=retries,
        timeout=timeout,
    )

    tournaments: list[dict[str, Any]] = []
    for line_number, line in enumerate(body.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            tournaments.append(json.loads(line))
        except json.JSONDecodeError as error:
            raise ValueError(f"Invalid NDJSON on line {line_number}: {error}") from error
    return tournaments


def fetch_team_standings(
    tournament_id: str,
    *,
    token: str | None,
    retries: int,
    timeout: int,
) -> dict[str, Any]:
    url = f"{BASE_URL}/api/tournament/{tournament_id}/teams"
    body = request_json_or_text(
        url,
        token=token,
        accept="application/json",
        retries=retries,
        timeout=timeout,
    )
    return json.loads(body)


def is_finished(tournament: dict[str, Any], now: datetime) -> bool:
    finishes_at = tournament.get("finishesAt")
    if not isinstance(finishes_at, int):
        return False
    return utc_from_millis(finishes_at) <= now


def matches_basic_filters(tournament: dict[str, Any], team_id: str, now: datetime) -> bool:
    if tournament.get("system") != "arena":
        return False
    if tournament.get("minutes") != 720:
        return False

    clock = tournament.get("clock") or {}
    if clock.get("limit") != 180 or clock.get("increment") != 0:
        return False

    teams = ((tournament.get("teamBattle") or {}).get("teams") or [])
    if team_id not in teams:
        return False

    return is_finished(tournament, now)


def find_team_row(standings: dict[str, Any], team_id: str) -> dict[str, Any] | None:
    for team in standings.get("teams", []):
        if team.get("id") == team_id:
            return team
    return None


def tournament_to_match(tournament: dict[str, Any], team_row: dict[str, Any]) -> Match:
    tournament_id = tournament["id"]
    return Match(
        started_at=utc_from_millis(tournament["startsAt"]),
        tournament_id=tournament_id,
        name=tournament.get("fullName") or tournament_id,
        url=f"{BASE_URL}/tournament/{tournament_id}",
        score=int(team_row["score"]),
        rank=int(team_row["rank"]),
        players=tournament.get("nbPlayers"),
        nb_leaders=(tournament.get("teamBattle") or {}).get("nbLeaders"),
    )


def scan(args: argparse.Namespace) -> tuple[list[Match], dict[str, int]]:
    token = args.token or os.getenv("LICHESS_TOKEN")
    now = datetime.now(timezone.utc)

    tournaments = fetch_team_arenas(
        args.team_id,
        max_tournaments=args.max_tournaments,
        token=token,
        retries=args.retries,
        timeout=args.timeout,
    )

    stats = {
        "arenas_seen": len(tournaments),
        "basic_filter_candidates": 0,
        "standings_checked": 0,
        "matches": 0,
    }
    matches: list[Match] = []

    for tournament in tournaments:
        if not matches_basic_filters(tournament, args.team_id, now):
            continue

        stats["basic_filter_candidates"] += 1
        standings = fetch_team_standings(
            tournament["id"],
            token=token,
            retries=args.retries,
            timeout=args.timeout,
        )
        stats["standings_checked"] += 1

        team_row = find_team_row(standings, args.team_id)
        if team_row and team_row.get("rank") == 1 and int(team_row.get("score", 0)) >= args.min_score:
            matches.append(tournament_to_match(tournament, team_row))

        if args.sleep_seconds > 0:
            time.sleep(args.sleep_seconds)

    matches.sort(key=lambda match: match.started_at)
    stats["matches"] = len(matches)
    return matches, stats


def write_json(matches: list[Match], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(
            [
                {
                    "started_at": match.started_at.isoformat(),
                    "tournament_id": match.tournament_id,
                    "name": match.name,
                    "url": match.url,
                    "rank": match.rank,
                    "score": match.score,
                    "players": match.players,
                    "nb_leaders": match.nb_leaders,
                }
                for match in matches
            ],
            file,
            indent=2,
        )
        file.write("\n")


def write_csv(matches: list[Match], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "started_at",
                "tournament_id",
                "name",
                "url",
                "rank",
                "score",
                "players",
                "nb_leaders",
            ],
        )
        writer.writeheader()
        for match in matches:
            writer.writerow(
                {
                    "started_at": match.started_at.isoformat(),
                    "tournament_id": match.tournament_id,
                    "name": match.name,
                    "url": match.url,
                    "rank": match.rank,
                    "score": match.score,
                    "players": match.players,
                    "nb_leaders": match.nb_leaders,
                }
            )


def write_markdown(
    matches: list[Match],
    output_path: Path,
    *,
    team_name: str,
    team_id: str,
    stats: dict[str, int],
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).isoformat()

    lines = [
        f"# {team_name}: Matching 3+0 12-hour team battles",
        "",
        f"Generated at: `{generated_at}`",
        f"Team: [{team_name}]({BASE_URL}/team/{team_id})",
        "",
        "Criteria: finished Arena team battle, 3+0, 12 hours, team rank 1, team score >= 2000.",
        "",
        f"Scanned arenas: `{stats['arenas_seen']}`",
        f"Candidate standings checked: `{stats['standings_checked']}`",
        f"Matches: `{stats['matches']}`",
        "",
    ]

    if not matches:
        lines.append("No matching tournaments found.")
    else:
        lines.extend(
            [
                "| Date (UTC) | Tournament | Score | Rank | Players | Leaders |",
                "| --- | --- | ---: | ---: | ---: | ---: |",
            ]
        )
        for match in matches:
            date = match.started_at.strftime("%Y-%m-%d %H:%M")
            players = "" if match.players is None else str(match.players)
            nb_leaders = "" if match.nb_leaders is None else str(match.nb_leaders)
            safe_name = match.name.replace("|", "\\|")
            lines.append(
                f"| {date} | [{safe_name}]({match.url}) | {match.score} | {match.rank} | {players} | {nb_leaders} |"
            )

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def print_summary(matches: list[Match], stats: dict[str, int]) -> None:
    print(
        f"Scanned {stats['arenas_seen']} arenas; "
        f"checked standings for {stats['standings_checked']} candidates; "
        f"found {stats['matches']} matches."
    )
    for match in matches:
        print(f"{match.started_at.date()} | {match.score} pts | {match.name} | {match.url}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scan Lichess team battle history for Elite Chess Players' Union 3+0 12-hour wins with 2000+ points."
    )
    parser.add_argument("--team-id", default=DEFAULT_TEAM_ID)
    parser.add_argument("--team-name", default=DEFAULT_TEAM_NAME)
    parser.add_argument("--max-tournaments", type=int, default=DEFAULT_MAX_TOURNAMENTS)
    parser.add_argument("--min-score", type=int, default=2000)
    parser.add_argument("--sleep-seconds", type=float, default=DEFAULT_SLEEP_SECONDS)
    parser.add_argument("--retries", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--token", default=None, help="Optional Lichess API token. Defaults to LICHESS_TOKEN.")
    parser.add_argument("--markdown", type=Path, default=Path("output/matches.md"))
    parser.add_argument("--csv", type=Path, default=Path("output/matches.csv"))
    parser.add_argument("--json", type=Path, default=Path("output/matches.json"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        matches, stats = scan(args)
    except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError) as error:
        print(f"Scan failed: {error}", file=sys.stderr)
        return 1

    write_markdown(matches, args.markdown, team_name=args.team_name, team_id=args.team_id, stats=stats)
    write_csv(matches, args.csv)
    write_json(matches, args.json)
    print_summary(matches, stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
