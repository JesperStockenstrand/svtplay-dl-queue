"""Tests for the "is this site supported?" check."""

import os
import shutil
import sys
import tempfile
import unittest

os.environ["SVTDL_QUEUE_HOME"] = tempfile.mkdtemp(prefix="svtdl-sites-test-")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "host"))

import svtdl_queue as q  # noqa: E402

SITES = [
    ["Svtplay", ["svtplay.se", "svt.se"], []],
    ["Eurosport", [], [r"^([^.]+\.)*eurosportplayer.com"]],
    ["Broken", [], ["(unclosed"]],
]


class MatchSiteTest(unittest.TestCase):
    def test_domains_with_and_without_www(self):
        self.assertEqual(q.match_site(SITES, "https://www.svtplay.se/video/1"), "Svtplay")
        self.assertEqual(q.match_site(SITES, "https://svt.se/x"), "Svtplay")

    def test_domain_regexes(self):
        self.assertEqual(q.match_site(SITES, "https://a.b.eurosportplayer.com/"), "Eurosport")

    def test_other_subdomains_and_sites_do_not_match(self):
        # svtplay-dl itself only accepts the listed name or www. + it.
        self.assertIsNone(q.match_site(SITES, "https://beta.svtplay.se/"))
        self.assertIsNone(q.match_site(SITES, "https://www.youtube.com/watch?v=1"))


class CheckUrlTest(unittest.TestCase):
    def test_stream_links_need_no_site_list(self):
        res = q.cmd_check_url("https://cdn.example.com/a/master.m3u8")
        self.assertEqual((res["supported"], res["kind"]), ("yes", "stream"))

    def test_invalid_url(self):
        self.assertEqual(q.cmd_check_url("ftp://x")["supported"], "no")

    def test_unknown_when_site_list_cannot_be_read(self):
        # The fake downloader is a plain Python script without svtplay_dl.
        fake = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fake_downloader.py")
        q.save_config({"binary": fake})
        self.assertEqual(q.cmd_check_url("https://www.svtplay.se/x")["supported"], "unknown")

    def test_interpreter_from_shebang(self):
        d = tempfile.mkdtemp()
        try:
            direct = os.path.join(d, "a")
            with open(direct, "w") as f:
                f.write("#!/opt/venv/bin/python -s\nprint()\n")
            self.assertEqual(q._interpreter_for(direct), ["/opt/venv/bin/python", "-s"])
            binary = os.path.join(d, "b")
            with open(binary, "wb") as f:
                f.write(b"\x7fELF...")
            self.assertIsNone(q._interpreter_for(binary))

            # A pip/pipx launcher .exe: the #! line sits just before a zip.
            python = os.path.join(d, "My Python", "python.exe")
            os.makedirs(os.path.dirname(python))
            open(python, "w").close()
            launcher = os.path.join(d, "svtplay-dl.exe")
            with open(launcher, "wb") as f:
                f.write(b"MZ" + b"\0" * 300 + b'#!"' + python.encode() + b'"\r\nPK\x03\x04zipdata')
            self.assertEqual(q._interpreter_for(launcher), [python])

            # A standalone .exe without a launcher line.
            with open(launcher, "wb") as f:
                f.write(b"MZ" + b"\0" * 300 + b"PK\x03\x04")
            self.assertIsNone(q._interpreter_for(launcher))
        finally:
            shutil.rmtree(d)


@unittest.skipUnless(q.find_binary(dict(q.DEFAULT_CONFIG)), "svtplay-dl not installed")
class RealSvtplayDlTest(unittest.TestCase):
    def setUp(self):
        q.save_config({"binary": ""})

    def test_reads_site_list_from_installed_svtplay_dl(self):
        self.assertEqual(q.cmd_check_url("https://www.svtplay.se/video/x")["supported"], "yes")
        self.assertEqual(q.cmd_check_url("https://example.org/")["supported"], "maybe")


if __name__ == "__main__":
    unittest.main()
