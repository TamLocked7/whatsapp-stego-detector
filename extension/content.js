/**
 * content.js -- runs inside web.whatsapp.com
 *
 * Strategy (v2 -- fixes sidebar-avatar false positives + layout breakage):
 *  1. Only scan images inside the OPEN CHAT PANEL (WhatsApp's stable
 *     container id="main"). The left sidebar (id="pane-side") -- contact
 *     avatars, chat-list previews, group icons -- is deliberately skipped
 *     entirely, since those are never message media and were being
 *     mis-flagged.
 *  2. Badges are drawn as position:fixed overlays computed from the image's
 *     exact on-screen coordinates (getBoundingClientRect), instead of being
 *     injected into WhatsApp's own DOM/layout. This avoids ever touching
 *     WhatsApp's internal CSS (which broke when we did in v1, since
 *     WhatsApp recycles row elements for its virtualized lists).
 *  3. Badge position is recalculated on scroll/resize so it stays glued to
 *     its image.
 */

const BACKEND_URL = "http://127.0.0.1:5000/predict";
const MIN_RENDERED_SIZE = 100; // px -- skip anything smaller (icons, emoji, tiny thumbs)

// img element -> { badgeEl, state }
const tracked = new Map();

function isInChatPanel(imgEl) {
  // Blocklist approach (instead of only-allow-#main): the sidebar
  // (#pane-side) is the one place we NEVER want to scan (avatars, chat
  // list previews). Everything else -- the open chat panel, and WhatsApp's
  // full-screen image preview/lightbox viewer (which renders outside
  // #main as an overlay) -- is allowed, and the size filter still keeps
  // out small icons/emoji.
  return !imgEl.closest("#pane-side");
}

function isBigEnough(imgEl) {
  const r = imgEl.getBoundingClientRect();
  return r.width >= MIN_RENDERED_SIZE && r.height >= MIN_RENDERED_SIZE;
}

function makeBadge() {
  const badge = document.createElement("div");
  badge.className = "stego-badge scanning";
  badge.textContent = "Scanning…";
  document.body.appendChild(badge); // lives at document root, not inside WhatsApp's DOM
  return badge;
}

function positionBadge(imgEl, badgeEl) {
  const r = imgEl.getBoundingClientRect();
  // if the image scrolled off-screen or is gone, hide the badge instead of
  // drawing garbage coordinates
  if (r.width === 0 || r.height === 0 || !document.body.contains(imgEl)) {
    badgeEl.style.display = "none";
    return;
  }
  badgeEl.style.display = "block";
  badgeEl.style.top = `${r.top + 4}px`;
  badgeEl.style.left = `${r.right - badgeEl.offsetWidth - 4}px`;
}

function repositionAll() {
  tracked.forEach((entry, imgEl) => positionBadge(imgEl, entry.badgeEl));
}
window.addEventListener("scroll", repositionAll, true); // capture=true: WhatsApp scrolls inner panels
window.addEventListener("resize", repositionAll);
setInterval(repositionAll, 500); // cheap fallback for WhatsApp's own animated layout shifts

async function imageToBase64(imgEl) {
  const resp = await fetch(imgEl.src, { mode: "cors" });
  const blob = await resp.blob();
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => resolve(reader.result);
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
}

async function analyzeImage(imgEl, badgeEl) {
  try {
    const dataUrl = await imageToBase64(imgEl);
    const resp = await fetch(BACKEND_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ image: dataUrl }),
    });
    if (!resp.ok) throw new Error(`backend responded ${resp.status}`);
    const result = await resp.json();

    badgeEl.className = `stego-badge ${result.is_suspicious ? "suspicious" : "safe"}`;
    badgeEl.textContent = result.is_suspicious
      ? `⚠ Suspicious (${Math.round(result.confidence * 100)}%)`
      : `✓ Safe (${Math.round(result.confidence * 100)}%)`;
    badgeEl.title = JSON.stringify(result.top_signals, null, 2);
    positionBadge(imgEl, badgeEl);

    chrome.storage?.local.get(["scanned", "flagged"], (data) => {
      const scanned = (data.scanned || 0) + 1;
      const flagged = (data.flagged || 0) + (result.is_suspicious ? 1 : 0);
      chrome.storage.local.set({ scanned, flagged });
    });
  } catch (err) {
    badgeEl.className = "stego-badge scanning";
    badgeEl.textContent = "Backend offline";
    badgeEl.title = String(err);
    positionBadge(imgEl, badgeEl);
  }
}

function watch(imgEl) {
  if (tracked.has(imgEl)) return;
  if (!isInChatPanel(imgEl)) return;

  const start = () => {
    if (!isBigEnough(imgEl)) return; // still skip small thumbnails/icons
    const badge = makeBadge();
    tracked.set(imgEl, { badgeEl: badge });
    positionBadge(imgEl, badge);
    analyzeImage(imgEl, badge);
  };

  if (imgEl.complete && imgEl.naturalWidth > 0) start();
  else imgEl.addEventListener("load", start, { once: true });
}

function scanExisting() {
  document.querySelectorAll("img").forEach(watch);
}

function cleanupRemoved() {
  tracked.forEach((entry, imgEl) => {
    if (!document.body.contains(imgEl)) {
      entry.badgeEl.remove();
      tracked.delete(imgEl);
    }
  });
}

const observer = new MutationObserver((mutations) => {
  for (const m of mutations) {
    m.addedNodes.forEach((node) => {
      if (!(node instanceof HTMLElement)) return;
      if (node.tagName === "IMG") watch(node);
      node.querySelectorAll?.("img").forEach(watch);
    });
  }
  cleanupRemoved();
});

observer.observe(document.body, { childList: true, subtree: true });
scanExisting();

console.log("[Stego Detector] content script active (chat-panel-only mode) on web.whatsapp.com");
