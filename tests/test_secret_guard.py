import shutil
import subprocess
import sys
from pathlib import Path


def test_commit_guard_blocks_private_file_and_credential(tmp_path):
    root = Path(__file__).resolve().parent.parent
    (tmp_path / "scripts").mkdir()
    shutil.copy(root / "scripts/check-secrets.py", tmp_path / "scripts/check-secrets.py")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    dummy = "test-only-credential-not-a-real-api-key"
    (tmp_path / ".env").write_text("OLLAMA_API_KEY=" + dummy + "\n")
    (tmp_path / "accidental.txt").write_text(dummy)
    subprocess.run(["git", "add", ".env", "accidental.txt"], cwd=tmp_path, check=True)
    result = subprocess.run(
        [sys.executable, "scripts/check-secrets.py", "--staged"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "environment file" in result.stderr and "credential detected" in result.stderr
    assert dummy not in result.stdout + result.stderr
