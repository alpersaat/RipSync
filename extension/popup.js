document.addEventListener("DOMContentLoaded", async () => {
  const statusBox = document.getElementById("status-box");
  const statusText = document.getElementById("status-text");
  const chkIntercept = document.getElementById("chk-intercept");
  const chkSniffer = document.getElementById("chk-sniffer");
  const chkFilterAds = document.getElementById("chk-filter-ads");
  const chkCookies = document.getElementById("chk-cookies");
  const cookieWarn = document.getElementById("cookie-warn");
  const siteSection = document.getElementById("site-section");
  const lblSite = document.getElementById("lbl-site");
  const chkSite = document.getElementById("chk-site");
  const siteDesc = document.getElementById("site-desc");
  const authDetails = document.getElementById("auth-details");
  const inpPort = document.getElementById("inp-port");
  const inpToken = document.getElementById("inp-token");
  const btnSaveAuth = document.getElementById("btn-save-auth");
  const btnSyncConfig = document.getElementById("btn-sync-config");
  const footerPort = document.getElementById("footer-port");

  // Load saved settings
  const settings = await chrome.storage.local.get({
    interceptDownloads: true,
    showVideoSniffer: true,
    filterAds: true,
    shareCookies: false,
    disabledDomains: [],
    bridgePort: 28710,
    bridgeToken: ""
  });

  chkIntercept.checked = settings.interceptDownloads;
  chkSniffer.checked = settings.showVideoSniffer;
  chkFilterAds.checked = settings.filterAds;
  chkCookies.checked = settings.shareCookies;
  if (chkCookies.checked) {
    cookieWarn.style.display = "block";
  }

  inpPort.value = settings.bridgePort || 28710;
  inpToken.value = settings.bridgeToken || "";

  // Auto-sync token and port from config.json via extension-internal messaging
  try {
    const res = await chrome.runtime.sendMessage({ action: "get_bridge_config" });
    if (res && res.success) {
      let changed = false;
      const toUpdate = {};
      if (res.bridgeToken && res.bridgeToken !== settings.bridgeToken) {
        inpToken.value = res.bridgeToken;
        toUpdate.bridgeToken = res.bridgeToken;
        changed = true;
      }
      if (res.bridgePort && res.bridgePort !== settings.bridgePort) {
        inpPort.value = res.bridgePort;
        toUpdate.bridgePort = res.bridgePort;
        changed = true;
      }
      if (changed) {
        await chrome.storage.local.set(toUpdate);
      }
    }
  } catch (e) {}

  footerPort.textContent = `Port: 127.0.0.1:${inpPort.value}`;

  // Current tab detection
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

  // Toggle handlers
  chkIntercept.addEventListener("change", () => {
    chrome.storage.local.set({ interceptDownloads: chkIntercept.checked });
  });

  chkSniffer.addEventListener("change", () => {
    chrome.storage.local.set({ showVideoSniffer: chkSniffer.checked });
  });

  chkFilterAds.addEventListener("change", () => {
    chrome.storage.local.set({ filterAds: chkFilterAds.checked });
  });

  chkCookies.addEventListener("change", () => {
    chrome.storage.local.set({ shareCookies: chkCookies.checked });
    cookieWarn.style.display = chkCookies.checked ? "block" : "none";
  });

  chkSite.addEventListener("change", async () => {
    if (!currentHost) return;
    const res = await chrome.storage.local.get({ disabledDomains: [] });
    let list = Array.isArray(res.disabledDomains) ? [...res.disabledDomains] : [];
    if (!chkSite.checked) {
      if (!list.includes(currentHost)) list.push(currentHost);
      siteDesc.textContent = "Bu sitede video butonu kapalı";
    } else {
      list = list.filter(d => d !== currentHost);
      siteDesc.textContent = "Bu sitede video butonu açık";
    }
    await chrome.storage.local.set({ disabledDomains: list });
  });

  async function checkConnection() {
    const port = parseInt(inpPort.value, 10) || 28710;
    const token = inpToken.value.trim();
    const apiBase = `http://127.0.0.1:${port}`;
    footerPort.textContent = `Port: 127.0.0.1:${port}`;

    statusBox.className = "status-badge status-offline";
    statusText.textContent = "Bağlanıyor...";

    try {
      const headers = {};
      if (token) {
        headers["X-RipSync-Token"] = token;
      }
      const res = await fetch(`${apiBase}/api/status`, {
        method: "GET",
        headers: headers
      });

      if (res.status === 200) {
        statusBox.className = "status-badge status-online";
        statusText.textContent = "Masaüstü Uygulaması Bağlı";
      } else if (res.status === 401) {
        statusBox.className = "status-badge status-warning";
        statusText.textContent = "Yetkisiz (Token Uyuşmuyor)";
        authDetails.open = true;
      } else if (res.status === 403) {
        statusBox.className = "status-badge status-warning";
        statusText.textContent = "Yasaklı Origin (403)";
      } else {
        throw new Error(`HTTP ${res.status}`);
      }
    } catch (err) {
      // If offline, check if config has updated port via background sync
      try {
        const res = await chrome.runtime.sendMessage({ action: "get_bridge_config" });
        if (res && res.success && res.bridgePort && res.bridgePort !== port) {
          inpPort.value = res.bridgePort;
          if (res.bridgeToken) inpToken.value = res.bridgeToken;
          await chrome.storage.local.set({
            bridgePort: res.bridgePort,
            bridgeToken: res.bridgeToken || token
          });
          // Retry check with updated port
          return await checkConnection();
        }
      } catch (e2) {}

      statusBox.className = "status-badge status-offline";
      statusText.textContent = `Uygulama Kapalı / Port Çakışması (${port})`;
    }
  }

  btnSaveAuth.addEventListener("click", async () => {
    const port = parseInt(inpPort.value, 10) || 28710;
    const token = inpToken.value.trim();
    await chrome.storage.local.set({
      bridgePort: port,
      bridgeToken: token
    });
    await checkConnection();
  });

  btnSyncConfig.addEventListener("click", async () => {
    try {
      const res = await chrome.runtime.sendMessage({ action: "get_bridge_config" });
      if (res && res.success) {
        if (res.bridgeToken) inpToken.value = res.bridgeToken;
        if (res.bridgePort) inpPort.value = res.bridgePort;
        await chrome.storage.local.set({
          bridgeToken: res.bridgeToken || "",
          bridgePort: res.bridgePort || 28710
        });
        await checkConnection();
      } else {
        alert("Yapılandırma alınamadı. Lütfen masaüstü uygulamasını başlatın.");
      }
    } catch (e) {
      alert("Yapılandırma okunamadı: " + e.message);
    }
  });

  // Initial connection test
  await checkConnection();
});
