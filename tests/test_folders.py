"""Tests for saving films and series in separate folders (host/svtdl_folders.py)."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["SVTDL_QUEUE_HOME"] = tempfile.mkdtemp(prefix="svtdl-folders-test-")
sys.path.insert(0, os.path.join(ROOT, "host"))

import svtdl_queue as q  # noqa: E402

# A tiny stand-in for svtplay-dl with the same structure as the real one:
# modules import formatname at load time, and main() writes one file.
FAKE_PACKAGE = {
    "svtplay_dl/__init__.py": """
        import sys
        from svtplay_dl.utils.output import formatname

        def main():
            url = sys.argv[-1]
            output = {"title": "My Show", "ext": "mp4"}
            if "episode" in url:
                output.update(season="01", episode="05")
            name = formatname(output, None)
            name.parent.mkdir(parents=True, exist_ok=True)
            name.write_text(" ".join(sys.argv[1:]))
            print("INFO: Outfile: %s" % name.name)
            return 0
    """,
    "svtplay_dl/utils/__init__.py": "",
    "svtplay_dl/utils/text.py": """
        def filenamify(title):
            return title.lower().replace(" ", ".")
    """,
    "svtplay_dl/utils/output.py": """
        import pathlib
        from svtplay_dl.utils.text import filenamify

        def formatname(output, config):
            name = filenamify(output["title"])
            if output.get("season"):
                name += ".s%se%s" % (output["season"], output["episode"])
            return pathlib.Path(name + "." + output["ext"])
    """,
}


def make_fake_svtplay_dl(folder):
    """A virtual environment with the fake package, and a file that points to
    its Python the way an installed svtplay-dl does (#! line or .exe launcher)."""
    venv = os.path.join(folder, "venv")
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", venv], check=True)
    python = os.path.join(venv, "Scripts" if os.name == "nt" else "bin",
                          "python.exe" if os.name == "nt" else "python")
    site = subprocess.run([python, "-c", "import sysconfig; print(sysconfig.get_paths()['purelib'])"],
                          capture_output=True, text=True, check=True).stdout.strip()
    for rel, code in FAKE_PACKAGE.items():
        path = os.path.join(site, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(textwrap.dedent(code))
    if os.name == "nt":
        binary = os.path.join(folder, "svtplay-dl.exe")
        with open(binary, "wb") as f:
            f.write(b"MZ" + b"\0" * 64 + b'#!"' + python.encode() + b'"\r\nPK\x03\x04')
    else:
        binary = os.path.join(folder, "svtplay-dl")
        with open(binary, "w") as f:
            f.write("#!%s\n" % python)
        os.chmod(binary, 0o755)
    return binary


class SeparateFoldersTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="svtdl-fake-")
        cls.binary = make_fake_svtplay_dl(cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        self.downloads = tempfile.mkdtemp(prefix="svtdl-dl-", dir=self.tmp)
        self.series = os.path.join(self.tmp, "elsewhere", "Series")

    def run_download(self, url, **settings):
        cfg = dict(q.DEFAULT_CONFIG, download_dir=self.downloads, **settings)
        cmd, env, ok = q.download_command(cfg, self.binary, False, url)
        self.assertTrue(ok)
        out = subprocess.run(cmd, cwd=self.downloads, env=dict(os.environ, **env),
                             capture_output=True, text=True, timeout=60)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertNotIn("WARNING", out.stdout)
        return out.stdout

    def files(self, root):
        found = []
        for dirpath, _, names in os.walk(root):
            found += [os.path.relpath(os.path.join(dirpath, n), root).replace(os.sep, "/")
                      for n in names]
        return sorted(found)

    def test_films_and_series_go_to_their_folders(self):
        settings = dict(separate_folders=True, movies_dir="Movies", series_dir=self.series)
        self.run_download("https://example.com/film", **settings)
        self.run_download("https://example.com/episode", **settings)
        self.assertEqual(self.files(self.downloads), ["Movies/my.show.mp4"])
        self.assertEqual(self.files(self.series), ["my.show.s01e05.mp4"])

    def test_show_folders_inside_the_series_folder(self):
        self.run_download("https://example.com/episode", separate_folders=True,
                          series_dir="TV", subfolder=True)
        self.assertEqual(self.files(self.downloads), ["TV/my.show/my.show.s01e05.mp4"])

    def test_svtplay_dl_gets_no_subfolder_option(self):
        # The hook makes the show folders; svtplay-dl's own --subfolder would
        # add a "movies" folder inside the films folder.
        self.run_download("https://example.com/film", separate_folders=True, subfolder=True)
        self.assertEqual(self.files(self.downloads), ["Movies/my.show.mp4"])
        with open(os.path.join(self.downloads, "Movies", "my.show.mp4")) as f:
            self.assertNotIn("--subfolder", f.read())

    def test_without_a_python_svtplay_dl_it_runs_directly(self):
        standalone = os.path.join(self.tmp, "standalone.exe")
        with open(standalone, "wb") as f:
            f.write(b"MZ" + b"\0" * 64)
        cfg = dict(q.DEFAULT_CONFIG, download_dir=self.downloads, separate_folders=True)
        cmd, env, ok = q.download_command(cfg, standalone, False, "https://example.com/x")
        self.assertEqual((cmd[0], env, ok), (standalone, {}, False))


REAL_SNIPPET = r"""
import json, pathlib, sys
sys.path.insert(0, sys.argv[1])
import svtplay_dl
import svtdl_folders
from svtplay_dl.utils import output as out
from svtplay_dl.utils.parser import Options, FILENAME
from svtplay_dl.fetcher import hls

replaced = svtdl_folders.install({"movies": "/M", "series": "/S", "show_folders": True})
c = Options()
c.set("filename", FILENAME)
names = [str(out.formatname(o, c)) for o in json.loads(sys.argv[2])]
print(json.dumps({"replaced": replaced, "names": names,
                  "fetchers_use_hook": hls.formatname is out.formatname}))
"""


def _real_python():
    binary = q.find_binary(dict(q.DEFAULT_CONFIG))
    return q._interpreter_for(os.path.realpath(binary)) if binary else None


@unittest.skipUnless(_real_python(), "svtplay-dl (Python install) not found")
class RealSvtplayDlTest(unittest.TestCase):
    """Install the hook in the real svtplay-dl and check the paths it builds."""

    def test_paths(self):
        videos = [
            dict(title="Mästarnas mästare", season="16", episode="3", episodename="Finalen",
                 id="1a2b3c4", service="svtplay", ext="mp4", tvshow=True),
            dict(title="Rapport", episode="5", id="9f8", service="svtplay", ext="mp4",
                 tvshow=False),
            dict(title="Jönssonligan", id="5c6", service="svtplay", ext="mp4", tvshow=False),
        ]
        out = subprocess.run(
            _real_python() + ["-I", "-c", REAL_SNIPPET, os.path.join(ROOT, "host"),
                              json.dumps(videos)],
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(out.returncode, 0, out.stderr)
        result = json.loads(out.stdout)
        self.assertGreaterEqual(result["replaced"], 5)
        self.assertTrue(result["fetchers_use_hook"])
        to_posix = [n.replace("\\", "/") for n in result["names"]]
        self.assertEqual(to_posix, [
            "/S/mastarnas.mastare/mastarnas.mastare.s16e03.finalen-1a2b3c4-svtplay.mp4",
            "/S/rapport/rapport.e05-9f8-svtplay.mp4",
            "/M/jonssonligan-5c6-svtplay.mp4",
        ])


if __name__ == "__main__":
    unittest.main()
