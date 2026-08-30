from pathlib import Path

from scripts.report_ci_failure import _escape_workflow_command, report_failure


def test_escape_workflow_command() -> None:
    assert _escape_workflow_command("50%\r\nnext") == "50%25%0D%0Anext"


def test_report_failure_uses_last_meaningful_lines(
    tmp_path: Path,
    capsys,
) -> None:
    log_path = tmp_path / "release-build.log"
    log_path.write_text("old\n\nfirst error\nlast error\n", encoding="utf-8")

    assert report_failure(log_path, limit=2) == 1

    output = capsys.readouterr().out
    assert "first error" in output
    assert "last error" in output
    assert "old" not in output
    assert "::error file=" in output
