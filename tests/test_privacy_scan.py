from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "scripts" / "privacy_scan.py"
SPEC = importlib.util.spec_from_file_location("privacy_scan", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
privacy_scan = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = privacy_scan
SPEC.loader.exec_module(privacy_scan)


def test_scan_reports_a_secret_without_echoing_it() -> None:
    sample_value = "gh" + "p_" + "a" * 36

    findings = privacy_scan.scan_text("config.txt", f"TOKEN={sample_value}\n".encode())

    assert {finding.rule for finding in findings} == {"github-token", "assigned-secret"}
    assert all(sample_value not in finding.display() for finding in findings)


def test_scan_allows_placeholders_and_github_noreply_addresses() -> None:
    content = b"API_KEY=${API_KEY}\nauthor=123+name@users.noreply.github.com\n"

    assert privacy_scan.scan_text("config.example", content) == []


def test_scan_flags_local_machine_paths() -> None:
    path = "C:" + "\\" + "Users" + "\\" + "someone" + "\\" + "project"

    findings = privacy_scan.scan_text("notes.txt", path.encode())

    assert {finding.rule for finding in findings} == {
        "local-windows-user-path",
    }


def test_sensitive_file_names_are_rejected() -> None:
    assert privacy_scan._forbidden_path(".secrets/local.env") is not None
    assert privacy_scan._forbidden_path("config/.env") is not None
    assert privacy_scan._forbidden_path("config/.env.example") is None
