#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import urllib.parse
from urllib.request import Request, urlopen

from fifa_upcoming_matches import (
    DEFAULT_TIMEZONE,
    fetch_matches,
    get_season_metadata,
    render_telegram_message,
    filter_upcoming_matches,
)


def send_telegram_message(token: str, chat_id: str, text: str) -> dict:
    payload = urllib.parse.urlencode(
        {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
        }
    ).encode()
    request = Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Envía por Telegram los próximos partidos del Mundial.",
    )
    parser.add_argument("--hours", type=int, default=24, help="Ventana hacia adelante.")
    parser.add_argument(
        "--timezone",
        default=os.environ.get("WORLD_CUP_TIMEZONE", DEFAULT_TIMEZONE),
        help="Zona horaria IANA para mostrar los partidos.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="No envía a Telegram; solo imprime el mensaje.",
    )
    args = parser.parse_args()

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

    metadata = get_season_metadata()
    matches = fetch_matches(metadata["season_id"])
    upcoming = filter_upcoming_matches(matches, args.hours, args.timezone)
    message = render_telegram_message(upcoming, args.hours, args.timezone)

    if args.dry_run:
        print(message)
        return 0

    if not token:
        raise RuntimeError("Falta TELEGRAM_BOT_TOKEN en el entorno.")
    if not chat_id:
        raise RuntimeError("Falta TELEGRAM_CHAT_ID en el entorno.")

    result = send_telegram_message(token, chat_id, message)
    print(f"Mensaje enviado a chat_id={chat_id}")
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
