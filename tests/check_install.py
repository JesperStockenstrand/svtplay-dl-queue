"""Check an installed helper the way a browser would use it.

Finds the Chrome registration (registry on Windows, a JSON file elsewhere),
starts the registered program, talks native messaging to it, adds a job and
waits for the background worker to process it. Used in CI after running the
installer; safe to run by hand too (it removes the job it adds).

    python tests/check_install.py
"""

import json
import os
import struct
import subprocess
import sys
import time

NAME = "svtplay_dl_queue"
ORIGIN = "chrome-extension://oonjepebfihcafficfecahlgfafinoee/"
TEST_URL = "https://www.svtplay.se/video/install-check"


def manifest_path():
    if os.name == "nt":
        import winreg
        key = r"Software\Google\Chrome\NativeMessagingHosts\%s" % NAME
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
            return winreg.QueryValue(k, None)
    if sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support/Google/Chrome")
    else:
        base = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"),
                            "google-chrome")
    return os.path.join(base, "NativeMessagingHosts", NAME + ".json")


def send(path, *messages):
    data = b""
    for m in messages:
        raw = json.dumps(m).encode()
        data += struct.pack("@I", len(raw)) + raw
    out = subprocess.run([path, ORIGIN], input=data, capture_output=True, timeout=60)
    if out.returncode != 0:
        sys.exit("Helper exited with %d: %s" % (out.returncode, out.stderr.decode(errors="replace")))
    replies, buf = [], out.stdout
    while buf:
        (n,) = struct.unpack("@I", buf[:4])
        replies.append(json.loads(buf[4:4 + n]))
        buf = buf[4 + n:]
    if len(replies) != len(messages):
        sys.exit("Expected %d replies, got: %r" % (len(messages), out.stdout[:500]))
    for r in replies:
        if not r.get("ok"):
            sys.exit("Helper error: %s" % r)
    return replies


def main():
    mpath = manifest_path()
    with open(mpath, encoding="utf-8") as f:
        manifest = json.load(f)
    assert manifest["name"] == NAME, manifest
    assert ORIGIN in manifest["allowed_origins"], manifest
    print("Manifest:", mpath)
    print("Helper:  ", manifest["path"])

    ping, cfg = send(manifest["path"], {"action": "ping"}, {"action": "get_config"})
    print("Version: ", ping["version"])
    print("svtplay-dl:", cfg["detected_binary"] or "not installed")

    # Add a job and wait for the background worker to pick it up. Without
    # svtplay-dl it fails with "not found"; with it, it starts downloading.
    job = send(manifest["path"], {"action": "add", "url": TEST_URL})[0]["job"]
    deadline = time.time() + 60
    status = None
    while time.time() < deadline:
        jobs = send(manifest["path"], {"action": "list"})[0]["jobs"]
        status = next((j for j in jobs if j["id"] == job["id"]), None)
        if status and status["status"] != "queued":
            break
        time.sleep(0.5)
    send(manifest["path"], {"action": "remove", "id": job["id"]})
    if not status or status["status"] == "queued":
        sys.exit("The background worker never picked up the job.")
    print("Worker:   picked up the job (%s: %s)" % (status["status"], status["message"]))
    print("OK")


if __name__ == "__main__":
    main()
