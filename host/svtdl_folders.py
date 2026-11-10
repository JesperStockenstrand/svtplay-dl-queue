"""Run svtplay-dl, saving films and series in separate folders.

Started by the queue worker with svtplay-dl's own Python:

    <svtplay-dl's python> -I svtdl_folders.py <svtplay-dl arguments>

The folders come from the SVTDL_QUEUE_FOLDERS environment variable (JSON):
{"movies": "/abs/path", "series": "/abs/path", "show_folders": true}

svtplay-dl builds the path of every file it writes (video, subtitles, info
files, cover images) with svtplay_dl.utils.output.formatname. This wraps that
function so the path starts in the films or series folder, depending on
whether the video is a series episode. Because svtplay-dl itself sees the
final path, it still skips episodes you already have.

If svtplay-dl's internals ever change so the wrapper can't be installed, a
warning is printed and svtplay-dl runs normally (everything in one folder).
"""

import json
import os
import pathlib
import sys


def is_series(output):
    """A video counts as a series episode if svtplay-dl says it's a TV show,
    or if it has an episode number (some sites have no season numbers)."""
    if output.get("tvshow"):
        return True
    return bool(output.get("episode"))


def install(opts):
    import svtplay_dl.utils.output as output_module
    from svtplay_dl.utils.text import filenamify

    original = output_module.formatname
    movies = pathlib.Path(opts["movies"])
    series = pathlib.Path(opts["series"])
    show_folders = bool(opts.get("show_folders"))

    def formatname(output, config):
        name = original(output, config)
        # "basedir" asks for the output folder itself; absolute paths come
        # from an explicit -o option. Leave both alone.
        if output.get("basedir") or pathlib.Path(name).is_absolute():
            return name
        if is_series(output):
            base = series
            if show_folders and output.get("title"):
                base = base / filenamify(output["title"])
        else:
            base = movies
        return base / name

    replaced = 0
    for module_name, module in list(sys.modules.items()):
        if module_name.startswith("svtplay_dl") and getattr(module, "formatname", None) is original:
            module.formatname = formatname
            replaced += 1
    if not replaced:
        raise RuntimeError("formatname is not used where expected")
    return replaced


def main():
    import svtplay_dl

    opts = json.loads(os.environ.get("SVTDL_QUEUE_FOLDERS") or "null")
    if opts:
        try:
            install(opts)
        except Exception as e:  # never stop a download because of this
            print("WARNING: svtplay-dl Queue couldn't separate films and series (%s). "
                  "Saving in the download folder instead." % e, flush=True)
    sys.argv = ["svtplay-dl"] + sys.argv[1:]
    sys.exit(svtplay_dl.main())


if __name__ == "__main__":
    main()
