/**
 * Chat Support embeddable chat widget.
 *
 * Usage on any website:
 *   <script src="https://cdn.example.com/oasis-chatbot-widget.js"
 *           data-org-slug="acme-corp"
 *           data-api-base="https://api.example.com"
 *           data-title="Welcome!"
 *           data-subtitle="Text us"
 *           data-agent-name="Priya Sharma"
 *           data-agent-avatar="https://.../priya.jpg"
 *           data-topics="Track my order,Refund status,Talk to a human"></script>
 *
 * Only data-org-slug and data-api-base are required; everything else has
 * a sensible default.
 *
 * Deliberately vanilla JS, not React/Vue: this has to run correctly on
 * whatever framework (or no framework) the HOST site uses, so it can't
 * assume anything about the page it's embedded in. Everything lives
 * inside one script tag's execution — no bundler, no build step for the
 * business embedding it.
 */
(function () {
  "use strict";

  var scriptTag = document.currentScript;
  var ORG_SLUG = scriptTag.getAttribute("data-org-slug");
  var API_BASE = scriptTag.getAttribute("data-api-base") || "";
  var STORAGE_KEY = "oasis_external_id_" + ORG_SLUG;

  if (!ORG_SLUG) {
    console.error("[Chat Support] Missing required data-org-slug attribute.");
    return;
  }

  // ---------- Branding, all optional ----------
  var TITLE = scriptTag.getAttribute("data-title") || "Hello there!";
  var SUBTITLE = scriptTag.getAttribute("data-subtitle") || "How can we help?";
  var AGENT_NAME = scriptTag.getAttribute("data-agent-name") || "Support team";
  var AGENT_AVATAR = scriptTag.getAttribute("data-agent-avatar") || "";
  var GREETING =
    scriptTag.getAttribute("data-greeting") ||
    "Hi! Ask us anything, or pick a topic to get started.";
  // Launcher behaviour. The teaser is the single biggest thing that turns
  // a widget nobody notices into one people click, so it is on by default
  // — but it appears once per browser session and can be dismissed, which
  // is the line between inviting and nagging.
  var LAUNCHER_TEXT = scriptTag.getAttribute("data-launcher-text") || "";
  // How long the visitor watches a spinner before it becomes a gentler,
  // open-ended wait. Two minutes is long enough that most chats are picked
  // up first, short enough that nobody sits in front of a lie.
  var WAIT_PATIENCE_MS =
    parseInt(scriptTag.getAttribute("data-wait-patience") || "120", 10) * 1000;
  var WAIT_LONG_TEXT =
    scriptTag.getAttribute("data-wait-long-text") ||
    "Still looking for someone to help you. Your message is saved.";
  var TEASER_TEXT =
    scriptTag.getAttribute("data-teaser") || "Hi there! Need any help?";
  var TEASER_DELAY = parseInt(scriptTag.getAttribute("data-teaser-delay") || "6", 10) * 1000;
  var TEASER_OFF = scriptTag.getAttribute("data-teaser") === "off";

  // Which countries the number field offers, in order. The full table
  // below stays complete, so widening this is a one-attribute change
  // rather than a code change.
  var COUNTRY_CODES = (scriptTag.getAttribute("data-countries") || "GB,US,CA,AU")
    .split(",")
    .map(function (c) { return c.trim().toUpperCase(); })
    .filter(Boolean);

  var TOPICS = (scriptTag.getAttribute("data-topics") || "")
    .split(",")
    .map(function (t) { return t.trim(); })
    .filter(Boolean);

  // Theme colours, overridable per site.
  var BRAND = scriptTag.getAttribute("data-color") || "#0e7c66";
  var BRAND_DARK = scriptTag.getAttribute("data-color-dark") || "#0b2b27";
  var INK = "#10201e";
  var MUTED = "#5d716d";
  var LINE = "#dce5e2";
  var CANVAS = "#f4f8f6";

  // ---------- Visitor identity (NOT a login — just a stable per-browser id) ----------

  function getOrCreateExternalId() {
    var existing = window.localStorage.getItem(STORAGE_KEY);
    if (existing) return existing;
    var generated =
      "visitor-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 10);
    window.localStorage.setItem(STORAGE_KEY, generated);
    return generated;
  }

  var externalId = getOrCreateExternalId();
  var socket = null;
  var historyLoaded = false;
  var reconnectAttempts = 0;
  var reconnectTimer = null;
  var unreadCount = 0;
  var pendingTopic = null;
  // When an agent last had this chat open. Anything the visitor sent
  // before this moment has been read.
  var agentReadAt = null;
  var lastOutgoingRow = null;
  var waitRow = null;
  var waitTimer = null;
  var waitRing = null;
  var agentHasReplied = false;
  var lastAgentMessageAt = null;

  // ---------- Conversation continuity across page loads ----------
  // Without this, a page refresh dropped the thread: the visitor saw an
  // empty box and their next message opened a brand new conversation, so
  // one person showed up in the dashboard (and in any CRM listening to
  // webhooks) as several unrelated chats.
  var CONVERSATION_STORAGE_KEY = "oasis_conversation_" + ORG_SLUG;

  function getSavedConversationId() {
    return window.localStorage.getItem(CONVERSATION_STORAGE_KEY);
  }

  function saveConversationId(id) {
    if (id) window.localStorage.setItem(CONVERSATION_STORAGE_KEY, id);
  }

  function clearConversationId() {
    window.localStorage.removeItem(CONVERSATION_STORAGE_KEY);
    conversationId = null;
    historyLoaded = false;
    agentHasReplied = false;
  }

  var conversationId = getSavedConversationId();

  // ---------- Pre-chat visitor details (name + mobile, mandatory) ----------
  // Persisted per-visitor so a returning visitor isn't asked again — same
  // "known once, known forever" idea as externalId itself.
  var DETAILS_STORAGE_KEY = "oasis_visitor_details_" + ORG_SLUG;
  var COUNTRY_STORAGE_KEY = "oasis_country_" + ORG_SLUG;
  var LAST_SEEN_KEY = "oasis_last_seen_" + ORG_SLUG;

  function markSeenNow() {
    try {
      window.localStorage.setItem(LAST_SEEN_KEY, new Date().toISOString());
    } catch (e) { /* private mode — auto-open simply won't trigger */ }
  }

  function lastSeenAt() {
    var raw = window.localStorage.getItem(LAST_SEEN_KEY);
    return raw ? new Date(raw).getTime() : 0;
  }

  function getSavedDetails() {
    try {
      var raw = window.localStorage.getItem(DETAILS_STORAGE_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch (e) {
      return null;
    }
  }

  function saveDetails(details) {
    // The captcha answer is deliberately not persisted: it is spent on the
    // first message and would be meaningless — and misleading — later.
    window.localStorage.setItem(
      DETAILS_STORAGE_KEY,
      JSON.stringify({ name: details.name, phone: details.phone })
    );
  }

  var visitorDetails = getSavedDetails();

  // ---------- Country dialling codes ----------
  // Bundled rather than fetched: the widget must work on any website with
  // no extra network calls and no build step.
  var COUNTRIES = [
    { iso: "IN", name: "India", dial: "91" },
    { iso: "US", name: "United States", dial: "1" },
    { iso: "GB", name: "United Kingdom", dial: "44" },
    { iso: "AE", name: "United Arab Emirates", dial: "971" },
    { iso: "AU", name: "Australia", dial: "61" },
    { iso: "BD", name: "Bangladesh", dial: "880" },
    { iso: "BR", name: "Brazil", dial: "55" },
    { iso: "CA", name: "Canada", dial: "1" },
    { iso: "CN", name: "China", dial: "86" },
    { iso: "DE", name: "Germany", dial: "49" },
    { iso: "EG", name: "Egypt", dial: "20" },
    { iso: "ES", name: "Spain", dial: "34" },
    { iso: "FR", name: "France", dial: "33" },
    { iso: "ID", name: "Indonesia", dial: "62" },
    { iso: "IE", name: "Ireland", dial: "353" },
    { iso: "IL", name: "Israel", dial: "972" },
    { iso: "IT", name: "Italy", dial: "39" },
    { iso: "JP", name: "Japan", dial: "81" },
    { iso: "KE", name: "Kenya", dial: "254" },
    { iso: "KR", name: "South Korea", dial: "82" },
    { iso: "KW", name: "Kuwait", dial: "965" },
    { iso: "LK", name: "Sri Lanka", dial: "94" },
    { iso: "MX", name: "Mexico", dial: "52" },
    { iso: "MY", name: "Malaysia", dial: "60" },
    { iso: "NG", name: "Nigeria", dial: "234" },
    { iso: "NL", name: "Netherlands", dial: "31" },
    { iso: "NP", name: "Nepal", dial: "977" },
    { iso: "NZ", name: "New Zealand", dial: "64" },
    { iso: "OM", name: "Oman", dial: "968" },
    { iso: "PH", name: "Philippines", dial: "63" },
    { iso: "PK", name: "Pakistan", dial: "92" },
    { iso: "PL", name: "Poland", dial: "48" },
    { iso: "QA", name: "Qatar", dial: "974" },
    { iso: "RU", name: "Russia", dial: "7" },
    { iso: "SA", name: "Saudi Arabia", dial: "966" },
    { iso: "SE", name: "Sweden", dial: "46" },
    { iso: "SG", name: "Singapore", dial: "65" },
    { iso: "TH", name: "Thailand", dial: "66" },
    { iso: "TR", name: "Turkey", dial: "90" },
    { iso: "UA", name: "Ukraine", dial: "380" },
    { iso: "VN", name: "Vietnam", dial: "84" },
    { iso: "ZA", name: "South Africa", dial: "27" }
  ];

  var TIMEZONE_HINTS = {
    "Asia/Kolkata": "IN", "Asia/Calcutta": "IN", "Asia/Karachi": "PK",
    "Asia/Dhaka": "BD", "Asia/Kathmandu": "NP", "Asia/Colombo": "LK",
    "Asia/Dubai": "AE", "Asia/Riyadh": "SA", "Asia/Singapore": "SG",
    "Europe/London": "GB", "Europe/Dublin": "IE", "Europe/Berlin": "DE",
    "Europe/Paris": "FR", "Europe/Madrid": "ES", "Europe/Rome": "IT",
    "America/New_York": "US", "America/Chicago": "US", "America/Denver": "US",
    "America/Los_Angeles": "US", "America/Toronto": "CA", "Australia/Sydney": "AU"
  };

  // ISO codes double as the short label, with the one exception everybody
  // writes differently: Britain's code is GB, but people read "UK".
  var SHORT_LABELS = { GB: "UK" };

  // How many digits a national number has, excluding the country code.
  // Ten is right for the UK, the US and Canada — but an Australian mobile
  // is nine, so a flat "must be 10" would make the form impossible to
  // complete from Australia.
  var NATIONAL_DIGITS = { GB: 10, US: 10, CA: 10, AU: 9, IN: 10 };

  function shortLabel(iso) {
    return SHORT_LABELS[iso] || iso;
  }

  function findCountry(iso) {
    for (var i = 0; i < COUNTRIES.length; i++) {
      if (COUNTRIES[i].iso === iso) return COUNTRIES[i];
    }
    return null;
  }

  /**
   * Best guess at the visitor's country, so most people never touch the
   * dropdown: saved choice, then locale region, then timezone.
   */
  function offeredCountries() {
    return COUNTRY_CODES.map(findCountry).filter(Boolean);
  }

  function isOffered(iso) {
    return COUNTRY_CODES.indexOf(iso) !== -1;
  }

  function detectCountry() {
    var saved = window.localStorage.getItem(COUNTRY_STORAGE_KEY);
    if (saved && isOffered(saved)) return saved;

    try {
      var locale = navigator.language || "";
      var parts = locale.split("-");
      var region = parts.length > 1 ? parts[parts.length - 1].toUpperCase() : "";
      if (isOffered(region)) return region;
    } catch (e) { /* fall through */ }

    try {
      var tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
      if (TIMEZONE_HINTS[tz] && isOffered(TIMEZONE_HINTS[tz])) return TIMEZONE_HINTS[tz];
    } catch (e) { /* fall through */ }

    // Whatever the guess, it has to be a country this form actually
    // offers — otherwise the field opens on nothing.
    return COUNTRY_CODES[0] || "GB";
  }

  // ---------- API calls ----------

  function apiUrl(path) {
    return API_BASE + "/api/v1/public/" + ORG_SLUG + path;
  }

  function identify() {
    var payload = {
      external_id: externalId,
      browser: navigator.userAgent,
      language: navigator.language,
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      current_page: window.location.href,
    };
    if (visitorDetails) {
      payload.full_name = visitorDetails.name;
      payload.phone = visitorDetails.phone;
    }
    return fetch(apiUrl("/customers/identify"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).catch(function () {
      // Identify is best-effort context, never worth blocking the chat over.
    });
  }

  var captcha = { id: null, question: null };
  var captchaPass = null;

  /**
   * Asks the server for a challenge. The answer is never sent to the
   * browser, so the check cannot be bypassed by editing this file.
   *
   * If the endpoint is missing or verification is switched off on the
   * server, the form simply carries on without the field — an older
   * backend must not leave visitors staring at a question they can't
   * submit.
   */
  function loadCaptcha() {
    return fetch(apiUrl("/conversations/captcha"))
      .then(function (res) {
        if (!res.ok) throw new Error("no_captcha");
        return res.json();
      })
      .then(function (data) {
        captcha = { id: data.challenge_id, question: data.question };
        return captcha;
      })
      .catch(function () {
        captcha = { id: null, question: null };
        return captcha;
      });
  }

  function startConversation(message) {
    return fetch(apiUrl("/conversations"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        external_id: externalId,
        initial_message: message,
        full_name: visitorDetails.name,
        phone: visitorDetails.phone,
        captcha_pass: captchaPass,
      }),
    }).then(function (res) {
      if (!res.ok) throw new Error("start_failed_" + res.status);
      return res.json();
    });
  }

  function sendMessage(message) {
    return fetch(apiUrl("/conversations/" + conversationId + "/messages"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ external_id: externalId, content: message }),
    }).then(function (res) {
      if (!res.ok) throw new Error("send_failed_" + res.status);
      return res.json();
    });
  }

  /**
   * Tells the server the visitor is looking at the chat. Fire-and-forget:
   * a receipt that fails to register is not worth an error message.
   */
  function markRead() {
    if (!conversationId) return;
    fetch(
      apiUrl("/conversations/" + conversationId + "/read?external_id=" + encodeURIComponent(externalId)),
      { method: "POST" }
    ).catch(function () {});
  }

  /**
   * Checks the answer while the visitor is still looking at the question.
   * Resolves with a pass to spend on the first message; rejects with a
   * message written for the person, not for a log.
   */
  function verifyCaptcha(answer) {
    return fetch(apiUrl("/conversations/captcha/verify"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ challenge_id: captcha.id, answer: answer }),
    }).then(function (res) {
      return res.json().then(function (data) {
        if (res.ok) return data.captcha_pass;
        throw new Error(data.detail || "That answer wasn't right. Please try again.");
      });
    });
  }

  function loadHistory() {
    if (!conversationId || historyLoaded) return Promise.resolve();
    return fetch(
      apiUrl("/conversations/" + conversationId + "?external_id=" + encodeURIComponent(externalId))
    )
      .then(function (res) {
        if (res.status === 403 || res.status === 404) {
          // The stored id no longer belongs to this visitor (cleared DB,
          // different org, closed and purged). Start clean rather than
          // leaving the widget pointed at a thread it can't use.
          clearConversationId();
          return null;
        }
        if (!res.ok) throw new Error("history_failed_" + res.status);
        return res.json();
      })
      .then(function (data) {
        if (!data) return;
        historyLoaded = true;
        agentReadAt = data.agent_last_read_at || null;
        messageList.innerHTML = "";
        introRendered = false;
        lastOutgoingRow = null;
        renderIntro();
        data.messages.forEach(function (m) {
          if (m.sender_type !== "customer") {
            agentHasReplied = true;
            lastAgentMessageAt = m.created_at || lastAgentMessageAt;
          }
          renderMessage(m.sender_type, m.content, m.created_at);
        });
        paintReceipt();
        // Reopening a page while still unanswered should put the visitor
        // back where they were, not pretend the wait restarted.
        if (!agentHasReplied && data.messages.length) showWaiting();
        if (data.status === "closed") {
          renderNotice("This chat was closed. Send a message to start a new one.");
          clearConversationId();
        } else {
          connectSocket();
          markRead();
        }
      })
      .catch(function () {
        renderNotice("Couldn't load your earlier messages. You can still send a new one.");
      });
  }

  function connectSocket() {
    if (!conversationId) return;
    if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
      return;
    }
    var wsBase = API_BASE.replace(/^http/, "ws");
    var url =
      wsBase + "/api/v1/public/" + ORG_SLUG + "/conversations/" + conversationId +
      "/ws?external_id=" + encodeURIComponent(externalId);

    socket = new WebSocket(url);

    socket.onopen = function () {
      reconnectAttempts = 0;
    };

    socket.onmessage = function (event) {
      var payload;
      try {
        payload = JSON.parse(event.data);
      } catch (e) {
        return;
      }
      if (payload.type === "read_receipt" && payload.by === "agent") {
        agentReadAt = payload.at || null;
        paintReceipt();
        return;
      }
      if (payload.type === "new_message" && payload.message.sender_type !== "customer") {
        agentHasReplied = true;
        lastAgentMessageAt = payload.message.created_at || new Date().toISOString();
        hideWaiting();
        if (panel.style.display === "flex" && chatScreen.style.display === "flex") {
          markSeenNow();
        }
        renderMessage(payload.message.sender_type, payload.message.content, payload.message.created_at);
        // The visitor is looking at the panel, so the reply is read now.
        if (panel.style.display === "flex" && chatScreen.style.display === "flex") markRead();
        // A reply that arrives while the panel is shut should be visible
        // from the launcher, or the visitor never learns it came.
        if (panel.style.display !== "flex") {
          unreadCount += 1;
          paintBadge();
        }
      }
    };

    socket.onclose = function () {
      // Networks drop, laptops sleep, servers redeploy. Without this the
      // visitor's widget looked fine but silently stopped receiving agent
      // replies until they reloaded the page.
      if (!conversationId) return;
      var delay = Math.min(30000, 1000 * Math.pow(2, reconnectAttempts));
      reconnectAttempts += 1;
      clearTimeout(reconnectTimer);
      reconnectTimer = setTimeout(connectSocket, delay);
    };
  }

  // ---------- Small helpers ----------

  function el(tag, css, text) {
    var node = document.createElement(tag);
    if (css) node.style.cssText = css;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  // Pinned to the workspace's zone rather than the visitor's own device
  // clock, so a message timestamp matches what the agent sees in the
  // dashboard — otherwise the same message shows two different times
  // depending on which side is looking at it. Set from the admin's
  // Settings > Time zone choice via this attribute:
  //   <script ... data-timezone="Asia/Kolkata">
  var DISPLAY_TIMEZONE = scriptTag.getAttribute("data-timezone") || "Asia/Kolkata";

  function clockTime(iso) {
    var d = iso ? new Date(iso) : new Date();
    if (isNaN(d.getTime())) d = new Date();
    return d.toLocaleTimeString("en-IN", {
      hour: "numeric",
      minute: "2-digit",
      timeZone: DISPLAY_TIMEZONE,
    });
  }

  function initials(name) {
    return (name || "?")
      .split(/\s+/)
      .slice(0, 2)
      .map(function (w) { return w.charAt(0).toUpperCase(); })
      .join("");
  }

  /** Avatar with the little green "we're here" dot, used in three places. */
  function avatar(size) {
    var wrap = el("div", "position:relative;width:" + size + "px;height:" + size + "px;flex-shrink:0;");
    var face;
    if (AGENT_AVATAR) {
      face = el("img", "width:100%;height:100%;border-radius:50%;object-fit:cover;display:block;");
      face.src = AGENT_AVATAR;
      face.alt = AGENT_NAME;
    } else {
      face = el(
        "div",
        "width:100%;height:100%;border-radius:50%;background:" + BRAND_DARK +
          ";color:#fff;display:flex;align-items:center;justify-content:center;" +
          "font-size:" + Math.round(size * 0.38) + "px;font-weight:600;",
        initials(AGENT_NAME)
      );
    }
    wrap.appendChild(face);

    var dotSize = Math.max(9, Math.round(size * 0.26));
    wrap.appendChild(
      el(
        "span",
        "position:absolute;right:-1px;bottom:-1px;width:" + dotSize + "px;height:" + dotSize +
          "px;border-radius:50%;background:#22c55e;border:2px solid #fff;box-sizing:border-box;"
      )
    );
    return wrap;
  }

  // ---------- UI ----------

  /**
   * A handful of keyframes, injected once. Inline styles can't express
   * animation, and a stylesheet scoped to our own ids can't leak into the
   * host page's CSS.
   */
  function injectStyles() {
    if (document.getElementById("oasis-widget-styles")) return;
    var style = document.createElement("style");
    style.id = "oasis-widget-styles";
    style.textContent =
      "@keyframes oasis-pop{0%{transform:scale(0);opacity:0}60%{transform:scale(1.12)}100%{transform:scale(1);opacity:1}}" +
      "@keyframes oasis-ring{0%{transform:scale(1);opacity:.55}100%{transform:scale(1.9);opacity:0}}" +
      "@keyframes oasis-slide{0%{transform:translateY(10px);opacity:0}100%{transform:translateY(0);opacity:1}}" +
      "@keyframes oasis-blink{0%,80%,100%{opacity:.3}40%{opacity:1}}" +
      ".oasis-dot{animation:oasis-blink 1400ms infinite}" +
      ".oasis-dot:nth-child(2){animation-delay:200ms}" +
      ".oasis-dot:nth-child(3){animation-delay:400ms}" +
      ".oasis-dot:nth-child(4){animation-delay:600ms}" +
      ".oasis-dot:nth-child(5){animation-delay:800ms}" +
      "#oasis-bubble{animation:oasis-pop 420ms cubic-bezier(.2,.9,.3,1.2) both}" +
      "#oasis-teaser{animation:oasis-slide 300ms ease both}" +
      ".oasis-ring{position:absolute;inset:0;border-radius:50%;background:" + BRAND + ";" +
      "animation:oasis-ring 1800ms ease-out 3;pointer-events:none}" +
      // Anyone who has asked their system to calm down gets a still widget.
      "@media (prefers-reduced-motion:reduce){#oasis-bubble,#oasis-teaser,.oasis-ring," +
      ".oasis-dot{animation:none!important}}";
    document.head.appendChild(style);
  }

  var panel, bubble, badge, messageList, input, sendBtn, teaser;
  var homeScreen, formScreen, chatScreen, tabBar, homeTab, chatTab;
  var introRendered = false;

  /**
   * Reopens the panel when the visitor comes back to a reply they haven't
   * read — the case where they wandered off mid-conversation and an agent
   * answered while they were away.
   *
   * Deliberately conditional. Opening on every page load would mean the
   * chat panel following them around the site with nothing new to say,
   * which is how a helpful widget turns into an annoying one.
   */
  function openIfReplyWaiting() {
    if (!visitorDetails || !conversationId) return;
    if (panel.style.display === "flex") return;

    var seen = lastSeenAt();
    var hasNewer = lastAgentMessageAt && new Date(lastAgentMessageAt).getTime() > seen;
    if (!hasNewer) return;

    panel.style.display = "flex";
    unreadCount = 0;
    paintBadge();
    dismissTeaser();
    showScreen("chat");
  }

  function paintBadge() {
    badge.textContent = unreadCount > 9 ? "9+" : String(unreadCount);
    badge.style.display = unreadCount > 0 ? "flex" : "none";
  }

  /** Only one screen shows at a time; the tab bar hides on the form. */
  function showScreen(name) {
    homeScreen.style.display = name === "home" ? "flex" : "none";
    formScreen.style.display = name === "form" ? "flex" : "none";
    chatScreen.style.display = name === "chat" ? "flex" : "none";
    tabBar.style.display = name === "form" ? "none" : "flex";

    homeTab.style.color = name === "home" ? INK : MUTED;
    chatTab.style.color = name === "chat" ? INK : MUTED;

    if (name === "chat") {
      renderIntro();
      loadHistory();
      markRead();
      markSeenNow();
      setTimeout(function () { input.focus(); }, 50);
    }
  }

  /** Where a visitor lands: greeting, who they'll talk to, one button. */
  function buildHomeScreen() {
    homeScreen = el("div", "flex:1;display:none;flex-direction:column;overflow-y:auto;");

    var header = el(
      "div",
      "padding:26px 22px 32px;background:linear-gradient(160deg," + BRAND_DARK + " 0%," + BRAND + " 100%);"
    );

    var mark = el(
      "div",
      "width:42px;height:42px;border-radius:12px;background:rgba(255,255,255,0.16);" +
        "display:flex;align-items:center;justify-content:center;margin-bottom:18px;"
    );
    mark.innerHTML =
      '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">' +
      '<path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" ' +
      'stroke="#ffffff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
    header.appendChild(mark);

    header.appendChild(el("div", "font-size:26px;font-weight:700;color:#fff;line-height:1.25;", TITLE));
    header.appendChild(
      el("div", "font-size:26px;font-weight:700;color:rgba(255,255,255,0.7);line-height:1.25;", SUBTITLE)
    );
    homeScreen.appendChild(header);

    // Agent card, pulled up over the gradient so the two read as one unit.
    var card = el(
      "div",
      "margin:-18px 16px 0;background:#fff;border-radius:14px;padding:16px;" +
        "box-shadow:0 6px 20px rgba(11,43,39,0.12);border:1px solid " + LINE + ";"
    );

    var who = el("div", "display:flex;align-items:center;gap:11px;margin-bottom:14px;");
    who.appendChild(avatar(38));
    var whoText = el("div", "min-width:0;");
    whoText.appendChild(el("div", "font-size:14px;font-weight:600;color:" + INK + ";", AGENT_NAME));
    whoText.appendChild(el("div", "font-size:12.5px;color:" + MUTED + ";", "Usually replies in a few minutes"));
    who.appendChild(whoText);
    card.appendChild(who);

    var startBtn = el(
      "button",
      "width:100%;background:" + BRAND + ";color:#fff;border:none;border-radius:10px;" +
        "padding:13px;font-size:15px;font-weight:600;font-family:inherit;cursor:pointer;" +
        "display:flex;align-items:center;justify-content:center;gap:8px;"
    );
    startBtn.appendChild(el("span", "", conversationId ? "Continue chat" : "Let's chat"));
    startBtn.insertAdjacentHTML(
      "beforeend",
      '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">' +
      '<path d="M5 12h14M13 6l6 6-6 6" stroke="#ffffff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>'
    );
    startBtn.addEventListener("click", function () {
      showScreen(visitorDetails ? "chat" : "form");
    });
    card.appendChild(startBtn);
    homeScreen.appendChild(card);

    if (TOPICS.length) {
      var topicWrap = el("div", "padding:22px 16px 18px;");
      topicWrap.appendChild(
        el("div", "font-size:12.5px;color:" + MUTED + ";margin-bottom:10px;", "Common questions")
      );
      TOPICS.forEach(function (topic) {
        var chip = el(
          "button",
          "display:block;width:100%;text-align:left;background:" + CANVAS + ";border:1px solid " + LINE + ";" +
            "border-radius:10px;padding:11px 13px;margin-bottom:8px;font-size:13.5px;" +
            "font-family:inherit;color:" + INK + ";cursor:pointer;",
          topic
        );
        chip.addEventListener("mouseenter", function () { chip.style.borderColor = BRAND; });
        chip.addEventListener("mouseleave", function () { chip.style.borderColor = LINE; });
        // A topic is just a first message the visitor didn't have to type.
        chip.addEventListener("click", function () {
          pendingTopic = topic;
          showScreen(visitorDetails ? "chat" : "form");
          if (visitorDetails) {
            input.value = pendingTopic;
            pendingTopic = null;
            handleSend();
          }
        });
        topicWrap.appendChild(chip);
      });
      homeScreen.appendChild(topicWrap);
    }
  }

  /** Name + mobile, both required, asked once per visitor. */
  function buildFormScreen() {
    formScreen = el("div", "flex:1;display:none;flex-direction:column;overflow-y:auto;");

    var head = el(
      "div",
      "padding:16px 18px 14px;border-bottom:1px solid " + LINE + ";display:flex;align-items:center;gap:10px;"
    );
    var back = el(
      "button",
      "width:30px;height:30px;border-radius:50%;border:1px solid " + LINE + ";background:#fff;" +
        "cursor:pointer;font-size:17px;line-height:1;color:" + MUTED + ";flex-shrink:0;padding:0;",
      "‹"
    );
    back.setAttribute("aria-label", "Back");
    back.addEventListener("click", function () { showScreen("home"); });
    head.appendChild(back);
    head.appendChild(el("div", "font-size:15px;font-weight:600;", "Before we start"));
    formScreen.appendChild(head);

    var body = el("div", "padding:18px 20px;");
    body.appendChild(
      el("div", "font-size:13.5px;color:" + MUTED + ";margin-bottom:18px;line-height:1.5;",
        "So we can reply even if you leave this page, please share your name and mobile number.")
    );

    function labelFor(text) {
      var l = el("label", "display:block;font-size:13px;font-weight:600;color:" + INK + ";margin-bottom:6px;");
      l.appendChild(document.createTextNode(text));
      l.appendChild(el("span", "color:#dc2626;margin-left:3px;", "*"));
      return l;
    }

    body.appendChild(labelFor("Name"));
    var nameInput = el(
      "input",
      "width:100%;box-sizing:border-box;border:1px solid " + LINE + ";border-radius:9px;" +
        "padding:11px 12px;font-size:14px;font-family:inherit;color:" + INK + ";outline:none;"
    );
    nameInput.type = "text";
    nameInput.placeholder = "Your full name";
    body.appendChild(nameInput);
    var nameError = el("div", "font-size:12px;color:#dc2626;min-height:17px;margin:4px 0 8px;");
    body.appendChild(nameError);

    body.appendChild(labelFor("Mobile number"));
    var phoneRow = el("div", "display:flex;gap:7px;");
    // A native <select> shows the selected option's full text when
    // closed, so "United Kingdom +44" would eat most of the row. This is
    // a small custom picker instead: the dial code alone when shut, full
    // country names when open.
    var selectedIso = detectCountry();

    var countryButton = el(
      "button",
      "display:flex;align-items:center;gap:5px;border:1px solid " + LINE + ";border-radius:9px;" +
        "padding:11px 10px;font-size:14px;font-family:inherit;color:" + INK + ";background:#fff;" +
        "cursor:pointer;flex-shrink:0;white-space:nowrap;"
    );
    countryButton.type = "button";
    countryButton.setAttribute("aria-label", "Country code");

    var countryLabel = el("span", "font-variant-numeric:tabular-nums;", "");
    countryButton.appendChild(countryLabel);
    countryButton.insertAdjacentHTML(
      "beforeend",
      '<svg width="10" height="10" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">' +
      '<path d="M6 9l6 6 6-6" stroke="' + MUTED + '" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/></svg>'
    );

    var countryList = el(
      "div",
      "position:absolute;top:100%;left:0;margin-top:4px;background:#fff;border:1px solid " + LINE + ";" +
        "border-radius:10px;box-shadow:0 8px 24px rgba(11,43,39,0.16);z-index:10;display:none;" +
        "min-width:210px;overflow:hidden;"
    );

    function paintCountry() {
      var country = findCountry(selectedIso);
      // Collapsed, the dial code alone is ambiguous — +1 is the US and
      // Canada both. The country abbreviation next to it removes the
      // doubt without costing the width a full name would.
      countryLabel.textContent = country
        ? shortLabel(country.iso) + " +" + country.dial
        : "+";
    }

    offeredCountries().forEach(function (c) {
      var option = el(
        "button",
        "display:block;width:100%;text-align:left;border:none;background:#fff;cursor:pointer;" +
          "padding:10px 13px;font-size:13.5px;font-family:inherit;color:" + INK + ";",
        c.name + "  +" + c.dial
      );
      option.type = "button";
      option.addEventListener("mouseenter", function () { option.style.background = CANVAS; });
      option.addEventListener("mouseleave", function () { option.style.background = "#fff"; });
      option.addEventListener("click", function () {
        selectedIso = c.iso;
        paintCountry();
        applyPhoneHint();
        countryList.style.display = "none";
        phoneError.textContent = "";
        phoneInput.focus();
      });
      countryList.appendChild(option);
    });

    countryButton.addEventListener("click", function (e) {
      e.stopPropagation();
      countryList.style.display = countryList.style.display === "block" ? "none" : "block";
    });
    // Clicking anywhere else closes it, which is what every dropdown on
    // the web does and what people expect without being told.
    document.addEventListener("click", function () {
      countryList.style.display = "none";
    });

    var countryWrap = el("div", "position:relative;flex-shrink:0;");
    countryWrap.appendChild(countryButton);
    countryWrap.appendChild(countryList);
    paintCountry();

    var phoneInput = el(
      "input",
      "flex:1;min-width:0;border:1px solid " + LINE + ";border-radius:9px;padding:11px 12px;" +
        "font-size:14px;font-family:inherit;color:" + INK + ";outline:none;"
    );
    phoneInput.type = "tel";
    phoneInput.placeholder = "98765 43210";
    phoneInput.setAttribute("inputmode", "tel");
    phoneInput.setAttribute("maxlength", "20");

    function applyPhoneHint() {
      var expected = NATIONAL_DIGITS[selectedIso];
      // Spaces and dashes are allowed, so the cap is generous — the exact
      // check happens on the digits themselves.
      phoneInput.setAttribute("maxlength", expected ? String(expected + 6) : "20");
      phoneInput.placeholder = expected === 9 ? "412 345 678" : "98765 43210";
    }

    applyPhoneHint();

    phoneRow.appendChild(countryWrap);
    phoneRow.appendChild(phoneInput);
    body.appendChild(phoneRow);
    var phoneError = el("div", "font-size:12px;color:#dc2626;min-height:17px;margin:4px 0 10px;");
    body.appendChild(phoneError);

    // Verification. Hidden entirely when the server isn't asking for it,
    // so nobody is made to do arithmetic for nothing.
    var captchaWrap = el("div", "display:none;");
    var captchaLabel = labelFor("Verification");
    captchaWrap.appendChild(captchaLabel);

    var captchaRow = el("div", "display:flex;align-items:center;gap:9px;");
    var captchaQuestion = el(
      "div",
      "background:" + CANVAS + ";border:1px solid " + LINE + ";border-radius:9px;" +
        "padding:11px 14px;font-size:15px;font-weight:600;color:" + INK + ";" +
        "white-space:nowrap;font-variant-numeric:tabular-nums;",
      ""
    );
    var captchaInput = el(
      "input",
      "flex:1;min-width:0;border:1px solid " + LINE + ";border-radius:9px;padding:11px 12px;" +
        "font-size:14px;font-family:inherit;color:" + INK + ";outline:none;"
    );
    captchaInput.type = "text";
    captchaInput.setAttribute("inputmode", "numeric");
    captchaInput.setAttribute("maxlength", "3");
    captchaInput.placeholder = "Answer";

    captchaRow.appendChild(captchaQuestion);
    captchaRow.appendChild(el("span", "color:" + MUTED + ";font-size:15px;", "="));
    captchaRow.appendChild(captchaInput);
    captchaWrap.appendChild(captchaRow);

    var captchaError = el("div", "font-size:12px;color:#dc2626;min-height:17px;margin:4px 0 10px;");
    captchaWrap.appendChild(captchaError);
    body.appendChild(captchaWrap);

    // Asked for once the form is on screen, so the five-minute window
    // starts when the visitor starts typing, not when the page loaded.
    loadCaptcha().then(function (challenge) {
      if (!challenge.question) return;
      captchaQuestion.textContent = challenge.question;
      captchaWrap.style.display = "block";
    });

    captchaInput.addEventListener("input", function () {
      captchaInput.value = captchaInput.value.replace(/[^0-9]/g, "");
      captchaInput.style.borderColor = LINE;
      captchaError.textContent = "";
    });

    var submit = el(
      "button",
      "width:100%;background:" + BRAND + ";color:#fff;border:none;border-radius:10px;padding:13px;" +
        "font-size:15px;font-weight:600;font-family:inherit;cursor:pointer;",
      "Start the chat"
    );
    body.appendChild(submit);
    body.appendChild(
      el("div", "font-size:11.5px;color:" + MUTED + ";margin-top:12px;text-align:center;line-height:1.5;",
        "We use this only to continue this conversation.")
    );
    formScreen.appendChild(body);

    function selectedDialCode() {
      var country = findCountry(selectedIso);
      return country ? country.dial : "";
    }

    // Mirrors the server-side rule in backend/app/shared/phone.py. The
    // point of checking here is to tell the person what's wrong while
    // they're still looking at the field — the server check is what
    // actually protects the data.
    function phoneProblem(nationalNumber) {
      if (!nationalNumber) return "Please fill in this field.";
      if (!/^[0-9()\-.\s]+$/.test(nationalNumber)) {
        return "Digits only, please.";
      }

      var digits = nationalNumber.replace(/\D/g, "");
      var expected = NATIONAL_DIGITS[selectedIso];

      if (expected) {
        // Say the number, not just "invalid" — someone who typed nine
        // digits needs to know they are one short, not that they failed.
        if (digits.length !== expected) {
          var label = shortLabel(selectedIso);
          // "A AU number" reads wrong; the article follows how the
          // abbreviation is said aloud, not how it is spelled.
          var article = "AEFHILMNORSX".indexOf(label.charAt(0)) !== -1 ? "An" : "A";
          return (
            article + " " + label + " number is " + expected +
            " digits. You've entered " + digits.length + "."
          );
        }
      } else {
        if (digits.length < 6) return "That number is too short.";
        if (digits.length > 13) return "That number is too long.";
      }

      if (/^(\d)\1+$/.test(digits)) return "Enter a real mobile number.";
      return null;
    }

    function submitForm() {
      var name = nameInput.value.trim();
      var phone = phoneInput.value.trim();
      nameError.textContent = "";
      phoneError.textContent = "";

      if (name.length < 2) {
        nameError.textContent = "Please fill in this field.";
        nameInput.style.borderColor = "#dc2626";
        nameInput.focus();
        return;
      }
      var problem = phoneProblem(phone);
      if (problem) {
        phoneError.textContent = problem;
        phoneInput.style.borderColor = "#dc2626";
        phoneInput.focus();
        return;
      }

      if (captcha.id && !captchaInput.value.trim()) {
        captchaError.textContent = "Please answer the question.";
        captchaInput.style.borderColor = "#dc2626";
        captchaInput.focus();
        return;
      }

      // Stored in full international form so an agent (or a CRM) can dial
      // it without guessing where the customer is.
      var fullPhone = "+" + selectedDialCode() + phone.replace(/\D/g, "");

      function proceed() {
        window.localStorage.setItem(COUNTRY_STORAGE_KEY, selectedIso);
        visitorDetails = { name: name, phone: fullPhone };
        saveDetails(visitorDetails);
        identify();
        showScreen("chat");

        // A topic tapped on the home screen becomes the first message once
        // the form is out of the way.
        if (pendingTopic) {
          input.value = pendingTopic;
          pendingTopic = null;
          handleSend();
        }
      }

      if (!captcha.id) {
        proceed();
        return;
      }

      // Nothing moves until the sum is right. Getting it wrong leaves the
      // visitor exactly where they are, with a new question — the old
      // flow sent them to the chat screen and then told them their
      // message had failed, which named the wrong problem entirely.
      submit.disabled = true;
      submit.textContent = "Checking…";
      verifyCaptcha(captchaInput.value.trim())
        .then(function (pass) {
          captchaPass = pass;
          submit.disabled = false;
          submit.textContent = "Start the chat";
          proceed();
        })
        .catch(function (err) {
          submit.disabled = false;
          submit.textContent = "Start the chat";
          captchaError.textContent = err.message;
          captchaInput.value = "";
          captchaInput.style.borderColor = "#dc2626";
          // A spent challenge can't be reused, so fetch a fresh sum
          // rather than leaving a question that can never be right.
          loadCaptcha().then(function (c) {
            if (c.question) captchaQuestion.textContent = c.question;
            captchaInput.focus();
          });
        });
    }

    submit.addEventListener("click", submitForm);
    nameInput.addEventListener("keydown", function (e) {
      if (e.key === "Enter") phoneInput.focus();
    });
    phoneInput.addEventListener("keydown", function (e) {
      if (e.key === "Enter") submitForm();
    });
    nameInput.addEventListener("input", function () {
      nameInput.style.borderColor = LINE;
      nameError.textContent = "";
    });
    phoneInput.addEventListener("input", function () {
      // Strip anything that could never belong in a phone number as it is
      // typed, so pasted junk is visibly rejected instead of silently sent.
      var cleaned = phoneInput.value.replace(/[^0-9()\-.\s]/g, "");
      if (cleaned !== phoneInput.value) {
        phoneInput.value = cleaned;
        phoneError.textContent = "Digits only, please.";
      } else {
        phoneInput.style.borderColor = LINE;
        phoneError.textContent = "";
      }
    });

  }

  function buildChatScreen() {
    chatScreen = el("div", "flex:1;display:none;flex-direction:column;overflow:hidden;");

    var head = el(
      "div",
      "padding:12px 14px;border-bottom:1px solid " + LINE + ";display:flex;align-items:center;gap:11px;background:#fff;"
    );
    head.appendChild(avatar(34));
    var headText = el("div", "min-width:0;flex:1;");
    headText.appendChild(el("div", "font-size:14px;font-weight:600;", AGENT_NAME));
    headText.appendChild(el("div", "font-size:12px;color:#16a34a;", "Online"));
    head.appendChild(headText);

    var minimize = el(
      "button",
      "border:none;background:transparent;cursor:pointer;color:" + MUTED +
        ";font-size:22px;line-height:1;padding:2px 6px;font-family:inherit;",
      "−"
    );
    minimize.setAttribute("aria-label", "Minimise chat");
    minimize.addEventListener("click", function () { panel.style.display = "none"; });
    head.appendChild(minimize);
    chatScreen.appendChild(head);

    messageList = el("div", "flex:1;overflow-y:auto;padding:16px;background:" + CANVAS + ";");
    messageList.id = "oasis-messages";
    chatScreen.appendChild(messageList);

    var composer = el(
      "div",
      "display:flex;align-items:center;gap:9px;padding:11px 12px;border-top:1px solid " + LINE + ";background:#fff;"
    );
    input = el(
      "input",
      "flex:1;min-width:0;border:1px solid " + LINE + ";border-radius:22px;padding:11px 15px;" +
        "font-size:14px;font-family:inherit;color:" + INK + ";outline:none;"
    );
    input.type = "text";
    input.placeholder = "Write a message…";
    input.addEventListener("focus", function () { input.style.borderColor = BRAND; });
    input.addEventListener("blur", function () { input.style.borderColor = LINE; });
    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter") handleSend();
    });

    sendBtn = el(
      "button",
      "width:40px;height:40px;border-radius:50%;background:" + BRAND + ";border:none;cursor:pointer;" +
        "display:flex;align-items:center;justify-content:center;flex-shrink:0;padding:0;"
    );
    sendBtn.setAttribute("aria-label", "Send message");
    sendBtn.innerHTML =
      '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">' +
      '<path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z" stroke="#ffffff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
    sendBtn.addEventListener("click", handleSend);

    composer.appendChild(input);
    composer.appendChild(sendBtn);
    chatScreen.appendChild(composer);
  }

  function buildTabBar() {
    tabBar = el(
      "div",
      "display:none;border-top:1px solid " + LINE + ";background:#fff;padding:6px 8px 8px;"
    );
    var inner = el("div", "display:flex;width:100%;");

    function tab(label, icon, onClick) {
      var t = el(
        "button",
        "flex:1;background:transparent;border:none;cursor:pointer;font-family:inherit;" +
          "font-size:11.5px;color:" + MUTED + ";display:flex;flex-direction:column;" +
          "align-items:center;gap:3px;padding:6px 0;"
      );
      t.innerHTML = icon;
      t.appendChild(el("span", "", label));
      t.addEventListener("click", onClick);
      return t;
    }

    homeTab = tab(
      "Home",
      '<svg width="19" height="19" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">' +
      '<path d="M3 10.5L12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1v-9.5z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/></svg>',
      function () { showScreen("home"); }
    );
    chatTab = tab(
      "Chat",
      '<svg width="19" height="19" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">' +
      '<path d="M21 11.5a8.5 8.5 0 0 1-8.5 8.5 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 1 1 17 0z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/></svg>',
      function () { showScreen(visitorDetails ? "chat" : "form"); }
    );

    inner.appendChild(homeTab);
    inner.appendChild(chatTab);
    tabBar.appendChild(inner);
  }

  var TEASER_SEEN_KEY = "oasis_teaser_seen_" + ORG_SLUG;

  /**
   * The small "Hi there! Need any help?" card that slides in above the
   * launcher after a few seconds.
   *
   * Rules that keep it an invitation rather than a nuisance:
   *  - once per browser session, remembered even across page navigations
   *  - never for someone who already has a chat open with us
   *  - dismissable, and dismissing counts as seen
   */
  function showTeaser() {
    if (TEASER_OFF || conversationId || teaser) return;
    if (panel.style.display === "flex") return;
    try {
      if (window.sessionStorage.getItem(TEASER_SEEN_KEY)) return;
    } catch (e) { /* private mode — just show it */ }

    teaser = el(
      "div",
      "position:fixed;bottom:92px;right:20px;max-width:270px;background:#fff;" +
        "border:1px solid " + LINE + ";border-radius:14px;padding:13px 14px;" +
        "box-shadow:0 12px 32px rgba(11,43,39,0.18);z-index:99998;display:flex;gap:10px;" +
        "align-items:flex-start;cursor:pointer;" +
        "font-family:Inter,'Segoe UI',system-ui,sans-serif;"
    );
    teaser.id = "oasis-teaser";

    teaser.appendChild(avatar(32));

    var body = el("div", "min-width:0;flex:1;");
    body.appendChild(el("div", "font-size:12.5px;font-weight:600;color:" + INK + ";", AGENT_NAME));
    body.appendChild(
      el("div", "font-size:13px;color:" + MUTED + ";line-height:1.45;margin-top:2px;", TEASER_TEXT)
    );
    teaser.appendChild(body);

    var close = el(
      "button",
      "border:none;background:transparent;color:" + MUTED + ";font-size:16px;line-height:1;" +
        "cursor:pointer;padding:0 2px;flex-shrink:0;font-family:inherit;",
      "×"
    );
    close.setAttribute("aria-label", "Dismiss");
    close.addEventListener("click", function (e) {
      e.stopPropagation();
      dismissTeaser();
    });
    teaser.appendChild(close);

    teaser.addEventListener("click", function () {
      dismissTeaser();
      window.OasisChatbot.open();
    });

    document.body.appendChild(teaser);
  }

  function dismissTeaser() {
    try {
      window.sessionStorage.setItem(TEASER_SEEN_KEY, "1");
    } catch (e) { /* nothing to remember it with — fine */ }
    if (teaser && teaser.parentNode) teaser.parentNode.removeChild(teaser);
    teaser = null;
  }

  function buildUI() {
    injectStyles();

    // ----- Launcher -----
    // A pill when the site gives it words, a circle otherwise. Words get
    // noticed more, but they also take more room, so it stays opt-in.
    var isPill = !!LAUNCHER_TEXT;
    bubble = el(
      "button",
      "position:fixed;bottom:20px;right:20px;" +
        (isPill
          ? "height:54px;border-radius:27px;padding:0 20px 0 16px;gap:10px;"
          : "width:60px;height:60px;border-radius:50%;padding:0;") +
        "background:" + BRAND + ";border:none;cursor:pointer;z-index:99999;" +
        "box-shadow:0 10px 28px rgba(11,43,39,0.34);display:flex;align-items:center;" +
        "justify-content:center;transition:transform 160ms ease,box-shadow 160ms ease;" +
        "font-family:Inter,'Segoe UI',system-ui,sans-serif;"
    );
    bubble.id = "oasis-bubble";
    bubble.setAttribute("aria-label", "Open chat");

    // A human face pulls more attention than a generic speech bubble, so
    // an agent photo is used as the launcher when the site provides one.
    if (AGENT_AVATAR) {
      var face = el(
        "img",
        "width:" + (isPill ? 36 : 40) + "px;height:" + (isPill ? 36 : 40) +
          "px;border-radius:50%;object-fit:cover;border:2px solid rgba(255,255,255,0.85);"
      );
      face.src = AGENT_AVATAR;
      face.alt = "";
      bubble.appendChild(face);
    } else {
      bubble.insertAdjacentHTML(
        "beforeend",
        '<svg width="26" height="26" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">' +
        '<path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" ' +
        'stroke="#ffffff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>'
      );
    }

    if (isPill) {
      bubble.appendChild(
        el("span", "color:#fff;font-size:15px;font-weight:600;white-space:nowrap;", LAUNCHER_TEXT)
      );
    }

    // Two expanding rings, three times, then silence. A widget that pulses
    // forever stops being an invitation and becomes something to ignore.
    var ring = el("span", "");
    ring.className = "oasis-ring";
    ring.style.zIndex = "-1";
    bubble.appendChild(ring);
    setTimeout(function () {
      if (ring.parentNode) ring.parentNode.removeChild(ring);
    }, 6000);

    bubble.onmouseenter = function () {
      bubble.style.transform = "scale(1.06)";
      bubble.style.boxShadow = "0 14px 34px rgba(11,43,39,0.42)";
    };
    bubble.onmouseleave = function () {
      bubble.style.transform = "scale(1)";
      bubble.style.boxShadow = "0 10px 28px rgba(11,43,39,0.34)";
    };

    badge = el(
      "span",
      "position:absolute;top:-2px;right:-2px;min-width:20px;height:20px;border-radius:10px;" +
        "background:#e11d48;color:#fff;font-size:11px;font-weight:600;display:none;" +
        "align-items:center;justify-content:center;padding:0 5px;border:2px solid #fff;box-sizing:border-box;"
    );
    bubble.appendChild(badge);

    // ----- Panel -----
    panel = el(
      "div",
      "position:fixed;bottom:88px;right:20px;width:372px;max-width:calc(100vw - 32px);" +
        "height:580px;max-height:calc(100vh - 120px);background:#fff;border-radius:16px;" +
        "box-shadow:0 20px 60px rgba(11,43,39,0.28);display:none;flex-direction:column;" +
        "z-index:99999;overflow:hidden;border:1px solid " + LINE + ";" +
        "font-family:Inter,'Segoe UI',system-ui,-apple-system,sans-serif;font-size:14px;color:" + INK + ";"
    );
    panel.id = "oasis-panel";

    buildHomeScreen();
    buildFormScreen();
    buildChatScreen();
    buildTabBar();

    panel.appendChild(homeScreen);
    panel.appendChild(formScreen);
    panel.appendChild(chatScreen);
    panel.appendChild(tabBar);

    document.body.appendChild(bubble);
    document.body.appendChild(panel);

    bubble.addEventListener("click", function () {
      var isOpen = panel.style.display === "flex";
      panel.style.display = isOpen ? "none" : "flex";
      dismissTeaser();
      if (isOpen) return;

      unreadCount = 0;
      paintBadge();
      // A returning visitor with a live thread should land in it, not on a
      // welcome screen they've already read.
      showScreen(visitorDetails && conversationId ? "chat" : "home");
      if (visitorDetails) identify();
    });

    // Pull unread replies in even before the visitor opens the panel.
    if (visitorDetails && conversationId) {
      loadHistory().then(openIfReplyWaiting);
    }

    // Long enough that the visitor has looked at the page first, short
    // enough to catch them before they leave.
    if (!TEASER_OFF) setTimeout(showTeaser, TEASER_DELAY);
  }

  // ---------- Rendering ----------

  /** The agent's opening line, shown once above whatever follows. */
  function renderIntro() {
    if (introRendered) return;
    introRendered = true;
    renderMessage("agent", GREETING, null, true);
  }

  function renderMessage(senderType, content, createdAt, skipScroll) {
    // "Priya joined the chat" is not a message from Priya — it is the room
    // narrating itself. Centred grey text, no avatar, no bubble.
    if (senderType === "system") {
      var note = el(
        "div",
        "text-align:center;font-size:12px;color:" + MUTED + ";margin:12px 0;padding:0 14px;" +
          "line-height:1.4;",
        content
      );
      messageList.appendChild(note);
      if (!skipScroll) messageList.scrollTop = messageList.scrollHeight;
      return note;
    }

    var mine = senderType === "customer";
    var row = el("div", "display:flex;gap:8px;margin-bottom:12px;" + (mine ? "justify-content:flex-end;" : ""));

    if (!mine) row.appendChild(avatar(26));

    var stack = el(
      "div",
      "max-width:78%;display:flex;flex-direction:column;" + (mine ? "align-items:flex-end;" : "")
    );
    var bubbleEl = el(
      "div",
      "padding:10px 13px;border-radius:14px;font-size:14px;line-height:1.45;white-space:pre-wrap;" +
        "word-break:break-word;" +
        (mine
          ? "background:" + BRAND + ";color:#fff;border-bottom-right-radius:4px;"
          : "background:#fff;color:" + INK + ";border:1px solid " + LINE + ";border-bottom-left-radius:4px;"),
      content
    );
    stack.appendChild(bubbleEl);

    var meta = el("div", "font-size:11px;color:" + MUTED + ";margin-top:4px;padding:0 3px;", clockTime(createdAt));
    if (mine) {
      // Only the newest outgoing message shows a receipt — the thread is
      // read top to bottom, so repeating it on every bubble is noise.
      var receipt = el("span", "margin-left:6px;", "Sent");
      meta.appendChild(receipt);
      row.dataset.sentAt = createdAt || new Date().toISOString();
      row._receipt = receipt;
      lastOutgoingRow = row;
    }
    stack.appendChild(meta);
    row.appendChild(stack);

    messageList.appendChild(row);
    if (mine) paintReceipt();
    if (!skipScroll) messageList.scrollTop = messageList.scrollHeight;
    return row;
  }

  /**
   * Moves the last outgoing message between "Sent" and "Seen". Driven by
   * one timestamp rather than per-message flags, so a receipt that arrives
   * for an older message still lights up the right bubble.
   */
  function paintReceipt() {
    if (!lastOutgoingRow || !lastOutgoingRow._receipt) return;
    var sentAt = lastOutgoingRow.dataset.sentAt;
    var seen =
      agentReadAt && sentAt && new Date(agentReadAt).getTime() >= new Date(sentAt).getTime();
    lastOutgoingRow._receipt.textContent = seen ? "Seen" : "Sent";
    lastOutgoingRow._receipt.style.color = seen ? BRAND : MUTED;
    lastOutgoingRow._receipt.style.fontWeight = seen ? "600" : "400";
  }

  /**
   * Shown while the visitor's first message sits unanswered.
   *
   * Starts as a spinner, which reads as "someone is coming". After
   * WAIT_PATIENCE_MS it becomes slow dots and a plain sentence, because a
   * spinner that never stops starts to feel like the page has hung — and
   * the honest message at that point is "still looking", not "loading".
   */
  function showWaiting() {
    if (waitRow || !conversationId) return;

    waitRow = el("div", "display:flex;justify-content:center;margin:14px 0;");
    var box = el(
      "div",
      "display:flex;align-items:center;gap:9px;background:#fff;border:1px solid " + LINE + ";" +
        "border-radius:20px;padding:8px 14px;font-size:12.5px;color:" + MUTED + ";max-width:90%;"
    );

    // A ring that drains rather than a spinner that loops. A loop says
    // "working" forever; a draining ring says "this has a limit", which
    // is the truth — at the end of it the message changes.
    var ring = document.createElement("div");
    ring.style.cssText = "width:20px;height:20px;flex-shrink:0;";
    ring.innerHTML =
      '<svg width="20" height="20" viewBox="0 0 36 36" style="transform:rotate(-90deg)">' +
      '<circle cx="18" cy="18" r="15.5" fill="none" stroke="' + LINE + '" stroke-width="4"/>' +
      '<circle class="oasis-countdown" cx="18" cy="18" r="15.5" fill="none" stroke="' + BRAND +
      '" stroke-width="4" stroke-linecap="round" stroke-dasharray="97.4" stroke-dashoffset="0"/>' +
      "</svg>";
    box.appendChild(ring);

    // Driven in JS rather than CSS so the duration follows the configured
    // patience, and so a visitor who returns mid-wait sees the ring where
    // it actually is instead of starting over.
    var startedAt = Date.now();
    var arc = ring.querySelector(".oasis-countdown");
    clearInterval(waitRing);
    waitRing = setInterval(function () {
      if (!waitRow || !arc.isConnected) {
        clearInterval(waitRing);
        return;
      }
      var done = Math.min(1, (Date.now() - startedAt) / WAIT_PATIENCE_MS);
      arc.setAttribute("stroke-dashoffset", String(97.4 * done));
    }, 200);

    box.appendChild(el("span", "", "Connecting you to an agent…"));

    waitRow.appendChild(box);
    messageList.appendChild(waitRow);
    messageList.scrollTop = messageList.scrollHeight;

    clearTimeout(waitTimer);
    waitTimer = setTimeout(softenWaiting, WAIT_PATIENCE_MS);
  }

  /** Spinner out, slow dots in, and say what is actually happening. */
  function softenWaiting() {
    if (!waitRow) return;
    clearInterval(waitRing);
    waitRing = null;
    waitRow.innerHTML = "";

    var box = el(
      "div",
      "display:flex;align-items:center;gap:9px;background:#fff;border:1px solid " + LINE + ";" +
        "border-radius:20px;padding:9px 14px;font-size:12.5px;color:" + MUTED + ";max-width:90%;"
    );

    var dots = el("span", "display:flex;gap:3px;flex-shrink:0;");
    for (var i = 0; i < 5; i++) {
      var dot = el("span", "width:4px;height:4px;border-radius:50%;background:" + MUTED + ";display:block;");
      dot.className = "oasis-dot";
      dots.appendChild(dot);
    }
    box.appendChild(dots);
    box.appendChild(el("span", "", WAIT_LONG_TEXT));

    waitRow.appendChild(box);
    messageList.scrollTop = messageList.scrollHeight;
  }

  function hideWaiting() {
    clearTimeout(waitTimer);
    clearInterval(waitRing);
    waitTimer = null;
    waitRing = null;
    if (waitRow && waitRow.parentNode) waitRow.parentNode.removeChild(waitRow);
    waitRow = null;
  }

  function renderNotice(text) {
    messageList.appendChild(
      el("div", "text-align:center;font-size:12px;color:" + MUTED + ";margin:10px 0;padding:0 12px;", text)
    );
    messageList.scrollTop = messageList.scrollHeight;
  }

  function setPending(row, pending) {
    row.style.opacity = pending ? "0.6" : "1";
  }

  function setFailed(row, text) {
    row.style.opacity = "1";
    var bubbleEl = row.querySelector("div > div");
    if (bubbleEl) {
      bubbleEl.style.background = "#a32b2b";
      bubbleEl.style.border = "none";
      bubbleEl.style.color = "#fff";
    }
    row.title = "Not delivered — tap to retry";
    row.style.cursor = "pointer";
    row.onclick = function () {
      row.remove();
      input.value = text;
      input.focus();
    };
    renderNotice("Message not sent. Check your connection and tap the red message to retry.");
  }

  function handleSend() {
    var text = input.value.trim();
    if (!text) return;
    input.value = "";
    var row = renderMessage("customer", text);
    setPending(row, true);

    var request = conversationId
      ? sendMessage(text).then(function () { return null; })
      : startConversation(text).then(function (data) {
          conversationId = data.id;
          historyLoaded = true;
          saveConversationId(conversationId);
          connectSocket();
          return null;
        });

    request
      .then(function () {
        setPending(row, false);
        // Only while nobody has replied yet — a chat already being handled
        // doesn't need a "connecting you" notice on every message.
        if (!agentHasReplied) showWaiting();
      })
      .catch(function () {
        // The message never left the browser — say so instead of showing
        // it as delivered and letting the visitor wait for a reply that
        // can never come.
        setFailed(row, text);
        // A rejected or expired challenge is spent either way, so fetch a
        // fresh one rather than letting a retry fail for the same reason.
        if (captcha.id) loadCaptcha();
      });
  }

  buildUI();

  // Exposed for host pages that want programmatic control.
  window.OasisChatbot = {
    open: function () {
      panel.style.display = "flex";
      dismissTeaser();
      unreadCount = 0;
      paintBadge();
      showScreen(visitorDetails && conversationId ? "chat" : "home");
      if (visitorDetails) identify();
    },
    close: function () {
      panel.style.display = "none";
    },
    reset: function () {
      clearConversationId();
      window.localStorage.removeItem(DETAILS_STORAGE_KEY);
      window.localStorage.removeItem(COUNTRY_STORAGE_KEY);
      window.localStorage.removeItem(STORAGE_KEY);
    },
    externalId: externalId,

    /** Prints why the panel did or didn't open by itself. */
    debug: function () {
      var seen = lastSeenAt();
      console.log("[Chat Support] conversation :", conversationId || "(none)");
      console.log("[Chat Support] visitor saved:", !!visitorDetails);
      console.log("[Chat Support] last agent msg:", lastAgentMessageAt || "(none yet)");
      console.log("[Chat Support] last seen at  :", seen ? new Date(seen).toISOString() : "(never)");
      console.log(
        "[Oasis] would auto-open:",
        !!(lastAgentMessageAt && new Date(lastAgentMessageAt).getTime() > seen)
      );
    },
  };
})();
