const $ = (id) => document.getElementById(id);

const STATUS_TEXT = {
  queued: "Queued",
  downloading: "Downloading",
  done: "Done",
  failed: "Failed",
  canceled: "Canceled",
};

let currentTab = null;
let busy = false;

function showError(message) {
  $("error").textContent = message || "";
  $("error").hidden = !message;
}

function button(label, title, onClick) {
  const b = document.createElement("button");
  b.className = "icon";
  b.textContent = label;
  b.title = title;
  b.setAttribute("aria-label", title);
  b.addEventListener("click", onClick);
  return b;
}

async function act(message) {
  try {
    await host(message);
    showError("");
  } catch (e) {
    showError(e.message);
  }
  await refresh();
}

function renderJob(job, queuedIndex, queuedCount) {
  const li = document.createElement("li");
  li.className = "job " + job.status;

  const top = document.createElement("div");
  top.className = "job-top";

  const title = document.createElement("a");
  title.className = "job-title";
  title.textContent = job.title || job.url;
  title.title = job.url;
  title.href = job.url;
  title.target = "_blank";
  title.rel = "noopener noreferrer";
  top.appendChild(title);

  const actions = document.createElement("div");
  actions.className = "job-actions";
  if (job.status === "queued") {
    if (queuedIndex > 0) actions.appendChild(button("↑", "Move up", () => act({ action: "move", id: job.id, delta: -1 })));
    if (queuedIndex < queuedCount - 1) actions.appendChild(button("↓", "Move down", () => act({ action: "move", id: job.id, delta: 1 })));
  }
  if (job.status === "queued" || job.status === "downloading") {
    actions.appendChild(button("■", "Cancel", () => act({ action: "cancel", id: job.id })));
  } else {
    if (job.status !== "done") actions.appendChild(button("↻", "Retry", () => act({ action: "retry", id: job.id })));
    actions.appendChild(button("✕", "Remove", () => act({ action: "remove", id: job.id })));
  }
  top.appendChild(actions);
  li.appendChild(top);

  const status = document.createElement("div");
  status.className = "job-status";
  let text = STATUS_TEXT[job.status] || job.status;
  if (job.all_episodes) text += " · all episodes";
  if (job.status === "downloading" && job.progress != null) text += ` · ${Math.round(job.progress)}%`;
  status.textContent = text;
  li.appendChild(status);

  if (job.status === "downloading") {
    const bar = document.createElement("div");
    bar.className = "bar" + (job.progress == null ? " indeterminate" : "");
    const fill = document.createElement("div");
    fill.style.width = (job.progress == null ? 30 : job.progress) + "%";
    bar.appendChild(fill);
    li.appendChild(bar);
  }

  if (job.message && (job.status === "failed" || job.status === "downloading")) {
    const msg = document.createElement("div");
    msg.className = "job-message";
    msg.textContent = job.message;
    msg.title = job.message;
    li.appendChild(msg);
  }
  return li;
}

let refreshing = false;

async function refresh() {
  if (refreshing) return;
  refreshing = true;
  try {
    await render();
  } finally {
    refreshing = false;
  }
}

async function render() {
  let info;
  try {
    info = await host({ action: "list" });
  } catch (e) {
    showError(e.message);
    $("add").disabled = true;
    return;
  }
  $("add").disabled = !isDownloadable(currentTab);
  updateBadge(info.jobs);

  $("warning").hidden = !!info.binary;
  $("warning").textContent = info.binary
    ? ""
    : "svtplay-dl wasn't found. Install it, or set its path in Settings.";

  const list = $("jobs");
  list.replaceChildren();
  const queued = info.jobs.filter((j) => j.status === "queued");
  // Show active jobs first (in queue order), newest finished jobs after.
  const active = info.jobs.filter((j) => j.status === "downloading").concat(queued);
  const finished = info.jobs
    .filter((j) => j.status !== "downloading" && j.status !== "queued")
    .sort((a, b) => (b.finished || 0) - (a.finished || 0));
  for (const job of active.concat(finished)) {
    list.appendChild(renderJob(job, queued.indexOf(job), queued.length));
  }
  $("empty").hidden = info.jobs.length > 0;
  $("clear").disabled = finished.length === 0;
}

function isDownloadable(tab) {
  return !!(tab && tab.url && /^https?:\/\//.test(tab.url));
}

async function init() {
  [currentTab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const urlBox = $("current-url");
  if (isDownloadable(currentTab)) {
    urlBox.textContent = currentTab.title || currentTab.url;
    urlBox.title = currentTab.url;
  } else {
    urlBox.textContent = "This page can't be downloaded.";
  }

  $("add").addEventListener("click", async () => {
    if (busy || !isDownloadable(currentTab)) return;
    busy = true;
    $("add").disabled = true;
    try {
      const res = await host({
        action: "add",
        url: currentTab.url,
        title: currentTab.title,
        all_episodes: $("all-episodes").checked,
      });
      showError(res.duplicate ? "This page is already in the queue." : "");
      chrome.runtime.sendMessage({ type: "queue-changed" }).catch(() => {});
    } catch (e) {
      showError(e.message);
    }
    busy = false;
    await refresh();
  });

  $("clear").addEventListener("click", () => act({ action: "clear" }));
  $("open-folder").addEventListener("click", () => act({ action: "open_folder" }));
  $("settings").addEventListener("click", () => chrome.runtime.openOptionsPage());

  await refresh();
  setInterval(refresh, 1000);
}

init();
