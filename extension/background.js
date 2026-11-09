// Background script: right-click menu, badge updates.
// Chrome runs it as a service worker, Firefox as an event page.

if (typeof importScripts === "function") {
  importScripts("common.js");
}

const MENU_PAGE = "svtdl-add-page";
const MENU_LINK = "svtdl-add-link";
const MENU_ALL = "svtdl-add-all";
const POLL_ALARM = "svtdl-poll";

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({
      id: MENU_PAGE,
      title: "Download this page with svtplay-dl",
      contexts: ["page", "video"],
    });
    chrome.contextMenus.create({
      id: MENU_LINK,
      title: "Download link with svtplay-dl",
      contexts: ["link"],
    });
    chrome.contextMenus.create({
      id: MENU_ALL,
      title: "Download all episodes with svtplay-dl",
      contexts: ["page", "link"],
    });
  });
});

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  const url = info.linkUrl || info.pageUrl || (tab && tab.url);
  const title = info.linkUrl ? info.selectionText || "" : (tab && tab.title) || "";
  try {
    const res = await host({
      action: "add",
      url,
      title,
      all_episodes: info.menuItemId === MENU_ALL,
    });
    await flash(res.duplicate ? "dup" : "+", "#2b6cb0");
    startPolling();
  } catch (e) {
    console.error("svtplay-dl Queue:", e);
    await flash("!", "#c53030");
  }
});

// Briefly show a symbol on the badge, then go back to the queue count.
async function flash(text, color) {
  await chrome.action.setBadgeBackgroundColor({ color });
  await chrome.action.setBadgeText({ text });
  setTimeout(refresh, 1500);
}

async function refresh() {
  try {
    const { jobs } = await host({ action: "list" });
    const active = await updateBadge(jobs);
    if (!active) chrome.alarms.clear(POLL_ALARM);
  } catch (e) {
    chrome.alarms.clear(POLL_ALARM);
  }
}

function startPolling() {
  chrome.alarms.create(POLL_ALARM, { periodInMinutes: 0.5 });
}

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === POLL_ALARM) refresh();
});

chrome.runtime.onMessage.addListener((msg) => {
  if (msg && msg.type === "queue-changed") startPolling();
});

chrome.runtime.onStartup.addListener(refresh);
