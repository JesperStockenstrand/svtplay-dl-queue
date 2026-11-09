// Shared helpers for the background script, popup and options page.

const HOST_NAME = "svtplay_dl_queue";

const HOST_MISSING_HELP =
  "The helper app isn't installed. Run ./install.sh from the project folder, " +
  "then restart the browser.";

// Send one message to the native host and return its reply.
// Throws an Error with a readable message on failure.
async function host(message) {
  let reply;
  try {
    reply = await chrome.runtime.sendNativeMessage(HOST_NAME, message);
  } catch (e) {
    const text = String((e && e.message) || e);
    if (/not found|no such native application|access to the specified native messaging host is forbidden/i.test(text)) {
      throw new Error(HOST_MISSING_HELP);
    }
    throw new Error(text);
  }
  if (!reply) throw new Error("No reply from the helper app.");
  if (!reply.ok) throw new Error(reply.error || "Unknown error");
  return reply;
}

async function updateBadge(jobs) {
  const active = jobs.filter((j) => j.status === "queued" || j.status === "downloading").length;
  const failed = jobs.some((j) => j.status === "failed");
  await chrome.action.setBadgeText({ text: active ? String(active) : "" });
  await chrome.action.setBadgeBackgroundColor({ color: failed ? "#c53030" : "#2b6cb0" });
  return active;
}
