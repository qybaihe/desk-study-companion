#!/usr/bin/env python3
"""Snapshot every tracked source file and every asset manifest into TiDB."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
VOICE_ROOT = REPO_ROOT / "services" / "voice_ai"
sys.path.insert(0, str(VOICE_ROOT))

from mimo_voice_qa import DEFAULT_ENV, load_dotenv  # noqa: E402
from tidb_store import (  # noqa: E402
    connect,
    ensure_schema,
    persist_event,
    upsert_asset_manifests,
    upsert_code_snapshots,
)


PROJECT_ID = "desk-study-companion"
GITHUB_REPO = "https://github.com/qybaihe/desk-study-companion"
TEXT_NAMES = {"Makefile", ".gitignore", ".gitattributes"}
TEXT_SUFFIXES = {
    ".css", ".env", ".example", ".html", ".ini", ".js", ".json",
    ".md", ".py", ".sql", ".svg", ".toml", ".txt", ".yaml", ".yml",
}
LANGUAGE_BY_SUFFIX = {
    ".css": "CSS",
    ".html": "HTML",
    ".js": "JavaScript",
    ".json": "JSON",
    ".md": "Markdown",
    ".py": "Python",
    ".sql": "SQL",
    ".svg": "SVG",
    ".yaml": "YAML",
    ".yml": "YAML",
}


def git(*arguments: str) -> str:
    return subprocess.check_output(
        ["git", *arguments], cwd=REPO_ROOT, text=True
    ).strip()


def tracked_paths() -> list[Path]:
    payload = subprocess.check_output(
        ["git", "ls-files", "-z"], cwd=REPO_ROOT
    )
    return [REPO_ROOT / raw.decode("utf-8") for raw in payload.split(b"\0") if raw]


def is_source(path: Path, data: bytes) -> bool:
    relative = path.relative_to(REPO_ROOT)
    if relative.name in TEXT_NAMES or relative.suffix.lower() in TEXT_SUFFIXES:
        try:
            data.decode("utf-8")
            return True
        except UnicodeDecodeError:
            return False
    return False


def build_rows(commit: str) -> tuple[list[dict], list[dict]]:
    code_rows = []
    asset_rows = []
    for path in tracked_paths():
        data = path.read_bytes()
        relative = path.relative_to(REPO_ROOT).as_posix()
        digest = hashlib.sha256(data).hexdigest()
        github_url = "%s/blob/%s/%s" % (GITHUB_REPO, commit, relative)
        common = {
            "project_id": PROJECT_ID,
            "git_commit": commit,
            "path": relative,
            "content_sha256": digest,
            "size_bytes": len(data),
            "github_url": github_url,
        }
        if is_source(path, data):
            code_rows.append(
                {
                    **common,
                    "language": LANGUAGE_BY_SUFFIX.get(
                        path.suffix.lower(), "Text"
                    ),
                    "content": data.decode("utf-8"),
                }
            )
        else:
            asset_rows.append(
                {
                    **common,
                    "mime_type": mimetypes.guess_type(relative)[0]
                    or "application/octet-stream",
                }
            )
    return code_rows, asset_rows


def main() -> None:
    load_dotenv(DEFAULT_ENV)
    commit = git("rev-parse", "HEAD")
    branch = git("branch", "--show-current") or "detached"
    code_rows, asset_rows = build_rows(commit)
    connection = connect()
    try:
        ensure_schema(connection)
        code_count = upsert_code_snapshots(code_rows, connection)
        asset_count = upsert_asset_manifests(asset_rows, connection)
        event_id = persist_event(
            {
                "event_id": "repository-sync-" + commit,
                "event_type": "project.repository_synced",
                "source": "tooling.sync_project_to_tidb",
                "device_id": "mac-development-host",
                "session_id": commit,
                "repository": GITHUB_REPO,
                "branch": branch,
                "git_commit": commit,
                "code_files": code_count,
                "asset_files": asset_count,
            },
            connection,
        )
    finally:
        connection.close()
    print(
        json.dumps(
            {
                "ok": True,
                "git_commit": commit,
                "code_files": code_count,
                "asset_files": asset_count,
                "event_id": event_id,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
