#!/usr/bin/env python3
from __future__ import annotations

import argparse
import io
import math
import os
from functools import lru_cache
from pathlib import Path
from urllib.request import Request, urlopen

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from fifa_upcoming_matches import (
    DEFAULT_TIMEZONE,
    fetch_matches,
    filter_upcoming_matches,
    format_local_day,
    format_local_time,
    get_season_metadata,
    split_matches_by_local_day,
)


WIDTH = 1024
PADDING_X = 22
TOP_PADDING = 18
BOTTOM_PADDING = 36
HEADER_HEIGHT = 286
DAY_BANNER_HEIGHT = 64
DAY_BANNER_GAP = 18
MATCH_CARD_HEIGHT = 246
MATCH_CARD_GAP = 18
TIME_BOX_WIDTH = 198
RESAMPLE_LANCZOS = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
HEADER_CUP_PATH = Path(__file__).resolve().parent.parent / "tmp" / "copa.png"
STADIUM_BG_PATH = Path(__file__).resolve().parent.parent / "tmp" / "estadio.jpg"


COLORS = {
    "bg_top": "#071223",
    "bg_mid": "#0d223b",
    "bg_bottom": "#0f3210",
    "panel": "#081019",
    "panel2": "#0a1420",
    "panel_border": "#7f8da0",
    "gold": "#f0c25b",
    "gold_deep": "#b6811f",
    "blue": "#153e91",
    "blue_dark": "#0a2256",
    "green": "#238711",
    "green_dark": "#105807",
    "white": "#f7f7f3",
    "muted": "#c9d4de",
    "soft_line": "#44505f",
}


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = []
    if bold:
        candidates.extend(
            [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
            ]
        )
    else:
        candidates.extend(
            [
                "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed.ttf",
                "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
            ]
        )

    for candidate in candidates:
        if os.path.exists(candidate):
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


FONT_TITLE = load_font(52, bold=True)
FONT_SUBTITLE = load_font(26, bold=True)
FONT_META = load_font(19)
FONT_DAY = load_font(30, bold=True)
FONT_TIME = load_font(40, bold=True)
FONT_CITY = load_font(22, bold=True)
FONT_STADIUM = load_font(18)
FONT_TEAM = load_font(44, bold=True)
FONT_GROUP = load_font(20, bold=True)
FONT_VS = load_font(52, bold=True)
FONT_FOOTER = load_font(19, bold=True)


def text_size(draw: ImageDraw.ImageDraw, text: str, font) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0], box[3] - box[1]


def centered_text(draw: ImageDraw.ImageDraw, x: int, y: int, text: str, font, fill: str) -> None:
    w, h = text_size(draw, text, font)
    draw.text((x - w / 2, y - h / 2), text, font=font, fill=fill)


def fit_font(draw: ImageDraw.ImageDraw, text: str, max_width: int, start_size: int) -> ImageFont.ImageFont:
    size = start_size
    while size >= 22:
        font = load_font(size, bold=True)
        width, _ = text_size(draw, text, font)
        if width <= max_width:
            return font
        size -= 2
    return load_font(22, bold=True)


def create_base(height: int) -> Image.Image:
    image = Image.new("RGBA", (WIDTH, height), COLORS["bg_top"])
    draw = ImageDraw.Draw(image)

    stadium_bg = load_stadium_background()
    if stadium_bg is not None:
        bg = build_header_background(stadium_bg, height)
        image.alpha_composite(bg)
    else:
        for y in range(height):
            t = y / max(1, height - 1)
            if t < 0.6:
                factor = t / 0.6
                color = blend(COLORS["bg_top"], COLORS["bg_mid"], factor)
            else:
                factor = (t - 0.6) / 0.4
                color = blend(COLORS["bg_mid"], COLORS["bg_bottom"], factor)
            draw.line((0, y, WIDTH, y), fill=color)

    add_stadium_lights(image)
    add_grass(image, height)
    return image


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))


def blend(a: str, b: str, t: float) -> tuple[int, int, int]:
    ar, ag, ab = hex_to_rgb(a)
    br, bg, bb = hex_to_rgb(b)
    return (
        int(ar + (br - ar) * t),
        int(ag + (bg - ag) * t),
        int(ab + (bb - ab) * t),
    )


def add_stadium_lights(image: Image.Image) -> None:
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    for side in ("left", "right"):
        center_x = 110 if side == "left" else WIDTH - 110
        for i in range(10):
            y = 42 + i * 12
            radius = 40 - i
            draw.ellipse(
                (center_x - radius, y - radius, center_x + radius, y + radius),
                fill=(255, 246, 220, max(18, 90 - i * 7)),
            )

    draw.arc((10, 28, WIDTH - 10, 360), start=192, end=348, fill=(255, 255, 255, 55), width=8)
    draw.arc((42, 44, WIDTH - 42, 378), start=194, end=346, fill=(255, 255, 255, 32), width=4)
    blurred = overlay.filter(ImageFilter.GaussianBlur(8))
    image.alpha_composite(blurred)


def add_grass(image: Image.Image, height: int) -> None:
    stadium_bg = load_stadium_background()
    if stadium_bg is not None:
        grass = stadium_bg.crop((0, int(stadium_bg.height * 0.68), stadium_bg.width, stadium_bg.height))
        grass = resize_cover(grass, WIDTH, max(220, height - int(height * 0.82)))
        overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
        overlay.alpha_composite(grass, (0, height - grass.height))
        dark = Image.new("RGBA", (WIDTH, grass.height), (12, 40, 8, 92))
        overlay.alpha_composite(dark, (0, height - grass.height))
        image.alpha_composite(overlay)
        return

    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    top = int(height * 0.82)
    draw.rectangle((0, top, WIDTH, height), fill=(31, 86, 12, 255))
    for x in range(0, WIDTH, 4):
        draw.line((x, top, x + 12, height), fill=(73, 145, 32, 80), width=1)
    overlay = overlay.filter(ImageFilter.GaussianBlur(0.5))
    image.alpha_composite(overlay)


@lru_cache(maxsize=1)
def load_stadium_background() -> Image.Image | None:
    if not STADIUM_BG_PATH.exists():
        return None
    try:
        return Image.open(STADIUM_BG_PATH).convert("RGBA")
    except Exception:
        return None


@lru_cache(maxsize=1)
def load_cup_asset() -> Image.Image | None:
    if not HEADER_CUP_PATH.exists():
        return None
    try:
        image = Image.open(HEADER_CUP_PATH).convert("RGBA")
        pixels = image.load()
        for y in range(image.height):
            for x in range(image.width):
                r, g, b, a = pixels[x, y]
                if r < 20 and g < 20 and b < 20:
                    pixels[x, y] = (0, 0, 0, 0)
        return image
    except Exception:
        return None


def build_header_background(stadium_bg: Image.Image, height: int) -> Image.Image:
    canvas = Image.new("RGBA", (WIDTH, height), COLORS["bg_top"])

    top_slice = stadium_bg.crop((0, 0, stadium_bg.width, stadium_bg.height))
    top_bg = resize_cover(top_slice, WIDTH, max(520, int(height * 0.42)))
    top_bg = top_bg.filter(ImageFilter.GaussianBlur(7))
    top_tint = Image.new("RGBA", top_bg.size, (4, 14, 30, 130))
    top_bg.alpha_composite(top_tint)
    canvas.alpha_composite(top_bg, (0, 0))

    mid_overlay = Image.new("RGBA", (WIDTH, height), (5, 14, 28, 118))
    canvas.alpha_composite(mid_overlay)

    return canvas


def add_ball(image: Image.Image, height: int) -> None:
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    cx, cy = WIDTH - 70, height - 58
    r = 86
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(236, 237, 239, 255), outline=(180, 185, 190, 255), width=4)
    for dx, dy, rr in [(-28, -22, 20), (18, -8, 22), (-2, 24, 18)]:
        draw.polygon(
            [
                (cx + dx, cy + dy - rr),
                (cx + dx + rr, cy + dy - rr // 3),
                (cx + dx + rr // 2, cy + dy + rr),
                (cx + dx - rr // 2, cy + dy + rr),
                (cx + dx - rr, cy + dy - rr // 3),
            ],
            fill=(20, 24, 30, 220),
        )
    image.alpha_composite(overlay)


@lru_cache(maxsize=64)
def fetch_remote_image(url: str) -> Image.Image | None:
    if not url:
        return None
    request = Request(url, headers={"User-Agent": "world-cup-enjoyer/0.1"})
    try:
        with urlopen(request, timeout=30) as response:
            return Image.open(io.BytesIO(response.read())).convert("RGBA")
    except Exception:
        return None


def fit_flag(country_code: str | None, size: tuple[int, int]) -> Image.Image | None:
    if not country_code:
        return None
    url = f"https://api.fifa.com/api/v3/picture/flags-sq-4/{country_code.upper()}"
    image = fetch_remote_image(url)
    if image is None:
        return None
    return resize_cover(image, *size)


def resize_cover(image: Image.Image, width: int, height: int) -> Image.Image:
    scale = max(width / image.width, height / image.height)
    new_size = (max(1, int(image.width * scale)), max(1, int(image.height * scale)))
    resized = image.resize(new_size, RESAMPLE_LANCZOS)
    left = (resized.width - width) // 2
    top = (resized.height - height) // 2
    return resized.crop((left, top, left + width, top + height))


def rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, size[0], size[1]), radius=radius, fill=255)
    return mask


def paste_round(base: Image.Image, item: Image.Image, xy: tuple[int, int], radius: int) -> None:
    mask = rounded_mask(item.size, radius)
    base.paste(item, xy, mask)


def card_shadow(base: Image.Image, box: tuple[int, int, int, int], radius: int) -> None:
    shadow = Image.new("RGBA", (box[2] - box[0] + 22, box[3] - box[1] + 22), (0, 0, 0, 0))
    draw = ImageDraw.Draw(shadow)
    draw.rounded_rectangle((10, 10, shadow.width - 10, shadow.height - 10), radius=radius, fill=(0, 0, 0, 95))
    shadow = shadow.filter(ImageFilter.GaussianBlur(12))
    base.alpha_composite(shadow, (box[0] - 8, box[1] - 2))


def draw_header(base: Image.Image, draw: ImageDraw.ImageDraw, hours: int, timezone_name: str) -> None:
    header_crop = Image.new("RGBA", (WIDTH - 48, 210), (0, 0, 0, 0))
    stadium_bg = load_stadium_background()
    if stadium_bg is not None:
        header_crop = resize_cover(stadium_bg, WIDTH - 48, 210)
        header_crop = header_crop.filter(ImageFilter.GaussianBlur(4))
        overlay = Image.new("RGBA", header_crop.size, (5, 15, 28, 88))
        header_crop.alpha_composite(overlay)
    paste_round(base, header_crop, (24, 18), 28)
    draw.rounded_rectangle((24, 18, WIDTH - 24, 228), radius=28, outline=(255, 255, 255, 26), width=1)

    cup = load_cup_asset()
    if cup is not None:
        cup = resize_cover(cup, 156, 156)
        shadow = Image.new("RGBA", cup.size, (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow)
        shadow_draw.ellipse((20, 118, 138, 150), fill=(0, 0, 0, 95))
        shadow = shadow.filter(ImageFilter.GaussianBlur(12))
        base.alpha_composite(shadow, (72, 52))
        base.alpha_composite(cup, (70, 30))

    draw.text((230, 34), "MUNDIAL 2026", font=FONT_TITLE, fill=COLORS["white"])
    draw.text((290, 106), "PRÓXIMOS PARTIDOS", font=FONT_SUBTITLE, fill=COLORS["gold"])

    pill_left = (68, 188, 414, 240)
    pill_right = (598, 188, 960, 240)
    draw_pill(draw, pill_left, "VENTANA: PRÓXIMAS 24H")
    draw_pill(draw, pill_right, f"HORARIO: {timezone_name.upper()}")


def draw_pill(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], text: str) -> None:
    draw.rounded_rectangle(box, radius=19, outline=(215, 189, 126, 200), fill=(13, 17, 24, 190), width=2)
    draw.text((box[0] + 18, box[1] + 12), text, font=FONT_META, fill=COLORS["white"])


def draw_day_banner(base: Image.Image, draw: ImageDraw.ImageDraw, y: int, label: str, color: str) -> int:
    left = 246
    right = WIDTH - 324
    poly = [
        (left, y + DAY_BANNER_HEIGHT),
        (left + 46, y),
        (right + 34, y),
        (right, y + DAY_BANNER_HEIGHT),
    ]
    draw.polygon(poly, fill=color, outline=(140, 168, 224, 120))
    draw.line((24, y + DAY_BANNER_HEIGHT // 2, left + 8, y + DAY_BANNER_HEIGHT // 2), fill=(255, 255, 255, 130), width=1)
    draw.line((right - 8, y + DAY_BANNER_HEIGHT // 2, WIDTH - 24, y + DAY_BANNER_HEIGHT // 2), fill=(255, 255, 255, 130), width=1)
    centered_text(draw, (left + right) // 2, y + DAY_BANNER_HEIGHT // 2 - 2, label.upper(), FONT_DAY, COLORS["white"])
    return y + DAY_BANNER_HEIGHT + DAY_BANNER_GAP


def draw_match_card(base: Image.Image, draw: ImageDraw.ImageDraw, y: int, match, accent_color: str) -> int:
    box = (22, y, WIDTH - 22, y + MATCH_CARD_HEIGHT)
    card_shadow(base, box, 28)
    draw.rounded_rectangle(box, radius=30, fill=(6, 14, 20, 228), outline=(163, 183, 215, 120), width=2)

    time_box = (42, y + 30, 42 + TIME_BOX_WIDTH, y + MATCH_CARD_HEIGHT - 30)
    draw.rounded_rectangle(time_box, radius=22, fill=(10, 24, 34, 205), outline=(58, 93, 139, 140), width=1)
    time_chip = (58, y + 48, 208, y + 120)
    draw.rounded_rectangle(time_chip, radius=16, fill=accent_color)
    centered_text(draw, (time_chip[0] + time_chip[2]) // 2, (time_chip[1] + time_chip[3]) // 2 - 2, format_local_time(match.local_date), FONT_TIME, COLORS["white"])

    draw_location_icon(draw, 141, y + 148)

    city_font = load_font(16, bold=True)
    stadium_font = load_font(14)
    city_lines = wrap_multiline(draw, (match.city or "").upper(), city_font, 154, 2)
    city_y = y + 180
    for line in city_lines:
        centered_text(draw, 141, city_y, line, city_font, COLORS["white"])
        city_y += 20

    stadium_lines = wrap_multiline(draw, (match.stadium or "").upper(), stadium_font, 154, 2)
    stadium_y = y + 226
    for line in stadium_lines:
        centered_text(draw, 141, stadium_y, line, stadium_font, COLORS["white"])
        stadium_y += 18

    inner_left = 242
    inner_right = WIDTH - 42
    inner_box = (inner_left, y + 10, inner_right, y + MATCH_CARD_HEIGHT - 10)
    draw.rounded_rectangle(inner_box, radius=24, fill=(4, 10, 16, 125), outline=(255, 214, 137, 90), width=1)

    flag_w, flag_h = 176, 122
    left_flag = fit_flag(match.home_country, (flag_w, flag_h))
    right_flag = fit_flag(match.away_country, (flag_w, flag_h))
    if left_flag:
        paste_round(base, left_flag, (302, y + 42), 18)
    if right_flag:
        paste_round(base, right_flag, (722, y + 42), 18)

    centered_text(draw, 580, y + 110, "VS", FONT_VS, COLORS["gold"])

    team_font_left = fit_font(draw, (match.home_team or "").upper(), 240, 44)
    team_font_right = fit_font(draw, (match.away_team or "").upper(), 240, 44)
    centered_text(draw, 390, y + 188, (match.home_team or "").upper(), team_font_left, COLORS["white"])
    centered_text(draw, 810, y + 188, (match.away_team or "").upper(), team_font_right, COLORS["white"])

    group_text = (match.group or match.stage).upper()
    group_box = (510, y + 168, 650, y + 206)
    draw.rounded_rectangle(group_box, radius=14, outline=hex_to_rgb(accent_color) + (255,), fill=(2, 9, 15, 150), width=2)
    centered_text(draw, (group_box[0] + group_box[2]) // 2, (group_box[1] + group_box[3]) // 2 - 1, group_text, FONT_GROUP, COLORS["white"])

    dot_y = y + MATCH_CARD_HEIGHT - 6
    draw.line((486, dot_y, 560, dot_y), fill=(214, 211, 204, 110), width=1)
    draw.line((598, dot_y, 672, dot_y), fill=(214, 211, 204, 110), width=1)
    draw.ellipse((575, dot_y - 4, 583, dot_y + 4), fill=(214, 211, 204, 160))

    return y + MATCH_CARD_HEIGHT + MATCH_CARD_GAP


def draw_location_icon(draw: ImageDraw.ImageDraw, x: int, y: int) -> None:
    draw.ellipse((x - 9, y - 18, x + 9, y), outline=COLORS["white"], width=3)
    draw.polygon([(x, y + 14), (x - 8, y - 2), (x + 8, y - 2)], fill=COLORS["white"])


def wrap_multiline(draw: ImageDraw.ImageDraw, text: str, font, max_width: int, max_lines: int) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    lines = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        width, _ = text_size(draw, candidate, font)
        if width <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
            if len(lines) == max_lines - 1:
                break
    remaining = current if len(lines) < max_lines else current
    lines.append(remaining)
    return lines[:max_lines]


def build_image(matches, hours: int, timezone_name: str, header_image_url: str | None = None) -> Image.Image:
    groups = split_matches_by_local_day(matches)
    total_matches = sum(len(day_matches) for _, day_matches in groups)
    height = TOP_PADDING + HEADER_HEIGHT + 36
    height += len(groups) * (DAY_BANNER_HEIGHT + DAY_BANNER_GAP)
    height += total_matches * (MATCH_CARD_HEIGHT + MATCH_CARD_GAP)
    height += 92 + BOTTOM_PADDING

    base = create_base(height)
    draw = ImageDraw.Draw(base)
    draw_header(base, draw, hours, timezone_name)

    cursor_y = TOP_PADDING + HEADER_HEIGHT + 26
    day_colors = [COLORS["blue"], COLORS["green"]]
    for index, (day_label, day_matches) in enumerate(groups):
        accent = day_colors[index % len(day_colors)]
        cursor_y = draw_day_banner(base, draw, cursor_y, day_label, accent)
        card_accent = "#0d3f91" if accent == COLORS["blue"] else "#19780e"
        for match in day_matches:
            cursor_y = draw_match_card(base, draw, cursor_y, match, card_accent)

    footer_box = (216, height - 76, WIDTH - 216, height - 22)
    draw.rounded_rectangle(footer_box, radius=20, fill=(9, 17, 24, 198), outline=(255, 255, 255, 50), width=1)
    centered_text(draw, (footer_box[0] + footer_box[2]) // 2, (footer_box[1] + footer_box[3]) // 2, f"HORARIO MOSTRADO: {timezone_name.upper()}", FONT_FOOTER, COLORS["white"])
    add_ball(base, height)
    return base.convert("RGB")


def main() -> int:
    parser = argparse.ArgumentParser(description="Genera un PNG vertical con estilo poster para los próximos partidos.")
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--timezone", default=DEFAULT_TIMEZONE)
    parser.add_argument("--output", default="/tmp/world_cup_matches.png")
    args = parser.parse_args()

    metadata = get_season_metadata()
    matches = fetch_matches(metadata["season_id"])
    upcoming = filter_upcoming_matches(matches, args.hours, args.timezone)
    image = build_image(upcoming, args.hours, args.timezone, header_image_url=metadata.get("page", {}).get("meta", {}).get("image"))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, format="PNG")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
