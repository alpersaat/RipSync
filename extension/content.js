(function() {
  let isSnifferEnabled = true;
  let disabledDomains = [];
  let filterAds = true;
  const dismissedVideos = new WeakSet();

  function isContextValid() {
    try {
      return typeof chrome !== "undefined" && !!(chrome.runtime && chrome.runtime.id);
    } catch (e) {
      return false;
    }
  }

  function isCurrentSiteDisabled() {
    try {
      const host = window.location.hostname.toLowerCase();
      if (!host) return false;
      return disabledDomains.some(d => host === d || host.endsWith("." + d));
    } catch (e) {
      return false;
    }
  }

  try {
    if (isContextValid() && chrome.storage && chrome.storage.local) {
      chrome.storage.local.get(["showVideoSniffer", "disabledDomains", "filterAds"], (res) => {
        if (!chrome.runtime.lastError && res) {
          if (res.showVideoSniffer === false) {
            isSnifferEnabled = false;
          }
          if (Array.isArray(res.disabledDomains)) {
            disabledDomains = res.disabledDomains;
          }
          if (res.filterAds !== undefined) {
            filterAds = res.filterAds;
          }
          scheduleUpdate();
        }
      });
    }
  } catch (e) {}

  function findRecentMediaFromPerformance() {
    try {
      const entries = performance.getEntriesByType("resource");
      for (let i = entries.length - 1; i >= 0; i--) {
        const name = entries[i].name;
        // Ignore fragmented DASH/CMAF init chunks like /0/0/...mp4
        if (name.includes("/0/0/") || name.includes("/1/0/") || name.includes("init.mp4")) {
          continue;
        }
        if (name.includes(".m3u8") || name.includes(".mpd")) {
          return name;
        }
        if (name.includes(".mp4") && !name.includes("log") && !name.includes("stat") && !name.includes("tracking")) {
          return name;
        }
      }
    } catch (e) {}
    return null;
  }

  function findTweetStatusUrl(videoElem) {
    try {
      const article = videoElem.closest("article");
      if (article) {
        const statusLink = article.querySelector('a[href*="/status/"]');
        if (statusLink) {
          const href = statusLink.getAttribute("href");
          return href.startsWith("http") ? href : (window.location.origin + href);
        }
      }
    } catch (e) {}
    return null;
  }

  function findTikTokVideoUrl(videoElem) {
    try {
      if (window.location.hostname.includes("tiktok.com")) {
        // Direct page url if on video page
        if (window.location.pathname.includes("/video/")) {
          return window.location.href;
        }
        // Container with anchor to the video
        const container = videoElem.closest('[data-e2e="feed-item"], [data-e2e="recommend-list-item-container"], div[class*="ItemContainer"], div[class*="DivItemContainer"], div[class*="VideoCard"], article') || videoElem.parentElement;
        if (container) {
          const link = container.querySelector('a[href*="/video/"]');
          if (link && link.href) {
            return link.href;
          }
        }
        // Fallback: check closest video links
        const allLinks = document.querySelectorAll('a[href*="/video/"]');
        for (let l of allLinks) {
          const vr = videoElem.getBoundingClientRect();
          const lr = l.getBoundingClientRect();
          if (Math.abs(vr.top - lr.top) < 400) {
            return l.href;
          }
        }
      }
    } catch (e) {}
    return null;
  }

  function findInstagramMediaUrl(videoElem) {
    try {
      if (window.location.hostname.includes("instagram.com")) {
        // Direct page url if on /reel/ or /p/
        if (window.location.pathname.includes("/reel/") || window.location.pathname.includes("/p/")) {
          return window.location.href;
        }
        // Closest container anchor
        const container = videoElem.closest('article, div[role="presentation"], div[role="dialog"], div[class*="x1lliihq"], div') || videoElem.parentElement;
        if (container) {
          const link = container.querySelector('a[href*="/reel/"], a[href*="/p/"], a[href*="/reels/"]');
          if (link && link.href) {
            return link.href;
          }
        }
        // Check performance entries for direct unwatermarked cdninstagram video
        const entries = performance.getEntriesByType("resource");
        for (let i = entries.length - 1; i >= 0; i--) {
          const name = entries[i].name;
          if (name.includes("cdninstagram.com") && name.includes(".mp4")) {
            return name.replace(/[?&]bytestart=\d+/, '').replace(/[?&]byteend=\d+/, '');
          }
        }
      }
    } catch (e) {}
    return null;
  }

  function getMediaUrl(mediaElem) {
    // 1. TikTok specific detection: ALWAYS prioritize video permalink for watermark-free download
    if (window.location.hostname.includes("tiktok.com")) {
      const ttUrl = findTikTokVideoUrl(mediaElem);
      if (ttUrl) return ttUrl;
      if (mediaElem.currentSrc && !mediaElem.currentSrc.startsWith("blob:")) {
        return mediaElem.currentSrc;
      }
      return window.location.href;
    }

    // 2. Instagram specific detection: Prioritize Reel permalink or unwatermarked CDN mp4
    if (window.location.hostname.includes("instagram.com")) {
      const igUrl = findInstagramMediaUrl(mediaElem);
      if (igUrl) return igUrl;
      if (mediaElem.currentSrc && !mediaElem.currentSrc.startsWith("blob:")) {
        return mediaElem.currentSrc;
      }
      return window.location.href;
    }

    // 3. Twitter / X.com specific detection: ALWAYS prioritize the tweet permalink
    if (window.location.hostname.includes("x.com") || window.location.hostname.includes("twitter.com")) {
      const tweetUrl = findTweetStatusUrl(mediaElem);
      if (tweetUrl) {
        return tweetUrl;
      }
      if (window.location.pathname.includes("/status/")) {
        return window.location.href;
      }
      const m3u8Url = findRecentMediaFromPerformance();
      if (m3u8Url && m3u8Url.includes(".m3u8")) {
        return m3u8Url;
      }
      return window.location.href;
    }

    // 4. YouTube
    if (window.location.hostname.includes("youtube.com") || window.location.hostname.includes("youtu.be")) {
      return window.location.href;
    }

    // 5. Direct src attribute if valid and not a blob
    if (mediaElem.currentSrc && !mediaElem.currentSrc.startsWith("blob:")) {
      return mediaElem.currentSrc;
    }
    if (mediaElem.src && !mediaElem.src.startsWith("blob:")) {
      return mediaElem.src;
    }

    // 6. Child <source> tags
    const sources = mediaElem.querySelectorAll("source");
    for (let s of sources) {
      if (s.src && !s.src.startsWith("blob:")) {
        return s.src;
      }
    }

    // 7. Check performance entries for other streaming sites (.m3u8, .mpd, .mp4)
    const perfUrl = findRecentMediaFromPerformance();
    if (perfUrl) {
      return perfUrl;
    }

    return window.location.href;
  }


  // ---------------------------------------------------------------------
  // Button placement
  //
  // The button is a single body-level `position: fixed` element per video
  // (NOT a child of the player). It is placed OUTSIDE the video, aligned to
  // the video's top-right corner, and is hidden while fullscreen is active.
  // ---------------------------------------------------------------------
  const GAP = 4;          // px between the video edge and the button
  const MIN_W = 160;      // ignore tiny videos (ads, previews, icons)
  const MIN_H = 90;

  const tracked = new Map(); // <video> element -> button element
  let updateQueued = false;

  function isFullscreenActive() {
    // Element fullscreen (YouTube / X / any player's fullscreen button)
    return !!(document.fullscreenElement || document.webkitFullscreenElement);
  }

  function isPlayerPage() {
    // On YouTube only watch / shorts / live pages: the home page's hover
    // previews are also <video> elements and must not get a button.
    if (location.hostname.includes("youtube.com")) {
      const p = location.pathname;
      return p.startsWith("/watch") || p.startsWith("/shorts") || p.startsWith("/live");
    }
    return true;
  }

  function isAdOrDecorativeVideo(video, rect) {
    if (!filterAds) return false;
    try {
      const host = window.location.hostname.toLowerCase();
      const isMajorVideoPlatform = host.includes("youtube.com") || host.includes("tiktok.com") ||
                                   host.includes("instagram.com") || host.includes("x.com") ||
                                   host.includes("twitter.com");

      // 1. Silent looping background / ad video without controls
      if (video.loop && video.muted && !video.controls) {
        if (!isMajorVideoPlatform) {
          return true;
        }
      }

      // 2. Short looping autoplaying clip without controls (like banner GIFs)
      if (video.loop && !video.controls && video.autoplay && (!video.duration || video.duration <= 25)) {
        if (!isMajorVideoPlatform) {
          return true;
        }
      }

      // 3. Known ad containers / widgets
      const adContainer = video.closest(
        '[class*="ad-"], [class*="ads-"], [class*="banner"], [class*="sponsor"], [class*="sponsored"], [class*="taboola"], [class*="criteo"], [class*="outbrain"], [class*="insider-"], [id*="google_ads"], [id*="taboola"]'
      );
      if (adContainer && !video.closest('#movie_player, .html5-video-player, [data-testid="videoPlayer"], .video-js, .jwplayer, [data-e2e="feed-video"]')) {
        return true;
      }

      // 4. Square/compact banner ads with tiny dimensions without controls
      if (!isMajorVideoPlatform && !video.controls && (rect.width < 220 || rect.height < 140)) {
        return true;
      }
    } catch (e) {}
    return false;
  }

  // Returns the true visual player bounding rect.
  // On YouTube and custom players, the raw <video> element is often positioned
  // off-screen (e.g. top: -748px) before play, while the container has the real box.
  function getPlayerBox(video) {
    const player = video.closest(
      "#movie_player, .html5-video-player, [data-testid='videoPlayer'], [data-testid='videoComponent'], .video-js, .jwplayer, .player-container, [data-e2e='feed-video'], [data-e2e='recommend-list-item-container'], div[class*='DivVideoContainer'], div[class*='DivPlayerContainer'], div[class*='_ab1y']"
    );
    if (player) {

      const pr = player.getBoundingClientRect();
      if (pr.width >= MIN_W && pr.height >= MIN_H) {
        return pr;
      }
    }
    const vr = video.getBoundingClientRect();
    if (vr.top < 0 && video.parentElement) {
      const parentRect = video.parentElement.getBoundingClientRect();
      if (parentRect.width >= MIN_W && parentRect.height >= MIN_H && parentRect.top >= 0) {
        return parentRect;
      }
    }
    return vr;
  }

  function isVideoShown(video, rect) {
    if (!video.isConnected) return false;
    if (dismissedVideos.has(video)) return false;
    if (rect.width < MIN_W || rect.height < MIN_H) return false;
    if (isAdOrDecorativeVideo(video, rect)) return false;
    const vw = window.innerWidth, vh = window.innerHeight;
    if (rect.right <= 0 || rect.bottom <= 0 || rect.left >= vw || rect.top >= vh) return false;
    const cs = window.getComputedStyle(video);
    return cs.display !== "none" && cs.visibility !== "hidden";
  }

  // Computes button coordinates: strictly OUTSIDE the video and at the TOP-RIGHT.
  // Never places the button at the bottom of the video.
  function computePosition(rect, bw, bh) {
    const vw = window.innerWidth, vh = window.innerHeight;
    const alignedLeft = Math.min(Math.max(rect.right - bw, 4), vw - bw - 4);

    // 1) Primary choice: Directly ABOVE the video, right-aligned to the video edge
    const topAbove = rect.top - bh - GAP;
    if (topAbove >= 4 && alignedLeft >= 0 && alignedLeft + bw <= vw) {
      return { left: alignedLeft, top: topAbove };
    }

    // 2) Secondary choice: Directly to the RIGHT of the video, aligned with top edge
    // (Applicable when video is flush against the top of the viewport)
    const leftBeside = rect.right + GAP;
    const topBeside = Math.max(rect.top, 4);
    if (leftBeside + bw <= vw - 4 && topBeside >= 0 && topBeside + bh <= vh) {
      return { left: leftBeside, top: topBeside };
    }

    // 3) Tight space above: if space above is between 0 and 4px
    if (topAbove >= 0 && alignedLeft >= 0 && alignedLeft + bw <= vw) {
      return { left: alignedLeft, top: topAbove };
    }

    return null;
  }

  let pollIntervalId = null;
  let observer = null;
  let mutationPending = false;

  function teardown() {
    if (pollIntervalId) {
      clearInterval(pollIntervalId);
      pollIntervalId = null;
    }
    if (observer) {
      try { observer.disconnect(); } catch (e) {}
      observer = null;
    }
    for (const [video, btn] of tracked) {
      try { btn.remove(); } catch (e) {}
    }
    tracked.clear();
  }

  function hideButton(btn) {
    btn.classList.remove("ripsync-on");
  }

  function updateAll() {
    if (!isContextValid()) {
      teardown();
      return;
    }
    updateQueued = false;
    const hideEverything = !isSnifferEnabled || isCurrentSiteDisabled() || isFullscreenActive() || !isPlayerPage();

    for (const [video, btn] of tracked) {
      if (!video.isConnected) {
        btn.remove();
        tracked.delete(video);
        continue;
      }
      if (hideEverything) {
        hideButton(btn);
        continue;
      }
      const rect = getPlayerBox(video);
      if (!isVideoShown(video, rect)) {
        hideButton(btn);
        continue;
      }
      const bw = btn.offsetWidth || 125;
      const bh = btn.offsetHeight || 22;
      const pos = computePosition(rect, bw, bh);
      if (!pos) {
        hideButton(btn);
        continue;
      }
      btn.style.left = Math.round(pos.left) + "px";
      btn.style.top = Math.round(pos.top) + "px";
      btn.classList.add("ripsync-on");
    }
  }

  function scheduleUpdate() {
    if (!isContextValid()) {
      teardown();
      return;
    }
    if (updateQueued) return;
    updateQueued = true;
    requestAnimationFrame(updateAll);
  }

  function createButton(mediaElem) {
    const btn = document.createElement("div");
    btn.className = "ripsync-sniffer-btn";
    btn.title = "RipSync Kalite ve Format Seçenekleri";

    const isSocial = window.location.hostname.includes("tiktok.com") || window.location.hostname.includes("instagram.com");
    const defaultLabelText = isSocial ? "Filigransız İndir" : "Bu Videoyu İndir";

    // Use DOM creation (avoids innerHTML / TrustedHTML restrictions)
    const icon = document.createElement("span");
    icon.className = "ripsync-icon";
    icon.textContent = isSocial ? "✨" : "⚡";

    const label = document.createElement("span");
    label.className = "ripsync-label";
    label.textContent = defaultLabelText;

    const arrow = document.createElement("span");
    arrow.className = "ripsync-arrow";
    arrow.textContent = "▼";

    const dismiss = document.createElement("span");
    dismiss.className = "ripsync-dismiss-btn";
    dismiss.textContent = "✕";
    dismiss.title = "Bu videoda gizle";
    dismiss.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      dismissedVideos.add(mediaElem);
      hideButton(btn);
      btn.remove();
      tracked.delete(mediaElem);
    });

    btn.appendChild(icon);
    btn.appendChild(label);
    btn.appendChild(arrow);
    btn.appendChild(dismiss);

    // Dropdown menu container
    const menu = document.createElement("div");
    menu.className = "ripsync-dropdown-menu";

    const menuItems = isSocial ? [
      {
        icon: "✨",
        title: "Filigransız Video İndir",
        badge: "HD MP4",
        quality: "max",
        ext: ".mp4"
      },
      {
        type: "divider"
      },
      {
        icon: "🎵",
        title: "Sadece Ses / Müzik",
        badge: "MP3",
        quality: "audio",
        ext: ".mp3"
      }
    ] : [
      {
        icon: "🎬",
        title: "1080p Full HD",
        badge: "MP4",
        quality: "1080p",
        ext: ".mp4"
      },
      {
        icon: "🎬",
        title: "720p HD",
        badge: "MP4",
        quality: "720p",
        ext: ".mp4"
      },
      {
        type: "divider"
      },
      {
        icon: "🎵",
        title: "Sadece Ses / Müzik",
        badge: "MP3",
        quality: "audio",
        ext: ".mp3"
      },
      {
        type: "divider"
      },
      {
        icon: "📄",
        title: "Altyazı İndir",
        badge: ".SRT",
        quality: "subtitle",
        ext: ".srt"
      }
    ];

    function setStatus(text, isLoading) {
      if (isLoading) {
        btn.classList.add("loading");
      } else {
        btn.classList.remove("loading");
      }
      label.textContent = text;
    }

    function triggerDownload(quality, ext, labelText) {
      if (!isContextValid()) {
        teardown();
        alert("Eklenti yenilendi. Lütfen bu sayfayı (F5) yenileyin.");
        return;
      }

      const mediaUrl = getMediaUrl(mediaElem);
      if (!mediaUrl) {
        alert("Medya adresi tespit edilemedi.");
        return;
      }

      setStatus("Bağlanıyor...", true);
      menu.classList.remove("show");
      btn.classList.remove("open");

      const baseTitle = document.title.replace(/[\/\\?%*:|"<>]/g, '_').slice(0, 100).trim() || "video";
      const suggestedName = baseTitle + ext;

      try {
        chrome.runtime.sendMessage({
          action: "download_media",
          url: mediaUrl,
          filename: suggestedName,
          quality: quality
        }, (resp) => {
          if (chrome.runtime.lastError || !(resp && resp.success)) {
            setStatus("❌ Bağlantı Yok", false);
          } else {
            setStatus("✔ Başlatıldı", false);
          }
          setTimeout(() => {
            setStatus(defaultLabelText, false);
            scheduleUpdate();
          }, 3000);
          scheduleUpdate();
        });
      } catch (err) {
        setStatus("❌ Bağlantı Yok", false);
      }
    }


    // Build Menu Items
    menuItems.forEach((item) => {
      if (item.type === "divider") {
        const div = document.createElement("div");
        div.className = "ripsync-menu-divider";
        menu.appendChild(div);
        return;
      }

      const row = document.createElement("div");
      row.className = "ripsync-menu-item";

      const rIcon = document.createElement("span");
      rIcon.className = "ripsync-menu-item-icon";
      rIcon.textContent = item.icon;

      const rText = document.createElement("span");
      rText.className = "ripsync-menu-item-text";
      rText.textContent = item.title;

      const rBadge = document.createElement("span");
      rBadge.className = "ripsync-menu-item-badge";
      rBadge.textContent = item.badge;

      row.appendChild(rIcon);
      row.appendChild(rText);
      row.appendChild(rBadge);

      row.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        triggerDownload(item.quality, item.ext, item.title);
      });

      menu.appendChild(row);
    });

    btn.appendChild(menu);

    // Toggle menu on button click
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      const isShowing = menu.classList.contains("show");
      if (isShowing) {
        menu.classList.remove("show");
        btn.classList.remove("open");
      } else {
        menu.classList.add("show");
        btn.classList.add("open");
      }
    });

    // Close menu when clicking outside
    document.addEventListener("click", (e) => {
      if (!btn.contains(e.target)) {
        menu.classList.remove("show");
        btn.classList.remove("open");
      }
    }, true);

    return btn;
  }

  function attachSnifferButton(mediaElem) {
    if (tracked.has(mediaElem)) return;

    const btn = createButton(mediaElem);
    // Attached to <html>/<body>, never inside the player: it therefore does
    // not overlay the video and is not part of the fullscreen element.
    (document.body || document.documentElement).appendChild(btn);
    tracked.set(mediaElem, btn);
    scheduleUpdate();
  }

  function scanMedia() {
    if (!isContextValid()) {
      teardown();
      return;
    }
    document.querySelectorAll("video").forEach(attachSnifferButton);
  }

  // Initial scan
  scanMedia();

  // MutationObserver scan for dynamically loaded video elements.
  // Debounced: mutation-heavy pages don't re-scan on every microtask.
  try {
    observer = new MutationObserver(() => {
      if (!isContextValid()) {
        teardown();
        return;
      }
      if (mutationPending) return;
      mutationPending = true;
      setTimeout(() => {
        mutationPending = false;
        scanMedia();
        scheduleUpdate();
      }, 300);
    });
    observer.observe(document.body || document.documentElement, {
      childList: true,
      subtree: true
    });
  } catch (e) {}

  // Keep the button glued to the video while the page changes
  window.addEventListener("scroll", scheduleUpdate, { capture: true, passive: true });
  window.addEventListener("resize", scheduleUpdate, { passive: true });
  document.addEventListener("fullscreenchange", updateAll);
  document.addEventListener("webkitfullscreenchange", updateAll);

  // Layout changes that fire no event (theater mode, lazy layout, SPA nav).
  // 2 s instead of 300 ms, and skipped entirely when no button is tracked
  // (i.e. pages without videos do not poll at all).
  pollIntervalId = setInterval(() => {
    if (!isContextValid()) {
      teardown();
      return;
    }
    if (tracked.size === 0) return;
    scheduleUpdate();
  }, 2000);

  // Also scan on media play
  document.addEventListener("play", (e) => {
    if (!isContextValid()) {
      teardown();
      return;
    }
    if (e.target && e.target.tagName === "VIDEO") {
      attachSnifferButton(e.target);
    }
  }, true);

  // React to the popup toggle without needing a page reload
  try {
    if (isContextValid() && chrome.storage && chrome.storage.onChanged) {
      chrome.storage.onChanged.addListener((changes, area) => {
        if (!isContextValid()) {
          teardown();
          return;
        }
        if (area === "local") {
          if (changes.showVideoSniffer) {
            isSnifferEnabled = changes.showVideoSniffer.newValue !== false;
          }
          if (changes.disabledDomains) {
            disabledDomains = changes.disabledDomains.newValue || [];
          }
          if (changes.filterAds) {
            filterAds = changes.filterAds.newValue !== false;
          }
          scheduleUpdate();
        }
      });
    }
  } catch (e) {}

})();
