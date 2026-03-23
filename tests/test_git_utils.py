import os
import subprocess
import tempfile
import unittest
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from src.utils.git import get_git_diff_fingerprint


@contextmanager
def _temporary_cwd(path: str) -> Generator[None, None, None]:
    original_cwd = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(original_cwd)


class GitFingerprintTests(unittest.TestCase):
    def test_git_diff_fingerprint_changes_when_untracked_file_contents_change(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, _temporary_cwd(temp_dir):
            subprocess.run(["git", "init"], check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "Test User"], check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], check=True, capture_output=True)

            tracked_file = Path("tracked.txt")
            tracked_file.write_text("tracked\n", encoding="utf-8")
            subprocess.run(["git", "add", "tracked.txt"], check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "initial"], check=True, capture_output=True)

            untracked_file = Path("scratch.py")
            untracked_file.write_text("print('first')\n", encoding="utf-8")
            first_fingerprint = get_git_diff_fingerprint()

            untracked_file.write_text("print('second')\n", encoding="utf-8")
            second_fingerprint = get_git_diff_fingerprint()

        self.assertIsNotNone(first_fingerprint)
        self.assertIsNotNone(second_fingerprint)
        self.assertNotEqual(first_fingerprint, second_fingerprint)
