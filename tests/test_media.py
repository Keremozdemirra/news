import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "media.sh"


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


class MediaPull(unittest.TestCase):
    """scripts/media.sh pull: only a branch that does not exist counts as first use."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.remote = root / "remote.git"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(self.remote)], check=True)
        self.repo = root / "repo"
        git(root, "clone", "-q", str(self.remote), str(self.repo))
        git(self.repo, "config", "user.name", "t")
        git(self.repo, "config", "user.email", "t@example.com")
        (self.repo / "scripts").mkdir()
        shutil.copy(SCRIPT, self.repo / "scripts" / "media.sh")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "seed")
        git(self.repo, "push", "-q", "-u", "origin", "main")
        # a git that cannot fetch, as on a network error; every other command passes through
        self.shim = root / "shim"
        self.shim.mkdir()
        real = shutil.which("git")
        (self.shim / "git").write_text(f'#!/bin/sh\n[ "$1" = fetch ] && exit 1\nexec {real} "$@"\n')
        (self.shim / "git").chmod(0o755)

    def tearDown(self):
        self.tmp.cleanup()

    def pull(self, broken_fetch):
        env = dict(os.environ)
        if broken_fetch:
            env["PATH"] = f"{self.shim}:{env['PATH']}"
        return subprocess.run(["bash", "scripts/media.sh", "pull"], cwd=self.repo, env=env, capture_output=True, text=True)

    def test_first_use_gives_an_empty_checkout(self):
        r = self.pull(broken_fetch=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual([p.name for p in (self.repo / "media").iterdir() if p.name != ".git"], [])

    def test_failed_fetch_of_an_existing_branch_stops_the_job(self):
        git(self.repo, "push", "-q", "origin", "HEAD:refs/heads/media")
        r = self.pull(broken_fetch=True)
        self.assertEqual(r.returncode, 1)
        self.assertFalse((self.repo / "media").exists())

    def test_existing_branch_is_checked_out(self):
        git(self.repo, "push", "-q", "origin", "HEAD:refs/heads/media")
        self.assertEqual(self.pull(broken_fetch=False).returncode, 0)
        self.assertTrue((self.repo / "media").exists())
