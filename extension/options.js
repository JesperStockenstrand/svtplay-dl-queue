const $ = (id) => document.getElementById(id);

function showError(message) {
  $("error").textContent = message || "";
  $("error").hidden = !message;
}

function fill({ config, detected_binary }) {
  $("download_dir").value = config.download_dir;
  $("binary").value = config.binary;
  $("extra_args").value = config.extra_args;
  $("max_parallel").value = String(config.max_parallel);
  $("notify").checked = !!config.notify;
  $("detected").textContent = detected_binary
    ? `Found automatically: ${detected_binary}`
    : "svtplay-dl wasn't found automatically. Install it (e.g. brew install svtplay-dl) or enter its full path.";
}

async function load() {
  try {
    fill(await host({ action: "get_config" }));
  } catch (e) {
    showError(e.message);
  }
}

$("form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const res = await host({
      action: "set_config",
      config: {
        download_dir: $("download_dir").value,
        binary: $("binary").value,
        extra_args: $("extra_args").value,
        max_parallel: Number($("max_parallel").value),
        notify: $("notify").checked,
      },
    });
    fill(res);
    showError("");
    $("saved").hidden = false;
    setTimeout(() => ($("saved").hidden = true), 2000);
  } catch (e) {
    showError(e.message);
  }
});

load();
