from __future__ import annotations

import argparse
import fnmatch
import hashlib
import re
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

MAX_TEXT_BYTES = 8 * 1024 * 1024
SAFE_SECRET_VALUES = {
    "",
    "changeme",
    "dummy",
    "example",
    "false",
    "none",
    "null",
    "placeholder",
    "test",
    "true",
}
IGNORED_PATHS = (
    ".git/*",
    ".runtime/*",
    ".secrets/*",
    ".venv/*",
    "frontend/node_modules/*",
    "frontend/dist/*",
    "node_modules/*",
)


@dataclass(frozen=True, slots=True)
class Rule:
    id: str
    expression: re.Pattern[str]
    group: int = 0


@dataclass(frozen=True, slots=True)
class Finding:
    rule: str
    path: str
    line: int
    fingerprint: str
    object_id: str | None = None

    def display(self) -> str:
        location = f"{self.path}:{self.line}"
        history = f" blob={self.object_id[:12]}" if self.object_id else ""
        return f"{self.rule} {location} fingerprint={self.fingerprint}{history}"


RULES = (
    Rule(
        "private-key",
        re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----"),
    ),
    Rule(
        "github-token",
        re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b"),
    ),
    Rule("aws-access-key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    Rule("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b")),
    Rule("openai-api-key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b")),
    Rule("slack-token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b")),
    Rule(
        "credential-url",
        re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s/:@]+:([^\s/@]+)@", re.IGNORECASE),
        1,
    ),
    Rule(
        "local-windows-user-path",
        re.compile(
            r"\b[A-Za-z]:[\\/](?:Users|Documents and Settings)[\\/]([^\\/\s\"'<>]+)",
            re.IGNORECASE,
        ),
        1,
    ),
    Rule(
        "local-unix-user-path",
        re.compile(r"(?:^|[\s=\"'])(?:/Users|/home)/([^/\s\"'<>]+)"),
        1,
    ),
    Rule(
        "local-project-path",
        re.compile(
            r"\b[A-Za-z]:[\\/][^\r\n\"'<>]*[\\/]ra2-explorer(?:[\\/][^\r\n\"'<>]*)?",
            re.IGNORECASE,
        ),
    ),
    Rule(
        "personal-email",
        re.compile(r"\b[A-Z0-9._%+-]+@(?:[A-Z0-9-]+\.)+[A-Z]{2,}\b", re.IGNORECASE),
    ),
)

SECRET_ASSIGNMENT = re.compile(
    r"(?im)^\s*(?:export\s+)?(?:[A-Za-z0-9_.-]*(?:password|passwd|secret|token|api[_-]?key|client[_-]?secret)[A-Za-z0-9_.-]*)"
    r"\s*[:=]\s*([^\s#;,]+)"
)


class ScanError(RuntimeError):
    pass


def _run_git(arguments: list[str], *, input_bytes: bytes | None = None) -> bytes:
    process = subprocess.run(
        ["git", *arguments],
        input=input_bytes,
        capture_output=True,
        check=False,
    )
    if process.returncode != 0:
        message = process.stderr.decode("utf-8", errors="replace").strip()
        raise ScanError(message or f"git {' '.join(arguments)} failed")
    return process.stdout


def _normalized_path(path: str) -> str:
    normalized = path.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def _ignored(path: str) -> bool:
    normalized = _normalized_path(path)
    return any(fnmatch.fnmatch(normalized, pattern) for pattern in IGNORED_PATHS)


def _decode_text(data: bytes) -> str | None:
    if len(data) > MAX_TEXT_BYTES:
        return None
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return data.decode("utf-16")
        except UnicodeDecodeError:
            return None
    if b"\x00" in data[:8192]:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return data.decode("windows-1252")
        except UnicodeDecodeError:
            return None


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()[:12]


def _safe_email(value: str) -> bool:
    lowered = value.casefold()
    return lowered.endswith("@users.noreply.github.com") or lowered.endswith("@example.com")


def _safe_assignment(value: str) -> bool:
    cleaned = value.strip("\"'").casefold()
    if cleaned in SAFE_SECRET_VALUES:
        return True
    return (
        cleaned.startswith(("${", "%", "<", "{{"))
        or cleaned.startswith(("(", "[", "{"))
        or "(" in cleaned
        or "getenv(" in cleaned
        or "environ[" in cleaned
        or cleaned.endswith(("_here", "_value"))
    )


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def scan_text(path: str, data: bytes, *, object_id: str | None = None) -> list[Finding]:
    normalized = _normalized_path(path)
    if _ignored(normalized):
        return []
    text = _decode_text(data)
    if text is None:
        return []
    findings: list[Finding] = []
    for rule in RULES:
        for match in rule.expression.finditer(text):
            value = match.group(rule.group)
            if rule.id == "personal-email" and _safe_email(value):
                continue
            findings.append(
                Finding(
                    rule.id,
                    normalized,
                    _line_number(text, match.start()),
                    _fingerprint(value),
                    object_id,
                )
            )
    for match in SECRET_ASSIGNMENT.finditer(text):
        value = match.group(1)
        if _safe_assignment(value):
            continue
        findings.append(
            Finding(
                "assigned-secret",
                normalized,
                _line_number(text, match.start()),
                _fingerprint(value),
                object_id,
            )
        )
    return findings


def _forbidden_path(path: str, *, object_id: str | None = None) -> Finding | None:
    normalized = _normalized_path(path)
    lowered = normalized.casefold()
    basename = lowered.rsplit("/", 1)[-1]
    forbidden = (
        "/.secrets/" in f"/{lowered}/"
        or basename in {".env", "id_rsa", "id_ed25519"}
        or basename.endswith((".pem", ".p12", ".pfx"))
    )
    if not forbidden or basename in {".env.example", ".env.sample"}:
        return None
    return Finding("sensitive-path", normalized, 1, _fingerprint(normalized), object_id)


def _tracked_entries(staged: bool) -> Iterable[tuple[str, bytes, str | None]]:
    if staged:
        output = _run_git(["diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"])
    else:
        output = _run_git(["ls-files", "-z"])
    for raw_path in output.split(b"\x00"):
        if not raw_path:
            continue
        path = raw_path.decode("utf-8", errors="surrogateescape")
        if staged:
            data = _run_git(["show", f":{path}"])
        else:
            try:
                data = Path(path).read_bytes()
            except FileNotFoundError:
                continue
        yield path, data, None


def _history_paths() -> set[str]:
    output = _run_git(["log", "--all", "--name-only", "--pretty=format:"])
    return {
        line.decode("utf-8", errors="surrogateescape").strip()
        for line in output.splitlines()
        if line.strip()
    }


def _history_entries() -> Iterable[tuple[str, bytes, str | None]]:
    output = _run_git(["rev-list", "--objects", "--all"])
    object_paths: dict[str, str] = {}
    for line in output.splitlines():
        object_id, separator, raw_path = line.partition(b" ")
        if not separator or not raw_path:
            continue
        object_paths.setdefault(
            object_id.decode("ascii"),
            raw_path.decode("utf-8", errors="surrogateescape"),
        )
    commit_ids = [
        value.decode("ascii")
        for value in _run_git(["rev-list", "--all"]).splitlines()
        if value
    ]

    process = subprocess.Popen(
        ["git", "cat-file", "--batch"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert process.stdin is not None
    assert process.stdout is not None
    try:
        for object_id, path in object_paths.items():
            process.stdin.write(f"{object_id}\n".encode("ascii"))
            process.stdin.flush()
            header = process.stdout.readline().decode("ascii", errors="replace").strip()
            parts = header.split()
            if len(parts) != 3:
                raise ScanError(f"unexpected git cat-file response for {object_id[:12]}")
            _, object_type, size_text = parts
            size = int(size_text)
            data = process.stdout.read(size)
            process.stdout.read(1)
            if object_type == "blob":
                yield path, data, object_id
        for object_id in commit_ids:
            process.stdin.write(f"{object_id}\n".encode("ascii"))
            process.stdin.flush()
            header = process.stdout.readline().decode("ascii", errors="replace").strip()
            parts = header.split()
            if len(parts) != 3:
                raise ScanError(f"unexpected git cat-file response for {object_id[:12]}")
            _, object_type, size_text = parts
            size = int(size_text)
            data = process.stdout.read(size)
            process.stdout.read(1)
            if object_type == "commit":
                yield f"commit/{object_id[:12]}", data, object_id
    finally:
        process.stdin.close()
        process.wait(timeout=10)


def scan(mode: str) -> list[Finding]:
    findings: list[Finding] = []
    if mode == "history":
        for path in sorted(_history_paths()):
            finding = _forbidden_path(path)
            if finding:
                findings.append(finding)
        entries = _history_entries()
    else:
        entries = _tracked_entries(mode == "staged")

    for path, data, object_id in entries:
        path_finding = _forbidden_path(path, object_id=object_id)
        if path_finding:
            findings.append(path_finding)
        findings.extend(scan_text(path, data, object_id=object_id))

    unique = {
        (item.rule, item.path, item.line, item.fingerprint, item.object_id): item
        for item in findings
    }
    return sorted(unique.values(), key=lambda item: (item.path, item.line, item.rule))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scan tracked Git content without printing matched private values."
    )
    parser.add_argument(
        "--mode",
        choices=("tracked", "staged", "history"),
        default="tracked",
        help=(
            "tracked scans the worktree, staged scans the index, "
            "history scans every reachable blob"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        findings = scan(args.mode)
    except (OSError, ScanError, subprocess.SubprocessError) as error:
        print(f"privacy scan failed: {error}", file=sys.stderr)
        return 2
    if findings:
        print(f"privacy scan found {len(findings)} issue(s):", file=sys.stderr)
        grouped: dict[tuple[str, str], list[Finding]] = {}
        for finding in findings:
            grouped.setdefault((finding.rule, finding.fingerprint), []).append(finding)
        for matches in list(grouped.values())[:50]:
            first = matches[0]
            suffix = f" occurrences={len(matches)}" if len(matches) > 1 else ""
            print(f"  {first.display()}{suffix}", file=sys.stderr)
        if len(grouped) > 50:
            print(f"  ... {len(grouped) - 50} additional fingerprint group(s)", file=sys.stderr)
        return 1
    print(f"privacy scan passed ({args.mode})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
