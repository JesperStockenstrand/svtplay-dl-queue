# svtplay-dl Queue

A browser extension that sends the page you're on to [svtplay-dl](https://github.com/spaam/svtplay-dl) with one click, and manages a download queue that keeps running after you close the browser.

- **One click:** a toolbar button and right-click menu items ("Download this page", "Download link", "Download all episodes").
- **Queue:** downloads run one at a time (or up to 4 in parallel), in order. You can reorder, cancel, retry and remove them.
- **Runs in the background:** the queue is processed by a small helper app, so downloads continue when the browser is closed, and the queue survives restarts.
- **Progress and notifications:** the popup shows progress for each download, and you get a system notification when a download finishes or fails.
- **Settings:** download folder, extra svtplay-dl options (e.g. subtitles or quality), and how many downloads run at once.
- **Command line:** add to and inspect the same queue from a terminal.

Works with Chrome, Brave, Edge, Chromium, Vivaldi, Arc and Firefox on macOS and Linux.

> This project is not affiliated with svtplay-dl or with any streaming service. Only download content you have the right to download, and follow the terms of the services you use.

## How it works

```
 Browser extension ──native messaging──▶ helper (svtdl_queue.py)
   popup, menus                            adds jobs to queue.json,
                                           starts the worker if needed
                                                   │
                                                   ▼
                                        worker (background process)
                                           runs svtplay-dl for each job,
                                           writes progress to queue.json
```

Browsers don't let extensions start programs directly. Instead, an extension can talk to an approved local program through [native messaging](https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging). The installer registers the helper with your browsers so only this extension can use it.

The helper is a single Python script with no dependencies beyond the standard library.

## Installation

### 1. Install svtplay-dl

If you don't have it already:

```bash
brew install svtplay-dl
```

or `pipx install svtplay-dl`. svtplay-dl also needs [ffmpeg](https://ffmpeg.org/) (`brew install ffmpeg`).

### 2. Install the helper

You need Python 3.8 or later (`python3`), which macOS and most Linux distributions include.

```bash
git clone https://github.com/<your-account>/svtplay-dl-queue.git
cd svtplay-dl-queue
./install.sh
```

This copies the helper to `~/Library/Application Support/svtplay-dl-queue` (macOS) or `~/.local/share/svtplay-dl-queue` (Linux) and registers it with every supported browser it finds.

### 3. Load the extension

**Chrome, Brave, Edge, Vivaldi, Arc:**

1. Open `chrome://extensions` (`brave://extensions`, `edge://extensions`, …).
2. Turn on **Developer mode**.
3. Click **Load unpacked** and select the `extension` folder.
4. Restart the browser if it was already running when you ran `install.sh`.

**Firefox:** open `about:debugging#/runtime/this-firefox`, click **Load Temporary Add-on…** and choose `extension/manifest.json`. Firefox removes temporary add-ons when it restarts. For permanent use, the add-on must be signed by Mozilla.

## Usage

- Click the toolbar button on a video page and click **Add to queue**. Check **All episodes** to download a whole series.
- The popup tells you whether svtplay-dl supports the site you're on. The list comes from your installed svtplay-dl, so it's always up to date. Sites without a module can still work when the page has a video player svtplay-dl recognizes, so you can add them anyway.
- Or right-click a page or a link and choose one of the svtplay-dl items.
- The badge on the toolbar button shows how many downloads are queued or running.
- Open **⚙ Settings** in the popup to choose the download folder (default `~/Downloads/svtplay-dl`), video quality and file format, subtitles, extras such as cover images and info files for Kodi/Jellyfin/Plex, how many episodes "All episodes" gets, and how many downloads run at once. Each setting explains what it does, and the page shows the svtplay-dl command your choices produce. Other svtplay-dl options can be added under **Advanced**.

### Command line

The helper doubles as a CLI for the same queue:

```bash
~/Library/Application\ Support/svtplay-dl-queue/bin/svtdl-queue add https://www.svtplay.se/video/...
```

Other commands: `check URL` (is the site supported?), `list`, `cancel ID`, `retry ID`, `remove ID`, `clear`, `config [key=value ...]` (e.g. `config subtitles=embedded resolution=720`). On Linux the path is `~/.local/share/svtplay-dl-queue/bin/svtdl-queue`. Add an alias if you use it often.

## Troubleshooting

| Problem | What to do |
| --- | --- |
| "The helper app isn't installed" | Run `./install.sh` and restart the browser. If you installed the extension from a store rather than unpacked, pass its ID: `./install.sh --extension-id <id>`. |
| "svtplay-dl wasn't found" | Install it, or set its full path in Settings (`which svtplay-dl` shows it). |
| A download failed | The last line of svtplay-dl's output is shown under the job. The full output is in `logs/<job id>.log` in the data folder. |

Data folder: `~/Library/Application Support/svtplay-dl-queue` (macOS) or `~/.local/share/svtplay-dl-queue` (Linux). It contains `queue.json`, `config.json`, logs and the helper itself.

## Uninstall

```bash
./uninstall.sh
```

This removes the helper, its browser registrations, the queue and the settings (use `--keep-data` to keep the queue and settings). Your downloaded files are not touched. Remove the extension from the browser's extensions page.

## Development

```
extension/        the browser extension (Manifest V3, no build step)
host/             svtdl_queue.py: native host, worker and CLI
tests/            end-to-end tests with a fake svtplay-dl
tools/            make_icons.py regenerates the icons
install.sh        registers the helper with installed browsers
```

Run the tests:

```bash
python3 -m unittest discover tests -v
```

After changing `host/svtdl_queue.py`, run `./install.sh` again to copy it into place. After changing the extension, click the reload button on the browser's extensions page.

The extension ID (`oonjepebfihcafficfecahlgfafinoee`) is fixed by the public `key` in `extension/manifest.json`, so the installer knows it in advance. If you publish your own build to a store, it gets a different ID; pass that with `--extension-id`.

Contributions are welcome. Please open an issue first for larger changes.

## License

[MIT](LICENSE)
