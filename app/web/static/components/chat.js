(() => {
  // ── Lightweight markdown renderer ───────────────────────────
  function renderMarkdown(text) {
    const escapeHtml = (s) => s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
    const codeBlockRe = /```(\w*)\n([\s\S]*?)```/g;
    const inlineCodeRe = /`([^`]+)`/g;
    const boldRe = /\*\*([^*]+)\*\*/g;
    const italicRe = /\*([^*]+)\*/g;
    const linkRe = /\[([^\]]+)\]\(([^)]+)\)/g;
    const headingRe = /^(#{1,6})\s+(.*)$/gm;
    const ulRe = /^[\s]*[-*]\s+(.*)$/gm;
    const olRe = /^\s*\d+\.\s+(.*)$/gm;

    let html = escapeHtml(text);
    html = html.replace(codeBlockRe, '<pre><code>$2</code></pre>');
    html = html.replace(inlineCodeRe, '<code>$1</code>');
    html = html.replace(boldRe, '<strong>$1</strong>');
    html = html.replace(italicRe, '<em>$1</em>');
    html = html.replace(linkRe, '<a href="$2" target="_blank" rel="noopener">$1</a>');
    html = html.replace(headingRe, (_m, hashes, content) => {
      const level = hashes.length;
      return `<h${level}>${content}</h${level}>`;
    });

    const lines = html.split("\n");
    const out = [];
    let inList = false;
    let listTag = null;
    let listType = null;

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      const ulMatch = line.match(/^[\s]*[-*]\s+(.*)$/);
      const olMatch = line.match(/^\s*\d+\.\s+(.*)$/);

      if (ulMatch) {
        if (!inList || listType !== "ul") {
          if (inList) out.push(`</${listTag}>`);
          out.push("<ul>");
          inList = true;
          listTag = "ul";
          listType = "ul";
        }
        out.push(`<li>${ulMatch[1]}</li>`);
      } else if (olMatch) {
        if (!inList || listType !== "ol") {
          if (inList) out.push(`</${listTag}>`);
          out.push("<ol>");
          inList = true;
          listTag = "ol";
          listType = "ol";
        }
        out.push(`<li>${olMatch[1]}</li>`);
      } else {
        if (inList) { out.push(`</${listTag}>`); inList = false; listTag = null; listType = null; }
        if (line.trim() === "") {
          out.push("");
        } else if (line.match(/^<h[1-6]/)) {
          out.push(line);
        } else {
          out.push(`<p>${line}</p>`);
        }
      }
    }
    if (inList) out.push(`</${listTag}>`);
    return out.join("\n");
  }

  // ── Auth state ──────────────────────────────────────────────
  let authToken = localStorage.getItem("auth_token");
  let currentUser = null;
  let userApiKeys = {};
  let quotaState = {
    token_limit: null,
    tokens_used: null,
    tokens_remaining: null,
    quota_exhausted: false,
    has_byok: false,
    billing_mode: "platform",
  };

  function setAuth(token, username) {
    authToken = token;
    currentUser = username;
    if (token) localStorage.setItem("auth_token", token);
    else localStorage.removeItem("auth_token");
  }

  function authHeaders() {
    return authToken ? { Authorization: `Bearer ${authToken}` } : {};
  }

  async function checkAuth() {
    if (!authToken) return false;
    try {
      const r = await fetch("/api/auth/me", { headers: authHeaders() });
      if (!r.ok) { setAuth(null, null); return false; }
      const data = await r.json();
      currentUser = data.username;
      return true;
    } catch {
      setAuth(null, null);
      return false;
    }
  }

  // ── DOM refs ────────────────────────────────────────────────
  const loginOverlay = document.getElementById("loginOverlay");
  const loginForm = document.getElementById("loginForm");
  const loginUsername = document.getElementById("loginUsername");
  const loginPassword = document.getElementById("loginPassword");
  const loginError = document.getElementById("loginError");
  const loginBtn = loginForm?.querySelector(".login-btn");

  const chatMessages = document.getElementById("chatMessages");
  const chatForm = document.getElementById("chatForm");
  const chatInput = document.getElementById("chatInput");
  const sendButton = document.getElementById("sendButton");
  const responseMode = document.getElementById("responseMode");
  const personaSelect = document.getElementById("personaSelect");
  const personaField = document.getElementById("personaField");
  const scenarioLockedLabel = document.getElementById("scenarioLockedLabel");
  const newChatBackdrop = document.getElementById("newChatBackdrop");
  const newChatScenarioSelect = document.getElementById("newChatScenarioSelect");
  const newChatCancel = document.getElementById("newChatCancel");
  const newChatStart = document.getElementById("newChatStart");
  const llmModelRow = document.getElementById("llmModelRow");
  const llmModelSelect = document.getElementById("llmModelSelect");
  const llmModelHint = document.getElementById("llmModelHint");
  const LLM_CHOICE_STORAGE_KEY = "sellm_llm_choice";
  let selectedLlmChoice = null;
  let yamlScenarios = [];
  let lockedScenarioSlug = null;
  const conversationList = document.getElementById("conversationList");
  const newConversationBtn = document.getElementById("newConversationBtn");
  const settingsBtn = document.getElementById("settingsBtn");
  const logoutBtn = document.getElementById("logoutBtn");
  const sideNav = document.getElementById("sideNav");
  const sideNavToggle = document.getElementById("sideNavToggle");
  const sideNavClose = document.getElementById("sideNavClose");
  const sideNavBackdrop = document.getElementById("sideNavBackdrop");
  const controlsPane = document.getElementById("controlsPane");
  const controlsPaneToggle = document.getElementById("controlsPaneToggle");
  const controlsPaneClose = document.getElementById("controlsPaneClose");
  const MOBILE_NAV_MQ = window.matchMedia("(max-width: 768px)");
  const WELCOME_HTML = `Hi! I'm a stakeholder on this project. I'm not very technical, so I might not use all the right terminology - that's just how I talk about things.<br><br><strong>Your task:</strong> Ask me questions to gather requirements, then formalize what I tell you into proper requirements documentation.<br><br>Start with <strong>+ New chat</strong> and pick a scenario (locked for that chat). Switch personas, mode, and model from the right panel anytime.`;
  const settingsBackdrop = document.getElementById("settingsBackdrop");
  const settingsForm = document.getElementById("settingsForm");
  const settingsCancel = document.getElementById("settingsCancel");
  const settingsDismiss = document.getElementById("settingsDismiss");
  const settingsStatus = document.getElementById("settingsStatus");
  const settingsProvidersContainer = document.getElementById("settingsProvidersContainer");

  const reflectionRow = document.getElementById("reflectionRow");
  const reflectBtn = document.getElementById("reflectBtn");
  const viewReflectionThreadsBtn = document.getElementById("viewReflectionThreadsBtn");
  const reflectionBusyHint = document.getElementById("reflectionBusyHint");
  const reflectionBackdrop = document.getElementById("reflectionBackdrop");
  const reflectionNotes = document.getElementById("reflectionNotes");
  const reflectionJson = document.getElementById("reflectionJson");
  const reflectionApply = document.getElementById("reflectionApply");
  const reflectionCancel = document.getElementById("reflectionCancel");
  const reflectionStatus = document.getElementById("reflectionStatus");
  const reflectionThreadList = document.getElementById("reflectionThreadList");
  const reflectionChatMessages = document.getElementById("reflectionChatMessages");
  const reflectionChatInput = document.getElementById("reflectionChatInput");
  const reflectionSendBtn = document.getElementById("reflectionSendBtn");

  const conversationHistory = [];
  let currentConversationId = null;
  let tweakModeEnabled = false;
  let currentReflectionThreadId = null;
  let reflectionThreads = [];
  const REFLECT_BTN_LABEL = "Reflect on session";
  const REFLECT_SEND_LABEL = "Send";

  // ── Init ────────────────────────────────────────────────────
  async function init() {
    const authed = await checkAuth();
    if (authed) {
      showApp();
      await loadUserConfig();
      await refreshQuotaFromMe();
    } else {
      showLogin();
    }
    loadRuntimeConfig();
    loadConversations();
    await loadYamlScenarios();
    applyLockedScenario(null);
    bindEvents();
    chatInput?.focus();
  }

  function populateScenarioSelect(selectEl, preferredSlug) {
    if (!selectEl) return;
    selectEl.innerHTML = "";
    const excelOpt = document.createElement("option");
    excelOpt.value = "excel";
    excelOpt.textContent = "Excel (PowerPay workbook)";
    selectEl.appendChild(excelOpt);
    yamlScenarios.forEach((s) => {
      const opt = document.createElement("option");
      opt.value = s.slug;
      opt.textContent = `${s.title} (${s.slug})`;
      selectEl.appendChild(opt);
    });
    if (preferredSlug && [...selectEl.options].some((o) => o.value === preferredSlug)) {
      selectEl.value = preferredSlug;
    } else if (yamlScenarios.length) {
      selectEl.value = yamlScenarios[0].slug;
    } else {
      selectEl.value = "excel";
    }
  }

  async function loadYamlScenarios() {
    try {
      const r = await fetch("/api/scenarios", { headers: authHeaders() });
      if (!r.ok) return;
      yamlScenarios = await r.json();
      populateScenarioSelect(newChatScenarioSelect, yamlScenarios[0]?.slug);
      if (lockedScenarioSlug) applyLockedScenario(lockedScenarioSlug);
    } catch (e) {
      console.error("Failed to load YAML scenarios", e);
    }
  }

  function isExcelScenario(slug) {
    return !slug || slug === "excel" || slug === "__excel__" || slug === "powerpay";
  }

  function scenarioDisplayName(slug) {
    if (isExcelScenario(slug)) return "Excel (PowerPay workbook)";
    const scen = yamlScenarios.find((s) => s.slug === slug);
    return scen ? `${scen.title}` : slug;
  }

  function fillPersonaOptions(slug, preferredPersona) {
    if (!personaSelect) return;
    personaSelect.innerHTML = "";
    if (isExcelScenario(slug)) {
      personaSelect.innerHTML = '<option value="">(Excel — no persona)</option>';
      personaSelect.disabled = true;
      if (personaField) personaField.classList.add("hidden");
      return;
    }
    if (personaField) personaField.classList.remove("hidden");
    personaSelect.disabled = false;
    const scen = yamlScenarios.find((s) => s.slug === slug);
    const personas = scen?.personas || [];
    if (!personas.length) {
      personaSelect.innerHTML = '<option value="">No personas</option>';
      return;
    }
    personas.forEach((p) => {
      const opt = document.createElement("option");
      opt.value = p.id;
      opt.textContent = p.display_name || p.id;
      if (p.role) opt.title = p.role;
      personaSelect.appendChild(opt);
    });
    if (preferredPersona && [...personaSelect.options].some((o) => o.value === preferredPersona)) {
      personaSelect.value = preferredPersona;
    }
  }

  function applyLockedScenario(slug) {
    lockedScenarioSlug = slug || null;
    if (!scenarioLockedLabel) return;
    if (!lockedScenarioSlug) {
      scenarioLockedLabel.innerHTML = `No chat yet<span class="scenario-locked-meta">Chosen when you start a new chat</span>`;
      fillPersonaOptions("excel");
      return;
    }
    const name = scenarioDisplayName(lockedScenarioSlug);
    const meta = isExcelScenario(lockedScenarioSlug)
      ? "Locked for this chat"
      : `Locked · ${lockedScenarioSlug}`;
    scenarioLockedLabel.innerHTML = `${name}<span class="scenario-locked-meta">${meta}</span>`;
    fillPersonaOptions(lockedScenarioSlug);
  }

  // ── Login / Logout ──────────────────────────────────────────
  function showLogin() {
    if (loginOverlay) loginOverlay.classList.remove("hidden");
  }

  function showApp() {
    if (loginOverlay) loginOverlay.classList.add("hidden");
  }

  function isMobileNav() {
    return MOBILE_NAV_MQ.matches;
  }

  function syncBackdrop() {
    const anyOpen = Boolean(
      (sideNav && sideNav.classList.contains("open")) ||
      (controlsPane && controlsPane.classList.contains("open"))
    );
    if (!sideNavBackdrop) return;
    if (anyOpen) {
      sideNavBackdrop.classList.add("visible");
      sideNavBackdrop.setAttribute("aria-hidden", "false");
    } else {
      sideNavBackdrop.classList.remove("visible");
      sideNavBackdrop.setAttribute("aria-hidden", "true");
    }
  }

  function openSideNav() {
    if (!sideNav) return;
    closeControlsPane({ skipBackdrop: true });
    sideNav.classList.add("open");
    document.body.classList.add("side-nav-open");
    if (sideNavToggle) sideNavToggle.setAttribute("aria-expanded", "true");
    syncBackdrop();
  }

  function closeSideNav() {
    if (!sideNav) return;
    sideNav.classList.remove("open");
    document.body.classList.remove("side-nav-open");
    if (sideNavToggle) sideNavToggle.setAttribute("aria-expanded", "false");
    syncBackdrop();
  }

  function openControlsPane() {
    if (!controlsPane) return;
    closeSideNav();
    controlsPane.classList.add("open");
    document.body.classList.add("controls-pane-open");
    if (controlsPaneToggle) controlsPaneToggle.setAttribute("aria-expanded", "true");
    syncBackdrop();
  }

  function closeControlsPane(opts = {}) {
    if (!controlsPane) return;
    controlsPane.classList.remove("open");
    document.body.classList.remove("controls-pane-open");
    if (controlsPaneToggle) controlsPaneToggle.setAttribute("aria-expanded", "false");
    if (!opts.skipBackdrop) syncBackdrop();
  }

  function openNewChatModal() {
    populateScenarioSelect(newChatScenarioSelect, yamlScenarios[0]?.slug || "excel");
    if (!newChatBackdrop) return;
    newChatBackdrop.classList.add("visible");
    newChatBackdrop.setAttribute("aria-hidden", "false");
    newChatScenarioSelect?.focus();
  }

  function closeNewChatModal() {
    if (!newChatBackdrop) return;
    newChatBackdrop.classList.remove("visible");
    newChatBackdrop.setAttribute("aria-hidden", "true");
  }

  async function startNewChatWithScenario() {
    const slug = newChatScenarioSelect?.value || "excel";
    if (newChatStart) newChatStart.disabled = true;
    try {
      const r = await fetch("/api/conversations", {
        method: "POST",
        headers: { ...authHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify({ scenario_slug: slug }),
      });
      if (!r.ok) {
        let detail = "Could not create chat";
        try {
          const err = await r.json();
          detail = err.detail || detail;
        } catch (_) { /* ignore */ }
        throw new Error(detail);
      }
      const data = await r.json();
      closeNewChatModal();
      closeSideNav();
      await loadConversations();
      await openConversation(data.id);
      chatInput?.focus();
    } catch (e) {
      window.alert(e?.message || "Could not create chat");
    } finally {
      if (newChatStart) newChatStart.disabled = false;
    }
  }

  async function doLogin(username, password) {
    if (loginBtn) loginBtn.disabled = true;
    if (loginError) loginError.hidden = true;
    try {
      const r = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      const data = await r.json();
      if (!r.ok) {
        if (loginError) { loginError.textContent = data.detail || "Login failed"; loginError.hidden = false; }
        return;
      }
      setAuth(data.token, data.username);
      applyQuotaState(data);
      showApp();
      await loadUserConfig();
      await refreshQuotaFromMe();
      loadRuntimeConfig();
      loadConversations();
    } catch {
      if (loginError) { loginError.textContent = "Network error"; loginError.hidden = false; }
    } finally {
      if (loginBtn) loginBtn.disabled = false;
    }
  }

  function applyQuotaState(data) {
    if (!data || typeof data !== "object") return;
    quotaState = {
      token_limit: data.token_limit ?? quotaState.token_limit,
      tokens_used: data.tokens_used ?? quotaState.tokens_used,
      tokens_remaining: data.tokens_remaining ?? quotaState.tokens_remaining,
      quota_exhausted: Boolean(data.quota_exhausted ?? (data.billing === "byok" && data.tokens_remaining === 0)),
      has_byok: Boolean(data.has_byok ?? Object.values(userApiKeys).some((k) => k.has_key)),
      billing_mode: data.billing || data.billing_mode || quotaState.billing_mode || "platform",
    };
    renderQuotaBanner();
  }

  function _formatTokenCount(n) {
    const v = Number(n) || 0;
    if (v >= 1000) return `${(v / 1000).toFixed(v >= 10000 ? 0 : 1)}k`;
    return String(v);
  }

  function renderQuotaBanner() {
    const meter = document.getElementById("budgetMeter");
    const fill = document.getElementById("budgetMeterFill");
    const bar = document.getElementById("budgetMeterBar");
    const stats = document.getElementById("budgetMeterStats");
    const pctEl = document.getElementById("budgetMeterPct");
    const badge = document.getElementById("budgetMeterBadge");
    const hint = document.getElementById("budgetMeterHint");
    const settingsHint = document.getElementById("settingsQuotaHint");
    if (!meter || !fill) return;

    const limit = Number(quotaState.token_limit);
    const used = Number(quotaState.tokens_used) || 0;
    const remaining = quotaState.tokens_remaining == null
      ? (Number.isFinite(limit) ? Math.max(0, limit - used) : null)
      : Number(quotaState.tokens_remaining);
    const hasByok = quotaState.has_byok || Object.values(userApiKeys).some((k) => k.has_key);
    const onByok = quotaState.billing_mode === "byok" || quotaState.quota_exhausted;

    if (!Number.isFinite(limit) || limit <= 0) {
      meter.classList.remove("visible");
      meter.hidden = true;
      if (settingsHint) settingsHint.style.display = "none";
      return;
    }

    meter.hidden = false;
    meter.classList.add("visible");

    const pctUsed = Math.min(100, Math.max(0, (used / limit) * 100));
    const pctLeft = Math.max(0, 100 - pctUsed);
    fill.style.width = `${pctUsed}%`;
    if (bar) {
      bar.setAttribute("aria-valuenow", String(Math.round(pctUsed)));
      bar.setAttribute("aria-valuetext", `${Math.round(pctUsed)}% of shared budget used`);
    }
    if (pctEl) pctEl.textContent = `${Math.round(pctUsed)}% used`;
    if (stats) {
      stats.textContent = onByok && hasByok
        ? `Pool exhausted · ${_formatTokenCount(used)} / ${_formatTokenCount(limit)}`
        : `${_formatTokenCount(remaining)} left · ${_formatTokenCount(used)} / ${_formatTokenCount(limit)} used`;
    }

    let level = "ok";
    if (onByok && hasByok) level = "byok";
    else if (remaining <= 0 || pctUsed >= 100) level = "empty";
    else if (pctLeft <= 15) level = "low";
    else if (pctLeft <= 35) level = "warn";
    meter.dataset.level = level;

    if (badge) {
      badge.className = "budget-meter-badge";
      if (onByok && hasByok) {
        badge.textContent = "Your key";
        badge.classList.add("pool");
      } else if (remaining <= 0) {
        badge.textContent = "Budget out";
        badge.classList.add("danger");
      } else if (pctLeft <= 35) {
        badge.textContent = "Running low";
        badge.classList.add("warn");
      } else {
        badge.textContent = "Shared pool";
        badge.classList.add("pool");
      }
    }

    if (hint) {
      if (onByok && hasByok) {
        hint.innerHTML = "Shared interview budget used up — continuing on <strong>your API key</strong>.";
      } else if (remaining <= 0) {
        hint.innerHTML = `Budget used up. <button type="button" id="budgetOpenSettings">Add your API key</button> to keep interviewing.`;
        const btn = document.getElementById("budgetOpenSettings");
        if (btn) btn.onclick = () => openSettings();
      } else if (pctLeft <= 35) {
        hint.textContent = "Budget running low — enough for wrapping up base requirements, then add a key if you need more.";
      } else {
        hint.textContent = "Sized for one focused requirements interview. Usage updates after each reply.";
      }
    }

    if (settingsHint) {
      if (remaining <= 0 && !hasByok) {
        settingsHint.style.display = "block";
        settingsHint.style.color = "#b45309";
        settingsHint.textContent = "Shared budget exhausted — save a key below to continue chatting.";
      } else if (onByok && hasByok) {
        settingsHint.style.display = "block";
        settingsHint.style.color = "#047857";
        settingsHint.textContent = "Using your saved API key (shared pool exhausted).";
      } else {
        settingsHint.style.display = "none";
      }
    }
  }

  async function refreshQuotaFromMe() {
    try {
      const r = await fetch("/api/auth/me", { headers: authHeaders() });
      if (!r.ok) return;
      const data = await r.json();
      applyQuotaState(data);
    } catch (_) {
      /* ignore */
    }
  }

  async function doLogout() {
    await fetch("/api/auth/logout", { method: "POST", headers: authHeaders() });
    setAuth(null, null);
    currentUser = null;
    showLogin();
    resetConversationUi();
    conversationList.innerHTML = "";
    if (loginUsername) loginUsername.value = "";
    if (loginPassword) loginPassword.value = "";
    if (loginError) loginError.hidden = true;
    userApiKeys = {};
  }

  // ── User API Config ─────────────────────────────────────────
  async function loadUserConfig() {
    try {
      const r = await fetch("/api/user/config", { headers: authHeaders() });
      if (!r.ok) return;
      const data = await r.json();
      userApiKeys = {};
      if (Array.isArray(data.keys)) {
        for (const entry of data.keys) {
          userApiKeys[entry.provider] = {
            has_key: entry.has_key,
            api_key_hint: entry.api_key_hint,
            api_key_masked: entry.api_key_masked || entry.api_key_hint || "",
            base_url: entry.base_url || "",
          };
        }
      }
    } catch { /* ignore */ }
  }

  function _gatherProviderKeys() {
    const keys = [];
    const container = settingsProvidersContainer;
    if (!container) return keys;
    const rows = container.querySelectorAll(".settings-provider-row");
    for (const row of rows) {
      const provider = row.dataset.provider;
      const apiKeyInput = row.querySelector(".settings-provider-key");
      const baseUrlInput = row.querySelector(".settings-provider-url");
      if (provider && apiKeyInput) {
        const val = (apiKeyInput.value || "").trim();
        const masked = (apiKeyInput.dataset.masked || "").trim();
        let api_key = val;
        if (masked && val === masked) {
          api_key = "__UNCHANGED__";
        }
        keys.push({
          provider: provider,
          api_key,
          base_url: baseUrlInput ? baseUrlInput.value || null : null,
        });
      }
    }
    return keys;
  }

  async function saveAllUserConfigs(event) {
    if (event) event.preventDefault();
    if (settingsStatus) settingsStatus.textContent = "Saving…";
    const keys = _gatherProviderKeys();
    try {
      const r = await fetch("/api/user/config", {
        method: "POST",
        headers: { ...authHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify({ keys }),
      });
      if (!r.ok) {
        let detail = "Save failed";
        try { const d = await r.json(); detail = d.detail || detail; } catch {}
        if (settingsStatus) settingsStatus.textContent = detail;
        return;
      }
      if (settingsStatus) settingsStatus.textContent = "Saved! Your API keys will be used when the shared budget runs out (or when you select that provider).";
      await loadUserConfig();
      await refreshQuotaFromMe();
      loadRuntimeConfig();
    } catch {
      if (settingsStatus) settingsStatus.textContent = "Network error";
    }
  }

  const PROVIDER_CONFIGS = [
    { provider: "openai", label: "OpenAI", keyPlaceholder: "sk-...", urlPlaceholder: "https://api.openai.com/v1", defaultUrl: "https://api.openai.com/v1", keyUrl: "https://platform.openai.com/api-keys" },
    { provider: "anthropic", label: "Anthropic", keyPlaceholder: "sk-ant-...", urlPlaceholder: "https://api.anthropic.com/v1", defaultUrl: "https://api.anthropic.com/v1", keyUrl: "https://console.anthropic.com/settings/keys" },
    { provider: "gemini", label: "Google Gemini (free tier)", keyPlaceholder: "AI...", urlPlaceholder: "https://generativelanguage.googleapis.com/v1beta/openai/v1", defaultUrl: "https://generativelanguage.googleapis.com/v1beta/openai/v1", keyUrl: "https://aistudio.google.com/apikey" },
    { provider: "groq", label: "Groq (free tier)", keyPlaceholder: "gsk_...", urlPlaceholder: "https://api.groq.com/openai/v1", defaultUrl: "https://api.groq.com/openai/v1", keyUrl: "https://console.groq.com/keys" },
    { provider: "openrouter", label: "OpenRouter", keyPlaceholder: "sk-or-...", urlPlaceholder: "https://openrouter.ai/api/v1", defaultUrl: "https://openrouter.ai/api/v1", keyUrl: "https://openrouter.ai/keys" },
  ];

  function renderSettingsProviders() {
    if (!settingsProvidersContainer) return;
    settingsProvidersContainer.innerHTML = "";
    for (const pc of PROVIDER_CONFIGS) {
      const info = userApiKeys[pc.provider] || { has_key: false, api_key_hint: null, api_key_masked: "", base_url: "" };
      const masked = info.api_key_masked || info.api_key_hint || "";
      const row = document.createElement("div");
      row.className = "settings-provider-row";
      row.dataset.provider = pc.provider;
      row.innerHTML = `
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px;">
          <label style="font-size:12px;font-weight:600;color:#6b7280;">
            ${pc.label}
            ${info.has_key ? '<span style="color:#10b981;font-weight:400;margin-left:6px;">&#10003;</span>' : ""}
          </label>
          <a href="${pc.keyUrl}" target="_blank" rel="noopener" style="font-size:11px;color:#667eea;text-decoration:none;">Get key</a>
        </div>
        <input type="password" class="settings-provider-key" placeholder="${info.has_key ? "Update key" : pc.keyPlaceholder}" value="${masked.replace(/"/g, "&quot;")}" data-masked="${masked.replace(/"/g, "&quot;")}" autocomplete="off" style="width:100%;padding:8px 12px;border:1px solid #d1d5db;border-radius:8px;margin-bottom:6px;font-size:14px;box-sizing:border-box;font-family:inherit;" />
        <input type="text" class="settings-provider-url" placeholder="${pc.urlPlaceholder}" value="${info.base_url || pc.defaultUrl}" style="width:100%;padding:8px 12px;border:1px solid #d1d5db;border-radius:8px;font-size:14px;box-sizing:border-box;font-family:inherit;color:#6b7280;" />
      `;
      settingsProvidersContainer.appendChild(row);
    }
  }

  function openSettings() {
    if (!settingsBackdrop) return;
    closeSideNav();
    renderSettingsProviders();
    if (settingsStatus) settingsStatus.textContent = "";
    settingsBackdrop.classList.add("visible");
    settingsBackdrop.setAttribute("aria-hidden", "false");
  }

  function closeSettings() {
    if (!settingsBackdrop) return;
    settingsBackdrop.classList.remove("visible");
    settingsBackdrop.setAttribute("aria-hidden", "true");
    if (settingsStatus) settingsStatus.textContent = "";
  }

  // ── Config ──────────────────────────────────────────────────
  async function loadRuntimeConfig() {
    try {
      const response = await fetch("/api/config", { headers: authHeaders() });
      if (!response.ok) return;
      const config = await response.json();
      tweakModeEnabled = Boolean(config.tweak_mode_enabled);
      if (reflectionRow) {
        reflectionRow.style.display = tweakModeEnabled ? "flex" : "none";
      }
      populateLlmModelSelect(config);
    } catch {
      tweakModeEnabled = false;
      if (reflectionRow) reflectionRow.style.display = "none";
      if (llmModelRow) llmModelRow.classList.add("hidden");
    }
  }

  // ── Reflection helpers ──────────────────────────────────────
  function lockReflectionWorkspace() {
    if (reflectionChatInput) reflectionChatInput.disabled = true;
    if (reflectionSendBtn) reflectionSendBtn.disabled = true;
    if (reflectionApply) reflectionApply.disabled = true;
  }

  function unlockReflectionWorkspace() {
    if (reflectionChatInput) reflectionChatInput.disabled = false;
    if (reflectionSendBtn) { reflectionSendBtn.disabled = false; reflectionSendBtn.textContent = REFLECT_SEND_LABEL; }
    if (reflectionApply) reflectionApply.disabled = false;
  }

  function setReflectRowBusy(isBusy, hintText = "") {
    if (reflectBtn) {
      reflectBtn.disabled = isBusy;
      reflectBtn.textContent = isBusy ? "Starting…" : REFLECT_BTN_LABEL;
      if (isBusy) reflectBtn.setAttribute("aria-busy", "true");
      else reflectBtn.removeAttribute("aria-busy");
    }
    if (viewReflectionThreadsBtn) viewReflectionThreadsBtn.disabled = isBusy;
    if (reflectionBusyHint) {
      reflectionBusyHint.hidden = !isBusy;
      reflectionBusyHint.textContent = isBusy ? hintText : "";
    }
  }

  function populateLlmModelSelect(config) {
    if (!llmModelSelect || !llmModelRow) return;
    const choices = Array.isArray(config.llm_choices) ? config.llm_choices : [];
    const enabled = Boolean(config.llm_model_switcher_enabled);
    llmModelRow.classList.toggle("hidden", !enabled);
    if (!enabled) {
      selectedLlmChoice = config.llm_default_choice || null;
      return;
    }
    const saved = localStorage.getItem(LLM_CHOICE_STORAGE_KEY);
    const defaultId = config.llm_default_choice || choices.find((c) => c.available !== false)?.id || choices[0]?.id;
    const validIds = new Set(choices.map((c) => c.id));
    const byId = Object.fromEntries(choices.map((c) => [c.id, c]));
    let pick = saved && validIds.has(saved) ? saved : defaultId;
    if (!validIds.has(pick) || byId[pick]?.available === false) {
      pick = defaultId;
      if (byId[pick]?.available === false) {
        pick = choices.find((c) => c.available !== false)?.id || defaultId;
      }
      try {
        localStorage.setItem(LLM_CHOICE_STORAGE_KEY, pick);
      } catch (_) {
        /* ignore */
      }
    }
    llmModelSelect.innerHTML = "";
    choices.forEach((c) => {
      const opt = document.createElement("option");
      opt.value = c.id;
      opt.textContent = c.label + (c.available === false ? " (unavailable)" : "");
      opt.disabled = c.available === false;
      llmModelSelect.appendChild(opt);
    });
    llmModelSelect.value = pick;
    selectedLlmChoice = pick;
    const providers = config.llm_providers || {};
    const hints = [];
    if (providers.openai) hints.push("OpenAI");
    if (providers.anthropic) hints.push("Anthropic");
    if (providers.gemini) hints.push("Gemini");
    if (providers.groq) hints.push("Groq");
    if (providers.openrouter) hints.push("OpenRouter");
    if (providers.ollama) hints.push("Ollama");
    if (llmModelHint) {
      llmModelHint.textContent = hints.length
        ? `Configured: ${hints.join(", ")}. Choice applies to the next message.`
        : "";
    }
  }

  if (llmModelSelect) {
    llmModelSelect.addEventListener("change", () => {
      selectedLlmChoice = llmModelSelect.value;
      localStorage.setItem(LLM_CHOICE_STORAGE_KEY, selectedLlmChoice);
    });
  }

  function openReflectionModal(data = {}) {
    if (!reflectionBackdrop || !reflectionNotes || !reflectionJson) return;
    if (data.loading) {
      reflectionNotes.textContent = data.loadingMessage || "Starting reflection…";
      reflectionJson.value = "";
      if (reflectionStatus) reflectionStatus.textContent = data.statusHint || "In progress — please wait.";
      renderReflectionMessages(data.prepMessages || [{ role: "assistant", content: "Working… Do not click Reflect again." }]);
    } else if (data.reflection) {
      reflectionNotes.textContent = data.reflection?.performance_notes || "(no notes)";
      reflectionJson.value = JSON.stringify(data.reflection || {}, null, 2);
    }
    if (!data.loading && data.mode_used && reflectionStatus) reflectionStatus.textContent = `Proposed via LLM mode: ${data.mode_used}.`;
    reflectionBackdrop.classList.add("visible");
    reflectionBackdrop.setAttribute("aria-hidden", "false");
  }

  function closeReflectionModal() {
    if (!reflectionBackdrop) return;
    reflectionBackdrop.classList.remove("visible");
    reflectionBackdrop.setAttribute("aria-hidden", "true");
    if (reflectionJson) reflectionJson.value = "";
    if (reflectionStatus) reflectionStatus.textContent = "";
    if (reflectionChatInput) reflectionChatInput.value = "";
    unlockReflectionWorkspace();
  }

  function renderReflectionMessages(messages = []) {
    if (!reflectionChatMessages) return;
    reflectionChatMessages.innerHTML = "";
    messages.forEach((m) => {
      const row = document.createElement("div");
      row.className = "reflection-chat-msg";
      const role = m.role === "assistant" ? "Assistant" : "You";
      row.innerHTML = `<strong>${role}:</strong> ${String(m.content || "").replace(/\n/g, "<br>")}`;
      reflectionChatMessages.appendChild(row);
    });
    reflectionChatMessages.scrollTop = reflectionChatMessages.scrollHeight;
  }

  function renderReflectionThreadList() {
    if (!reflectionThreadList) return;
    reflectionThreadList.innerHTML = "";
    reflectionThreads.forEach((t) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "reflection-thread-item";
      if (t.id === currentReflectionThreadId) btn.classList.add("active");
      btn.dataset.threadId = t.id;
      btn.textContent = t.title || t.id;
      reflectionThreadList.appendChild(btn);
    });
  }

  async function loadReflectionThreadsForConversation(conversationId) {
    if (!conversationId || !tweakModeEnabled) {
      reflectionThreads = [];
      currentReflectionThreadId = null;
      renderReflectionThreadList();
      return;
    }
    try {
      const r = await fetch(`/api/conversations/${conversationId}/reflections`, { headers: authHeaders() });
      if (!r.ok) return;
      reflectionThreads = await r.json();
      renderReflectionThreadList();
    } catch (e) { console.error(e); }
  }

  async function openReflectionThread(threadId) {
    if (!threadId) return;
    try {
      const r = await fetch(`/api/reflections/${threadId}`, { headers: authHeaders() });
      if (!r.ok) throw new Error("Could not load reflection thread");
      const data = await r.json();
      currentReflectionThreadId = data.id;
      unlockReflectionWorkspace();
      renderReflectionThreadList();
      renderReflectionMessages(data.messages || []);
      reflectionJson.value = data.latest_draft_json || "{}";
      reflectionNotes.textContent = "Refine this draft in the thread chat, then apply.";
      openReflectionModal();
    } catch (e) { console.error(e); window.alert("Could not load reflection thread."); }
  }

  async function openReflectionsForCurrentConversation() {
    if (!tweakModeEnabled) return;
    if (!currentConversationId) { window.alert("Select a conversation from the list first."); return; }
    if (viewReflectionThreadsBtn) viewReflectionThreadsBtn.disabled = true;
    try {
      await loadReflectionThreadsForConversation(currentConversationId);
      if (reflectionThreads.length === 0) {
        currentReflectionThreadId = null;
        renderReflectionThreadList();
        renderReflectionMessages([]);
        reflectionNotes.textContent = "No reflection threads yet. Use Reflect after at least one exchange.";
        reflectionJson.value = "{}";
        if (reflectionStatus) reflectionStatus.textContent = "";
        unlockReflectionWorkspace();
        openReflectionModal({});
      } else {
        await openReflectionThread(reflectionThreads[0].id);
      }
    } catch (e) { console.error(e); window.alert("Could not load reflection threads."); }
    finally { if (viewReflectionThreadsBtn) viewReflectionThreadsBtn.disabled = false; }
  }

  async function runReflection() {
    if (!reflectBtn) return;
    if (!currentConversationId) { window.alert("Open a saved conversation first."); return; }
    if (conversationHistory.length < 2) { window.alert("Have at least one full exchange before reflecting."); return; }
    setReflectRowBusy(true, "Reflection in progress — please wait.");
    lockReflectionWorkspace();
    openReflectionModal({ loading: true, loadingMessage: "Starting reflection. The meta-LLM is analyzing your conversation — this can take up to a minute." });
    try {
      const r = await fetch(`/api/conversations/${currentConversationId}/reflections/start`, { method: "POST", headers: { ...authHeaders(), "Content-Type": "application/json" } });
      let data = {};
      try { data = await r.json(); } catch { data = {}; }
      if (!r.ok) { closeReflectionModal(); window.alert(typeof data.detail === "string" ? data.detail : "Reflection failed"); return; }
      currentReflectionThreadId = data.thread?.id || null;
      await loadReflectionThreadsForConversation(currentConversationId);
      unlockReflectionWorkspace();
      renderReflectionMessages(data.thread?.messages || []);
      reflectionJson.value = JSON.stringify(data.reflection || {}, null, 2);
      reflectionNotes.textContent = "Initial draft generated. Continue in thread chat.";
      openReflectionModal(data);
    } catch (e) { console.error(e); closeReflectionModal(); window.alert("Reflection request failed."); }
    finally { setReflectRowBusy(false); unlockReflectionWorkspace(); }
  }

  async function applyReflection() {
    if (!reflectionJson || !reflectionApply) return;
    let reflection;
    try { reflection = JSON.parse(reflectionJson.value); } catch { if (reflectionStatus) reflectionStatus.textContent = "Invalid JSON — fix before applying."; return; }
    reflectionApply.disabled = true;
    const prev = reflectionApply.textContent;
    reflectionApply.textContent = "Applying…";
    try {
      if (!currentReflectionThreadId) { reflectionStatus.textContent = "No reflection thread selected."; return; }
      const r = await fetch(`/api/reflections/${currentReflectionThreadId}/apply`, { method: "POST", headers: { ...authHeaders(), "Content-Type": "application/json" }, body: JSON.stringify({ reflection }) });
      let data = {};
      try { data = await r.json(); } catch { data = {}; }
      if (!r.ok) { reflectionStatus.textContent = typeof data.detail === "string" ? data.detail : "Apply failed"; return; }
      const changes = data.changes || [];
      reflectionStatus.textContent = changes.length ? `Saved: ${changes.join("; ")}` : "Saved (file may still be updated).";
      if (data.thread?.messages) renderReflectionMessages(data.thread.messages);
    } catch (e) { console.error(e); reflectionStatus.textContent = "Apply request failed."; }
    finally { reflectionApply.disabled = false; reflectionApply.textContent = prev; }
  }

  async function sendReflectionMessage() {
    if (!currentReflectionThreadId || !reflectionChatInput || !reflectionSendBtn) return;
    const msg = reflectionChatInput.value.trim();
    if (!msg) return;
    reflectionSendBtn.disabled = true;
    reflectionSendBtn.textContent = "Sending…";
    if (reflectionStatus) reflectionStatus.textContent = "Waiting for meta-LLM response…";
    try {
      let draft = {};
      try { draft = JSON.parse(reflectionJson.value || "{}"); } catch { draft = {}; }
      const r = await fetch(`/api/reflections/${currentReflectionThreadId}/chat`, { method: "POST", headers: { ...authHeaders(), "Content-Type": "application/json" }, body: JSON.stringify({ message: msg, reflection: draft }) });
      const data = await r.json();
      if (!r.ok) { reflectionStatus.textContent = typeof data.detail === "string" ? data.detail : "Reflection chat failed"; return; }
      if (data.thread?.messages) renderReflectionMessages(data.thread.messages);
      reflectionNotes.textContent = data.reflection?.performance_notes || "Draft updated.";
      reflectionJson.value = JSON.stringify(data.reflection || {}, null, 2);
      reflectionChatInput.value = "";
      if (reflectionStatus) reflectionStatus.textContent = data.mode_used ? `Updated (mode: ${data.mode_used}).` : "";
    } catch (e) { console.error(e); reflectionStatus.textContent = "Reflection chat request failed."; }
    finally { reflectionSendBtn.disabled = false; reflectionSendBtn.textContent = REFLECT_SEND_LABEL; reflectionChatInput.focus(); }
  }

  // ── Conversations ───────────────────────────────────────────
  function formatConversationMeta(c) {
    let when = "";
    const raw = c.updated_at || c.created_at;
    if (raw) {
      try {
        const d = new Date(raw);
        if (!Number.isNaN(d.getTime())) {
          when = d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
        }
      } catch { /* ignore */ }
    }
    const scen = c.scenario_slug ? scenarioDisplayName(c.scenario_slug) : "";
    if (scen && when) return `${scen} · ${when}`;
    return scen || when;
  }

  function syncListSelection() {
    if (!conversationList) return;
    conversationList.querySelectorAll(".conversation-item").forEach((el) => {
      const match = Boolean(currentConversationId && el.dataset.conversationId === currentConversationId);
      el.classList.toggle("active", match);
      const btn = el.querySelector(".conversation-item-btn");
      if (btn) { const t = btn.querySelector(".conversation-title"); if (t) t.style.fontWeight = match ? "700" : "600"; }
    });
  }

  async function deleteConversation(conversationId) {
    if (!window.confirm("Delete this conversation?")) return;
    try {
      const r = await fetch(`/api/conversations/${conversationId}`, { method: "DELETE", headers: authHeaders() });
      if (!r.ok) throw new Error("Delete failed");
      if (currentConversationId === conversationId) resetConversationUi();
      await loadConversations();
    } catch (e) { console.error("Could not delete:", e); }
  }

  async function loadConversations() {
    try {
      const r = await fetch("/api/conversations", { headers: authHeaders() });
      if (!r.ok) return;
      const conversations = await r.json();
      if (!conversationList) return;
      conversationList.innerHTML = "";
      conversations.forEach((c) => {
        const item = document.createElement("div");
        item.className = "conversation-item";
        item.dataset.conversationId = c.id;
        item.setAttribute("role", "listitem");

        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "conversation-item-btn";
        btn.setAttribute("aria-label", `Open: ${c.title || c.id}`);
        const titleEl = document.createElement("span");
        titleEl.className = "conversation-title";
        titleEl.textContent = c.title || c.id;
        const metaEl = document.createElement("span");
        metaEl.className = "conversation-meta";
        metaEl.textContent = formatConversationMeta(c);
        btn.appendChild(titleEl);
        btn.appendChild(metaEl);

        const del = document.createElement("button");
        del.type = "button";
        del.className = "conversation-delete";
        del.textContent = "×";
        del.setAttribute("aria-label", `Delete: ${c.title || c.id}`);
        del.title = "Delete";
        del.addEventListener("click", (e) => { e.stopPropagation(); deleteConversation(c.id); });

        item.appendChild(btn);
        item.appendChild(del);
        conversationList.appendChild(item);
      });
      syncListSelection();
    } catch (e) { console.error("Could not load conversations:", e); }
  }

  function resetConversationUi() {
    closeSideNav();
    closeControlsPane();
    conversationHistory.length = 0;
    currentConversationId = null;
    applyLockedScenario(null);
    chatMessages.innerHTML = `<div class="message assistant"><div class="message-content">${WELCOME_HTML}</div></div>`;
    syncListSelection();
    loadReflectionThreadsForConversation(currentConversationId);
  }

  async function openConversation(conversationId) {
    if (!conversationId) { resetConversationUi(); return; }
    try {
      const r = await fetch(`/api/conversations/${conversationId}`, { headers: authHeaders() });
      if (!r.ok) throw new Error("Could not load conversation");
      const data = await r.json();
      currentConversationId = data.id;
      applyLockedScenario(data.scenario_slug || "excel");
      conversationHistory.length = 0;
      chatMessages.innerHTML = "";
      if (!data.messages?.length) {
        chatMessages.innerHTML = `<div class="message assistant"><div class="message-content">${WELCOME_HTML}</div></div>`;
      } else {
        data.messages.forEach((m) => { addMessage(m.role, m.content, null, null, null); conversationHistory.push({ role: m.role, content: m.content }); });
      }
      syncListSelection();
      await loadReflectionThreadsForConversation(currentConversationId);
      closeSideNav();
    } catch (e) { console.error(e); }
  }

  // ── Chat ────────────────────────────────────────────────────
  async function submitFeedback(meta, fb, desired = "") {
    return fetch("/api/feedback", { method: "POST", headers: { ...authHeaders(), "Content-Type": "application/json" }, body: JSON.stringify({ prompt: meta?.prompt || "", response: meta?.response || "", feedback: fb, mode_used: meta?.mode || null, desired_response: desired || null }) });
  }

  function formatRoutingBadge(modeUsed, routing, llmUsed) {
    if (!modeUsed) return null;
    const llmPart = llmUsed?.label ? ` · ${llmUsed.label}` : "";
    const labels = {
      vector: "Vector RAG",
      neo4j: "Neo4j RAG",
      direct: "Direct Model",
      compare: "Compare All",
      yaml: "YAML Scenario",
    };
    if (modeUsed === "compare") return `${labels.compare}${llmPart}`;
    if (modeUsed === "direct") return `${labels.direct}${llmPart}`;
    if (modeUsed === "vector" || modeUsed === "neo4j") {
      return `${labels[modeUsed] || modeUsed}${llmPart}`;
    }
    if (modeUsed.startsWith("yaml:")) {
      const parts = modeUsed.split(":");
      const slug = parts[1] || "";
      const persona = parts[2] || "";
      return `YAML Scenario → ${slug}${persona ? ` / ${persona}` : ""}${llmPart}`;
    }
    if (modeUsed.startsWith("hybrid")) {
      const route = routing?.route || modeUsed.split(":")[1] || "";
      const backends = (routing?.backends_used || []).join(" + ");
      return `Hybrid RAG → ${route}${backends ? ` (${backends})` : ""}${llmPart}`;
    }
    return `${modeUsed}${llmPart}`;
  }

  function addMessage(role, content, sources = null, modeUsed = null, meta = null) {
    const div = document.createElement("div");
    div.className = `message ${role}`;
    const cd = document.createElement("div");
    cd.className = "message-content";
    if (role === "assistant") cd.innerHTML = renderMarkdown(content);
    else cd.textContent = content;
    if (role === "assistant" && modeUsed) {
      const badge = document.createElement("div");
      badge.className = "mode-badge";
      badge.textContent =
        formatRoutingBadge(modeUsed, meta?.routing, meta?.llm_used) || `mode: ${modeUsed}`;
      const titleParts = [];
      if (meta?.routing) titleParts.push(JSON.stringify(meta.routing));
      if (meta?.llm_used) titleParts.push(JSON.stringify(meta.llm_used));
      badge.title = titleParts.join("\n");
      cd.prepend(badge);
    }
    if (role === "assistant" && meta?.prompt && tweakModeEnabled) {
      const row = document.createElement("div");
      row.className = "feedback-row";
      const up = document.createElement("button"); up.className = "feedback-btn"; up.type = "button"; up.textContent = "👍 Good";
      const down = document.createElement("button"); down.className = "feedback-btn"; down.type = "button"; down.textContent = "👎 Improve";
      const note = document.createElement("span"); note.className = "feedback-note"; note.textContent = "Help tune responses at runtime.";
      up.onclick = async () => { try { await submitFeedback(meta, "good_response"); note.textContent = "Saved."; } catch { note.textContent = "Error."; } };
      down.onclick = async () => { const fb = window.prompt("How should this improve?"); if (!fb || !fb.trim()) return; const d = window.prompt("Optional: provide a better response.") || ""; try { const r = await submitFeedback(meta, fb.trim(), d.trim()); const ch = (r.changes || []).join("; "); note.textContent = ch ? `Saved: ${ch}` : "Saved."; } catch { note.textContent = "Error."; } };
      row.appendChild(up); row.appendChild(down); row.appendChild(note);
      cd.appendChild(row);
    }
    div.appendChild(cd);
    chatMessages.appendChild(div);
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  function addTypingIndicator() {
    const div = document.createElement("div");
    div.className = "message assistant";
    div.id = "typingIndicator";
    const cd = document.createElement("div");
    cd.className = "message-content";
    cd.innerHTML = '<div class="typing-indicator"><div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div></div>';
    div.appendChild(cd);
    chatMessages.appendChild(div);
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  function removeTypingIndicator() { const el = document.getElementById("typingIndicator"); if (el) el.remove(); }

  async function sendMessage(message) {
    if (!currentConversationId || !lockedScenarioSlug) {
      openNewChatModal();
      return;
    }
    addMessage("user", message);
    conversationHistory.push({ role: "user", content: message });
    chatInput.value = "";
    sendButton.disabled = true;
    addTypingIndicator();
    try {
      const r = await fetch("/api/chat", {
        method: "POST",
        headers: { ...authHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify({
          message,
          conversation_history: conversationHistory,
          response_mode: responseMode.value,
          conversation_id: currentConversationId,
          llm_choice: selectedLlmChoice || llmModelSelect?.value || null,
          scenario_slug: lockedScenarioSlug,
          persona_key: isExcelScenario(lockedScenarioSlug) ? null : (personaSelect?.value || null),
        }),
      });
      if (!r.ok) {
        let detail = "Failed to get response";
        try {
          const errBody = await r.json();
          detail = errBody.detail || detail;
        } catch (_) {
          /* ignore */
        }
        if (r.status === 429) {
          await refreshQuotaFromMe();
          const wantsByok = /api key|token limit|budget/i.test(String(detail));
          if (wantsByok) {
            openSettings();
          }
        }
        throw new Error(detail);
      }
      const data = await r.json();
      removeTypingIndicator();
      applyQuotaState(data);
      addMessage("assistant", data.response, null, data.mode_used || null, {
        prompt: message,
        response: data.response,
        mode: data.mode_used || null,
        routing: data.routing || null,
        billing: data.billing || null,
        llm_used: data.llm_used || null,
      });
      conversationHistory.push({ role: "assistant", content: data.response });
      if (data.conversation_id) { currentConversationId = data.conversation_id; await loadConversations(); await loadReflectionThreadsForConversation(currentConversationId); }
    } catch (e) {
      removeTypingIndicator();
      addMessage("assistant", e?.message || "Sorry, I encountered an error. Please try again.");
      console.error(e);
    }
    finally { sendButton.disabled = false; chatInput.focus(); }
  }

  // ── Event binding ────────────────────────────────────────────
  function bindEvents() {
    if (loginForm) {
      loginForm.addEventListener("submit", (e) => {
        e.preventDefault();
        const u = loginUsername?.value.trim();
        const p = loginPassword?.value.trim();
        if (u && p) doLogin(u, p);
      });
    }
    if (logoutBtn) logoutBtn.addEventListener("click", doLogout);

    if (sideNavToggle) {
      sideNavToggle.addEventListener("click", () => {
        if (sideNav?.classList.contains("open")) closeSideNav();
        else openSideNav();
      });
    }
    if (sideNavClose) sideNavClose.addEventListener("click", closeSideNav);
    if (controlsPaneToggle) {
      controlsPaneToggle.addEventListener("click", () => {
        if (controlsPane?.classList.contains("open")) closeControlsPane();
        else openControlsPane();
      });
    }
    if (controlsPaneClose) controlsPaneClose.addEventListener("click", closeControlsPane);
    if (sideNavBackdrop) {
      sideNavBackdrop.addEventListener("click", () => {
        closeSideNav();
        closeControlsPane();
      });
    }
    if (newChatCancel) newChatCancel.addEventListener("click", closeNewChatModal);
    if (newChatStart) newChatStart.addEventListener("click", startNewChatWithScenario);
    if (newChatBackdrop) {
      newChatBackdrop.addEventListener("click", (e) => {
        if (e.target === newChatBackdrop) closeNewChatModal();
      });
    }
    if (settingsBtn) settingsBtn.addEventListener("click", openSettings);
    if (settingsCancel) settingsCancel.addEventListener("click", closeSettings);
    if (settingsDismiss) settingsDismiss.addEventListener("click", closeSettings);
    if (settingsBackdrop) settingsBackdrop.addEventListener("click", (e) => { if (e.target === settingsBackdrop) closeSettings(); });
    if (settingsForm) {
      settingsForm.addEventListener("submit", (e) => {
        e.preventDefault();
        saveAllUserConfigs();
      });
    }

    if (chatForm) {
      chatForm.addEventListener("submit", (e) => {
        e.preventDefault();
        const msg = chatInput.value.trim();
        if (msg) sendMessage(msg);
      });
    }
    if (conversationList) {
      conversationList.addEventListener("click", (e) => {
        const btn = e.target.closest(".conversation-item-btn");
        if (!btn) return;
        const item = btn.closest(".conversation-item");
        if (item?.dataset.conversationId) openConversation(item.dataset.conversationId);
      });
    }
    if (newConversationBtn) {
      newConversationBtn.addEventListener("click", () => {
        closeSideNav();
        openNewChatModal();
      });
    }

    if (reflectBtn) reflectBtn.addEventListener("click", runReflection);
    if (viewReflectionThreadsBtn) viewReflectionThreadsBtn.addEventListener("click", openReflectionsForCurrentConversation);
    if (reflectionCancel) reflectionCancel.addEventListener("click", closeReflectionModal);
    if (reflectionApply) reflectionApply.addEventListener("click", applyReflection);
    if (reflectionBackdrop) reflectionBackdrop.addEventListener("click", (e) => { if (e.target === reflectionBackdrop) closeReflectionModal(); });
    if (reflectionSendBtn) reflectionSendBtn.addEventListener("click", sendReflectionMessage);
    if (reflectionChatInput) reflectionChatInput.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); sendReflectionMessage(); } });
    if (reflectionThreadList) reflectionThreadList.addEventListener("click", (e) => { const item = e.target.closest(".reflection-thread-item"); if (item?.dataset.threadId) openReflectionThread(item.dataset.threadId); });

    document.addEventListener("keydown", (e) => {
      if (e.key !== "Escape") return;
      if (newChatBackdrop?.classList.contains("visible")) closeNewChatModal();
      else if (sideNav?.classList.contains("open")) closeSideNav();
      else if (controlsPane?.classList.contains("open")) closeControlsPane();
    });
    const onNavMqChange = () => {
      if (!isMobileNav()) {
        closeSideNav();
        closeControlsPane();
      }
    };
    if (typeof MOBILE_NAV_MQ.addEventListener === "function") {
      MOBILE_NAV_MQ.addEventListener("change", onNavMqChange);
    } else if (typeof MOBILE_NAV_MQ.addListener === "function") {
      MOBILE_NAV_MQ.addListener(onNavMqChange);
    }
  }

  // ── Start ───────────────────────────────────────────────────
  init();
})();
