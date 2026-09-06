const dot = document.getElementById("dot");
const statusText = document.getElementById("statusText");
const scannedEl = document.getElementById("scanned");
const flaggedEl = document.getElementById("flagged");

fetch("http://127.0.0.1:5000/health")
  .then((r) => r.json())
  .then((d) => {
    dot.classList.add("online");
    statusText.textContent = d.model_loaded ? "Backend online, model loaded" : "Backend online, no model";
  })
  .catch(() => {
    dot.classList.add("offline");
    statusText.textContent = "Backend offline (run backend/app.py)";
  });

chrome.storage.local.get(["scanned", "flagged"], (data) => {
  scannedEl.textContent = data.scanned || 0;
  flaggedEl.textContent = data.flagged || 0;
});

// content.js writes directly to chrome.storage.local on every scan; just
// listen for changes so the popup live-updates without double counting.
chrome.storage.onChanged.addListener((changes, area) => {
  if (area !== "local") return;
  if (changes.scanned) scannedEl.textContent = changes.scanned.newValue;
  if (changes.flagged) flaggedEl.textContent = changes.flagged.newValue;
});
