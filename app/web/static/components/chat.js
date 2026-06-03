(() => {
  // ── Auth state ──────────────────────────────────────────────
  let authToken = localStorage.getItem("auth_token");
  let currentUser = null;
  let userApiConfig = { provider: "openai", has_key: false };

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
  const conversationList = document.getElementById("conversationList");
  const newConversationBtn = document.getElementById("newConversationBtn");
  const settingsBtn = document.getElementById("settingsBtn");
  const logoutBtn = document.getElementById("logoutBtn");
  const settingsBackdrop = document.getElementById("settingsBackdrop");
  const settingsForm = document.getElementById("settingsForm");
  const settingsProvider = document.getElementById("settingsProvider");
  const settingsApiKey = document.getElementById("settingsApiKey");
  const settingsBaseUrl = document.getElementById("settingsBaseUrl");
  const settingsCancel = document.getElementById("settingsCancel");
  const settingsStatus = document.getElementById("settingsStatus");

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
    } else {
      showLogin();
    }
    loadRuntimeConfig();
    loadConversations();
    bindEvents();
    chatInput?.focus();
  }

  // ── Login / Logout ──────────────────────────────────────────
  function showLogin() {
    if (loginOverlay) loginOverlay.classList.remove("hidden");
  }

  function showApp() {
    if (loginOverlay) loginOverlay.classList.add("hidden");
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
      showApp();
      await loadUserConfig();
      loadRuntimeConfig();
      loadConversations();
    } catch {
      if (loginError) { loginError.textContent = "Network error"; loginError.hidden = false; }
    } finally {
      if (loginBtn) loginBtn.disabled = false;
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
    userApiConfig = { provider: "openai", has_key: false };
  }

  // ── User API Config ─────────────────────────────────────────
  async function loadUserConfig() {
    try {
      const r = await fetch("/api/user/config", { headers: authHeaders() });
      if (!r.ok) return;
      userApiConfig = await r.json();
    } catch { /* ignore */ }
  }

  async function saveUserConfig(provider, apiKey, baseUrl) {
    if (settingsStatus) settingsStatus.textContent = "Saving…";
    try {
      const r = await fetch("/api/user/config", {
        method: "POST",
        headers: { ...authHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify({ provider, api_key: apiKey, base_url: baseUrl || null }),
      });
      if (!r.ok) {
        const d = await r.json();
        if (settingsStatus) settingsStatus.textContent = d.detail || "Save failed";
        return;
      }
      if (settingsStatus) settingsStatus.textContent = "Saved! Your API key will be used for chat.";
      userApiConfig = { provider, has_key: !!apiKey };
    } catch {
      if (settingsStatus) settingsStatus.textContent = "Network error";
    }
  }

  function openSettings() {
    if (!settingsBackdrop) return;
    if (settingsProvider) settingsProvider.value = userApiConfig.provider || "openai";
    if (settingsApiKey) settingsApiKey.value = "";
    if (settingsBaseUrl) {
      const urls = { openai: "", groq: "", openrouter: "" };
      settingsBaseUrl.value = urls[userApiConfig.provider] || "";
    }
    if (settingsStatus) settingsStatus.textContent = userApiConfig.has_key ? "A key is already saved (paste again to change it)." : "";
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
      const r = await fetch("/api/config");
      if (!r.ok) return;
      const cfg = await r.json();
      tweakModeEnabled = Boolean(cfg.tweak_mode_enabled);
      if (reflectionRow) reflectionRow.style.display = tweakModeEnabled ? "flex" : "none";
    } catch {
      tweakModeEnabled = false;
      if (reflectionRow) reflectionRow.style.display = "none";
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
    if (reflectionBusyHint) { reflectionBusyHint.hidden = !isBusy; reflectionBusyHint.textContent = isBusy ? hintText : ""; }
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
    const raw = c.updated_at || c.created_at;
    if (!raw) return "";
    try { const d = new Date(raw); if (Number.isNaN(d.getTime())) return ""; return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }); } catch { return ""; }
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
    conversationHistory.length = 0;
    currentConversationId = null;
    chatMessages.innerHTML = `<div class="message assistant"><div class="message-content">Hi! I'm a stakeholder on this project. I'm not very technical, so I might not use all the right terminology - that's just how I talk about things.<br><br><strong>Your task:</strong> Ask me questions to gather requirements, then formalize what I tell you into proper requirements documentation.<br><br>You can ask me about:<br>• Who's involved in this project<br>• What we're trying to accomplish<br>• What the system needs to do<br>• Budget and cost concerns<br>• Any worries or risks we have<br><br><em>Remember: Take notes as we talk, then formalize my informal responses into structured requirements!</em></div></div>`;
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
      conversationHistory.length = 0;
      chatMessages.innerHTML = "";
      data.messages.forEach((m) => { addMessage(m.role, m.content, null, null, null); conversationHistory.push({ role: m.role, content: m.content }); });
      syncListSelection();
      await loadReflectionThreadsForConversation(currentConversationId);
    } catch (e) { console.error(e); }
  }

  // ── Chat ────────────────────────────────────────────────────
  async function submitFeedback(meta, fb, desired = "") {
    return fetch("/api/feedback", { method: "POST", headers: { ...authHeaders(), "Content-Type": "application/json" }, body: JSON.stringify({ prompt: meta?.prompt || "", response: meta?.response || "", feedback: fb, mode_used: meta?.mode || null, desired_response: desired || null }) });
  }

  function formatRoutingBadge(modeUsed, routing) {
    if (!modeUsed) return null;
    let label = `mode: ${modeUsed}`;
    if (routing?.route && modeUsed.startsWith("hybrid")) { const b = (routing.backends_used || []).join(" + "); label = `hybrid → ${routing.route}${b ? ` (${b})` : ""}`; }
    return label;
  }

  function addMessage(role, content, sources = null, modeUsed = null, meta = null) {
    const div = document.createElement("div");
    div.className = `message ${role}`;
    const cd = document.createElement("div");
    cd.className = "message-content";
    if (role === "assistant") cd.innerHTML = content.includes("<") ? content : content.replace(/\n/g, "<br>");
    else cd.textContent = content;
    if (role === "assistant" && modeUsed) {
      const badge = document.createElement("div");
      badge.className = "mode-badge";
      badge.textContent = formatRoutingBadge(modeUsed, meta?.routing) || `mode: ${modeUsed}`;
      badge.title = meta?.routing ? JSON.stringify(meta.routing) : "";
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
    addMessage("user", message);
    conversationHistory.push({ role: "user", content: message });
    chatInput.value = "";
    sendButton.disabled = true;
    addTypingIndicator();
    try {
      const r = await fetch("/api/chat", {
        method: "POST",
        headers: { ...authHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify({ message, conversation_history: conversationHistory, response_mode: responseMode.value, conversation_id: currentConversationId }),
      });
      if (!r.ok) throw new Error("Failed to get response");
      const data = await r.json();
      removeTypingIndicator();
      addMessage("assistant", data.response, null, data.mode_used || null, { prompt: message, response: data.response, mode: data.mode_used || null, routing: data.routing || null });
      conversationHistory.push({ role: "assistant", content: data.response });
      if (data.conversation_id) { currentConversationId = data.conversation_id; await loadConversations(); await loadReflectionThreadsForConversation(currentConversationId); }
    } catch (e) { removeTypingIndicator(); addMessage("assistant", "Sorry, I encountered an error. Please try again."); console.error(e); }
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

    if (settingsBtn) settingsBtn.addEventListener("click", openSettings);
    if (settingsCancel) settingsCancel.addEventListener("click", closeSettings);
    if (settingsBackdrop) settingsBackdrop.addEventListener("click", (e) => { if (e.target === settingsBackdrop) closeSettings(); });
    if (settingsForm) {
      settingsForm.addEventListener("submit", (e) => {
        e.preventDefault();
        saveUserConfig(settingsProvider?.value || "openai", settingsApiKey?.value || "", settingsBaseUrl?.value || "");
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
    if (newConversationBtn) newConversationBtn.addEventListener("click", resetConversationUi);

    if (reflectBtn) reflectBtn.addEventListener("click", runReflection);
    if (viewReflectionThreadsBtn) viewReflectionThreadsBtn.addEventListener("click", openReflectionsForCurrentConversation);
    if (reflectionCancel) reflectionCancel.addEventListener("click", closeReflectionModal);
    if (reflectionApply) reflectionApply.addEventListener("click", applyReflection);
    if (reflectionBackdrop) reflectionBackdrop.addEventListener("click", (e) => { if (e.target === reflectionBackdrop) closeReflectionModal(); });
    if (reflectionSendBtn) reflectionSendBtn.addEventListener("click", sendReflectionMessage);
    if (reflectionChatInput) reflectionChatInput.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); sendReflectionMessage(); } });
    if (reflectionThreadList) reflectionThreadList.addEventListener("click", (e) => { const item = e.target.closest(".reflection-thread-item"); if (item?.dataset.threadId) openReflectionThread(item.dataset.threadId); });
  }

  // ── Start ───────────────────────────────────────────────────
  init();
})();
