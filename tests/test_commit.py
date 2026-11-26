import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "commit.sh"


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


class CommitScript(unittest.TestCase):
    """scripts/commit.sh against a real bare remote: a status update must survive a rebase conflict."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.remote = root / "remote.git"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(self.remote)], check=True)
        self.a, self.b = root / "a", root / "b"
        git(root, "clone", "-q", str(self.remote), str(self.a))
        git(self.a, "config", "user.name", "t")
        git(self.a, "config", "user.email", "t@example.com")
        for n in (1, 2):
            (self.a / "queue" / f"p{n}").mkdir(parents=True)
            (self.a / "queue" / f"p{n}" / "post.json").write_text(f'{{"status": "queued", "n": {n}}}\n')
        (self.a / "state").mkdir()
        (self.a / "state" / "replies.json").write_text("{}\n")
        git(self.a, "add", "-A")
        git(self.a, "commit", "-q", "-m", "seed")
        git(self.a, "push", "-q", "-u", "origin", "main")
        git(root, "clone", "-q", str(self.remote), str(self.b))
        git(self.b, "config", "user.name", "other")
        git(self.b, "config", "user.email", "o@example.com")

    def tearDown(self):
        self.tmp.cleanup()

    def run_script(self):
        env = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null", COMMIT_RETRY_PAUSE="0")
        return subprocess.run(["bash", str(SCRIPT), "desk: publish test"], cwd=self.a, env=env,
                              capture_output=True, text=True)

    def other_pushes(self, path, text):
        (self.b / path).write_text(text)
        git(self.b, "add", "-A")
        git(self.b, "commit", "-q", "-m", "other run")
        git(self.b, "push", "-q", "origin", "main")

    def remote_file(self, path):
        return subprocess.run(["git", "--git-dir", str(self.remote), "show", f"main:{path}"],
                              capture_output=True, text=True).stdout

    def test_conflict_in_queue_keeps_this_runs_version(self):
        self.other_pushes("queue/p1/post.json", '{"status": "failed", "n": 1}\n')
        (self.a / "queue" / "p1" / "post.json").write_text('{"status": "published", "n": 1}\n')
        r = self.run_script()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("published", self.remote_file("queue/p1/post.json"))
        self.assertEqual(git(self.a, "status", "--porcelain"), "")

    def test_other_runs_unrelated_files_survive(self):
        self.other_pushes("queue/p2/post.json", '{"status": "vetoed", "n": 2}\n')
        (self.a / "queue" / "p1" / "post.json").write_text('{"status": "published", "n": 1}\n')
        r = self.run_script()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("published", self.remote_file("queue/p1/post.json"))
        self.assertIn("vetoed", self.remote_file("queue/p2/post.json"))

    def test_conflict_in_state_keeps_this_runs_version(self):
        self.other_pushes("state/replies.json", '{"x": 1}\n')
        (self.a / "state" / "replies.json").write_text('{"x": 2}\n')
        self.assertEqual(self.run_script().returncode, 0)
        self.assertIn('"x": 2', self.remote_file("state/replies.json"))

    def test_modify_delete_conflict_falls_back_to_this_runs_files(self):
        # upstream deleted the post this run changed: -X theirs cannot settle that, the fallback must
        (self.b / "queue" / "p1" / "post.json").unlink()
        git(self.b, "add", "-A")
        git(self.b, "commit", "-q", "-m", "delete")
        git(self.b, "push", "-q", "origin", "main")
        (self.a / "queue" / "p1" / "post.json").write_text('{"status": "published", "n": 1}\n')
        r = self.run_script()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("published", self.remote_file("queue/p1/post.json"))

    def test_nothing_to_commit(self):
        r = self.run_script()
        self.assertEqual(r.returncode, 0)
        self.assertIn("nothing to commit", r.stdout)

    def test_unreachable_remote_fails_loudly(self):
        (self.a / "queue" / "p1" / "post.json").write_text('{"status": "published", "n": 1}\n')
        shutil.rmtree(self.remote)
        r = self.run_script()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("NOT saved", r.stderr)


if __name__ == "__main__":
    unittest.main()
