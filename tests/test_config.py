"""Unit tests for turning settings into svtplay-dl options."""

import os
import sys
import tempfile
import unittest

os.environ["SVTDL_QUEUE_HOME"] = tempfile.mkdtemp(prefix="svtdl-config-test-")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "host"))

import svtdl_queue as q  # noqa: E402


def args(all_episodes=False, **settings):
    return q.build_args(dict(q.DEFAULT_CONFIG, **settings), all_episodes)


class BuildArgsTest(unittest.TestCase):
    def test_defaults_add_nothing(self):
        self.assertEqual(args(), [])
        self.assertEqual(args(all_episodes=True), ["--all-episodes"])

    def test_subtitle_choices(self):
        self.assertEqual(args(subtitles="separate"), ["--subtitle"])
        self.assertEqual(args(subtitles="embedded"), ["--merge-subtitle"])
        self.assertEqual(args(subtitles="both"), ["--subtitle", "--merge-subtitle"])
        self.assertEqual(args(subtitles="embedded", all_subtitles=True),
                         ["--merge-subtitle", "--all-subtitles"])
        # "All languages" means nothing without subtitles.
        self.assertEqual(args(subtitles="none", all_subtitles=True), [])

    def test_video_and_files(self):
        self.assertEqual(
            args(subfolder=True, overwrite=True, resolution="720", output_format="mkv",
                 thumbnail=True, nfo=True, chapters=True),
            ["--subfolder", "--force", "--resolution", "720", "--output-format", "mkv",
             "--thumbnail", "--nfo", "--chapters"])

    def test_series_options_only_for_all_episodes(self):
        self.assertEqual(args(all_last=5, include_clips=True), [])
        self.assertEqual(args(True, all_last=5, include_clips=True),
                         ["--all-episodes", "--all-last", "5", "--include-clips"])

    def test_extra_args_come_last_and_respect_quotes(self):
        self.assertEqual(args(subtitles="separate", extra_args="--exclude 'a b,c'"),
                         ["--subtitle", "--exclude", "a b,c"])


class ValidateTest(unittest.TestCase):
    def test_bools_from_strings(self):
        # The CLI passes strings: "false" must not become True.
        self.assertIs(q._validate("nfo", "false"), False)
        self.assertIs(q._validate("nfo", "true"), True)

    def test_bad_values(self):
        for key, value in (("resolution", "4k"), ("subtitles", "maybe"), ("all_last", -1),
                           ("max_parallel", "x"), ("download_dir", ""), ("bogus", 1)):
            with self.assertRaises(ValueError, msg=(key, value)):
                q._validate(key, value)


if __name__ == "__main__":
    unittest.main()
