const API_BASE = "http://127.0.0.1:28710";

// Default settings
chrome.runtime.onInstalled.addListener(() => {
  chrome.storage.local.set({
    interceptDownloads: true,
    showVideoSniffer: true
  });

  // Context Menu
  chrome.contextMenus.create({
    id: "ripsync-download-link",
    title: "Bu bağlantıyı RipSync ile indir",
    contexts: ["link", "video", "audio", "image"]
  });
});

// Check if desktop app is alive
async function checkDesktopApp() {
  try {
    // nosemgrep: typescript.react.security.react-insecure-request.react-insecure-request
    const res = await fetch(`${API_BASE}/api/status`, { method: "GET" });
    return res.ok;
  } catch (err) {
    return false;
  }
}

// Forward download to desktop app
async function sendDownloadToApp(data) {
  try {
    // nosemgrep: typescript.react.security.react-insecure-request.react-insecure-request
    const res = await fetch(`${API_BASE}/api/download`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data)
    });
    return res.ok;
  } catch (err) {
    console.error("RipSync masaüstü uygulamasına bağlanılamadı:", err);
    return false;
  }
}

// Intercept browser downloads
chrome.downloads.onCreated.addListener(async (downloadItem) => {
  const { interceptDownloads } = await chrome.storage.local.get("interceptDownloads");
  if (!interceptDownloads) return;

  // Avoid intercepting blob or data URLs or files already created by extension
  if (!downloadItem.url.startsWith("http://") && !downloadItem.url.startsWith("https://")) {
    return;
  }

  // Check if desktop app is active before cancelling browser download
  const isAlive = await checkDesktopApp();
  if (!isAlive) return;

  // Cancel the native Chrome download
  chrome.downloads.cancel(downloadItem.id, () => {
    chrome.downloads.erase({ id: downloadItem.id });
  });

  // Fetch cookies for the target URL
  let cookieHeader = "";
  try {
    const cookies = await chrome.cookies.getAll({ url: downloadItem.url });
    cookieHeader = cookies.map(c => `${c.name}=${c.value}`).join("; ");
  } catch (e) {
    console.warn("Çerezler alınamadı:", e);
  }

  await sendDownloadToApp({
    url: downloadItem.url,
    filename: downloadItem.filename ? downloadItem.filename.replace(/^.*[\\\/]/, '') : "",
    referer: downloadItem.referrer || "",
    cookies: cookieHeader,
    userAgent: navigator.userAgent,
    mimeType: downloadItem.mime || ""
  });
});

// Handle Context Menu clicks
chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId === "ripsync-download-link") {
    const targetUrl = info.linkUrl || info.srcUrl || info.pageUrl;
    if (!targetUrl) return;

    let cookieHeader = "";
    try {
      const cookies = await chrome.cookies.getAll({ url: targetUrl });
      cookieHeader = cookies.map(c => `${c.name}=${c.value}`).join("; ");
    } catch (e) {}

    await sendDownloadToApp({
      url: targetUrl,
      filename: "",
      referer: tab ? tab.url : "",
      cookies: cookieHeader,
      userAgent: navigator.userAgent
    });
  }
});

// Listen to messages from content scripts (Video sniffer)
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "download_media") {
    (async () => {
      let cookieHeader = "";
      try {
        const cookies = await chrome.cookies.getAll({ url: request.url });
        cookieHeader = cookies.map(c => `${c.name}=${c.value}`).join("; ");
      } catch (e) {}

      const success = await sendDownloadToApp({
        url: request.url,
        filename: request.filename || "",
        quality: request.quality || "max",
        referer: sender.tab ? sender.tab.url : "",
        cookies: cookieHeader,
        userAgent: navigator.userAgent
      });
      sendResponse({ success });
    })();
    return true; // Keep message channel open for async response
  }
});
