from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urlparse

import requests


def repository_from_url(source_url: str) -> tuple[str, str] | None:
    """Extract owner/repository from a public GitHub repository or release URL."""
    try:
        parsed = urlparse((source_url or "").strip())
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() not in {"github.com", "www.github.com"}:
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        return None
    owner, repo = parts[0], parts[1]
    if repo.endswith(".git"):
        repo = repo[:-4]
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", owner) or not re.fullmatch(r"[A-Za-z0-9_.-]+", repo):
        return None
    return owner, repo


def _release_date(value: object) -> str:
    """Normalize a GitHub timestamp to an ISO calendar date."""
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return text[:10]


def fetch_latest_stable(source_url: str, app_version: str) -> dict[str, str] | None:
    """Return the newest stable GitHub release, or None for non-GitHub URLs."""
    repo = repository_from_url(source_url)
    if not repo:
        return None
    owner, name = repo
    api_url = f"https://api.github.com/repos/{owner}/{name}/releases?per_page=20"
    response = requests.get(
        api_url,
        timeout=15,
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": f"OutlawsInventory/{app_version}",
        },
    )
    response.raise_for_status()
    releases = response.json()
    if not isinstance(releases, list):
        raise RuntimeError("GitHub returned an unexpected releases response")

    stable = [item for item in releases if isinstance(item, dict) and not item.get("draft") and not item.get("prerelease")]
    if not stable:
        return {
            "latest": "",
            "release_date": "",
            "summary": "No stable GitHub release was found.",
            "notes_url": source_url,
            "confidence": "API",
            "source": "GitHub Releases API",
            "method": "Official website",
        }

    stable.sort(key=lambda item: (item.get("published_at") or item.get("created_at") or ""), reverse=True)
    release = stable[0]
    tag = str(release.get("tag_name") or release.get("name") or "").strip()
    latest = tag.lstrip("vV").strip()
    published = _release_date(release.get("published_at") or release.get("created_at"))
    body = str(release.get("body") or release.get("name") or "")
    notes_url = str(release.get("html_url") or source_url)

    if not latest or not re.search(r"\d", latest):
        return {
            "latest": "",
            "release_date": published,
            "summary": "The latest stable GitHub release has no usable version tag.",
            "notes_url": notes_url,
            "confidence": "API",
            "source": "GitHub Releases API",
            "method": "Official website",
        }

    return {
        "latest": latest,
        "release_date": published,
        "summary": body,
        "notes_url": notes_url,
        "confidence": "API",
        "source": "GitHub Releases API",
        "method": "Official website",
        "tag": tag,
    }
