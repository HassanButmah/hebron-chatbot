/**
 * Hebron University Chatbot Widget — widget.js
 *
 * Embed on any page:
 *   <link rel="stylesheet" href="/widget/widget.css">
 *   <script src="/widget/widget.js" defer></script>
 *
 * The script injects the widget HTML into document.body, then fetches
 * runtime config from  GET /widget/config  (served by rag_api.py).
 *
 * Optional override: set window.HCW_API_BASE before loading this script
 * if the API lives on a different origin from the host page.
 */
(function () {
  "use strict";

  /* ------------------------------------------------------------------ */
  /* 0. Detect API base URL                                               */
  /* ------------------------------------------------------------------ */
  function detectApiBase() {
    if (window.HCW_API_BASE) return window.HCW_API_BASE.replace(/\/$/, "");
    // Derive from script src: strip /widget/widget.js suffix
    const me =
      document.currentScript ||
      (function () {
        const scripts = document.querySelectorAll('script[src*="widget.js"]');
        return scripts[scripts.length - 1];
      })();
    if (me && me.src) {
      try {
        const url = new URL(me.src);
        return url.origin; // e.g. https://api.hebron.edu
      } catch (_) {
        /* ignore */
      }
    }
    return window.location.origin;
  }

  const API_BASE_URL = detectApiBase();

  /* ------------------------------------------------------------------ */
  /* 1. Inject widget HTML                                                */
  /* ------------------------------------------------------------------ */
  const WIDGET_HTML = `
<!-- Hebron University Chatbot Widget -->
<button type="button" class="chat-avatar" id="hcw-avatar" aria-label="افتح المساعد">
  <span class="avatar-emoji-fallback" aria-hidden="true">🎓</span>
</button>
<div class="chat-avatar-tooltip" id="hcw-avatar-tooltip" role="status">
  مرحباً، أنا خليلك 🌿، الشات بوت الرسمي لجامعة الخليل
</div>

<div class="chat-widget" id="hcw-widget" role="dialog" aria-modal="false" aria-label="مساعد جامعة الخليل">

  <!-- History View -->
  <div id="hcw-history-view">
    <div class="chat-header history-header">
      <div class="header-brand">
        <div class="header-logo header-logo--emoji" id="hcw-logo-history">🎓</div>
        <div class="header-wordmark">
          <div class="header-title-ar">جامعـة الخليـل</div>
          <div class="header-title-en">HEBRON UNIVERSITY</div>
        </div>
      </div>
      <button type="button" class="close-btn" id="hcw-close-history" aria-label="إغلاق">✕</button>
    </div>
    <button type="button" class="history-new-chat-btn" id="hcw-new-chat">ابدأ محادثة جديدة</button>
    <div id="hcw-session-list"></div>
  </div>

  <!-- Chat View -->
  <div id="hcw-chat-view">
    <div class="chat-header conversation-header">
      <button type="button" class="close-btn" id="hcw-close-chat" aria-label="إغلاق">✕</button>
      <div class="header-brand">
        <div class="header-logo header-logo--emoji" id="hcw-logo-chat">🎓</div>
        <div class="header-wordmark">
          <div class="header-title-ar">جامعـة الخليـل</div>
          <div class="header-title-en">HEBRON UNIVERSITY</div>
        </div>
      </div>
      <button type="button" class="back-btn" id="hcw-back" title="عودة" aria-label="عودة">←</button>
    </div>

    <div class="messages-area" id="hcw-messages" role="log" aria-live="polite" aria-label="المحادثة"></div>

    <div class="suggestions" id="hcw-suggestions">
      <div class="suggestions-title" id="hcw-suggestions-title">أسئلة شائعة:</div>
      <div class="suggestion-chips" id="hcw-chips"></div>
    </div>

    <div class="faq-overlay" id="hcw-faq-overlay" aria-hidden="true">
      <div class="faq-overlay-backdrop" id="hcw-faq-backdrop"></div>
      <div class="faq-overlay-panel" role="dialog" aria-labelledby="hcw-faq-heading">
        <div class="faq-overlay-header">
          <span id="hcw-faq-heading">أسئلة شائعة</span>
          <button type="button" class="faq-overlay-close" id="hcw-faq-close" title="إغلاق">✕</button>
        </div>
        <div class="suggestion-chips faq-overlay-chips" id="hcw-faq-chips"></div>
      </div>
    </div>

    <div class="file-preview" id="hcw-file-preview">
      <span class="file-preview-text" id="hcw-file-name">📎 file.pdf</span>
      <span class="file-remove" id="hcw-file-remove" role="button" tabindex="0" aria-label="إزالة الملف">✕</span>
    </div>

    <div class="input-area">
      <div class="input-status-bar" id="hcw-status-bar" role="status" aria-live="polite">
        <span class="input-spinner" aria-hidden="true"></span>
        <span class="input-status-text" id="hcw-status-text"></span>
      </div>
      <div class="input-toolbar" id="hcw-toolbar">
        <div class="voice-record-cluster" id="hcw-voice-cluster" aria-live="polite">
          <canvas class="voice-visualizer" id="hcw-visualizer" width="120" height="32" aria-hidden="true"></canvas>
          <span class="record-timer" id="hcw-timer">00:00</span>
          <button type="button" class="cancel-record-btn" id="hcw-cancel-rec" title="إلغاء التسجيل">✖️ إلغاء</button>
          <button type="button" class="action-btn mic-btn" id="hcw-mic" title="تسجيل صوتي" aria-label="تسجيل صوتي">
            <svg class="mic-icon" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
              <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z"/>
              <path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z"/>
            </svg>
          </button>
        </div>
        <input type="text" class="input-field" id="hcw-input" placeholder="اكتب رسالتك..." dir="rtl" autocomplete="off" />
        <button type="button" class="action-btn faq-btn" id="hcw-faq-btn" title="أسئلة شائعة" aria-label="أسئلة شائعة">?</button>
        <button type="button" class="action-btn map-input-btn" id="hcw-map-btn" title="خريطة الحرم" aria-label="خريطة الحرم">
          <img class="map-icon-img" id="hcw-map-icon" alt="" aria-hidden="true" />
          <svg class="map-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9"
               stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">
            <path d="M3 6.8l5-2.3 5 2.3 5-2.3 3 1.4v12.8l-3-1.4-5 2.3-5-2.3-5 2.3V6.8z"/>
            <path d="M8 4.5v12.8"/><path d="M16 5.4v12.8"/>
            <path d="M12 14s3.2-2.9 3.2-5.4a3.2 3.2 0 0 0-6.4 0C8.8 11.1 12 14 12 14z"/>
            <circle cx="12" cy="8.6" r="1"/>
          </svg>
        </button>
        <button type="button" class="action-btn send-btn" id="hcw-send" aria-label="إرسال">➤</button>
      </div>
    </div>

    <button type="button" class="scroll-to-bottom" id="hcw-scroll-btn"
            title="الذهاب إلى الآخر" aria-label="الذهاب إلى الآخر">↓</button>
  </div>

  <!-- Campus Map Modal -->
  <div class="map-modal" id="hcw-map-modal" aria-hidden="true">
    <div class="map-modal-backdrop" id="hcw-map-backdrop"></div>
    <div class="map-modal-panel" role="dialog" aria-modal="true" aria-label="خريطة الحرم الجامعي">
      <div class="map-modal-topbar">
        <div class="map-modal-title">خريطة الحرم الجامعي</div>
        <button type="button" class="map-modal-close" id="hcw-map-close" title="إغلاق" aria-label="إغلاق">×</button>
      </div>
      <div class="map-modal-body" id="hcw-map-body">
        <div class="map-viewport" id="hcw-map-viewport">
          <img id="hcw-map-img" class="map-image" alt="خريطة الحرم الجامعي" />
        </div>
        <div class="map-controls" aria-hidden="true">
          <button type="button" class="map-ctrl-btn" id="hcw-zoom-out" title="تصغير">−</button>
          <button type="button" class="map-ctrl-btn" id="hcw-zoom-in"  title="تكبير">＋</button>
          <button type="button" class="map-ctrl-btn" id="hcw-map-reset" title="إعادة ضبط">⟲</button>
        </div>
      </div>
    </div>
  </div>
</div>
`;

  const container = document.createElement("div");
  container.id = "hcw-root";
  container.innerHTML = WIDGET_HTML;
  document.body.appendChild(container);

  /* ------------------------------------------------------------------ */
  /* 2. Runtime state                                                     */
  /* ------------------------------------------------------------------ */
  let FAQ_ITEMS = [];
  let BOT_LOGO_B64 = null;
  let CAMPUS_MAP_SRC = null; // URL or data-URI
  let MAP_ICON_SRC = null; // data-URI

  if (!localStorage.getItem("rag_user_id")) {
    localStorage.setItem("rag_user_id", crypto.randomUUID());
  }
  window.userId = localStorage.getItem("rag_user_id");
  window.currentSessionId = null;

  const DEFAULT_SUGGESTIONS_TITLE = "أسئلة شائعة:";
  const FOLLOWUP_SUGGESTIONS_TITLE = "ربما يفيدك أحد الأسئلة التالية:";

  let lastDisplayedDate = null;
  let selectedFile = null;
  let isRecording = false;
  let mediaRecorder = null;
  let recordingStream = null;
  let audioChunks = [];
  let recordingTimeoutId = null;
  const MAX_RECORDING_MS = 60 * 1000;
  let recordTimerIntervalId = null;
  let recordStartedAt = 0;
  let recordingDiscardFlag = false;
  let vizRafId = null;
  let audioVizContext = null;
  let audioVizAnalyser = null;
  let audioVizSource = null;
  let messageCount = 0;
  let lastBotMessageId = null;
  let mapOpen = false;
  const MAP_MIN_SCALE = 0.15;
  const MAP_MAX_SCALE = 4;
  let mapScale = 1,
    mapTx = 0,
    mapTy = 0;
  let isMapDragging = false;
  let mapDragStartX = 0,
    mapDragStartY = 0,
    mapDragOriginTx = 0,
    mapDragOriginTy = 0;

  /* ------------------------------------------------------------------ */
  /* 3. DOM references                                                    */
  /* ------------------------------------------------------------------ */
  const chatAvatar = document.getElementById("hcw-avatar");
  const chatWidget = document.getElementById("hcw-widget");
  const closeBtnHistory = document.getElementById("hcw-close-history");
  const closeBtn = document.getElementById("hcw-close-chat");
  const backBtn = document.getElementById("hcw-back");
  const newChatBtn = document.getElementById("hcw-new-chat");
  const historyView = document.getElementById("hcw-history-view");
  const chatView = document.getElementById("hcw-chat-view");
  const sessionList = document.getElementById("hcw-session-list");
  const messagesArea = document.getElementById("hcw-messages");
  const suggestions = document.getElementById("hcw-suggestions");
  const suggestionsTitle = document.getElementById("hcw-suggestions-title");
  const suggestionChips = document.getElementById("hcw-chips");
  const faqBtn = document.getElementById("hcw-faq-btn");
  const faqOverlay = document.getElementById("hcw-faq-overlay");
  const faqOverlayBackdrop = document.getElementById("hcw-faq-backdrop");
  const faqOverlayClose = document.getElementById("hcw-faq-close");
  const faqOverlayChips = document.getElementById("hcw-faq-chips");
  const filePreview = document.getElementById("hcw-file-preview");
  const fileName = document.getElementById("hcw-file-name");
  const fileRemove = document.getElementById("hcw-file-remove");
  const inputStatusBar = document.getElementById("hcw-status-bar");
  const inputStatusText = document.getElementById("hcw-status-text");
  const inputToolbar = document.getElementById("hcw-toolbar");
  const messageInput = document.getElementById("hcw-input");
  /** Empty → rtl (Arabic placeholder); typed → auto so English caret/scroll tracks correctly */
  function syncChatInputDir() {
    if (!messageInput) return;
    messageInput.dir = messageInput.value.trim() ? "auto" : "rtl";
  }
  syncChatInputDir();
  const sendBtn = document.getElementById("hcw-send");
  const micBtn = document.getElementById("hcw-mic");
  const voiceRecordCluster = document.getElementById("hcw-voice-cluster");
  const recordTimer = document.getElementById("hcw-timer");
  const cancelRecordBtn = document.getElementById("hcw-cancel-rec");
  const voiceVisualizer = document.getElementById("hcw-visualizer");
  const scrollToBottomBtn = document.getElementById("hcw-scroll-btn");
  const mapModal = document.getElementById("hcw-map-modal");
  const mapModalBackdrop = document.getElementById("hcw-map-backdrop");
  const mapModalClose = document.getElementById("hcw-map-close");
  const campusMapImg = document.getElementById("hcw-map-img");
  const mapViewport = document.getElementById("hcw-map-viewport");
  const mapZoomInBtn = document.getElementById("hcw-zoom-in");
  const mapZoomOutBtn = document.getElementById("hcw-zoom-out");
  const mapResetBtn = document.getElementById("hcw-map-reset");
  const mapInputBtn = document.getElementById("hcw-map-btn");
  const logoHistory = document.getElementById("hcw-logo-history");
  const logoChat = document.getElementById("hcw-logo-chat");

  /* ------------------------------------------------------------------ */
  /* 4. Fetch runtime config from backend                                 */
  /* ------------------------------------------------------------------ */
  async function loadConfig() {
    try {
      const res = await fetch(API_BASE_URL + "/widget/config");
      if (!res.ok) return;
      const cfg = await res.json();

      if (cfg.bot_logo_b64) {
        BOT_LOGO_B64 = cfg.bot_logo_b64;
        applyLogo();
      }
      if (cfg.campus_map_url) {
        CAMPUS_MAP_SRC = cfg.campus_map_url;
      } else if (cfg.campus_map_b64) {
        const mime = cfg.campus_map_mime || "image/jpeg";
        CAMPUS_MAP_SRC = "data:" + mime + ";base64," + cfg.campus_map_b64;
      }
      if (campusMapImg && CAMPUS_MAP_SRC) {
        campusMapImg.onload = resetMapView;
        campusMapImg.src = CAMPUS_MAP_SRC;
        if (campusMapImg.complete) resetMapView();
      }
      if (cfg.map_icon_b64) {
        const mime = cfg.map_icon_mime || "image/jpeg";
        MAP_ICON_SRC = "data:" + mime + ";base64," + cfg.map_icon_b64;
        applyMapIcon();
      }
      if (Array.isArray(cfg.faq_items)) {
        FAQ_ITEMS = cfg.faq_items;
        renderFaqSuggestions();
      }
    } catch (e) {
      console.warn("[HCW] config fetch failed", e);
    }
  }

  function applyLogo() {
    const imgTag =
      '<img src="data:image/png;base64,' +
      BOT_LOGO_B64 +
      '" alt="شعار البوت" />';
    [logoHistory, logoChat].forEach(function (el) {
      if (!el) return;
      el.classList.remove("header-logo--emoji");
      el.classList.add("header-logo--image");
      el.innerHTML = imgTag;
    });
    if (chatAvatar) {
      chatAvatar.innerHTML =
        '<img src="data:image/png;base64,' +
        BOT_LOGO_B64 +
        '" alt="شعار البوت" />';
    }
  }

  function applyMapIcon() {
    const iconImg = document.getElementById("hcw-map-icon");
    if (!iconImg || !MAP_ICON_SRC) return;
    iconImg.src = MAP_ICON_SRC;
    iconImg.classList.add("is-loaded");
  }

  /* ------------------------------------------------------------------ */
  /* 5. Utility helpers                                                   */
  /* ------------------------------------------------------------------ */
  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function makeEmailsClickable(text) {
    return text.replace(
      /([a-zA-Z0-9._-]+@[a-zA-Z0-9._-]+\.[a-zA-Z0-9_-]+)/g,
      function (email) {
        const safe = email.replace(/&/g, "&amp;").replace(/"/g, "&quot;");
        return (
          '<a class="email-link" href="mailto:' +
          safe +
          '" target="_blank" rel="noopener noreferrer">' +
          email +
          "</a>"
        );
      },
    );
  }

  function formatAssistantText(raw) {
    let text = escapeHtml(raw || "");
    text = text.replace(/([\\.!؟:]) -\s+/g, "$1\n- ");
    text = text.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    text = text.replace(/(https?:\/\/[^\s<]+)/g, function (match) {
      const href = match.replace(/&amp;/g, "&");
      const safe = href.replace(/&/g, "&amp;").replace(/"/g, "&quot;");
      return (
        '<a href="' +
        safe +
        '" target="_blank" rel="noopener noreferrer">' +
        match +
        "</a>"
      );
    });
    text = makeEmailsClickable(text);
    return text;
  }

  function formatMessageTimestamp(date) {
    const d =
      date instanceof Date && !isNaN(date.getTime()) ? date : new Date();
    return escapeHtml(formatTimestampText(d));
  }

  function formatTimestampText(date) {
    const d =
      date instanceof Date && !isNaN(date.getTime()) ? date : new Date();
    const dateText = d.toLocaleDateString("ar-SA", {
      month: "short",
      day: "numeric",
      timeZone: "Asia/Hebron",
    });
    const timeText = d.toLocaleTimeString("ar-SA", {
      hour: "2-digit",
      minute: "2-digit",
      timeZone: "Asia/Hebron",
    });
    return dateText + " - " + timeText;
  }

  function getTimeString() {
    return formatMessageTimestamp(new Date());
  }

  function formatTimeFromDbIso(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    if (isNaN(d.getTime())) return "—";
    return formatMessageTimestamp(d);
  }

  function getDateStringAR(date) {
    return new Date(date).toLocaleDateString("ar-SA", {
      year: "numeric",
      month: "long",
      day: "numeric",
      timeZone: "Asia/Hebron",
    });
  }

  function shouldInsertDateSeparator(currentDate) {
    const s = getDateStringAR(currentDate);
    if (lastDisplayedDate !== s) {
      lastDisplayedDate = s;
      return true;
    }
    return false;
  }

  function insertDateSeparator(currentDate) {
    const div = document.createElement("div");
    div.className = "date-separator";
    div.innerHTML =
      '<span class="date-separator-text">' +
      escapeHtml(getDateStringAR(currentDate)) +
      "</span>";
    messagesArea.appendChild(div);
  }

  /* ------------------------------------------------------------------ */
  /* 6. Scroll helpers                                                    */
  /* ------------------------------------------------------------------ */
  function isAtBottom() {
    if (!messagesArea) return true;
    return (
      messagesArea.scrollTop >=
      messagesArea.scrollHeight - messagesArea.clientHeight - 40
    );
  }

  function updateScrollToBottomButton() {
    if (!messagesArea || !scrollToBottomBtn) return;
    const scrollable =
      messagesArea.scrollHeight > messagesArea.clientHeight + 5;
    scrollToBottomBtn.classList.toggle("visible", scrollable && !isAtBottom());
  }

  function scrollToBottomSmooth() {
    if (messagesArea)
      messagesArea.scrollTo({
        top: messagesArea.scrollHeight,
        behavior: "smooth",
      });
  }

  function scrollToBottomImmediate() {
    if (messagesArea) messagesArea.scrollTop = messagesArea.scrollHeight;
  }

  function prefersReducedMotion() {
    try {
      return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    } catch (_) {
      return false;
    }
  }

  /** Scroll messages area so `el`'s top aligns near the top (smooth when allowed). */
  function scrollMessagesAreaToElementTop(el, behavior) {
    if (!messagesArea || !el) return;
    const pad = 8;
    const elRect = el.getBoundingClientRect();
    const areaRect = messagesArea.getBoundingClientRect();
    const nextTop = Math.max(
      0,
      messagesArea.scrollTop + (elRect.top - areaRect.top) - pad,
    );
    messagesArea.scrollTo({
      top: nextTop,
      behavior: behavior === "smooth" ? "smooth" : "auto",
    });
    updateScrollToBottomButton();
  }

  /** Find the user bubble directly above this bot message (skip date separators). */
  function findPreviousUserMessage(botEl) {
    let el = botEl.previousElementSibling;
    while (el) {
      if (el.classList && el.classList.contains("user-message")) return el;
      el = el.previousElementSibling;
    }
    return null;
  }

  /**
   * After a bot reply, keep the user's question in view and show the start of the answer.
   * Uses smooth scrolling inside the messages pane (falls back to instant if reduced-motion).
   */
  function scrollBotReplyWithQuestionIntoView(botEl) {
    if (!messagesArea || !botEl) return;
    const questionEl = findPreviousUserMessage(botEl);
    const anchor = questionEl || botEl;
    const smooth = !prefersReducedMotion();

    function align(mode) {
      scrollMessagesAreaToElementTop(anchor, mode === "smooth" ? "smooth" : "auto");
    }

    requestAnimationFrame(function () {
      align(smooth ? "smooth" : "auto");
    });

    if (smooth) {
      /* One settle pass after layout / fonts — instant micro-adjust only if needed */
      setTimeout(function () {
        const elRect = anchor.getBoundingClientRect();
        const areaRect = messagesArea.getBoundingClientRect();
        const pad = 8;
        const idealTop =
          messagesArea.scrollTop + (elRect.top - areaRect.top) - pad;
        if (Math.abs(messagesArea.scrollTop - idealTop) > 3)
          messagesArea.scrollTo({ top: Math.max(0, idealTop), behavior: "auto" });
        updateScrollToBottomButton();
      }, 420);
    }
  }

  function keepLatestMessageVisible() {
    scrollToBottomImmediate();
    requestAnimationFrame(function () {
      scrollToBottomImmediate();
      updateScrollToBottomButton();
    });
    setTimeout(function () {
      scrollToBottomImmediate();
      updateScrollToBottomButton();
    }, 80);
    setTimeout(function () {
      scrollToBottomImmediate();
      updateScrollToBottomButton();
    }, 220);
  }

  /* ------------------------------------------------------------------ */
  /* 7. Status bar                                                        */
  /* ------------------------------------------------------------------ */
  function showInputStatus(msg) {
    if (inputStatusText) inputStatusText.textContent = msg;
    if (inputStatusBar) inputStatusBar.classList.add("is-visible");
  }
  function hideInputStatus() {
    if (inputStatusBar) inputStatusBar.classList.remove("is-visible");
    if (inputStatusText) inputStatusText.textContent = "";
  }

  /* ------------------------------------------------------------------ */
  /* 8. Suggestions / FAQ chips                                           */
  /* ------------------------------------------------------------------ */
  function resetSuggestionsTitle() {
    if (suggestionsTitle)
      suggestionsTitle.textContent = DEFAULT_SUGGESTIONS_TITLE;
    if (suggestions) suggestions.classList.remove("suggestions--followup");
  }

  function setFollowupSuggestionsTitle() {
    if (suggestionsTitle)
      suggestionsTitle.textContent = FOLLOWUP_SUGGESTIONS_TITLE;
    if (suggestions) suggestions.classList.add("suggestions--followup");
  }

  function renderFaqChipsInto(container) {
    if (!container) return;
    container.innerHTML = "";
    if (!Array.isArray(FAQ_ITEMS) || FAQ_ITEMS.length === 0) {
      const empty = document.createElement("div");
      empty.style.cssText = "color:#777;font-size:13px";
      empty.textContent = "لا توجد أسئلة شائعة مضافة حالياً.";
      container.appendChild(empty);
      return;
    }
    FAQ_ITEMS.forEach(function (faq) {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "suggestion-chip";
      chip.textContent = (faq.question || "").trim();
      chip.addEventListener("click", function () {
        sendFaq(faq.id, faq.question || "", faq.answer || "");
      });
      container.appendChild(chip);
    });
  }

  function renderFaqSuggestions() {
    renderFaqChipsInto(suggestionChips);
    renderFaqChipsInto(faqOverlayChips);
    const horiz = Array.isArray(FAQ_ITEMS) && FAQ_ITEMS.length > 4;
    if (suggestionChips)
      suggestionChips.classList.toggle("horizontal-scroll", horiz);
    if (faqOverlayChips)
      faqOverlayChips.classList.toggle("horizontal-scroll", horiz);
    if (horiz) {
      if (suggestionChips) suggestionChips.scrollLeft = 0;
      if (faqOverlayChips) faqOverlayChips.scrollLeft = 0;
    }
  }

  function closeFaqOverlay() {
    if (!faqOverlay) return;
    faqOverlay.classList.remove("open");
    faqOverlay.setAttribute("aria-hidden", "true");
  }

  function openFaqOverlay() {
    if (!faqOverlay) return;
    renderFaqChipsInto(faqOverlayChips);
    faqOverlay.classList.add("open");
    faqOverlay.setAttribute("aria-hidden", "false");
  }

  function toggleFaqOverlay() {
    if (faqOverlay && faqOverlay.classList.contains("open")) closeFaqOverlay();
    else openFaqOverlay();
  }

  /* ------------------------------------------------------------------ */
  /* 9. Add message                                                       */
  /* ------------------------------------------------------------------ */
  function addMessage(
    text,
    role,
    showFeedback,
    feedbackId,
    messageId,
    timestampIso,
    fromHistory,
  ) {
    showFeedback = !!showFeedback;
    fromHistory = !!fromHistory;

    const wasAtBottom = fromHistory ? false : isAtBottom();
    const msgDate =
      timestampIso && !isNaN(new Date(timestampIso).getTime())
        ? new Date(timestampIso)
        : new Date();

    if (shouldInsertDateSeparator(msgDate)) insertDateSeparator(msgDate);

    const msgDiv = document.createElement("div");
    msgDiv.className = "message " + role + "-message";

    const avatarHtml =
      role === "bot"
        ? BOT_LOGO_B64
          ? '<div class="message-avatar message-avatar-bot-img"><img src="data:image/png;base64,' +
            BOT_LOGO_B64 +
            '" alt=""/></div>'
          : '<div class="message-avatar">🤖</div>'
        : '<div class="message-avatar" aria-hidden="true"><svg class="message-avatar-user-icon" viewBox="0 0 24 24" fill="currentColor" focusable="false" aria-hidden="true"><path d="M12 12c2.761 0 5-2.239 5-5S14.761 2 12 2 7 4.239 7 7s2.239 5 5 5zm0 2c-4.418 0-8 2.239-8 5v1c0 .552.448 1 1 1h14c.552 0 1-.448 1-1v-1c0-2.761-3.582-5-8-5z"/></svg></div>';

    const renderedText =
      role === "bot" ? formatAssistantText(text) : escapeHtml(text);
    const timeStr = fromHistory
      ? formatTimeFromDbIso(timestampIso)
      : getTimeString();

    let feedbackHTML = "";
    if (role === "bot" && showFeedback) {
      const mid = messageId != null ? messageId : "";
      feedbackHTML =
        '<div class="feedback-buttons" id="' +
        feedbackId +
        '" data-message-id="' +
        mid +
        '">' +
        '<button class="feedback-btn" data-type="dislike">👎</button>' +
        '<button class="feedback-btn" data-type="like">👍</button>' +
        "</div>";
    }

    msgDiv.innerHTML =
      avatarHtml +
      '<div class="message-content">' +
      '<div class="message-bubble">' +
      renderedText +
      "</div>" +
      '<div class="message-time">' +
      timeStr +
      "</div>" +
      feedbackHTML +
      "</div>";

    // Wire feedback buttons
    if (showFeedback) {
      msgDiv.querySelectorAll(".feedback-btn").forEach(function (btn) {
        btn.addEventListener("click", function () {
          giveFeedback(btn, btn.dataset.type);
        });
      });
    }

    if (!fromHistory && role === "bot") {
      // Snapshot anchor position BEFORE append so the measurement is clean.
      const allUserMsgs = messagesArea.querySelectorAll(".user-message");
      const anchor =
        allUserMsgs.length > 0 ? allUserMsgs[allUserMsgs.length - 1] : null;
      const pad = 8;
      const preAnchorTop = anchor
        ? anchor.getBoundingClientRect().top -
          messagesArea.getBoundingClientRect().top
        : null;

      messagesArea.appendChild(msgDiv);

      // Synchronously set scrollTop in the same JS task as the append —
      // this happens before the browser paints, so there is no bottom-flash.
      if (anchor !== null && preAnchorTop !== null) {
        messagesArea.scrollTop = Math.max(
          0,
          messagesArea.scrollTop + preAnchorTop - pad,
        );
      } else {
        // No question bubble above (e.g. error message) — show bot reply top.
        const botRect = msgDiv.getBoundingClientRect();
        const areaRect = messagesArea.getBoundingClientRect();
        messagesArea.scrollTop = Math.max(
          0,
          messagesArea.scrollTop + (botRect.top - areaRect.top) - pad,
        );
      }

      // After the fadeInBot animation finishes (~500 ms), do a gentle smooth
      // correction in case fonts/images shifted the layout.
      var _anchor = anchor || msgDiv;
      setTimeout(function () {
        var anchorRect2 = _anchor.getBoundingClientRect();
        var areaRect2 = messagesArea.getBoundingClientRect();
        var ideal = Math.max(
          0,
          messagesArea.scrollTop + (anchorRect2.top - areaRect2.top) - pad,
        );
        if (Math.abs(messagesArea.scrollTop - ideal) > 4 && !prefersReducedMotion()) {
          messagesArea.scrollTo({ top: ideal, behavior: "smooth" });
        }
        updateScrollToBottomButton();
      }, 520);
    } else {
      messagesArea.appendChild(msgDiv);
      if (!fromHistory && wasAtBottom) {
        scrollToBottomSmooth();
      }
    }
    updateScrollToBottomButton();
  }

  /* ------------------------------------------------------------------ */
  /* 10. Welcome message                                                  */
  /* ------------------------------------------------------------------ */
  function addWelcomeMessage() {
    lastDisplayedDate = null;
    const now = new Date();
    if (shouldInsertDateSeparator(now)) insertDateSeparator(now);

    const botAv = BOT_LOGO_B64
      ? '<div class="message-avatar message-avatar-bot-img"><img src="data:image/png;base64,' +
        BOT_LOGO_B64 +
        '" alt=""/></div>'
      : '<div class="message-avatar">🤖</div>';

    const welcomeDiv = document.createElement("div");
    welcomeDiv.className = "message bot-message";
    welcomeDiv.id = "hcw-welcome";
    welcomeDiv.innerHTML =
      botAv +
      '<div class="message-content">' +
      '<div class="message-bubble welcome-bubble">' +
      '<p class="welcome-title">مرحبًا بك في نظام المساعد الذكي لجامعة الخليل 🤖</p>' +
      '<p class="welcome-body">يوفر النظام معلومات متعلقة بالقبول والتسجيل، البرامج الأكاديمية، الرسوم، والخدمات الطلابية.</p>' +
      '<p class="welcome-cta">اطرح سؤالك، وسأوفر لك المعلومات بسرعة ودقة.</p>' +
      "</div>" +
      '<div class="message-time">' +
      getTimeString() +
      "</div>" +
      "</div>";
    messagesArea.appendChild(welcomeDiv);
    messageCount = 0;
    suggestions.classList.remove("hidden");
    resetSuggestionsTitle();
    scrollToBottomImmediate();
    updateScrollToBottomButton();
  }

  /* ------------------------------------------------------------------ */
  /* 11. View switching                                                   */
  /* ------------------------------------------------------------------ */
  function showHistoryView() {
    historyView.style.display = "flex";
    chatView.classList.remove("visible");
    loadSessions();
  }

  function showChatView() {
    historyView.style.display = "none";
    chatView.classList.add("visible");
  }

  function startNewChat() {
    window.currentSessionId = crypto.randomUUID();
    messagesArea.innerHTML = "";
    lastDisplayedDate = null;
    addWelcomeMessage();
    showChatView();
  }

  function clearChatMessages() {
    messagesArea.innerHTML = "";
    lastDisplayedDate = null;
  }

  /* ------------------------------------------------------------------ */
  /* 12. Session management                                               */
  /* ------------------------------------------------------------------ */
  async function loadSessions() {
    sessionList.innerHTML = "";
    try {
      const res = await fetch(
        API_BASE_URL + "/users/" + window.userId + "/sessions",
      );
      let sessions = res.ok ? await res.json() : [];
      function _sortTs(x) {
        const raw = x.last_message_time || x.start_time;
        if (!raw) return 0;
        const n = new Date(raw).getTime();
        return Number.isFinite(n) ? n : 0;
      }
      sessions = sessions.slice().sort(function (a, b) {
        const ta = _sortTs(a),
          tb = _sortTs(b);
        if (tb !== ta) return tb - ta;
        return String(b.session_id).localeCompare(String(a.session_id));
      });
      sessions.forEach(function (s) {
        const div = document.createElement("div");
        div.className = "session-item";
        const title =
          (s.title || "New Chat").substring(0, 40) +
          ((s.title || "").length > 40 ? "…" : "");
        const ts = s.last_message_time || s.start_time;
        const sessionDate = ts ? new Date(ts) : null;
        const timeStr =
          sessionDate && !isNaN(sessionDate.getTime())
            ? formatTimestampText(sessionDate)
            : "";
        const sidSafe = String(s.session_id).replace(/"/g, "&quot;");
        div.innerHTML =
          '<div class="session-item-content">' +
          '<div class="session-item-title">' +
          escapeHtml(title) +
          "</div>" +
          '<div class="session-item-time">' +
          escapeHtml(timeStr) +
          "</div>" +
          "</div>" +
          '<button type="button" class="delete-btn" data-sid="' +
          sidSafe +
          '" title="حذف المحادثة">🗑️</button>';
        div.addEventListener("click", function (e) {
          if (!e.target.closest(".delete-btn")) openSession(s.session_id);
        });
        div
          .querySelector(".delete-btn")
          .addEventListener("click", function (e) {
            e.stopPropagation();
            deleteSession(e, s.session_id);
          });
        sessionList.appendChild(div);
      });
    } catch (e) {
      console.warn("[HCW] loadSessions failed", e);
    }
  }

  async function deleteSession(event, sessionId) {
    event.stopPropagation();
    if (!confirm("هل أنت متأكد من حذف هذه المحادثة؟")) return;
    try {
      const res = await fetch(API_BASE_URL + "/sessions/" + sessionId, {
        method: "DELETE",
      });
      if (res.ok) {
        if (window.currentSessionId === sessionId)
          window.currentSessionId = null;
        loadSessions();
      } else {
        console.error("[HCW] Delete session failed", res.status);
      }
    } catch (e) {
      console.error("[HCW] Delete session error", e);
    }
  }

  async function openSession(sessionId) {
    window.currentSessionId = sessionId;
    resetSuggestionsTitle();
    closeFaqOverlay();
    clearChatMessages();
    try {
      const res = await fetch(
        API_BASE_URL + "/sessions/" + sessionId + "/messages",
      );
      const msgs = res.ok ? await res.json() : [];
      msgs.sort(function (a, b) {
        return (a.id || 0) - (b.id || 0);
      });
      messageCount = msgs.length;
      if (messageCount >= 1) suggestions.classList.add("hidden");
      msgs.forEach(function (m) {
        addMessage(
          m.content || "",
          m.role === "bot" ? "bot" : "user",
          false,
          null,
          null,
          m.timestamp || null,
          true,
        );
      });
    } catch (e) {
      console.warn("[HCW] openSession failed", e);
    }
    showChatView();
    scrollToBottomImmediate();
    requestAnimationFrame(function () {
      scrollToBottomImmediate();
      updateScrollToBottomButton();
    });
    setTimeout(function () {
      scrollToBottomImmediate();
      updateScrollToBottomButton();
    }, 120);
  }

  /* ------------------------------------------------------------------ */
  /* 13. Send message                                                     */
  /* ------------------------------------------------------------------ */
  async function sendMessage() {
    const text = messageInput.value.trim();
    if (!text && !selectedFile) return;
    const fileToUpload = selectedFile;
    const oldPlaceholder = messageInput.placeholder;

    messageCount++;
    if (messageCount >= 1) suggestions.classList.add("hidden");
    if (lastBotMessageId) {
      const fb = document.getElementById(lastBotMessageId);
      if (fb) fb.classList.add("hidden");
    }

    let userMsg = text;
    if (fileToUpload) userMsg += " 📎 " + fileToUpload.name;
    addMessage(userMsg, "user");
    keepLatestMessageVisible();
    messageInput.value = "";
    syncChatInputDir();
    removeFile();

    if (!window.currentSessionId) window.currentSessionId = crypto.randomUUID();

    try {
      messageInput.placeholder = "";
      showInputStatus("لحظات من فضلك، أقوم بتجهيز الإجابة الوافية لسؤالك...");
      messageInput.disabled = true;
      sendBtn.disabled = true;
      micBtn.disabled = true;
      if (faqBtn) faqBtn.disabled = true;

      if (fileToUpload) {
        const fd = new FormData();
        fd.append("file", fileToUpload);
        const up = await fetch(API_BASE_URL + "/load", {
          method: "POST",
          body: fd,
        });
        if (!up.ok)
          addMessage("❌ فشل تحميل الملف إلى قاعدة المعرفة.", "bot", false);
      }

      const response = await fetch(API_BASE_URL + "/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: text,
          session_id: window.currentSessionId,
          user_id: window.userId,
        }),
      });
      const data = await response.json();
      const botAnswer = data.answer || "عذراً، حدث خطأ.";
      const botMsgId = "hcw-fb-" + Date.now();
      const messageId = data.message_id != null ? data.message_id : null;
      addMessage(botAnswer, "bot", true, botMsgId, messageId);
      lastBotMessageId = botMsgId;
      if (data.suggest_faq) {
        setFollowupSuggestionsTitle();
        suggestions.classList.remove("hidden");
      }
      await loadSessions();
    } catch (err) {
      addMessage(
        "⚠️ لا يمكن الاتصال بالخادم. تأكد من تشغيل API.",
        "bot",
        false,
      );
      console.error("[HCW] API error", err);
    } finally {
      hideInputStatus();
      messageInput.disabled = false;
      sendBtn.disabled = false;
      micBtn.disabled = false;
      if (faqBtn) faqBtn.disabled = false;
      messageInput.placeholder = oldPlaceholder || "اكتب رسالتك...";
    }
  }

  async function sendFaq(faqId, question, answer) {
    const q = String(question || "").trim();
    const a = String(answer || "").trim();
    if (!q || !a) return;
    closeFaqOverlay();
    if (!window.currentSessionId) window.currentSessionId = crypto.randomUUID();
    messageCount++;
    if (messageCount >= 1) suggestions.classList.add("hidden");
    if (lastBotMessageId) {
      const fb = document.getElementById(lastBotMessageId);
      if (fb) fb.classList.add("hidden");
    }
    addMessage(q, "user", false);
    keepLatestMessageVisible();
    try {
      const res = await fetch(API_BASE_URL + "/chat/faq", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          faq_id: faqId != null ? Number(faqId) : null,
          question: q,
          answer: a,
          session_id: window.currentSessionId,
          user_id: window.userId,
        }),
      });
      const data = await res.json();
      const botMsgId = "hcw-fb-" + Date.now();
      const persistedId =
        data && data.message_id != null ? data.message_id : null;
      addMessage(a, "bot", true, botMsgId, persistedId);
      lastBotMessageId = botMsgId;
      await loadSessions();
    } catch (err) {
      addMessage(a, "bot", false);
      console.warn("[HCW] FAQ persist failed", err);
    }
  }

  /* ------------------------------------------------------------------ */
  /* 14. Feedback                                                         */
  /* ------------------------------------------------------------------ */
  async function giveFeedback(btn, type) {
    const feedbackDiv = btn.closest(".feedback-buttons");
    const messageId = feedbackDiv
      ? feedbackDiv.getAttribute("data-message-id")
      : null;
    feedbackDiv.querySelectorAll(".feedback-btn").forEach(function (b) {
      b.classList.remove("active", "like", "dislike");
    });
    btn.classList.add("active", type);
    if (messageId) {
      try {
        const res = await fetch(API_BASE_URL + "/feedback", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            message_id: parseInt(messageId, 10),
            rating: type,
          }),
        });
        if (res.ok) feedbackDiv.classList.add("hidden");
      } catch (e) {
        console.warn("[HCW] Feedback failed", e);
      }
    }
  }

  /* ------------------------------------------------------------------ */
  /* 15. File attachment                                                  */
  /* ------------------------------------------------------------------ */
  // Hidden file input
  const fileInput = document.createElement("input");
  fileInput.type = "file";
  fileInput.accept = ".pdf,.txt,.docx,.doc";
  fileInput.style.display = "none";
  document.body.appendChild(fileInput);

  fileInput.addEventListener("change", function (e) {
    if (e.target.files.length > 0) {
      selectedFile = e.target.files[0];
      if (fileName) fileName.textContent = "📎 " + selectedFile.name;
      if (filePreview) filePreview.classList.add("show");
    }
  });

  function removeFile() {
    selectedFile = null;
    fileInput.value = "";
    if (filePreview) filePreview.classList.remove("show");
  }

  if (fileRemove) {
    fileRemove.addEventListener("click", removeFile);
    fileRemove.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") removeFile();
    });
  }

  /* ------------------------------------------------------------------ */
  /* 16. Voice recording                                                  */
  /* ------------------------------------------------------------------ */
  function startRecordTimer() {
    if (recordTimerIntervalId) clearInterval(recordTimerIntervalId);
    recordStartedAt = Date.now();
    if (recordTimer) recordTimer.textContent = "00:00";
    recordTimerIntervalId = setInterval(function () {
      const sec = Math.floor((Date.now() - recordStartedAt) / 1000);
      const m = Math.floor(sec / 60);
      const s = sec % 60;
      if (recordTimer)
        recordTimer.textContent =
          String(m).padStart(2, "0") + ":" + String(s).padStart(2, "0");
    }, 250);
  }

  function stopRecordTimer() {
    if (recordTimerIntervalId) {
      clearInterval(recordTimerIntervalId);
      recordTimerIntervalId = null;
    }
    if (recordTimer) recordTimer.textContent = "00:00";
  }

  function stopVoiceVisualizer() {
    if (vizRafId) {
      cancelAnimationFrame(vizRafId);
      vizRafId = null;
    }
    if (audioVizSource) {
      try {
        audioVizSource.disconnect();
      } catch (_) {}
      audioVizSource = null;
    }
    if (audioVizAnalyser) {
      try {
        audioVizAnalyser.disconnect();
      } catch (_) {}
      audioVizAnalyser = null;
    }
    if (audioVizContext) {
      try {
        audioVizContext.close();
      } catch (_) {}
      audioVizContext = null;
    }
    if (voiceVisualizer) {
      const ctx = voiceVisualizer.getContext("2d");
      if (ctx)
        ctx.clearRect(0, 0, voiceVisualizer.width, voiceVisualizer.height);
    }
  }

  function startVoiceVisualizer(stream) {
    if (!voiceVisualizer || !stream) return;
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return;
    stopVoiceVisualizer();
    try {
      audioVizContext = new AC();
      if (audioVizContext.state === "suspended")
        audioVizContext.resume().catch(function () {});
      audioVizSource = audioVizContext.createMediaStreamSource(stream);
      audioVizAnalyser = audioVizContext.createAnalyser();
      audioVizAnalyser.fftSize = 128;
      audioVizAnalyser.smoothingTimeConstant = 0.65;
      audioVizSource.connect(audioVizAnalyser);
      const canvas = voiceVisualizer;
      const ctx2d = canvas.getContext("2d");
      const barCount = 16;
      const dataArray = new Uint8Array(audioVizAnalyser.frequencyBinCount);
      function drawFrame() {
        if (!isRecording || !audioVizAnalyser) return;
        vizRafId = requestAnimationFrame(drawFrame);
        audioVizAnalyser.getByteFrequencyData(dataArray);
        const w = canvas.width,
          h = canvas.height;
        ctx2d.fillStyle = "#F5F5F5";
        ctx2d.fillRect(0, 0, w, h);
        const step = Math.max(1, Math.floor(dataArray.length / barCount));
        const slot = w / barCount,
          barW = slot * 0.65,
          gap = slot * 0.35;
        for (let i = 0; i < barCount; i++) {
          let sum = 0;
          for (let j = 0; j < step; j++) sum += dataArray[i * step + j] || 0;
          const v = sum / step / 255;
          const bh = Math.max(2, v * h * 0.92);
          ctx2d.fillStyle = "#2E7D32";
          ctx2d.fillRect(w - (i + 1) * slot + gap / 2, h - bh, barW, bh);
        }
      }
      drawFrame();
    } catch (e) {
      console.warn("[HCW] Voice viz failed", e);
      stopVoiceVisualizer();
    }
  }

  function setRecordingClusterActive(active) {
    if (voiceRecordCluster)
      voiceRecordCluster.classList.toggle(
        "voice-record-cluster--active",
        active,
      );
    if (inputToolbar)
      inputToolbar.classList.toggle("input-toolbar--voice-active", active);
  }

  function cancelRecording() {
    recordingDiscardFlag = true;
    if (recordingTimeoutId) {
      clearTimeout(recordingTimeoutId);
      recordingTimeoutId = null;
    }
    stopRecordTimer();
    stopVoiceVisualizer();
    setRecordingClusterActive(false);
    isRecording = false;
    micBtn.classList.remove("recording");
    if (mediaRecorder && mediaRecorder.state !== "inactive") {
      mediaRecorder.stop();
    } else {
      recordingDiscardFlag = false;
      audioChunks = [];
      if (recordingStream) {
        recordingStream.getTracks().forEach(function (t) {
          t.stop();
        });
        recordingStream = null;
      }
      mediaRecorder = null;
    }
  }

  function stopRecording() {
    if (recordingTimeoutId) {
      clearTimeout(recordingTimeoutId);
      recordingTimeoutId = null;
    }
    stopRecordTimer();
    stopVoiceVisualizer();
    setRecordingClusterActive(false);
    isRecording = false;
    micBtn.classList.remove("recording");
    if (mediaRecorder && mediaRecorder.state !== "inactive")
      mediaRecorder.stop();
  }

  async function startRecording() {
    if (!navigator.mediaDevices || !window.MediaRecorder) {
      addMessage("⚠️ المتصفح لا يدعم تسجيل الصوت.", "bot", false);
      return;
    }
    try {
      recordingDiscardFlag = false;
      recordingStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      mediaRecorder = new MediaRecorder(recordingStream);
      audioChunks = [];
      const recorderMime = mediaRecorder.mimeType || "audio/webm";

      mediaRecorder.ondataavailable = function (e) {
        if (e.data && e.data.size > 0) audioChunks.push(e.data);
      };

      mediaRecorder.onstop = async function () {
        if (recordingTimeoutId) {
          clearTimeout(recordingTimeoutId);
          recordingTimeoutId = null;
        }
        const wasDiscarded = recordingDiscardFlag;
        recordingDiscardFlag = false;
        let audioBlob = null;
        if (!wasDiscarded && audioChunks.length > 0)
          audioBlob = new Blob(audioChunks, { type: recorderMime });
        audioChunks = [];
        if (recordingStream) {
          recordingStream.getTracks().forEach(function (t) {
            t.stop();
          });
        }
        recordingStream = null;
        mediaRecorder = null;
        if (wasDiscarded) return;
        if (!audioBlob || audioBlob.size === 0) {
          addMessage("⚠️ لم يتم تسجيل أي صوت.", "bot", false);
          return;
        }
        await sendRecordedAudio(audioBlob);
      };

      mediaRecorder.start();
      isRecording = true;
      micBtn.classList.add("recording");
      setRecordingClusterActive(true);
      startRecordTimer();
      startVoiceVisualizer(recordingStream);
      recordingTimeoutId = setTimeout(function () {
        if (isRecording) {
          stopRecording();
          addMessage(
            "⏱️ تم إيقاف التسجيل تلقائياً بعد دقيقة واحدة.",
            "bot",
            false,
          );
        }
      }, MAX_RECORDING_MS);
    } catch (err) {
      console.error("[HCW] Recording start failed", err);
      addMessage("⚠️ تعذر الوصول إلى الميكروفون.", "bot", false);
      if (recordingTimeoutId) {
        clearTimeout(recordingTimeoutId);
        recordingTimeoutId = null;
      }
      stopRecordTimer();
      stopVoiceVisualizer();
      setRecordingClusterActive(false);
      isRecording = false;
      micBtn.classList.remove("recording");
      if (recordingStream) {
        recordingStream.getTracks().forEach(function (t) {
          t.stop();
        });
        recordingStream = null;
      }
      mediaRecorder = null;
      audioChunks = [];
    }
  }

  async function sendRecordedAudio(audioBlob) {
    if (!audioBlob || audioBlob.size === 0) {
      addMessage("⚠️ لم يتم تسجيل أي صوت.", "bot", false);
      return;
    }
    if (!window.currentSessionId) window.currentSessionId = crypto.randomUUID();
    const oldPlaceholder = messageInput.placeholder;
    try {
      messageInput.placeholder = "";
      showInputStatus("🎤 جاري تحويل رسالتك الصوتية إلى نص... يرجى الانتظار");
      messageInput.disabled = true;
      sendBtn.disabled = true;
      micBtn.disabled = true;
      if (faqBtn) faqBtn.disabled = true;
      const fd = new FormData();
      fd.append("audio", audioBlob, "voice.webm");
      fd.append("session_id", window.currentSessionId || "");
      fd.append("user_id", window.userId || "");
      fd.append("transcribe_only", "1");
      const res = await fetch(API_BASE_URL + "/chat/audio", {
        method: "POST",
        body: fd,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Audio request failed");
      const userText = (data.transcription || "").trim();
      if (!userText) {
        addMessage("⚠️ لم يتم استخراج نص من التسجيل.", "bot", false);
        return;
      }
      messageInput.value = userText;
      syncChatInputDir();
      messageInput.focus();
    } catch (err) {
      console.error("[HCW] Audio send failed", err);
      addMessage(err.message || "⚠️ فشل إرسال الرسالة الصوتية.", "bot", false);
    } finally {
      hideInputStatus();
      messageInput.disabled = false;
      sendBtn.disabled = false;
      micBtn.disabled = false;
      if (faqBtn) faqBtn.disabled = false;
      messageInput.placeholder = oldPlaceholder || "اكتب رسالتك...";
    }
  }

  /* ------------------------------------------------------------------ */
  /* 17. Campus map                                                       */
  /* ------------------------------------------------------------------ */
  function applyMapTransform() {
    if (!campusMapImg) return;
    campusMapImg.style.transform =
      "translate(calc(-50% + " +
      mapTx +
      "px), calc(-50% + " +
      mapTy +
      "px)) scale(" +
      mapScale +
      ")";
  }

  function getMapFitScale() {
    if (!campusMapImg) return 1;
    const naturalW = campusMapImg.naturalWidth || campusMapImg.width || 0;
    const naturalH = campusMapImg.naturalHeight || campusMapImg.height || 0;
    if (!naturalW || !naturalH) return 1;

    const viewW = (mapViewport && mapViewport.clientWidth) || window.innerWidth;
    const viewH =
      (mapViewport && mapViewport.clientHeight) || window.innerHeight;
    if (!viewW || !viewH) return 1;

    const fitScale = Math.min(viewW / naturalW, viewH / naturalH) * 0.96;
    return Math.max(MAP_MIN_SCALE, Math.min(1, fitScale));
  }

  function resetMapView() {
    mapScale = getMapFitScale();
    mapTx = 0;
    mapTy = 0;
    applyMapTransform();
  }

  function clampScale(v) {
    return Math.max(MAP_MIN_SCALE, Math.min(MAP_MAX_SCALE, v));
  }

  function zoomMap(delta) {
    const next = clampScale(mapScale + delta);
    if (next === mapScale) return;
    mapScale = next;
    applyMapTransform();
  }

  function setMapOpen(open) {
    mapOpen = !!open;
    if (!mapModal) return;
    mapModal.classList.toggle("open", mapOpen);
    mapModal.setAttribute("aria-hidden", String(!mapOpen));
    if (mapOpen) requestAnimationFrame(resetMapView);
    updateScrollToBottomButton();
  }

  function closeMapModal() {
    setMapOpen(false);
  }

  /* ------------------------------------------------------------------ */
  /* 18. Event listeners                                                  */
  /* ------------------------------------------------------------------ */
  chatAvatar.addEventListener("click", function () {
    chatWidget.classList.toggle("open");
    chatAvatar.classList.toggle(
      "avatar-hidden",
      chatWidget.classList.contains("open"),
    );
  });

  closeBtn.addEventListener("click", function () {
    closeFaqOverlay();
    chatWidget.classList.remove("open");
    chatAvatar.classList.remove("avatar-hidden");
  });

  closeBtnHistory.addEventListener("click", function () {
    closeFaqOverlay();
    chatWidget.classList.remove("open");
    chatAvatar.classList.remove("avatar-hidden");
  });

  backBtn.addEventListener("click", function () {
    closeFaqOverlay();
    showHistoryView();
  });
  newChatBtn.addEventListener("click", startNewChat);

  if (faqBtn)
    faqBtn.addEventListener("click", function (e) {
      e.stopPropagation();
      toggleFaqOverlay();
    });
  if (faqOverlayBackdrop)
    faqOverlayBackdrop.addEventListener("click", closeFaqOverlay);
  if (faqOverlayClose)
    faqOverlayClose.addEventListener("click", closeFaqOverlay);

  if (mapInputBtn) {
    mapInputBtn.addEventListener("click", function (e) {
      e.preventDefault();
      e.stopPropagation();
      setMapOpen(true);
    });
  }
  if (mapModalBackdrop)
    mapModalBackdrop.addEventListener("click", closeMapModal);
  if (mapModalClose) mapModalClose.addEventListener("click", closeMapModal);

  if (mapZoomInBtn)
    mapZoomInBtn.addEventListener("click", function (e) {
      e.stopPropagation();
      zoomMap(0.25);
    });
  if (mapZoomOutBtn)
    mapZoomOutBtn.addEventListener("click", function (e) {
      e.stopPropagation();
      zoomMap(-0.25);
    });
  if (mapResetBtn)
    mapResetBtn.addEventListener("click", function (e) {
      e.stopPropagation();
      resetMapView();
    });

  if (mapViewport) {
    mapViewport.addEventListener("mousedown", function (e) {
      if (!mapOpen) return;
      isMapDragging = true;
      mapViewport.classList.add("dragging");
      mapDragStartX = e.clientX;
      mapDragStartY = e.clientY;
      mapDragOriginTx = mapTx;
      mapDragOriginTy = mapTy;
    });
    window.addEventListener("mousemove", function (e) {
      if (!isMapDragging) return;
      mapTx = mapDragOriginTx + (e.clientX - mapDragStartX);
      mapTy = mapDragOriginTy + (e.clientY - mapDragStartY);
      applyMapTransform();
    });
    window.addEventListener("mouseup", function () {
      if (!isMapDragging) return;
      isMapDragging = false;
      mapViewport.classList.remove("dragging");
    });
    mapViewport.addEventListener(
      "wheel",
      function (e) {
        if (!mapOpen) return;
        e.preventDefault();
        zoomMap(e.deltaY > 0 ? -0.18 : 0.18);
      },
      { passive: false },
    );
  }

  sendBtn.addEventListener("click", sendMessage);
  messageInput.addEventListener("input", syncChatInputDir);
  messageInput.addEventListener("keypress", function (e) {
    if (e.key === "Enter") sendMessage();
  });

  if (cancelRecordBtn) {
    cancelRecordBtn.addEventListener("click", function (e) {
      e.stopPropagation();
      if (isRecording) cancelRecording();
    });
  }

  micBtn.addEventListener("click", async function () {
    if (!isRecording) await startRecording();
    else stopRecording();
  });

  if (scrollToBottomBtn) {
    scrollToBottomBtn.addEventListener("click", function () {
      scrollToBottomSmooth();
      setTimeout(updateScrollToBottomButton, 150);
    });
  }
  if (messagesArea)
    messagesArea.addEventListener("scroll", updateScrollToBottomButton);
  window.addEventListener("resize", updateScrollToBottomButton);

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      if (faqOverlay && faqOverlay.classList.contains("open"))
        closeFaqOverlay();
      if (mapOpen) closeMapModal();
    }
  });

  /* ------------------------------------------------------------------ */
  /* 19. Bootstrap                                                        */
  /* ------------------------------------------------------------------ */
  loadConfig();
  loadSessions();
})();
