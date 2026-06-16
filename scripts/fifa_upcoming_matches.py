#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


FIFA_BASE = "https://www.fifa.com"
CXM_API_BASE = "https://cxm-api.fifa.com/fifaplusweb/api/"
CALENDAR_API_BASE = "https://api.fifa.com/api/v3/"
SCORES_FIXTURES_PATH = (
    "pages/es/tournaments/mens/worldcup/canadamexicousa2026/scores-fixtures"
)
DEFAULT_TIMEZONE = "Europe/Madrid"
WEEKDAY_NAMES_ES = {
    0: "Lunes",
    1: "Martes",
    2: "Miércoles",
    3: "Jueves",
    4: "Viernes",
    5: "Sábado",
    6: "Domingo",
}
FIFA_COUNTRY_TO_ISO2 = {
    "ALG": "DZ",
    "ARG": "AR",
    "AUS": "AU",
    "AUT": "AT",
    "BEL": "BE",
    "BIH": "BA",
    "BRA": "BR",
    "CAN": "CA",
    "CPV": "CV",
    "COD": "CD",
    "CIV": "CI",
    "COL": "CO",
    "CRC": "CR",
    "CRO": "HR",
    "CUW": "CW",
    "CZE": "CZ",
    "ECU": "EC",
    "EGY": "EG",
    "ENG": "GB",
    "ESP": "ES",
    "FRA": "FR",
    "GER": "DE",
    "GHA": "GH",
    "HAI": "HT",
    "IRN": "IR",
    "IRQ": "IQ",
    "JOR": "JO",
    "JPN": "JP",
    "KOR": "KR",
    "MAR": "MA",
    "MEX": "MX",
    "NED": "NL",
    "NOR": "NO",
    "NZL": "NZ",
    "PAN": "PA",
    "PAR": "PY",
    "POR": "PT",
    "QAT": "QA",
    "RSA": "ZA",
    "SCO": "GB",
    "SEN": "SN",
    "SUI": "CH",
    "SWE": "SE",
    "TUN": "TN",
    "TUR": "TR",
    "URU": "UY",
    "USA": "US",
    "UZB": "UZ",
}


@dataclass
class MatchSummary:
    match_id: str
    utc_date: str
    local_date: str
    stage: str
    group: str | None
    home_country: str | None
    away_country: str | None
    home_team: str
    away_team: str
    stadium: str | None
    city: str | None
    status: int | None
    home_score: int | None
    away_score: int | None


def fetch_json(url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    full_url = url
    if params:
        full_url = f"{url}?{urlencode(params)}"

    request = Request(
        full_url,
        headers={
            "User-Agent": "world-cup-enjoyer/0.1",
            "Accept": "application/json",
        },
    )
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def extract_where_to_watch_endpoint(page_data: dict[str, Any]) -> str:
    for section in page_data.get("sections", []):
        if section.get("entryType") == "whereToWatch":
            endpoint = section.get("entryEndpoint")
            if endpoint:
                return endpoint.lstrip("/")
    raise RuntimeError("No encontré la sección whereToWatch en la página de FIFA.")


def get_season_metadata() -> dict[str, Any]:
    page_data = fetch_json(urljoin(CXM_API_BASE, SCORES_FIXTURES_PATH))
    endpoint = extract_where_to_watch_endpoint(page_data)
    section_data = fetch_json(urljoin(CXM_API_BASE, endpoint))
    return {
        "page": page_data,
        "where_to_watch": section_data,
        "season_id": section_data["seasonId"],
        "country_code": section_data.get("userCountryCode"),
    }


def parse_team(team: dict[str, Any]) -> str:
    names = team.get("TeamName") or []
    if names:
        return names[0].get("Description") or team.get("Abbreviation") or "TBD"
    return team.get("Abbreviation") or "TBD"


def country_flag_from_fifa_code(code: str | None) -> str:
    if not code:
        return ""
    iso2 = FIFA_COUNTRY_TO_ISO2.get(code.upper())
    if not iso2 or len(iso2) != 2:
        return ""
    return "".join(chr(127397 + ord(letter)) for letter in iso2.upper())


def parse_localized_first(items: list[dict[str, Any]] | None) -> str | None:
    if not items:
        return None
    return items[0].get("Description")


def fetch_matches(season_id: str, language: str = "es", count: int = 500) -> list[dict[str, Any]]:
    payload = fetch_json(
        urljoin(CALENDAR_API_BASE, "calendar/matches"),
        params={"language": language, "count": count, "idSeason": season_id},
    )
    return payload.get("Results", [])


def filter_upcoming_matches(
    matches: list[dict[str, Any]],
    hours: int,
    timezone_name: str = DEFAULT_TIMEZONE,
) -> list[MatchSummary]:
    now = datetime.now(timezone.utc)
    upper = now + timedelta(hours=hours)
    filtered: list[MatchSummary] = []
    local_tz = ZoneInfo(timezone_name)

    for match in matches:
        match_date = datetime.fromisoformat(match["Date"].replace("Z", "+00:00"))
        if not (now <= match_date <= upper):
            continue

        local_date = match_date.astimezone(local_tz)

        filtered.append(
            MatchSummary(
                match_id=match["IdMatch"],
                utc_date=match["Date"],
                local_date=local_date.isoformat(),
                stage=parse_localized_first(match.get("StageName")) or "Sin fase",
                group=parse_localized_first(match.get("GroupName")),
                home_country=(match.get("Home") or {}).get("IdCountry"),
                away_country=(match.get("Away") or {}).get("IdCountry"),
                home_team=parse_team(match.get("Home", {})),
                away_team=parse_team(match.get("Away", {})),
                stadium=parse_localized_first((match.get("Stadium") or {}).get("Name")),
                city=parse_localized_first((match.get("Stadium") or {}).get("CityName")),
                status=match.get("MatchStatus"),
                home_score=match.get("HomeTeamScore"),
                away_score=match.get("AwayTeamScore"),
            )
        )

    filtered.sort(key=lambda match: match.utc_date)
    return filtered


def format_local_kickoff(local_date: str) -> str:
    dt = datetime.fromisoformat(local_date)
    return dt.strftime("%Y-%m-%d %H:%M")


def format_local_day(local_date: str) -> str:
    dt = datetime.fromisoformat(local_date)
    return f"{WEEKDAY_NAMES_ES[dt.weekday()]} {dt.strftime('%d/%m')}"


def format_local_time(local_date: str) -> str:
    dt = datetime.fromisoformat(local_date)
    return dt.strftime("%H:%M")


def render_text(
    matches: list[MatchSummary],
    hours: int,
    timezone_name: str = DEFAULT_TIMEZONE,
) -> str:
    if not matches:
        return (
            f"No hay partidos entre ahora y las próximas {hours} horas "
            f"en horario de {timezone_name}."
        )

    lines = [f"Partidos del Mundial en las próximas {hours}h ({timezone_name}):"]
    for match in matches:
        location = ", ".join(part for part in [match.city, match.stadium] if part)
        phase = match.group or match.stage
        lines.append(
            f"- {format_local_kickoff(match.local_date)} | {match.home_team} vs {match.away_team} | {phase}"
            + (f" | {location}" if location else "")
        )
    return "\n".join(lines)


def render_telegram_message(
    matches: list[MatchSummary],
    hours: int,
    timezone_name: str = DEFAULT_TIMEZONE,
) -> str:
    if not matches:
        return (
            "🏆 *Próximos partidos del Mundial*\n"
            f"No hay partidos en las próximas *{hours}h*.\n"
            f"_Horario: {timezone_name}_"
        )

    lines = [
        "🏆 *Próximos partidos del Mundial*",
        f"Ventana: próximas *{hours}h*",
        f"_Horario mostrado: {timezone_name}_",
        "",
    ]

    current_day = None
    for match in matches:
        day_label = format_local_day(match.local_date)
        if day_label != current_day:
            if current_day is not None:
                lines.append("")
            lines.append(f"*{day_label}*")
            current_day = day_label

        phase = match.group or match.stage
        home_flag = country_flag_from_fifa_code(match.home_country)
        away_flag = country_flag_from_fifa_code(match.away_country)
        home_label = " ".join(part for part in [home_flag, match.home_team] if part)
        away_label = " ".join(part for part in [away_flag, match.away_team] if part)
        lines.append(
            f"• *{format_local_time(match.local_date)}*  {home_label} vs {away_label}"
        )
        lines.append(f"  {phase}")

        place_parts = [part for part in [match.city, match.stadium] if part]
        if place_parts:
            lines.append(f"  📍 {' - '.join(place_parts)}")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Consulta próximos partidos oficiales del Mundial desde FIFA.",
    )
    parser.add_argument("--hours", type=int, default=24, help="Ventana hacia adelante.")
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Formato de salida.",
    )
    parser.add_argument(
        "--timezone",
        default=DEFAULT_TIMEZONE,
        help="Zona horaria IANA para mostrar los partidos.",
    )
    args = parser.parse_args()

    metadata = get_season_metadata()
    matches = fetch_matches(metadata["season_id"])
    upcoming = filter_upcoming_matches(matches, args.hours, args.timezone)

    if args.format == "json":
        payload = {
            "source": {
                "page": f"{FIFA_BASE}/es/tournaments/mens/worldcup/canadamexicousa2026/scores-fixtures",
                "season_id": metadata["season_id"],
                "country_code": metadata["country_code"],
            },
            "window_hours": args.hours,
            "timezone": args.timezone,
            "matches": [match.__dict__ for match in upcoming],
        }
        json.dump(payload, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
        return 0

    print(render_text(upcoming, args.hours, args.timezone))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
