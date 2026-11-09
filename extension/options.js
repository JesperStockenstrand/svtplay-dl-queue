const $ = (id) => document.getElementById(id);

const CHECKBOXES = ["subfolder", "overwrite", "all_subtitles", "thumbnail", "nfo",
  "chapters", "include_clips", "notify"];
const SELECTS = ["resolution", "output_format", "max_parallel"];
const TEXTS = ["download_dir", "binary", "extra_args", "all_last"];

let toastTimer = null;

function showError(message) {
  $("error").textContent = message || "";
  $("error").hidden = !message;
}

function toast(text) {
  const el = $("saved");
  el.textContent = text;
  el.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), 1500);
}

function quote(arg) {
  return /^[\w@%+=:,./-]+$/.test(arg) ? arg : "'" + arg.replace(/'/g, "'\\''") + "'";
}

function commandLine(args) {
  return ["svtplay-dl", ...args.map(quote), "<page address>"].join(" ");
}

function fill(reply) {
  const { config } = reply;
  for (const key of CHECKBOXES) $(key).checked = !!config[key];
  for (const key of SELECTS) $(key).value = String(config[key]);
  for (const key of TEXTS) $(key).value = config[key];
  const radio = document.querySelector(`input[name="subtitles"][value="${config.subtitles}"]`);
  if (radio) radio.checked = true;

  updateDependent();
  $("command").textContent = commandLine(reply.command);
  $("command_all").textContent = commandLine(reply.command_all);

  let help = "Leave empty to find it automatically. ";
  if (reply.detected_binary) help += `Found: ${reply.detected_binary}`;
  else help += "It wasn't found automatically. Install it (brew install svtplay-dl) or enter its full path.";
  if (config.binary && !reply.binary_ok) help = "Nothing runnable at that path. " + help;
  $("binary_help").textContent = help;
  $("binary_help").classList.toggle("bad", !!config.binary && !reply.binary_ok);
}

// "All languages" only matters when subtitles are downloaded.
function updateDependent() {
  const subs = document.querySelector('input[name="subtitles"]:checked');
  const off = !subs || subs.value === "none";
  $("all_subtitles").disabled = off;
  $("all_subtitles_row").classList.toggle("disabled", off);
}

function collect() {
  const config = {};
  for (const key of CHECKBOXES) config[key] = $(key).checked;
  for (const key of SELECTS) config[key] = $(key).value;
  for (const key of TEXTS) config[key] = $(key).value;
  config.max_parallel = Number(config.max_parallel);
  config.all_last = config.all_last === "" ? 0 : Number(config.all_last);
  const subs = document.querySelector('input[name="subtitles"]:checked');
  config.subtitles = subs ? subs.value : "none";
  return config;
}

async function save() {
  updateDependent();
  try {
    fill(await host({ action: "set_config", config: collect() }));
    showError("");
    toast("Saved");
  } catch (e) {
    showError(e.message);
  }
}

async function load() {
  try {
    fill(await host({ action: "get_config" }));
  } catch (e) {
    showError(e.message);
  }
}

const form = $("form");
// Checkboxes, radios and menus save right away; text fields when you leave them or press Enter.
form.addEventListener("change", save);
form.addEventListener("submit", (event) => {
  event.preventDefault();
  save();
});

load();
