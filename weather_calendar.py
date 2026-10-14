#!/usr/bin/env python3
"""Weather -> calendar bridge.

Fetches daily forecasts from Open-Meteo (no API key) for configured cities
and writes iCalendar (.ics) files: one all-day event per city per day.
Import the .ics into a phone's built-in calendar, or serve the output
directory over HTTP and subscribe to it so the calendar refreshes itself.

Standard library only.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"
FORECAST_DAYS = 14

CITIES = [
    {"name": "东莞", "slug": "dongguan", "lat": 23.01797, "lon": 113.74866},
    {"name": "广州", "slug": "guangzhou", "lat": 23.11667, "lon": 113.25},
]

# WMO weather codes (Open-Meteo) -> (emoji, Chinese label)
WMO = {
    0: ("☀️", "晴"),
    1: ("🌤️", "大部晴"),
    2: ("⛅", "多云"),
    3: ("☁️", "阴"),
    45: ("🌫️", "雾"),
    48: ("🌫️", "雾凇"),
    51: ("🌦️", "毛毛雨"),
    53: ("🌦️", "毛毛雨"),
    55: ("🌦️", "毛毛雨"),
    56: ("🌧️", "冻毛毛雨"),
    57: ("🌧️", "冻毛毛雨"),
    61: ("🌧️", "小雨"),
    63: ("🌧️", "中雨"),
    65: ("🌧️", "大雨"),
    66: ("🌧️", "冻雨"),
    67: ("🌧️", "冻雨"),
    71: ("🌨️", "小雪"),
    73: ("🌨️", "中雪"),
    75: ("🌨️", "大雪"),
    77: ("🌨️", "雪粒"),
    80: ("🌦️", "阵雨"),
    81: ("🌦️", "阵雨"),
    82: ("🌦️", "暴雨阵雨"),
    85: ("🌨️", "阵雪"),
    86: ("🌨️", "阵雪"),
    95: ("⛈️", "雷阵雨"),
    96: ("⛈️", "雷阵雨伴冰雹"),
    99: ("⛈️", "雷阵雨伴冰雹"),
}


def weather_label(code) -> tuple[str, str]:
    return WMO.get(code, ("🌡️", f"天气代码{code}"))


def fetch_forecast(city: dict, days: int = FORECAST_DAYS, opener=None) -> dict:
    params = {
        "latitude": city["lat"],
        "longitude": city["lon"],
        "daily": ",".join([
            "weather_code", "temperature_2m_max", "temperature_2m_min",
            "precipitation_probability_max", "precipitation_sum",
            "wind_speed_10m_max", "sunrise", "sunset",
        ]),
        "timezone": "Asia/Shanghai",
        "forecast_days": days,
    }
    url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(params)
    open_fn = opener or (lambda u: urllib.request.urlopen(u, timeout=30))
    with open_fn(url) as resp:
        return json.load(resp)


def daily_rows(forecast: dict) -> list[dict]:
    daily = forecast.get("daily") or {}
    times = daily.get("time") or []
    rows = []
    for i, day in enumerate(times):
        def pick(key):
            values = daily.get(key) or []
            return values[i] if i < len(values) else None
        rows.append({
            "date": day,
            "code": pick("weather_code"),
            "tmax": pick("temperature_2m_max"),
            "tmin": pick("temperature_2m_min"),
            "pop": pick("precipitation_probability_max"),
            "precip": pick("precipitation_sum"),
            "wind": pick("wind_speed_10m_max"),
            "sunrise": pick("sunrise"),
            "sunset": pick("sunset"),
        })
    return rows


def fmt_num(value, unit: str = "") -> str:
    if value is None:
        return "—"
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return f"{value}{unit}"


def event_summary(city_name: str, row: dict) -> str:
    emoji, label = weather_label(row["code"])
    return (f"{city_name} {emoji}{label} "
            f"{fmt_num(row['tmin'])}~{fmt_num(row['tmax'], '°C')}")


def event_description(city_name: str, row: dict) -> str:
    _, label = weather_label(row["code"])
    lines = [
        f"{city_name}天气：{label}",
        f"气温：{fmt_num(row['tmin'], '°C')} ~ {fmt_num(row['tmax'], '°C')}",
        f"降水概率：{fmt_num(row['pop'], '%')}",
        f"降水量：{fmt_num(row['precip'], ' mm')}",
        f"最大风速：{fmt_num(row['wind'], ' km/h')}",
    ]
    if row.get("sunrise"):
        lines.append(f"日出：{row['sunrise'][11:16]}")
    if row.get("sunset"):
        lines.append(f"日落：{row['sunset'][11:16]}")
    lines.append("数据来源：Open-Meteo（桥自动生成）")
    return "\n".join(lines)


def ics_escape(text: str) -> str:
    return (text.replace("\\", "\\\\")
                .replace(";", "\\;")
                .replace(",", "\\,")
                .replace("\n", "\\n"))


def fold_line(line: str) -> str:
    """Fold long ICS lines at 75 octets (UTF-8 aware), per RFC 5545."""
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    chunks, current, size = [], "", 0
    limit = 75
    for ch in line:
        n = len(ch.encode("utf-8"))
        if size + n > limit:
            chunks.append(current)
            current, size = " " + ch, 1 + n
            limit = 75
        else:
            current += ch
            size += n
    chunks.append(current)
    return "\r\n".join(chunks)


def build_ics(city_forecasts: list[tuple[dict, dict]], calendar_name: str,
              now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//MuseWeatherCalendarBridge//CN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{ics_escape(calendar_name)}",
        "REFRESH-INTERVAL;VALUE=DURATION:PT6H",
        "X-PUBLISHED-TTL:PT6H",
    ]
    for city, forecast in city_forecasts:
        for row in daily_rows(forecast):
            day = date.fromisoformat(row["date"])
            next_day = day + timedelta(days=1)
            uid = f"{city['slug']}-{day.isoformat()}@weather-calendar-bridge"
            lines += [
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"DTSTAMP:{stamp}",
                f"DTSTART;VALUE=DATE:{day.strftime('%Y%m%d')}",
                f"DTEND;VALUE=DATE:{next_day.strftime('%Y%m%d')}",
                f"SUMMARY:{ics_escape(event_summary(city['name'], row))}",
                f"DESCRIPTION:{ics_escape(event_description(city['name'], row))}",
                f"LOCATION:{ics_escape(city['name'])}",
                "TRANSP:TRANSPARENT",
                "END:VEVENT",
            ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(fold_line(line) for line in lines) + "\r\n"


def generate(output_dir: Path = OUTPUT_DIR, days: int = FORECAST_DAYS) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    fetched = [(city, fetch_forecast(city, days)) for city in CITIES]
    written = []
    for city, forecast in fetched:
        path = output_dir / f"weather-{city['slug']}.ics"
        path.write_text(build_ics([(city, forecast)], f"天气 · {city['name']}"),
                        encoding="utf-8")
        written.append(path)
    combined = output_dir / "weather-all.ics"
    combined.write_text(build_ics(fetched, "天气 · 东莞+广州"), encoding="utf-8")
    written.append(combined)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description="天气日历桥：预报 -> ICS")
    parser.add_argument("--days", type=int, default=FORECAST_DAYS)
    parser.add_argument("--output", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()
    try:
        written = generate(args.output, args.days)
    except Exception as exc:
        print(f"生成失败：{exc}", file=sys.stderr)
        return 1
    for path in written:
        print(f"已生成：{path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
