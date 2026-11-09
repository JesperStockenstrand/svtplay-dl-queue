"""End-to-end tests: talk to the native host over stdin/stdout like a browser
would, with a fake svtplay-dl, and check that the worker processes the queue.

Run with:  python3 -m unittest discover tests
"""

import json
import os
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOST = os.path.join(ROOT, "host", "svtdl_queue.py")
FAKE = os.path.join(ROOT, "tests", "fake_downloader.py")
WINDOWS = os.name == "nt"

sys.path.insert(0, os.path.dirname(HOST))
from svtdl_queue import _kill_group, _pid_alive  # noqa: E402


def fake_binary(folder):
    """The fake svtplay-dl as something the helper can run directly."""
    if not WINDOWS:
        os.chmod(FAKE, 0o755)
        return FAKE
    path = os.path.join(folder, "fake-svtplay-dl.cmd")
    with open(path, "w") as f:
        f.write('@"%s" "%s" %%*\n' % (sys.executable, FAKE))
    return path


class HostTest(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="svtdl-test-")
        self.downloads = os.path.join(self.home, "downloads")
        self.env = dict(os.environ, SVTDL_QUEUE_HOME=self.home)
        reply = self.send({"action": "set_config", "config": {
            "binary": fake_binary(self.home), "download_dir": self.downloads, "notify": False,
            "subtitles": "embedded", "extra_args": "--audio-language swe",
        }})
        self.assertTrue(reply["ok"], reply)
        self.assertTrue(reply["binary_ok"])
        self.assertEqual(reply["command"], ["--merge-subtitle", "--audio-language", "swe"])

    def tearDown(self):
        # Stop downloads and the worker before deleting its folder.
        try:
            for job in self.send({"action": "list"})["jobs"]:
                if job["status"] in ("queued", "downloading"):
                    self.send({"action": "cancel", "id": job["id"]})
        except Exception:
            pass
        try:
            with open(os.path.join(self.home, "worker.pid")) as f:
                pid = int(f.read())
        except (OSError, ValueError):
            pid = None
        if pid:
            if WINDOWS:
                _kill_group(pid)
            else:
                os.kill(pid, signal.SIGTERM)
            deadline = time.time() + 5
            while _pid_alive(pid) and time.time() < deadline:
                time.sleep(0.05)
        shutil.rmtree(self.home, ignore_errors=True)

    def send(self, *messages):
        data = b""
        for m in messages:
            raw = json.dumps(m).encode()
            data += struct.pack("@I", len(raw)) + raw
        out = subprocess.run(
            [sys.executable, HOST, "chrome-extension://test/"],
            input=data, capture_output=True, env=self.env, timeout=20, check=True,
        ).stdout
        replies = []
        while out:
            (n,) = struct.unpack("@I", out[:4])
            replies.append(json.loads(out[4:4 + n]))
            out = out[4 + n:]
        self.assertEqual(len(replies), len(messages))
        return replies[0] if len(replies) == 1 else replies

    def wait_for(self, predicate, timeout=20):
        deadline = time.time() + timeout
        while time.time() < deadline:
            jobs = self.send({"action": "list"})["jobs"]
            if predicate(jobs):
                return jobs
            time.sleep(0.2)
        self.fail("Timed out; jobs: %s" % json.dumps(jobs, indent=1))

    def test_ping_and_bad_action(self):
        ping, bad = self.send({"action": "ping"}, {"action": "nope"})
        self.assertTrue(ping["ok"])
        self.assertFalse(bad["ok"])
        self.assertIn("Unknown action", bad["error"])

    def test_invalid_settings_are_rejected(self):
        for change in ({"resolution": "999"}, {"max_parallel": 0}, {"download_dir": " "},
                       {"extra_args": "--x 'unclosed"}, {"no_such_setting": 1}):
            reply = self.send({"action": "set_config", "config": change})
            self.assertFalse(reply["ok"], change)
        # Nothing was changed by the rejected attempts.
        self.assertEqual(self.send({"action": "get_config"})["config"]["max_parallel"], 1)

    def test_rejects_non_http_urls(self):
        reply = self.send({"action": "add", "url": "file:///etc/passwd"})
        self.assertFalse(reply["ok"])

    def test_queue_runs_in_order_and_reports_results(self):
        ok = self.send({"action": "add", "url": "https://example.com/ok", "title": "Good",
                        "all_episodes": True})
        bad = self.send({"action": "add", "url": "https://example.com/fail"})
        dup = self.send({"action": "add", "url": "https://example.com/ok", "all_episodes": True})
        self.assertTrue(dup["duplicate"])

        jobs = self.wait_for(lambda js: all(j["status"] in ("done", "failed") for j in js))
        by_id = {j["id"]: j for j in jobs}
        good, failed = by_id[ok["job"]["id"]], by_id[bad["job"]["id"]]

        self.assertEqual(good["status"], "done")
        self.assertEqual(good["title"], "fake-video.mp4")
        self.assertLessEqual(good["finished"], failed["started"])  # one at a time
        self.assertEqual(failed["status"], "failed")
        self.assertIn("not supported", failed["message"])

        with open(os.path.join(self.downloads, "fake-video.mp4")) as f:
            args = f.read()
        self.assertEqual(
            args, "--merge-subtitle --all-episodes --audio-language swe https://example.com/ok")

        # Retry puts it back in the queue; clear removes finished jobs.
        self.send({"action": "retry", "id": failed["id"]})
        self.wait_for(lambda js: by_status(js, failed["id"]) == "failed")
        self.send({"action": "clear"})
        self.assertEqual(self.send({"action": "list"})["jobs"], [])

    def test_cancel_running_and_reorder_queued(self):
        a = self.send({"action": "add", "url": "https://example.com/slow-a"})["job"]["id"]
        b = self.send({"action": "add", "url": "https://example.com/slow-b"})["job"]["id"]
        c = self.send({"action": "add", "url": "https://example.com/slow-c"})["job"]["id"]
        self.wait_for(lambda js: by_status(js, a) == "downloading")

        self.send({"action": "move", "id": c, "delta": -1})
        order = [j["id"] for j in self.send({"action": "list"})["jobs"]]
        self.assertLess(order.index(c), order.index(b))

        self.send({"action": "cancel", "id": a})
        jobs = self.wait_for(lambda js: by_status(js, c) == "downloading")
        self.assertEqual(by_status(jobs, a), "canceled")
        self.assertEqual(by_status(jobs, b), "queued")

        self.send({"action": "remove", "id": c})
        self.wait_for(lambda js: by_status(js, b) == "downloading")


def by_status(jobs, job_id):
    for j in jobs:
        if j["id"] == job_id:
            return j["status"]
    return None


if __name__ == "__main__":
    unittest.main()
