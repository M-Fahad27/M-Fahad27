#!/usr/bin/env python3
# Generate a local animated GitHub telemetry SVG for a profile README.
from __future__ import annotations

import argparse
import collections
import datetime as dt
import html
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

API = "https://api.github.com"
OUTPUT = Path(__file__).resolve().parents[1] / "assets" / "github-telemetry.svg"


def request_json(url: str, token: str | None) -> tuple[Any, dict[str, str]]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "profile-telemetry-action",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response), dict(response.headers.items())


def fetch_repositories(username: str, token: str | None) -> list[dict[str, Any]]:
    repositories: list[dict[str, Any]] = []
    page = 1
    while True:
        batch, _ = request_json(
            f"{API}/users/{username}/repos?per_page=100&page={page}&type=owner&sort=pushed",
            token,
        )
        if not isinstance(batch, list):
            raise RuntimeError("Unexpected repositories response")
        repositories.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return repositories


def parse_time(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def clean_text(value: object, max_length: int = 18) -> str:
    text = str(value or "—")
    if len(text) > max_length:
        text = text[: max_length - 1] + "…"
    return html.escape(text)


def build_metrics(profile: dict[str, Any], repos: list[dict[str, Any]]) -> tuple[list[tuple[str, str]], list[int]]:
    originals = [repo for repo in repos if not repo.get("fork") and not repo.get("archived")]
    stars = sum(int(repo.get("stargazers_count") or 0) for repo in originals)
    forks = sum(int(repo.get("forks_count") or 0) for repo in originals)
    languages = collections.Counter(repo.get("language") for repo in originals if repo.get("language"))
    top_language = languages.most_common(1)[0][0] if languages else "—"
    now = dt.datetime.now(dt.timezone.utc)
    active_30d = sum(
        1
        for repo in originals
        if (pushed := parse_time(repo.get("pushed_at"))) and (now - pushed).days <= 30
    )
    latest = max(originals or repos, key=lambda r: r.get("pushed_at") or "", default={})
    latest_date = parse_time(latest.get("pushed_at"))
    latest_label = latest_date.strftime("%d %b %Y") if latest_date else "—"

    metrics = [
        (str(profile.get("public_repos", len(repos))), "PUBLIC REPOS"),
        (str(len(originals)), "ORIGINAL BUILDS"),
        (str(stars), "STARS EARNED"),
        (str(active_30d), "ACTIVE / 30D"),
        (clean_text(top_language, 12).upper(), "TOP LANGUAGE"),
        (latest_label.upper(), "LAST PUSH"),
    ]

    recent = sorted(originals or repos, key=lambda r: r.get("pushed_at") or "", reverse=True)[:12]
    pulse: list[int] = []
    for repo in recent:
        pushed = parse_time(repo.get("pushed_at"))
        days = (now - pushed).days if pushed else 365
        recency = max(0, 100 - min(days, 100))
        signal = min(100, recency + min(25, int(repo.get("stargazers_count") or 0) * 5) + min(15, int(repo.get("forks_count") or 0) * 3))
        pulse.append(max(25, signal))
    while len(pulse) < 12:
        pulse.append(25 + len(pulse) * 4)
    return metrics, pulse


def generate_svg(username: str, metrics: list[tuple[str, str]], pulse: list[int]) -> str:
    colors = ["#22D3EE", "#60A5FA", "#818CF8", "#A78BFA", "#C084FC", "#E879F9"]
    card_x = [54, 240, 426, 612, 798, 984]
    cards = []
    for index, ((value, label), x) in enumerate(zip(metrics, card_x)):
        width = 170 if index < 5 else 162
        font_size = 31 if len(value) <= 4 else 22 if len(value) <= 9 else 17
        color = colors[index]
        cards.append(f'''<g><rect x="{x}" y="94" width="{width}" height="112" rx="16" fill="#071827" fill-opacity=".76" stroke="{color}" stroke-opacity=".55"/><text x="{x + width/2:.1f}" y="141" text-anchor="middle" class="sans" font-size="{font_size}" font-weight="800" fill="{color}" filter="url(#glow)">{clean_text(value, 16)}</text><text x="{x + width/2:.1f}" y="172" text-anchor="middle" class="mono" font-size="11" fill="#CBD5E1">{clean_text(label, 20)}</text></g>''')

    bars = []
    for i, amount in enumerate(pulse[:12]):
        height = 35 + round(amount * 0.95)
        y = 381 - height
        color = colors[i % len(colors)]
        delay = i * 0.15
        bars.append(f'<rect x="{i*82}" y="{y}" width="55" height="{height}" rx="7" fill="{color}" fill-opacity=".55" style="transform-origin:{i*82 + 27.5}px 381px;animation:bar 2.8s {delay:.2f}s ease-in-out infinite"/>')

    return f'''<svg width="1200" height="430" viewBox="0 0 1200 430" fill="none" xmlns="http://www.w3.org/2000/svg">
  <defs><linearGradient id="bg" x1="0" y1="0" x2="1200" y2="430"><stop stop-color="#030712"/><stop offset=".5" stop-color="#071426"/><stop offset="1" stop-color="#13071F"/></linearGradient><linearGradient id="g" x1="55" y1="0" x2="1145" y2="0"><stop stop-color="#22D3EE"/><stop offset=".5" stop-color="#818CF8"/><stop offset="1" stop-color="#D946EF"/></linearGradient><pattern id="grid" width="30" height="30" patternUnits="userSpaceOnUse"><path d="M30 0H0V30" stroke="#7DD3FC" stroke-opacity=".05"/></pattern><filter id="glow"><feGaussianBlur stdDeviation="4" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>
  <style>.sans{{font-family:Inter,Segoe UI,Arial,sans-serif}}.mono{{font-family:Consolas,'Liberation Mono',monospace}}.pulse{{animation:pulse 2.2s ease-in-out infinite}}.dash{{stroke-dasharray:10 11;animation:dash 2.6s linear infinite}}.spin{{transform-origin:1082px 54px;animation:spin 5s linear infinite}}.scan{{animation:scan 4.5s linear infinite}}@keyframes pulse{{0%,100%{{opacity:.48}}50%{{opacity:1}}}}@keyframes dash{{to{{stroke-dashoffset:-120}}}}@keyframes spin{{to{{transform:rotate(360deg)}}}}@keyframes scan{{from{{transform:translateX(-220px)}}to{{transform:translateX(1300px)}}}}@keyframes bar{{0%,100%{{transform:scaleY(.65);opacity:.55}}50%{{transform:scaleY(1);opacity:1}}}}</style>
  <rect width="1200" height="430" rx="24" fill="url(#bg)"/><rect width="1200" height="430" rx="24" fill="url(#grid)"/><rect x="1" y="1" width="1198" height="428" rx="23" stroke="url(#g)" stroke-opacity=".36"/>
  <text x="54" y="42" class="mono" font-size="14" fill="#67E8F9">// GITHUB TELEMETRY · @{clean_text(username, 30)} · API-SYNCED LOCAL SVG</text><circle cx="1082" cy="54" r="20" stroke="#22D3EE" stroke-opacity=".25" stroke-width="3"/><path d="M1082 34A20 20 0 0 1 1102 54" stroke="url(#g)" stroke-width="3" stroke-linecap="round" class="spin"/><circle cx="1133" cy="42" r="5" fill="#34D399" class="pulse"/><text x="1145" y="46" class="mono" font-size="11" fill="#A7F3D0">LIVE</text>
  <path d="M54 66H1146" stroke="url(#g)" stroke-width="2" opacity=".5" class="dash"/><rect x="-210" y="57" width="190" height="18" fill="url(#g)" opacity=".1" class="scan"/>
  {''.join(cards)}
  <text x="54" y="250" class="mono" font-size="12" fill="#94A3B8">RECENT REPOSITORY PULSE // signal combines push recency, stars and forks</text><path d="M54 269H1146" stroke="#334155" stroke-width="1"/><g transform="translate(75 0)">{''.join(bars)}</g>
  <text x="54" y="411" class="mono" font-size="11" fill="#64748B">updated&gt; {dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} · generated inside the profile repository</text>
</svg>'''


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", default=os.environ.get("GITHUB_REPOSITORY_OWNER", "M-Fahad27"))
    args = parser.parse_args()
    token = os.environ.get("GITHUB_TOKEN")
    try:
        profile, _ = request_json(f"{API}/users/{args.username}", token)
        repos = fetch_repositories(args.username, token)
        metrics, pulse = build_metrics(profile, repos)
        OUTPUT.write_text(generate_svg(args.username, metrics, pulse), encoding="utf-8")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, RuntimeError, ValueError) as exc:
        print(f"Telemetry update failed: {exc}", file=sys.stderr)
        return 1
    print(f"Updated {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
