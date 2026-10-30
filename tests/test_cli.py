import os
import subprocess
import sys
from pathlib import Path

from interview_coach.cli import main
from interview_coach.paths import default_db_path


def test_default_database_is_under_data(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("INTERVIEW_COACH_DB", raising=False)
    assert default_db_path() == tmp_path / "data" / "coach.sqlite"


def test_demo_command_prints_a_full_week(tmp_path):
    db = tmp_path / "demo.sqlite"
    code = main(["demo", "--db", str(db)])
    assert code == 0
    assert db.exists()


def test_demo_output(tmp_path, capsys):
    code = main(["demo", "--db", str(tmp_path / "demo.sqlite")])
    assert code == 0
    output = capsys.readouterr().out
    assert "Interview Study Coach demo" in output
    assert "LLM: offline (no API key)" in output
    assert "daily_minutes: 30" in output
    assert "Day 1" in output
    assert "Day 7" in output
    assert "acceptance:" in output
    assert "policy: shrink" in output
    assert "daily_minutes: 25" in output
    assert "Demo complete" in output


def test_cli_flow(tmp_path, capsys):
    db = ["--db", str(tmp_path / "coach.sqlite")]
    assert main([*db, "profile", "init", "--name", "Ada", "--role", "backend"]) == 0
    assert main([*db, "profile", "show"]) == 0
    assert "daily_minutes: 30" in capsys.readouterr().out
    assert main([*db, "assess", "--questions", "3", "--topics", "python", "--answers", "0,0,0"]) == 0
    assert main([*db, "plan", "--start", "2026-02-02"]) == 0
    assert main([*db, "log", "--day", "1", "--minutes", "30", "--quiz", "8/10"]) == 0
    assert main([*db, "log", "--day", "2", "--minutes", "0", "--missed"]) == 0
    assert main([*db, "progress"]) == 0
    progress = capsys.readouterr().out
    assert "reported_completion: 50%" in progress
    assert main([*db, "replan", "--start", "2026-02-09"]) == 0
    assert "policy: shrink" in capsys.readouterr().out
    assert main([*db, "ask", "what should I study today"]) == 0
    assert "Acceptance criteria" in capsys.readouterr().out


def test_missing_profile_is_an_error(tmp_path, capsys):
    code = main(["--db", str(tmp_path / "missing.sqlite"), "plan"])
    assert code == 1
    assert "No profile" in capsys.readouterr().err


def test_module_entrypoint_demo(tmp_path):
    db = tmp_path / "demo.sqlite"
    root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join([str(root / "src"), env.get("PYTHONPATH", "")])
    completed = subprocess.run(
        [sys.executable, "-m", "interview_coach", "demo", "--db", str(db)],
        cwd=root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "Demo complete" in completed.stdout
