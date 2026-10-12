const API_BASE = "http://127.0.0.1:28710";

document.addEventListener("DOMContentLoaded", async () => {
  const statusBox = document.getElementById("status-box");
  const statusText = document.getElementById("status-text");
  const chkIntercept = document.getElementById("chk-intercept");
  const chkSniffer = document.getElementById("chk-sniffer");
  const chkFilterAds = document.getElementById("chk-filter-ads");
  const siteSection = document.getElementById("site-section");
  const lblSite = document.getElementById("lbl-site");
  const chkSite = document.getElementById("chk-site");
  const siteDesc = document.getElementById("site-desc");

  // Load saved settings
  const settings = await chrome.storage.local.get({
    interceptDownloads: true,
    showVideoSniffer: true,
    filterAds: true,
    disabledDomains: []
  });

  chkIntercept.checked = settings.interceptDownloads;
  chkSniffer.checked = settings.showVideoSniffer;
  chkFilterAds.checked = settings.filterAds;

  let currentHost = "";
  try {
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tabs && tabs[0] && tabs[0].url) {
      const url = new URL(tabs[0].url);
      if (url.protocol.startsWith("http")) {
        currentHost = url.hostname.toLowerCase();
        siteSection.style.display = "block";
        lblSite.textContent = currentHost;
        const isDisabled = (settings.disabledDomains || []).some(d => currentHost === d || currentHost.endsWith("." + d));
        chkSite.checked = !isDisabled;
        siteDesc.textContent = isDisabled ? "Bu sitede video butonu kapalı" : "Bu sitede video butonu açık";
      }
    }
  } catch (e) {}

  // Save changes
  chkIntercept.addEventListener("change", () => {
    chrome.storage.local.set({ interceptDownloads: chkIntercept.checked });
  });

  chkSniffer.addEventListener("change", () => {
    chrome.storage.local.set({ showVideoSniffer: chkSniffer.checked });
  });

  chkFilterAds.addEventListener("change", () => {
    chrome.storage.local.set({ filterAds: chkFilterAds.checked });
  });

  chkSite.addEventListener("change", async () => {
    if (!currentHost) return;
    const res = await chrome.storage.local.get({ disabledDomains: [] });
    let list = Array.isArray(res.disabledDomains) ? [...res.disabledDomains] : [];
    if (!chkSite.checked) {
      // Disable this domain
      if (!list.includes(currentHost)) list.push(currentHost);
      siteDesc.textContent = "Bu sitede video butonu kapalı";
    } else {
      // Re-enable this domain
      list = list.filter(d => d !== currentHost);
      siteDesc.textContent = "Bu sitede video butonu açık";
    }
    await chrome.storage.local.set({ disabledDomains: list });
  });

  // Check connection to desktop app
  try {
    // Local loopback API is intentionally served over HTTP on localhost only.
    // nosemgrep: typescript.react.security.react-insecure-request.react-insecure-request
    const statusUrl = new URL("/api/status", API_BASE).toString();
    const res = await fetch(statusUrl);
    if (res.ok) {
      statusBox.className = "status-badge status-online";
      statusText.textContent = "Masaüstü Uygulaması Bağlı";
    } else {
      throw new Error();
    }
  } catch (err) {
    statusBox.className = "status-badge status-offline";
    statusText.textContent = "Uygulama Kapalı (Başlatın)";
  }
});

