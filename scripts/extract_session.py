#!/usr/bin/env python3
"""Preprocessor that extracts user/assistant text from Claude Code session JSONL files.

Usage:
    # Single session
    python extract_session.py <session.jsonl> [--since YYYY-MM-DD] [--max-chars 50000]

    # Scan all projects (--all)
    python extract_session.py --all [--since YYYY-MM-DD] [--max-chars 50000]

    # History index summary (--index)
    python extract_session.py --index [--since YYYY-MM-DD]

    # Extract specific project only (--project)
    python extract_session.py --project /path/to/project [--since YYYY-MM-DD] [--max-chars 50000]

Output:
    Condensed conversation flow to stdout (Markdown format)
"""

import json
import sys
import os
import argparse
from datetime import datetime
from pathlib import Path


CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"
CLAUDE_HISTORY_FILE = Path.home() / ".claude" / "history.jsonl"


def extract_messages(jsonl_path: str, since: datetime | None = None, max_chars: int = 50000, claude_max_chars_per_msg: int = 0) -> str:
    messages = []

    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            msg_type = data.get("type")
            if msg_type not in ("user", "assistant"):
                continue

            timestamp_raw = data.get("timestamp", "")
            try:
                if isinstance(timestamp_raw, str):
                    ts = datetime.fromisoformat(timestamp_raw.replace("Z", "+00:00"))
                else:
                    ts = datetime.fromtimestamp(timestamp_raw / 1000)
            except (ValueError, TypeError, OSError):
                ts = None

            if since and ts:
                ts_naive = ts.replace(tzinfo=None) if ts.tzinfo else ts
                if ts_naive < since:
                    continue

            message = data.get("message", {})

            if msg_type == "user":
                content = message.get("content", "")
                if isinstance(content, str) and content.strip():
                    messages.append({
                        "role": "user",
                        "text": content.strip(),
                        "ts": timestamp_raw,
                    })

            elif msg_type == "assistant":
                content = message.get("content", [])
                if isinstance(content, list):
                    texts = []
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            text = block.get("text", "").strip()
                            if text:
                                texts.append(text)
                    if texts:
                        full_text = "\n".join(texts)
                        # Truncate Claude responses: if claude_max_chars_per_msg > 0, trim each response
                        if claude_max_chars_per_msg > 0 and len(full_text) > claude_max_chars_per_msg:
                            full_text = full_text[:claude_max_chars_per_msg] + "\n...(truncated)"
                        messages.append({
                            "role": "assistant",
                            "text": full_text,
                            "ts": timestamp_raw,
                        })

    # Character limit: take from both front (problem definition) and back (conclusion).
    # Session start has the core purpose; session end has conclusions/implementation.
    if not messages:
        return ""

    total_all = sum(len(m["text"]) for m in messages)

    if total_all <= max_chars:
        trimmed = messages
    else:
        head_budget = max_chars * 2 // 5  # front 40%
        tail_budget = max_chars * 2 // 5  # back 40%
        # remaining 20% reserved for separators etc.

        # from front
        head = []
        head_chars = 0
        for msg in messages:
            msg_len = len(msg["text"])
            if head_chars + msg_len > head_budget:
                remaining = head_budget - head_chars
                if remaining > 200:
                    head.append({
                        **msg,
                        "text": msg["text"][:remaining] + "\n...(truncated)",
                    })
                break
            head_chars += msg_len
            head.append(msg)

        # from back
        tail = []
        tail_chars = 0
        for msg in reversed(messages):
            msg_len = len(msg["text"])
            if tail_chars + msg_len > tail_budget:
                remaining = tail_budget - tail_chars
                if remaining > 200:
                    tail.append({
                        **msg,
                        "text": "...(truncated)\n" + msg["text"][-remaining:],
                    })
                break
            tail_chars += msg_len
            tail.append(msg)
        tail.reverse()

        # deduplicate: exclude messages already in head from tail
        head_timestamps = {(m["role"], m["ts"]) for m in head}
        tail_deduped = [m for m in tail if (m["role"], m["ts"]) not in head_timestamps]

        if tail_deduped:
            trimmed = head + [{"role": "system", "text": f"--- ({total_all - head_chars - tail_chars} chars omitted) ---", "ts": ""}] + tail_deduped
        else:
            trimmed = head

    # Markdown output
    lines = []
    for msg in trimmed:
        if msg["role"] == "system":
            lines.append(msg["text"])
            lines.append("")
            continue
        role = "USER" if msg["role"] == "user" else "CLAUDE"
        lines.append(f"### [{role}] {msg['ts']}")
        lines.append("")
        lines.append(msg["text"])
        lines.append("")

    return "\n".join(lines)


def slug_to_path(slug: str) -> str | None:
    """Reverse-convert a project slug back to the actual filesystem path.

    Slugs replace / with - in the path, but directory names themselves may contain
    hyphens, so we probe for actually existing paths to reconstruct the original.
    For deleted paths (e.g. worktrees), returns the deepest matching path found.
    """
    parts = slug.strip("-").split("-")
    best_match = [None]  # mutable for closure

    def _resolve(idx: int, current: str) -> str | None:
        if idx >= len(parts):
            return current if os.path.isdir(current) else None

        for end in range(idx + 1, len(parts) + 1):
            candidate = current + "/" + "-".join(parts[idx:end])
            if os.path.isdir(candidate):
                # track deepest match so far
                if best_match[0] is None or len(candidate) > len(best_match[0]):
                    best_match[0] = candidate
                result = _resolve(end, candidate)
                if result:
                    return result

        return None

    exact = _resolve(0, "")
    return exact or best_match[0]


def slug_to_project_name(slug: str) -> str:
    """Extract a human-readable name from a project slug."""
    real_path = slug_to_path(slug)
    if real_path:
        home = str(Path.home())
        if real_path.startswith(home):
            rel = real_path[len(home):].strip("/")
            return rel if rel else "~(home)"
        return real_path

    # fallback: use slug as-is
    return slug


def find_all_sessions(since: datetime | None = None) -> dict[str, list[str]]:
    """Find all session JSONL files modified after `since` across all projects.

    Returns:
        {project_slug: [jsonl_path, ...], ...}
    """
    if not CLAUDE_PROJECTS_DIR.is_dir():
        return {}

    result = {}
    for proj_dir in CLAUDE_PROJECTS_DIR.iterdir():
        if not proj_dir.is_dir():
            continue

        sessions = []
        for jsonl_file in proj_dir.glob("*.jsonl"):
            if since:
                mtime = datetime.fromtimestamp(jsonl_file.stat().st_mtime)
                if mtime < since:
                    continue
            sessions.append(str(jsonl_file))

        if sessions:
            sessions.sort(key=lambda p: os.path.getmtime(p))
            result[proj_dir.name] = sessions

    return result


def extract_all(since: datetime | None = None, max_chars: int = 50000, claude_max_chars_per_msg: int = 0) -> str:
    """Extract sessions from all projects, organized by project."""
    projects = find_all_sessions(since)
    if not projects:
        return "(No session data found for this period)"

    # distribute max_chars budget across projects
    per_project_chars = max(max_chars // len(projects), 5000)

    lines = []
    for slug, jsonl_paths in sorted(projects.items(), key=lambda x: max(os.path.getmtime(p) for p in x[1])):
        proj_name = slug_to_project_name(slug)
        lines.append(f"# Project: {proj_name}")
        lines.append(f"<!-- slug: {slug} -->")
        lines.append("")

        # distribute budget across sessions
        per_session_chars = max(per_project_chars // len(jsonl_paths), 2000)

        for jsonl_path in jsonl_paths:
            session_id = Path(jsonl_path).stem[:8]
            lines.append(f"## Session: {session_id}...")
            lines.append("")
            content = extract_messages(jsonl_path, since=since, max_chars=per_session_chars, claude_max_chars_per_msg=claude_max_chars_per_msg)
            if content.strip():
                lines.append(content)
            else:
                lines.append("_(No messages found for this period)_")
            lines.append("")

    return "\n".join(lines)


def index_history(since: datetime | None = None) -> str:
    """Output per-project prompt counts and topic summaries from history.jsonl.

    Used as an index to decide which projects to examine in depth.
    """
    if not CLAUDE_HISTORY_FILE.exists():
        return "(history.jsonl not found)"

    projects: dict[str, list[dict]] = {}

    with open(CLAUDE_HISTORY_FILE, "r", encoding="utf-8") as f:
        for line in f:
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            ts_ms = data.get("timestamp")
            if not ts_ms:
                continue

            ts = datetime.fromtimestamp(ts_ms / 1000)
            if since and ts < since:
                continue

            project = data.get("project", "unknown")
            display = data.get("display", "").strip()
            if not display:
                continue

            if project not in projects:
                projects[project] = []
            projects[project].append({
                "time": ts.strftime("%m-%d %H:%M"),
                "display": display[:120],
            })

    if not projects:
        return "(No history found for this period)"

    lines = ["# History Index", ""]
    for project_path, prompts in sorted(projects.items(), key=lambda x: len(x[1]), reverse=True):
        # extract project name
        proj_name = os.path.basename(project_path) if project_path != "unknown" else "unknown"
        parent = os.path.basename(os.path.dirname(project_path)) if project_path != "unknown" else ""
        display_name = f"{parent}/{proj_name}" if parent else proj_name

        lines.append(f"## {display_name} ({len(prompts)} prompts)")
        lines.append(f"<!-- path: {project_path} -->")
        lines.append("")

        # prompt list (max 10, most recent)
        for p in prompts[-10:]:
            lines.append(f"- `{p['time']}` {p['display']}")
        if len(prompts) > 10:
            lines.append(f"- ... and {len(prompts) - 10} more")
        lines.append("")

    return "\n".join(lines)


def extract_project(project_path: str, since: datetime | None = None, max_chars: int = 50000, claude_max_chars_per_msg: int = 0) -> str:
    """Extract sessions matching a specific project path."""
    # project path → slug candidate matching
    if not CLAUDE_PROJECTS_DIR.is_dir():
        return "(Session directory not found)"

    project_path = os.path.abspath(project_path)
    matched_sessions = []

    for proj_dir in CLAUDE_PROJECTS_DIR.iterdir():
        if not proj_dir.is_dir():
            continue

        resolved = slug_to_path(proj_dir.name)
        if resolved and os.path.abspath(resolved) == project_path:
            for jsonl_file in proj_dir.glob("*.jsonl"):
                if since:
                    mtime = datetime.fromtimestamp(jsonl_file.stat().st_mtime)
                    if mtime < since:
                        continue
                matched_sessions.append(str(jsonl_file))

    if not matched_sessions:
        return f"(No sessions found for project '{project_path}')"

    matched_sessions.sort(key=lambda p: os.path.getmtime(p))
    per_session_chars = max(max_chars // len(matched_sessions), 3000)

    proj_name = os.path.basename(project_path)
    lines = [f"# Project: {proj_name}", ""]

    for jsonl_path in matched_sessions:
        session_id = Path(jsonl_path).stem[:8]
        lines.append(f"## Session: {session_id}...")
        lines.append("")
        content = extract_messages(jsonl_path, since=since, max_chars=per_session_chars, claude_max_chars_per_msg=claude_max_chars_per_msg)
        if content.strip():
            lines.append(content)
        else:
            lines.append("_(No messages found for this period)_")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Extract user/assistant text from Claude session JSONL")
    parser.add_argument("jsonl_path", nargs="?", help="Path to session .jsonl file (omit with --all/--index/--project)")
    parser.add_argument("--all", action="store_true", help="Scan all projects under ~/.claude/projects/")
    parser.add_argument("--index", action="store_true", help="Show history.jsonl index (project summary)")
    parser.add_argument("--project", help="Extract sessions for a specific project path")
    parser.add_argument("--since", help="Filter messages since date (YYYY-MM-DD)", default=None)
    parser.add_argument("--max-chars", type=int, default=50000, help="Max total characters to extract (default: 50000)")
    parser.add_argument("--claude-max", type=int, default=0, help="Max chars per Claude response (0=no limit). Use with --user-full for user-full + claude-truncated mode")
    parser.add_argument("--user-full", action="store_true", help="Keep all user messages, only truncate Claude responses via --claude-max")
    args = parser.parse_args()

    since = None
    if args.since:
        since = datetime.strptime(args.since, "%Y-%m-%d")

    claude_max = args.claude_max if args.user_full else 0
    effective_max = 0 if args.user_full else args.max_chars  # user-full mode disables total char limit

    if args.index:
        result = index_history(since=since)
    elif args.all:
        result = extract_all(since=since, max_chars=effective_max or args.max_chars, claude_max_chars_per_msg=claude_max)
    elif args.project:
        result = extract_project(args.project, since=since, max_chars=effective_max or args.max_chars, claude_max_chars_per_msg=claude_max)
    elif args.jsonl_path:
        result = extract_messages(args.jsonl_path, since=since, max_chars=effective_max or args.max_chars, claude_max_chars_per_msg=claude_max)
    else:
        parser.error("Provide a jsonl_path, or use --all, --index, or --project")

    print(result)


if __name__ == "__main__":
    main()
