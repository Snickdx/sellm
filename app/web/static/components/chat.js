(() => {
  const chatMessages = document.getElementById("chatMessages");
  const chatForm = document.getElementById("chatForm");
  const chatInput = document.getElementById("chatInput");
  const sendButton = document.getElementById("sendButton");
  const responseMode = document.getElementById("responseMode");
  const conversationList = document.getElementById("conversationList");
  const newConversationBtn = document.getElementById("newConversationBtn");
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

  function lockReflectionWorkspace() {
    if (reflectionChatInput) reflectionChatInput.disabled = true;
    if (reflectionSendBtn) reflectionSendBtn.disabled = true;
    if (reflectionApply) reflectionApply.disabled = true;
  }

  function unlockReflectionWorkspace() {
    if (reflectionChatInput) reflectionChatInput.disabled = false;
    if (reflectionSendBtn) {
      reflectionSendBtn.disabled = false;
      reflectionSendBtn.textContent = REFLECT_SEND_LABEL;
    }
    if (reflectionApply) reflectionApply.disabled = false;
  }

  function setReflectRowBusy(isBusy, hintText = "") {
    if (reflectBtn) {
      reflectBtn.disabled = isBusy;
      if (isBusy) {
        reflectBtn.textContent = "Starting…";
        reflectBtn.setAttribute("aria-busy", "true");
      } else {
        reflectBtn.textContent = REFLECT_BTN_LABEL;
        reflectBtn.removeAttribute("aria-busy");
      }
    }
    if (viewReflectionThreadsBtn) viewReflectionThreadsBtn.disabled = isBusy;
    if (reflectionBusyHint) {
      reflectionBusyHint.hidden = !isBusy;
      reflectionBusyHint.textContent = isBusy ? hintText : "";
    }
  }

  async function loadRuntimeConfig() {
    try {
      const response = await fetch("/api/config");
      if (!response.ok) return;
      const config = await response.json();
      tweakModeEnabled = Boolean(config.tweak_mode_enabled);
      if (reflectionRow) {
        reflectionRow.style.display = tweakModeEnabled ? "flex" : "none";
      }
    } catch {
      tweakModeEnabled = false;
      if (reflectionRow) reflectionRow.style.display = "none";
    }
  }

  function openReflectionModal(data = {}) {
    if (!reflectionBackdrop || !reflectionNotes || !reflectionJson) return;
    if (data.loading) {
      reflectionNotes.textContent =
        data.loadingMessage ||
        "Starting reflection. The meta-LLM is analyzing your conversation — this can take up to a minute.";
      reflectionJson.value = "";
      if (reflectionStatus) {
        reflectionStatus.textContent =
          data.statusHint ||
          "In progress — please wait. You cannot start another reflection until this one finishes.";
      }
      renderReflectionMessages(
        data.prepMessages || [
          {
            role: "assistant",
            content:
              "Working… Do not click “Reflect on session” again until this completes. You can close this dialog; the request will still run in the background.",
          },
        ]
      );
    } else if (data.reflection) {
      reflectionNotes.textContent = data.reflection?.performance_notes || "(no notes)";
      reflectionJson.value = JSON.stringify(data.reflection || {}, null, 2);
    }
    if (!data.loading) {
      const meta = data.mode_used ? `Proposed via LLM mode: ${data.mode_used}.` : "";
      if (reflectionStatus) reflectionStatus.textContent = meta;
    }
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
      const response = await fetch(`/api/conversations/${conversationId}/reflections`);
      if (!response.ok) return;
      reflectionThreads = await response.json();
      renderReflectionThreadList();
    } catch (e) {
      console.error(e);
    }
  }

  async function openReflectionThread(threadId) {
    if (!threadId) return;
    try {
      const response = await fetch(`/api/reflections/${threadId}`);
      if (!response.ok) throw new Error("Could not load reflection thread");
      const data = await response.json();
      currentReflectionThreadId = data.id;
      unlockReflectionWorkspace();
      renderReflectionThreadList();
      renderReflectionMessages(data.messages || []);
      reflectionJson.value = data.latest_draft_json || "{}";
      reflectionNotes.textContent = "Refine this draft in the thread chat, then apply.";
      openReflectionModal();
    } catch (e) {
      console.error(e);
      window.alert("Could not load reflection thread.");
    }
  }

  async function openReflectionsForCurrentConversation() {
    if (!tweakModeEnabled) return;
    if (!currentConversationId) {
      window.alert("Select a conversation from the list first (including older chats).");
      return;
    }
    if (viewReflectionThreadsBtn) viewReflectionThreadsBtn.disabled = true;
    try {
      await loadReflectionThreadsForConversation(currentConversationId);
      if (reflectionThreads.length === 0) {
        currentReflectionThreadId = null;
        renderReflectionThreadList();
        renderReflectionMessages([]);
        reflectionNotes.textContent =
          "No reflection threads for this conversation yet. Use “Reflect on session” after you have at least one exchange.";
        reflectionJson.value = "{}";
        if (reflectionStatus) reflectionStatus.textContent = "";
        unlockReflectionWorkspace();
        openReflectionModal({});
      } else {
        await openReflectionThread(reflectionThreads[0].id);
      }
    } catch (e) {
      console.error(e);
      window.alert("Could not load reflection threads.");
    } finally {
      if (viewReflectionThreadsBtn) viewReflectionThreadsBtn.disabled = false;
    }
  }

  async function runReflection() {
    if (!reflectBtn) return;
    if (!currentConversationId) {
      window.alert("Open a saved conversation first so reflection can be linked.");
      return;
    }
    if (conversationHistory.length < 2) {
      window.alert("Have at least one full exchange (your question and the stakeholder reply) before reflecting.");
      return;
    }
    setReflectRowBusy(true, "Reflection in progress — please wait.");
    lockReflectionWorkspace();
    openReflectionModal({
      loading: true,
      loadingMessage:
        "Starting reflection. The meta-LLM is analyzing your conversation — this can take up to a minute. Please do not start another reflection until this finishes.",
    });
    try {
      const response = await fetch(`/api/conversations/${currentConversationId}/reflections/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      let data = {};
      try {
        data = await response.json();
      } catch {
        data = {};
      }
      if (!response.ok) {
        const msg = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail || "Reflection failed");
        closeReflectionModal();
        window.alert(msg);
        return;
      }
      currentReflectionThreadId = data.thread?.id || null;
      await loadReflectionThreadsForConversation(currentConversationId);
      unlockReflectionWorkspace();
      renderReflectionMessages(data.thread?.messages || []);
      reflectionJson.value = JSON.stringify(data.reflection || {}, null, 2);
      reflectionNotes.textContent = "Initial draft generated. Continue this reflection in the thread chat.";
      openReflectionModal(data);
    } catch (e) {
      console.error(e);
      closeReflectionModal();
      window.alert("Reflection request failed.");
    } finally {
      setReflectRowBusy(false);
      unlockReflectionWorkspace();
    }
  }

  async function applyReflection() {
    if (!reflectionJson || !reflectionApply) return;
    let reflection;
    try {
      reflection = JSON.parse(reflectionJson.value);
    } catch {
      if (reflectionStatus) reflectionStatus.textContent = "Invalid JSON — fix before applying.";
      return;
    }
    reflectionApply.disabled = true;
    const prevApplyLabel = reflectionApply.textContent;
    reflectionApply.textContent = "Applying…";
    try {
      if (!currentReflectionThreadId) {
        reflectionStatus.textContent = "No reflection thread selected.";
        return;
      }
      const response = await fetch(`/api/reflections/${currentReflectionThreadId}/apply`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reflection }),
      });
      let data = {};
      try {
        data = await response.json();
      } catch {
        data = {};
      }
      if (!response.ok) {
        const msg = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail || "Apply failed");
        reflectionStatus.textContent = msg;
        return;
      }
      const changes = data.changes || [];
      reflectionStatus.textContent = changes.length
        ? `Saved: ${changes.join("; ")}`
        : "Saved (no new tweak entries — file may still be updated).";
      if (data.thread?.messages) renderReflectionMessages(data.thread.messages);
    } catch (e) {
      console.error(e);
      reflectionStatus.textContent = "Apply request failed.";
    } finally {
      reflectionApply.disabled = false;
      reflectionApply.textContent = prevApplyLabel;
    }
  }

  async function sendReflectionMessage() {
    if (!currentReflectionThreadId || !reflectionChatInput || !reflectionSendBtn) return;
    const message = reflectionChatInput.value.trim();
    if (!message) return;
    reflectionSendBtn.disabled = true;
    reflectionSendBtn.textContent = "Sending…";
    if (reflectionStatus) reflectionStatus.textContent = "Waiting for meta-LLM response…";
    try {
      let draft = {};
      try {
        draft = JSON.parse(reflectionJson.value || "{}");
      } catch {
        draft = {};
      }
      const response = await fetch(`/api/reflections/${currentReflectionThreadId}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, reflection: draft }),
      });
      const data = await response.json();
      if (!response.ok) {
        const msg = typeof data.detail === "string" ? data.detail : "Reflection chat failed";
        reflectionStatus.textContent = msg;
        return;
      }
      if (data.thread?.messages) renderReflectionMessages(data.thread.messages);
      reflectionNotes.textContent = data.reflection?.performance_notes || "Draft updated.";
      reflectionJson.value = JSON.stringify(data.reflection || {}, null, 2);
      reflectionChatInput.value = "";
      if (reflectionStatus) reflectionStatus.textContent = data.mode_used ? `Updated (mode: ${data.mode_used}).` : "";
    } catch (e) {
      console.error(e);
      reflectionStatus.textContent = "Reflection chat request failed.";
    } finally {
      reflectionSendBtn.disabled = false;
      reflectionSendBtn.textContent = REFLECT_SEND_LABEL;
      reflectionChatInput.focus();
    }
  }

  function formatConversationMeta(c) {
    const raw = c.updated_at || c.created_at;
    if (!raw) return "";
    try {
      const d = new Date(raw);
      if (Number.isNaN(d.getTime())) return "";
      return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
    } catch {
      return "";
    }
  }

  function syncListSelection() {
    if (!conversationList) return;
    conversationList.querySelectorAll(".conversation-item").forEach((el) => {
      const match = Boolean(currentConversationId && el.dataset.conversationId === currentConversationId);
      el.classList.toggle("active", match);
    });
  }

  async function loadConversations() {
    try {
      const response = await fetch("/api/conversations");
      if (!response.ok) return;
      const conversations = await response.json();
      if (!conversationList) return;
      conversationList.innerHTML = "";
      conversations.forEach((c) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "conversation-item";
        btn.dataset.conversationId = c.id;
        btn.setAttribute("role", "listitem");
        const titleEl = document.createElement("span");
        titleEl.className = "conversation-title";
        titleEl.textContent = c.title || c.id;
        const metaEl = document.createElement("span");
        metaEl.className = "conversation-meta";
        metaEl.textContent = formatConversationMeta(c);
        btn.appendChild(titleEl);
        btn.appendChild(metaEl);
        conversationList.appendChild(btn);
      });
      syncListSelection();
    } catch (error) {
      console.error("Could not load conversations:", error);
    }
  }

  function resetConversationUi() {
    conversationHistory.length = 0;
    currentConversationId = null;
    chatMessages.innerHTML = `
      <div class="message assistant">
        <div class="message-content">
          Hi! I'm a stakeholder on this project. I'm not very technical, so I might not use all the right terminology - that's just how I talk about things.
          <br><br><strong>Your task:</strong> Ask me questions to gather requirements, then formalize what I tell you into proper requirements documentation.
          <br><br>You can ask me about:
          <br>• Who's involved in this project
          <br>• What we're trying to accomplish
          <br>• What the system needs to do
          <br>• Budget and cost concerns
          <br>• Any worries or risks we have
          <br><br><em>Remember: Take notes as we talk, then formalize my informal responses into structured requirements!</em>
        </div>
      </div>
    `;
    syncListSelection();
    loadReflectionThreadsForConversation(currentConversationId);
  }

  async function openConversation(conversationId) {
    if (!conversationId) {
      resetConversationUi();
      return;
    }
    try {
      const response = await fetch(`/api/conversations/${conversationId}`);
      if (!response.ok) throw new Error("Could not load conversation");
      const data = await response.json();
      currentConversationId = data.id;
      conversationHistory.length = 0;
      chatMessages.innerHTML = "";
      data.messages.forEach((m) => {
        addMessage(m.role, m.content, null, null, null);
        conversationHistory.push({ role: m.role, content: m.content });
      });
      syncListSelection();
      await loadReflectionThreadsForConversation(currentConversationId);
    } catch (error) {
      console.error(error);
    }
  }

  async function submitFeedback(meta, feedbackText, desiredResponse = "") {
    const payload = {
      prompt: meta?.prompt || "",
      response: meta?.response || "",
      feedback: feedbackText,
      mode_used: meta?.mode || null,
      desired_response: desiredResponse || null,
    };
    const response = await fetch("/api/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) throw new Error("Failed to submit feedback");
    return response.json();
  }

  function addMessage(role, content, sources = null, modeUsed = null, meta = null) {
    const messageDiv = document.createElement("div");
    messageDiv.className = `message ${role}`;
    const contentDiv = document.createElement("div");
    contentDiv.className = "message-content";
    if (role === "assistant") {
      contentDiv.innerHTML = content.includes("<") ? content : content.replace(/\n/g, "<br>");
    } else {
      contentDiv.textContent = content;
    }

    if (role === "assistant" && modeUsed) {
      const badge = document.createElement("div");
      badge.className = "mode-badge";
      badge.textContent = `mode: ${modeUsed}`;
      contentDiv.prepend(badge);
    }

    if (role === "assistant" && meta?.prompt && tweakModeEnabled) {
      const feedbackRow = document.createElement("div");
      feedbackRow.className = "feedback-row";
      const thumbsUpBtn = document.createElement("button");
      thumbsUpBtn.className = "feedback-btn";
      thumbsUpBtn.type = "button";
      thumbsUpBtn.textContent = "👍 Good";
      const improveBtn = document.createElement("button");
      improveBtn.className = "feedback-btn";
      improveBtn.type = "button";
      improveBtn.textContent = "👎 Improve";
      const note = document.createElement("span");
      note.className = "feedback-note";
      note.textContent = "Help tune responses at runtime.";

      thumbsUpBtn.onclick = async () => {
        try {
          await submitFeedback(meta, "good_response");
          note.textContent = "Saved. No tweak needed.";
        } catch {
          note.textContent = "Could not save feedback.";
        }
      };
      improveBtn.onclick = async () => {
        const feedbackText = window.prompt("How should this response improve?");
        if (!feedbackText || !feedbackText.trim()) return;
        const desiredResponse = window.prompt("Optional: Provide a better response for this exact prompt.") || "";
        try {
          const result = await submitFeedback(meta, feedbackText.trim(), desiredResponse.trim());
          const changes = (result.changes || []).join("; ");
          note.textContent = changes ? `Saved and updated: ${changes}` : "Saved feedback.";
        } catch {
          note.textContent = "Could not save feedback.";
        }
      };
      feedbackRow.appendChild(thumbsUpBtn);
      feedbackRow.appendChild(improveBtn);
      feedbackRow.appendChild(note);
      contentDiv.appendChild(feedbackRow);
    }

    messageDiv.appendChild(contentDiv);
    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  function addTypingIndicator() {
    const messageDiv = document.createElement("div");
    messageDiv.className = "message assistant";
    messageDiv.id = "typingIndicator";
    const contentDiv = document.createElement("div");
    contentDiv.className = "message-content";
    contentDiv.innerHTML =
      '<div class="typing-indicator"><div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div></div>';
    messageDiv.appendChild(contentDiv);
    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  function removeTypingIndicator() {
    const indicator = document.getElementById("typingIndicator");
    if (indicator) indicator.remove();
  }

  async function sendMessage(message) {
    addMessage("user", message);
    conversationHistory.push({ role: "user", content: message });
    chatInput.value = "";
    sendButton.disabled = true;
    addTypingIndicator();
    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message,
          conversation_history: conversationHistory,
          response_mode: responseMode.value,
          conversation_id: currentConversationId,
        }),
      });
      if (!response.ok) throw new Error("Failed to get response");
      const data = await response.json();
      removeTypingIndicator();
      addMessage("assistant", data.response, null, data.mode_used || null, {
        prompt: message,
        response: data.response,
        mode: data.mode_used || null,
      });
      conversationHistory.push({ role: "assistant", content: data.response });
      if (data.conversation_id) {
        currentConversationId = data.conversation_id;
        await loadConversations();
        await loadReflectionThreadsForConversation(currentConversationId);
      }
    } catch (error) {
      removeTypingIndicator();
      addMessage("assistant", "Sorry, I encountered an error. Please try again.");
      console.error("Error:", error);
    } finally {
      sendButton.disabled = false;
      chatInput.focus();
    }
  }

  chatForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const message = chatInput.value.trim();
    if (message) sendMessage(message);
  });
  if (conversationList) {
    conversationList.addEventListener("click", (e) => {
      const item = e.target.closest(".conversation-item");
      if (!item || !item.dataset.conversationId) return;
      openConversation(item.dataset.conversationId);
    });
  }
  if (newConversationBtn) {
    newConversationBtn.addEventListener("click", () => {
      resetConversationUi();
    });
  }

  if (reflectBtn) reflectBtn.addEventListener("click", () => runReflection());
  if (viewReflectionThreadsBtn)
    viewReflectionThreadsBtn.addEventListener("click", () => openReflectionsForCurrentConversation());
  if (reflectionCancel) reflectionCancel.addEventListener("click", () => closeReflectionModal());
  if (reflectionApply) reflectionApply.addEventListener("click", () => applyReflection());
  if (reflectionBackdrop) {
    reflectionBackdrop.addEventListener("click", (e) => {
      if (e.target === reflectionBackdrop) closeReflectionModal();
    });
  }
  if (reflectionSendBtn) reflectionSendBtn.addEventListener("click", () => sendReflectionMessage());
  if (reflectionChatInput) {
    reflectionChatInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        sendReflectionMessage();
      }
    });
  }
  if (reflectionThreadList) {
    reflectionThreadList.addEventListener("click", (e) => {
      const item = e.target.closest(".reflection-thread-item");
      if (!item || !item.dataset.threadId) return;
      openReflectionThread(item.dataset.threadId);
    });
  }

  chatInput.focus();
  loadRuntimeConfig();
  loadConversations();
})();

