from __future__ import annotations

import asyncio
import hashlib
import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from app.services.text_extraction import extract_text_from_bytes


SOURCE_FILENAME = "company_policy_source.json"
ACTIVE_POLICY_FILENAME = "company_policy_active.md"


@dataclass(frozen=True)
class FetchedResource:
    url: str
    content: bytes
    content_type: str
    etag: str
    last_modified: str


def link_company_policy_source(
    policies_dir: Path,
    *,
    source_url: str,
    fetch_resource: Callable[[str], FetchedResource] | None = None,
) -> dict:
    cleaned_url = _validate_source_url(source_url)
    policies_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "source_type": "sharepoint_link",
        "source_url": cleaned_url,
        "sync_status": "pending",
        "message": "SharePoint policy source linked. Waiting for first sync.",
        "version": 0,
        "last_synced_at": None,
        "etag": None,
        "last_modified": None,
        "checksum": None,
        "active_policy_file": ACTIVE_POLICY_FILENAME,
    }
    _write_manifest(policies_dir, manifest)
    return sync_company_policy_source(
        policies_dir,
        fetch_resource=fetch_resource,
    )


def sync_company_policy_source(
    policies_dir: Path,
    *,
    fetch_resource: Callable[[str], FetchedResource] | None = None,
) -> dict:
    policies_dir.mkdir(parents=True, exist_ok=True)
    manifest = read_company_policy_source_status(policies_dir)
    source_url = manifest.get("source_url")
    if not source_url:
        return {
            "sync_status": "not_linked",
            "message": "No SharePoint company policy source has been linked yet.",
            "version": 0,
            "active_policy_file": ACTIVE_POLICY_FILENAME,
        }

    fetcher = fetch_resource or _fetch_sharepoint_resource
    try:
        resource = fetcher(source_url)
        checksum = hashlib.sha256(resource.content).hexdigest()
        unchanged = (
            checksum == manifest.get("checksum")
            and resource.etag == manifest.get("etag")
            and resource.last_modified == manifest.get("last_modified")
        )
        if unchanged and (policies_dir / ACTIVE_POLICY_FILENAME).exists():
            manifest.update({
                "sync_status": "up_to_date",
                "message": "Company policy is already up to date.",
                "last_checked_at": _now_iso(),
            })
            _write_manifest(policies_dir, manifest)
            return manifest

        extension = _extension_from_resource(resource)
        text = extract_text_from_bytes(resource.content, extension)
        if not text.strip():
            raise ValueError("The linked file was downloaded, but no readable policy text could be extracted.")

        next_version = int(manifest.get("version") or 0) + 1
        active_text = _render_policy_text(source_url, text, next_version, resource)
        (policies_dir / ACTIVE_POLICY_FILENAME).write_text(active_text, encoding="utf-8")
        version_file = policies_dir / f"company_policy_v{next_version}.md"
        version_file.write_text(active_text, encoding="utf-8")

        manifest.update({
            "source_type": "sharepoint_link",
            "source_url": source_url,
            "download_url": resource.url,
            "sync_status": "up_to_date",
            "message": f"Company policy synced as version {next_version}.",
            "version": next_version,
            "last_synced_at": _now_iso(),
            "last_checked_at": _now_iso(),
            "etag": resource.etag,
            "last_modified": resource.last_modified,
            "checksum": checksum,
            "content_type": resource.content_type,
            "active_policy_file": ACTIVE_POLICY_FILENAME,
            "latest_version_file": version_file.name,
        })
        _write_manifest(policies_dir, manifest)
        return manifest
    except Exception as exc:
        manifest.update({
            "sync_status": "error",
            "message": (
                "Could not sync the linked SharePoint policy. Make sure the link is a direct "
                f"download/shared file link that this server can access. Details: {exc}"
            ),
            "last_checked_at": _now_iso(),
        })
        _write_manifest(policies_dir, manifest)
        return manifest


def read_company_policy_source_status(policies_dir: Path) -> dict:
    manifest_path = policies_dir / SOURCE_FILENAME
    if not manifest_path.exists():
        return {
            "sync_status": "not_linked",
            "message": "No SharePoint company policy source has been linked yet.",
            "version": 0,
            "active_policy_file": ACTIVE_POLICY_FILENAME,
        }
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {
            "sync_status": "error",
            "message": "Company policy source metadata is unreadable.",
            "version": 0,
            "active_policy_file": ACTIVE_POLICY_FILENAME,
        }


async def company_policy_sync_loop(
    policies_dir: Path,
    *,
    interval_minutes: int,
) -> None:
    await asyncio.sleep(5)
    interval_seconds = max(interval_minutes, 5) * 60
    while True:
        await asyncio.to_thread(sync_company_policy_source, policies_dir)
        await asyncio.sleep(interval_seconds)


def start_company_policy_sync(
    policies_dir: Path,
    *,
    interval_minutes: int,
    enabled: bool,
) -> None:
    if not enabled:
        return
    loop = asyncio.get_event_loop()
    loop.create_task(company_policy_sync_loop(policies_dir, interval_minutes=interval_minutes))


def _validate_source_url(source_url: str) -> str:
    cleaned = source_url.strip()
    parsed = urllib.parse.urlparse(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Please enter a valid SharePoint/OneDrive file URL.")
    return cleaned


def _fetch_sharepoint_resource(source_url: str) -> FetchedResource:
    last_error: Exception | None = None
    for url in _candidate_download_urls(source_url):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "ContractSense/1.0"})
            with urllib.request.urlopen(request, timeout=30) as response:
                content = response.read()
                final_url = response.geturl()
                headers = response.headers
            if _looks_like_login_page(content, headers.get("content-type", "")):
                raise ValueError("The link appears to require Microsoft sign-in.")
            return FetchedResource(
                url=final_url,
                content=content,
                content_type=headers.get("content-type", ""),
                etag=headers.get("etag", ""),
                last_modified=headers.get("last-modified", ""),
            )
        except Exception as exc:
            last_error = exc
    raise ValueError(last_error or "Could not download the linked policy file.")


def _candidate_download_urls(source_url: str) -> list[str]:
    parsed = urllib.parse.urlparse(source_url)
    query = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
    query["download"] = "1"
    with_download = parsed._replace(query=urllib.parse.urlencode(query)).geturl()
    candidates = [with_download, source_url]
    seen: set[str] = set()
    return [url for url in candidates if not (url in seen or seen.add(url))]


def _extension_from_resource(resource: FetchedResource) -> str:
    path = urllib.parse.urlparse(resource.url).path.lower()
    for extension in (".docx", ".pdf", ".txt", ".md"):
        if path.endswith(extension):
            return extension
    content_type = resource.content_type.lower()
    if "pdf" in content_type:
        return ".pdf"
    if "wordprocessingml" in content_type or "msword" in content_type:
        return ".docx"
    return ".txt"


def _looks_like_login_page(content: bytes, content_type: str) -> bool:
    if "text/html" not in content_type.lower():
        return False
    sample = content[:3000].decode("utf-8", errors="ignore").lower()
    return any(marker in sample for marker in ("signin", "login.microsoftonline", "microsoft account", "sharepoint"))


def _render_policy_text(source_url: str, text: str, version: int, resource: FetchedResource) -> str:
    return "\n".join([
        f"# Company Policy Reference v{version}",
        "",
        f"Source: {source_url}",
        f"Downloaded from: {resource.url}",
        f"Synced at: {_now_iso()}",
        f"Source ETag: {resource.etag or 'not provided'}",
        f"Source Last-Modified: {resource.last_modified or 'not provided'}",
        "",
        "## Extracted Policy Text",
        "",
        text.strip(),
        "",
    ])


def _write_manifest(policies_dir: Path, manifest: dict) -> None:
    policies_dir.mkdir(parents=True, exist_ok=True)
    (policies_dir / SOURCE_FILENAME).write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
