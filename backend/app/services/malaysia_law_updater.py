from __future__ import annotations

import asyncio
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable


DEFAULT_SOURCE_URL = "https://lom.agc.gov.my/"
GENERATED_FILENAME = "malaysia_law_latest_agc_lom.md"
MANIFEST_FILENAME = "malaysia_law_update_manifest.json"


@dataclass(frozen=True)
class LawLink:
    title: str
    url: str


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._href: str | None = None
        self._text_parts: list[str] = []
        self.links: list[LawLink] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        attrs_dict = dict(attrs)
        href = attrs_dict.get("href")
        if href:
            self._href = href
            self._text_parts = []

    def handle_data(self, data: str) -> None:
        if self._href:
            self._text_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or not self._href:
            return
        title = " ".join(" ".join(self._text_parts).split())
        if title:
            self.links.append(LawLink(title=title, url=self._href))
        self._href = None
        self._text_parts = []


def _fetch_text(url: str, timeout: int = 20) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "ContractSense/1.0 (+https://lom.agc.gov.my/)",
            "Accept": "text/html,application/xhtml+xml,application/pdf,*/*",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
        content_type = response.headers.get("content-type", "")
    if "application/pdf" in content_type.lower():
        return ""
    return raw.decode("utf-8", errors="replace")


def _is_law_reference(title: str, url: str) -> bool:
    text = f"{title} {url}".lower()
    return any(
        marker in text
        for marker in (
            "act ",
            "act%20",
            "akta",
            "p.u.",
            "pu",
            "federal constitution",
            "principal",
            "amendment",
            "ordinance",
            "subsidiary",
        )
    )


def _normalise_links(html: str, source_url: str) -> list[LawLink]:
    parser = _LinkParser()
    parser.feed(html)

    seen: set[str] = set()
    links: list[LawLink] = []
    for link in parser.links:
        absolute_url = urllib.parse.urljoin(source_url, link.url)
        title = re.sub(r"\s+", " ", link.title).strip(" -")
        if not title or absolute_url in seen:
            continue
        if not _is_law_reference(title, absolute_url):
            continue
        seen.add(absolute_url)
        links.append(LawLink(title=title, url=absolute_url))
    return links


def _render_law_markdown(source_url: str, links: list[LawLink], fetched_at: datetime) -> str:
    lines = [
        "# Malaysia Federal Legislation Reference",
        "",
        "Automatically refreshed from the official Attorney General's Chambers",
        f"Laws of Malaysia portal: {source_url}",
        "",
        f"Last refreshed: {fetched_at.astimezone(timezone.utc).isoformat()}",
        "",
        "Use this as a live index for Malaysian law checks. For formal legal",
        "decisions, verify the linked official text and gazette publication.",
        "",
        "## Latest And Linked References",
        "",
    ]
    if not links:
        lines.append("No law links were found during the latest refresh.")
    for link in links:
        safe_title = link.title.replace("[", "(").replace("]", ")")
        lines.append(f"- [{safe_title}]({link.url})")
    lines.append("")
    return "\n".join(lines)


def _write_manifest(
    laws_dir: Path,
    *,
    source_url: str,
    fetched_at: datetime,
    status: str,
    message: str,
    links: list[LawLink],
) -> dict:
    manifest = {
        "source_url": source_url,
        "fetched_at": fetched_at.astimezone(timezone.utc).isoformat(),
        "status": status,
        "message": message,
        "generated_file": GENERATED_FILENAME,
        "link_count": len(links),
        "links": [{"title": link.title, "url": link.url} for link in links[:100]],
    }
    laws_dir.mkdir(parents=True, exist_ok=True)
    (laws_dir / MANIFEST_FILENAME).write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )
    return manifest


def update_malaysia_law_database(
    laws_dir: Path,
    *,
    source_url: str = DEFAULT_SOURCE_URL,
    fetch_text: Callable[[str], str] = _fetch_text,
) -> dict:
    fetched_at = datetime.now(timezone.utc)
    laws_dir.mkdir(parents=True, exist_ok=True)

    try:
        html = fetch_text(source_url)
        links = _normalise_links(html, source_url)
        content = _render_law_markdown(source_url, links, fetched_at)
        (laws_dir / GENERATED_FILENAME).write_text(content, encoding="utf-8")
        return _write_manifest(
            laws_dir,
            source_url=source_url,
            fetched_at=fetched_at,
            status="ok",
            message=f"Malaysia law reference refreshed with {len(links)} official links.",
            links=links,
        )
    except (OSError, urllib.error.URLError, TimeoutError, ValueError) as exc:
        existing = laws_dir / GENERATED_FILENAME
        message = f"Malaysia law refresh failed: {exc}"
        return _write_manifest(
            laws_dir,
            source_url=source_url,
            fetched_at=fetched_at,
            status="error",
            message=message if existing.exists() else f"{message}. No previous generated file exists.",
            links=[],
        )


def read_malaysia_law_update_status(laws_dir: Path) -> dict:
    manifest_path = laws_dir / MANIFEST_FILENAME
    if not manifest_path.exists():
        return {
            "status": "never_run",
            "message": "Malaysia law database has not been refreshed yet.",
            "generated_file": GENERATED_FILENAME,
            "link_count": 0,
        }
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {
            "status": "error",
            "message": "Malaysia law update manifest is unreadable.",
            "generated_file": GENERATED_FILENAME,
            "link_count": 0,
        }


async def malaysia_law_update_loop(
    laws_dir: Path,
    *,
    source_url: str,
    interval_hours: int,
) -> None:
    interval_seconds = max(interval_hours, 1) * 60 * 60
    await asyncio.sleep(2)
    while True:
        await asyncio.to_thread(
            update_malaysia_law_database,
            laws_dir,
            source_url=source_url,
        )
        await asyncio.sleep(interval_seconds)


def start_malaysia_law_updater(
    laws_dir: Path,
    *,
    source_url: str,
    interval_hours: int,
    enabled: bool,
) -> None:
    if not enabled:
        return
    loop = asyncio.get_event_loop()
    loop.create_task(
        malaysia_law_update_loop(
            laws_dir,
            source_url=source_url,
            interval_hours=interval_hours,
        )
    )
