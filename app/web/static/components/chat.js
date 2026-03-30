(() => {
  const chatMessages = document.getElementById("chatMessages");
  const chatForm = document.getElementById("chatForm");
  const chatInput = document.getElementById("chatInput");
  const sendButton = document.getElementById("sendButton");
  const responseMode = document.getElementById("responseMode");
  const conversationSelect = document.getElementById("conversationSelect");
  const newConversationBtn = document.getElementById("newConversationBtn");
  const conversationHistory = [];
  let currentConversationId = null;
  let tweakModeEnabled = false;

  async function loadRuntimeConfig() {
    try {
      const response = await fetch("/api/config");
      if (!response.ok) return;
      const config = await response.json();
      tweakModeEnabled = Boolean(config.tweak_mode_enabled);
    } catch {
      tweakModeEnabled = false;
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
  }

  async function loadConversations() {
    try {
      const response = await fetch("/api/conversations");
      if (!response.ok) return;
      const conversations = await response.json();
      conversationSelect.innerHTML = '<option value="">New conversation</option>';
      conversations.forEach((c) => {
        const option = document.createElement("option");
        option.value = c.id;
        option.textContent = c.title || c.id;
        conversationSelect.appendChild(option);
      });
      if (currentConversationId) conversationSelect.value = currentConversationId;
    } catch (error) {
      console.error("Could not load conversations:", error);
    }
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
        conversationSelect.value = currentConversationId;
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
  conversationSelect.addEventListener("change", async (e) => openConversation(e.target.value || null));
  newConversationBtn.addEventListener("click", () => {
    conversationSelect.value = "";
    resetConversationUi();
  });

  chatInput.focus();
  loadRuntimeConfig();
  loadConversations();
})();

