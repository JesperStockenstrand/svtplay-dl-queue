#!/usr/bin/env python3
"""svtplay-dl Queue: native messaging host, background queue worker and CLI.

One file, three roles:

* **Native messaging host** (default): started by the browser. Reads
  length-prefixed JSON messages on stdin, answers on stdout, then exits.
* **Worker** (``--worker``): a detached background process that takes jobs
  from the queue file and runs svtplay-dl on them. It is started on demand
  and exits by itself when the queue has been idle for a while.
* **CLI** (``add``, ``list``, ...): manage the same queue from a terminal.

Only the Python standard library is used. Works on macOS and Linux.
"""

import contextlib
import fcntl
import glob
import json
import os
import re
import shlex
import shutil
import signal
import struct
import subprocess
import sys
import threading
import time
import uuid

APP = "svtplay-dl-queue"
VERSION = "0.1.0"
IDLE_EXIT_SECONDS = 30
POLL_SECONDS = 1.0
MAX_JOBS_KEPT = 200

ACTIVE = ("queued", "downloading")
FINISHED = ("done", "failed", "canceled")

DEFAULT_CONFIG = {
    "binary": "",  # empty = auto-detect svtplay-dl
    "download_dir": "~/Downloads/svtplay-dl",
    "extra_args": "",  # extra command line arguments, shell syntax
    "max_parallel": 1,
    "notify": True,
}


# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------

def data_dir():
    override = os.environ.get("SVTDL_QUEUE_HOME")
    if override:
        return override
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Application Support/" + APP)
    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, APP)


DATA = data_dir()
STATE_FILE = os.path.join(DATA, "queue.json")
CONFIG_FILE = os.path.join(DATA, "config.json")
QUEUE_LOCK = os.path.join(DATA, "queue.lock")
WORKER_LOCK = os.path.join(DATA, "worker.lock")
LOG_DIR = os.path.join(DATA, "logs")
WORKER_LOG = os.path.join(DATA, "worker.log")


def _ensure_dirs():
    os.makedirs(LOG_DIR, exist_ok=True)


def _read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return default


def _write_json(path, data):
    tmp = "%s.%d.tmp" % (path, os.getpid())
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------

def load_config():
    cfg = dict(DEFAULT_CONFIG)
    stored = _read_json(CONFIG_FILE, {})
    if isinstance(stored, dict):
        cfg.update({k: v for k, v in stored.items() if k in DEFAULT_CONFIG})
    return cfg


def save_config(changes):
    cfg = load_config()
    for key, value in changes.items():
        if key not in DEFAULT_CONFIG:
            raise ValueError("Unknown setting: %s" % key)
        if key == "max_parallel":
            value = int(value)
            if not 1 <= value <= 8:
                raise ValueError("Parallel downloads must be between 1 and 8")
        elif key == "notify":
            value = bool(value)
        else:
            value = str(value).strip()
            if key == "extra_args":
                shlex.split(value)  # raises ValueError on bad quoting
            if key == "download_dir" and not value:
                raise ValueError("Download folder can't be empty")
        cfg[key] = value
    _ensure_dirs()
    _write_json(CONFIG_FILE, cfg)
    return cfg


def search_path():
    """PATH used to find svtplay-dl and ffmpeg.

    Browsers start native hosts with a minimal PATH, so add the usual
    install locations (Homebrew, pipx, pip --user).
    """
    extra = [
        "/opt/homebrew/bin",
        "/usr/local/bin",
        os.path.expanduser("~/.local/bin"),
    ]
    extra += sorted(glob.glob(os.path.expanduser("~/Library/Python/*/bin")), reverse=True)
    parts = os.environ.get("PATH", "/usr/bin:/bin").split(os.pathsep)
    for p in extra:
        if p not in parts:
            parts.append(p)
    return os.pathsep.join(parts)


def find_binary(cfg):
    configured = os.path.expanduser(cfg.get("binary") or "")
    if configured:
        if os.path.isfile(configured) and os.access(configured, os.X_OK):
            return configured
        return None
    return shutil.which("svtplay-dl", path=search_path())


# --------------------------------------------------------------------------
# Queue state (a JSON file guarded by an flock)
# --------------------------------------------------------------------------

@contextlib.contextmanager
def queue():
    """Lock the queue, yield its state, and save it if no exception occurred."""
    _ensure_dirs()
    with open(QUEUE_LOCK, "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = _read_json(STATE_FILE, {"jobs": []})
        if not isinstance(state.get("jobs"), list):
            state = {"jobs": []}
        yield state
        _write_json(STATE_FILE, state)


def _find(state, job_id):
    for job in state["jobs"]:
        if job["id"] == job_id:
            return job
    raise KeyError("No job with id %s" % job_id)


def _valid_url(url):
    return isinstance(url, str) and re.match(r"^https?://[^\s]+$", url.strip()) is not None


def _pid_alive(pid):
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _kill_group(pid):
    if not pid:
        return
    try:
        os.killpg(pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        pass


def _prune(state):
    """Keep the job list from growing forever: drop the oldest finished jobs."""
    finished = [j for j in state["jobs"] if j["status"] in FINISHED]
    excess = len(state["jobs"]) - MAX_JOBS_KEPT
    if excess > 0:
        drop = {j["id"] for j in sorted(finished, key=lambda j: j.get("finished") or 0)[:excess]}
        state["jobs"] = [j for j in state["jobs"] if j["id"] not in drop]


# --------------------------------------------------------------------------
# Commands (shared by the native host and the CLI)
# --------------------------------------------------------------------------

def cmd_add(url, title=None, all_episodes=False):
    if not _valid_url(url):
        raise ValueError("Not a valid http(s) URL: %r" % (url,))
    url = url.strip()
    all_episodes = bool(all_episodes)
    with queue() as state:
        for job in state["jobs"]:
            if job["url"] == url and job["all_episodes"] == all_episodes and job["status"] in ACTIVE:
                return {"duplicate": True, "job": job}
        job = {
            "id": uuid.uuid4().hex[:12],
            "url": url,
            "title": (title or "").strip() or url,
            "all_episodes": all_episodes,
            "status": "queued",
            "progress": None,
            "message": "",
            "added": time.time(),
            "started": None,
            "finished": None,
            "pid": None,
        }
        state["jobs"].append(job)
        _prune(state)
    ensure_worker()
    return {"duplicate": False, "job": job}


def cmd_list():
    cfg = load_config()
    with queue() as state:
        jobs = state["jobs"]
    return {
        "jobs": jobs,
        "binary": find_binary(cfg),
        "download_dir": os.path.expanduser(cfg["download_dir"]),
        "worker_running": worker_running(),
        "version": VERSION,
    }


def cmd_cancel(job_id):
    with queue() as state:
        job = _find(state, job_id)
        if job["status"] not in ACTIVE:
            return {"job": job}
        pid = job.get("pid")
        job.update(status="canceled", finished=time.time(), message="Canceled", pid=None)
    if pid:
        _kill_group(pid)
    return {"job": job}


def cmd_remove(job_id):
    pid = None
    with queue() as state:
        job = _find(state, job_id)
        if job["status"] == "downloading":
            pid = job.get("pid")
        state["jobs"].remove(job)
    if pid:
        _kill_group(pid)
    return {}


def cmd_retry(job_id):
    with queue() as state:
        job = _find(state, job_id)
        if job["status"] in FINISHED:
            job.update(status="queued", progress=None, message="", started=None,
                       finished=None, pid=None, added=time.time())
            # Move it to the end of the queue.
            state["jobs"].remove(job)
            state["jobs"].append(job)
    ensure_worker()
    return {"job": job}


def cmd_move(job_id, delta):
    """Move a queued job up (delta < 0) or down (delta > 0) among queued jobs."""
    with queue() as state:
        jobs = state["jobs"]
        job = _find(state, job_id)
        if job["status"] != "queued":
            return {}
        queued = [i for i, j in enumerate(jobs) if j["status"] == "queued"]
        pos = queued.index(jobs.index(job))
        new_pos = max(0, min(len(queued) - 1, pos + (1 if delta > 0 else -1)))
        if new_pos != pos:
            a, b = queued[pos], queued[new_pos]
            jobs[a], jobs[b] = jobs[b], jobs[a]
    return {}


def cmd_clear():
    with queue() as state:
        state["jobs"] = [j for j in state["jobs"] if j["status"] not in FINISHED]
    return {}


def cmd_get_config():
    cfg = load_config()
    return {"config": cfg, "detected_binary": find_binary(dict(cfg, binary=""))}


def cmd_set_config(changes):
    if not isinstance(changes, dict):
        raise ValueError("config must be an object")
    cfg = save_config(changes)
    return {"config": cfg, "detected_binary": find_binary(dict(cfg, binary=""))}


def cmd_open_folder():
    folder = os.path.expanduser(load_config()["download_dir"])
    os.makedirs(folder, exist_ok=True)
    opener = "open" if sys.platform == "darwin" else "xdg-open"
    subprocess.Popen([opener, folder], stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)
    return {}


def dispatch(msg):
    if not isinstance(msg, dict):
        raise ValueError("Message must be a JSON object")
    action = msg.get("action")
    if action == "ping":
        return {"version": VERSION}
    if action == "add":
        return cmd_add(msg.get("url"), msg.get("title"), msg.get("all_episodes", False))
    if action == "list":
        return cmd_list()
    if action == "cancel":
        return cmd_cancel(msg.get("id"))
    if action == "remove":
        return cmd_remove(msg.get("id"))
    if action == "retry":
        return cmd_retry(msg.get("id"))
    if action == "move":
        return cmd_move(msg.get("id"), int(msg.get("delta", 0)))
    if action == "clear":
        return cmd_clear()
    if action == "get_config":
        return cmd_get_config()
    if action == "set_config":
        return cmd_set_config(msg.get("config"))
    if action == "open_folder":
        return cmd_open_folder()
    raise ValueError("Unknown action: %r" % (action,))


# --------------------------------------------------------------------------
# Native messaging
# --------------------------------------------------------------------------

def read_message(stream):
    header = stream.read(4)
    if len(header) < 4:
        return None
    (length,) = struct.unpack("@I", header)
    return json.loads(stream.read(length).decode("utf-8"))


def write_message(stream, obj):
    data = json.dumps(obj).encode("utf-8")
    stream.write(struct.pack("@I", len(data)))
    stream.write(data)
    stream.flush()


def run_native_host():
    stdin, stdout = sys.stdin.buffer, sys.stdout.buffer
    # Anything printed by accident must not corrupt the protocol stream.
    sys.stdout = sys.stderr
    while True:
        try:
            msg = read_message(stdin)
        except ValueError as e:
            write_message(stdout, {"ok": False, "error": "Bad message: %s" % e})
            continue
        if msg is None:
            return
        try:
            reply = dispatch(msg)
            reply["ok"] = True
        except Exception as e:  # report every error back to the extension
            reply = {"ok": False, "error": str(e)}
        write_message(stdout, reply)


# --------------------------------------------------------------------------
# Worker
# --------------------------------------------------------------------------

def worker_running():
    _ensure_dirs()
    with open(WORKER_LOCK, "a") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(f, fcntl.LOCK_UN)
        return False


def ensure_worker():
    if worker_running():
        return
    log = open(WORKER_LOG, "a")
    subprocess.Popen(
        [sys.executable, os.path.abspath(__file__), "--worker"],
        stdin=subprocess.DEVNULL, stdout=log, stderr=log,
        start_new_session=True, close_fds=True,
    )
    log.close()


PROGRESS_RE = re.compile(r"\[(\d+)/(\d+)\]")
PERCENT_RE = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*%")
OUTFILE_RE = re.compile(r"Outfile:\s*(.+)$")


class Download:
    """A running svtplay-dl process plus a thread that follows its output."""

    def __init__(self, job, binary, cfg):
        self.progress = None
        self.last_line = ""
        self.outfile = None
        dest = os.path.expanduser(cfg["download_dir"])
        os.makedirs(dest, exist_ok=True)
        cmd = [binary] + shlex.split(cfg.get("extra_args") or "")
        if job["all_episodes"]:
            cmd.append("--all-episodes")
        cmd.append(job["url"])
        env = dict(os.environ, PATH=search_path(), PYTHONUNBUFFERED="1")
        self.log_path = os.path.join(LOG_DIR, job["id"] + ".log")
        self.proc = subprocess.Popen(
            cmd, cwd=dest, env=env, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        self.thread = threading.Thread(target=self._follow, daemon=True)
        self.thread.start()

    def _follow(self):
        buf = ""
        with open(self.log_path, "ab") as log:
            fd = self.proc.stdout.fileno()
            while True:
                chunk = os.read(fd, 4096)
                if not chunk:
                    break
                log.write(chunk)
                log.flush()
                buf += chunk.decode("utf-8", "replace")
                parts = re.split(r"[\r\n]", buf)
                buf = parts.pop()
                for line in parts:
                    self._line(line)
        if buf:
            self._line(buf)

    def _line(self, line):
        line = line.strip()
        if not line:
            return
        m = PROGRESS_RE.search(line)
        if m and int(m.group(2)) > 0:
            self.progress = min(100.0, 100.0 * int(m.group(1)) / int(m.group(2)))
            return
        m = PERCENT_RE.search(line)
        if m and "ETA" in line:
            self.progress = min(100.0, float(m.group(1)))
            return
        m = OUTFILE_RE.search(line)
        if m:
            self.outfile = os.path.basename(m.group(1).strip())
        self.last_line = line[:300]


def notify(title, message):
    try:
        if sys.platform == "darwin":
            subprocess.run(
                ["osascript", "-e", "on run argv", "-e",
                 "display notification (item 1 of argv) with title (item 2 of argv)",
                 "-e", "end run", message, title],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, timeout=10,
            )
        elif shutil.which("notify-send"):
            subprocess.run(["notify-send", title, message], timeout=10,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def run_worker():
    _ensure_dirs()
    lock = open(WORKER_LOCK, "a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return  # another worker is already running

    # Recover from a crash: anything marked "downloading" isn't ours.
    with queue() as state:
        for job in state["jobs"]:
            if job["status"] == "downloading":
                if _pid_alive(job.get("pid")):
                    _kill_group(job["pid"])
                job.update(status="queued", pid=None, progress=None,
                           message="Restarted after interruption")

    running = {}
    idle_since = None
    while True:
        cfg = load_config()
        notes = []
        with queue() as state:
            ids = {j["id"] for j in state["jobs"]}

            for job_id, dl in list(running.items()):
                rc = dl.proc.poll()
                if job_id not in ids:  # removed from the queue
                    if rc is None:
                        _kill_group(dl.proc.pid)
                    else:
                        running.pop(job_id)
                    continue
                job = _find(state, job_id)
                if dl.outfile:
                    job["title"] = dl.outfile
                if rc is None:
                    if job["status"] == "canceled":
                        _kill_group(dl.proc.pid)
                    else:
                        job["progress"] = dl.progress
                        job["message"] = dl.last_line
                    continue
                dl.thread.join(2)
                running.pop(job_id)
                if job["status"] == "canceled":
                    continue
                job["finished"] = time.time()
                job["pid"] = None
                if rc == 0:
                    job.update(status="done", progress=100.0, message="Finished")
                    notes.append(("Download finished", job["title"]))
                else:
                    msg = dl.last_line or "svtplay-dl exited with code %d" % rc
                    job.update(status="failed", message=msg)
                    notes.append(("Download failed", "%s: %s" % (job["title"], msg)))

            slots = int(cfg.get("max_parallel") or 1) - len(running)
            for job in state["jobs"]:
                if slots <= 0:
                    break
                if job["status"] != "queued":
                    continue
                binary = find_binary(cfg)
                if not binary:
                    job.update(status="failed", finished=time.time(),
                               message="svtplay-dl not found. Install it or set its "
                                       "path in the extension settings.")
                    continue
                try:
                    dl = Download(job, binary, cfg)
                except Exception as e:
                    job.update(status="failed", finished=time.time(),
                               message="Could not start svtplay-dl: %s" % e)
                    continue
                running[job["id"]] = dl
                job.update(status="downloading", started=time.time(),
                           pid=dl.proc.pid, progress=None, message="Starting…")
                slots -= 1

            busy = bool(running) or any(j["status"] == "queued" for j in state["jobs"])

        if cfg.get("notify"):
            for title, message in notes:
                notify(title, message)

        if busy:
            idle_since = None
        else:
            idle_since = idle_since or time.time()
            if time.time() - idle_since > IDLE_EXIT_SECONDS:
                return
        time.sleep(POLL_SECONDS)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

USAGE = """svtplay-dl Queue %s

Usage:
  svtdl_queue.py add URL [--all-episodes]   add a download to the queue
  svtdl_queue.py list                       show the queue
  svtdl_queue.py cancel ID | retry ID | remove ID
  svtdl_queue.py clear                      remove finished downloads
  svtdl_queue.py config [KEY=VALUE ...]     show or change settings
  svtdl_queue.py --worker                   run the queue worker (normally automatic)

Data folder: %s
""" % (VERSION, DATA)


def run_cli(args):
    cmd, rest = args[0], args[1:]
    if cmd in ("-h", "--help", "help"):
        print(USAGE)
    elif cmd == "--version":
        print(VERSION)
    elif cmd == "add" and rest:
        res = cmd_add(rest[0], all_episodes="--all-episodes" in rest)
        print(("Already queued: " if res["duplicate"] else "Queued: ") + res["job"]["id"])
    elif cmd == "list":
        info = cmd_list()
        if not info["jobs"]:
            print("The queue is empty.")
        for j in info["jobs"]:
            pct = " %3.0f%%" % j["progress"] if j.get("progress") is not None else ""
            print("%s  %-11s%s  %s" % (j["id"], j["status"], pct, j["title"]))
            if j.get("message") and j["status"] in ("failed", "downloading"):
                print("              " + j["message"])
    elif cmd in ("cancel", "retry", "remove") and rest:
        {"cancel": cmd_cancel, "retry": cmd_retry, "remove": cmd_remove}[cmd](rest[0])
    elif cmd == "clear":
        cmd_clear()
    elif cmd == "config":
        changes = {}
        for item in rest:
            key, _, value = item.partition("=")
            changes[key] = value
        cfg = save_config(changes) if changes else load_config()
        print(json.dumps(cfg, indent=2))
    else:
        print(USAGE, file=sys.stderr)
        return 2
    return 0


CLI_COMMANDS = {"add", "list", "cancel", "retry", "remove", "clear", "config",
                "help", "-h", "--help", "--version"}


def main(argv):
    if len(argv) > 1 and argv[1] == "--worker":
        run_worker()
        return 0
    if len(argv) > 1 and argv[1] in CLI_COMMANDS:
        try:
            return run_cli(argv[1:])
        except (ValueError, KeyError) as e:
            print("Error: %s" % e, file=sys.stderr)
            return 1
    if len(argv) == 1 and sys.stdin.isatty():
        print(USAGE)
        return 0
    # Browsers pass the extension origin (Chrome) or manifest path (Firefox).
    run_native_host()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
