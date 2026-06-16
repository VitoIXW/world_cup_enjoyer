#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import urllib.parse
from urllib.request import Request, urlopen

from fifa_upcoming_matches import (
    DEFAULT_TIMEZONE,
    fetch_matches,
    get_season_metadata,
    render_telegram_message,
    filter_upcoming_matches,
)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SUBSCRIBERS_FILE = DATA_DIR / "telegram_subscribers.json"
STATE_FILE = DATA_DIR / "telegram_state.json"


def telegram_api_request(token: str, method: str, payload: dict | None = None) -> dict:
    encoded_payload = None
    if payload is not None:
        encoded_payload = urllib.parse.urlencode(payload).encode()

    request = Request(
        f"https://api.telegram.org/bot{token}/{method}",
        data=encoded_payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST" if encoded_payload is not None else "GET",
    )
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def send_telegram_message(token: str, chat_id: str, text: str) -> dict:
    return telegram_api_request(
        token,
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
        },
    )


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def load_json_file(path: Path, default: dict) -> dict:
    if not path.exists():
        return default
    return json.loads(path.read_text())


def save_json_file(path: Path, payload: dict) -> None:
    ensure_data_dir()
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def load_subscribers() -> dict:
    return load_json_file(SUBSCRIBERS_FILE, {"subscribers": []})


def save_subscribers(payload: dict) -> None:
    save_json_file(SUBSCRIBERS_FILE, payload)


def load_state() -> dict:
    return load_json_file(STATE_FILE, {"last_update_id": 0})


def save_state(payload: dict) -> None:
    save_json_file(STATE_FILE, payload)


def upsert_subscriber(subscribers: dict, chat_id: str, name: str, username: str | None, enabled: bool) -> None:
    items = subscribers.setdefault("subscribers", [])
    for item in items:
        if str(item["chat_id"]) == str(chat_id):
            item["name"] = name
            item["username"] = username
            item["enabled"] = enabled
            item["updated_at"] = datetime.now(timezone.utc).isoformat()
            return

    items.append(
        {
            "chat_id": str(chat_id),
            "name": name,
            "username": username,
            "enabled": enabled,
            "source": "telegram",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    )


def seed_primary_chat(subscribers: dict, chat_id: str) -> None:
    if not chat_id:
        return
    upsert_subscriber(
        subscribers,
        chat_id=chat_id,
        name="Primary chat",
        username=None,
        enabled=True,
    )


def fetch_updates(token: str, offset: int) -> list[dict]:
    response = telegram_api_request(
        token,
        "getUpdates",
        {"offset": offset, "timeout": 0, "allowed_updates": json.dumps(["message"])},
    )
    return response.get("result", [])


def sync_subscribers_from_updates(token: str, subscribers: dict, state: dict) -> tuple[dict, dict, int]:
    updates = fetch_updates(token, int(state.get("last_update_id", 0)) + 1)
    added_or_updated = 0
    last_update_id = int(state.get("last_update_id", 0))

    for update in updates:
        last_update_id = max(last_update_id, update.get("update_id", 0))
        message = update.get("message") or {}
        text = (message.get("text") or "").strip()
        chat = message.get("chat") or {}
        chat_id = chat.get("id")
        if not chat_id:
            continue

        first_name = chat.get("first_name") or ""
        last_name = chat.get("last_name") or ""
        full_name = " ".join(part for part in [first_name, last_name] if part) or chat.get("title") or "Unknown"
        username = chat.get("username")

        if text.startswith("/start"):
            upsert_subscriber(subscribers, str(chat_id), full_name, username, True)
            added_or_updated += 1
        elif text.startswith("/stop"):
            upsert_subscriber(subscribers, str(chat_id), full_name, username, False)
            added_or_updated += 1

    state["last_update_id"] = last_update_id
    return subscribers, state, added_or_updated


def enabled_chat_ids(subscribers: dict) -> list[str]:
    return [
        str(item["chat_id"])
        for item in subscribers.get("subscribers", [])
        if item.get("enabled")
    ]


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

    subscribers = load_subscribers()
    seed_primary_chat(subscribers, chat_id)
    state = load_state()
    subscribers, state, synced = sync_subscribers_from_updates(token, subscribers, state)
    save_subscribers(subscribers)
    save_state(state)

    recipients = enabled_chat_ids(subscribers)
    if not recipients:
        raise RuntimeError(
            "No hay chats activos. Define TELEGRAM_CHAT_ID o escribe /start al bot."
        )

    print(f"Suscriptores sincronizados: {synced}")
    print(f"Destinatarios activos: {len(recipients)}")

    for recipient in recipients:
        result = send_telegram_message(token, recipient, message)
        print(f"Mensaje enviado a chat_id={recipient}")
        print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
