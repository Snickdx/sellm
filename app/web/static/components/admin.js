(() => {
  const PROVIDERS = [
    { id: "openai", label: "OpenAI", placeholder: "sk-..." },
    { id: "anthropic", label: "Anthropic", placeholder: "sk-ant-..." },
    { id: "gemini", label: "Gemini", placeholder: "AIza..." },
    { id: "groq", label: "Groq", placeholder: "gsk_..." },
    { id: "openrouter", label: "OpenRouter", placeholder: "sk-or-..." },
  ];
  const MODES = [
    ["vector", "Vector RAG"],
    ["neo4j", "Neo4j RAG"],
    ["hybrid", "Hybrid RAG"],
    ["direct", "Direct Model"],
    ["yaml", "YAML Persona"],
    ["compare", "Compare All"],
  ];
  const ROLES = [
    ["student", "Student (locked mode/model)"],
    ["tester", "Tester (can pick mode/model)"],
    ["admin", "Admin"],
  ];

  let authToken = localStorage.getItem("auth_token");
  let currentUser = null;
  let isAdmin = false;
  let view = "users";
  let users = [];
  let selectedUserId = null;
  let selectedConversationId = null;
  let llmChoices = [];
  let appSettings = null;

  const loginGate = document.getElementById("loginGate");
  const denyGate = document.getElementById("denyGate");
  const adminShell = document.getElementById("adminShell");
  const adminWho = document.getElementById("adminWho");
  const listTitle = document.getElementById("listTitle");
  const listToolbar = document.getElementById("listToolbar");
  const listBody = document.getElementById("listBody");
  const detailTitle = document.getElementById("detailTitle");
  const detailBody = document.getElementById("detailBody");

  function authHeaders(json = false) {
    const h = authToken ? { Authorization: `Bearer ${authToken}` } : {};
    if (json) h["Content-Type"] = "application/json";
    return h;
  }

  function setAuth(token) {
    authToken = token;
    if (token) localStorage.setItem("auth_token", token);
    else localStorage.removeItem("auth_token");
  }

  async function api(path, opts = {}) {
    const r = await fetch(path, {
      ...opts,
      headers: { ...authHeaders(Boolean(opts.body)), ...(opts.headers || {}) },
    });
    let data = null;
    const text = await r.text();
    try {
      data = text ? JSON.parse(text) : null;
    } catch {
      data = text;
    }
    if (!r.ok) {
      const detail = (data && data.detail) || text || r.statusText;
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }
    return data;
  }

  function show(el) {
    el?.classList.remove("hidden");
  }
  function hide(el) {
    el?.classList.add("hidden");
  }

  function fmtTokens(n) {
    const v = Number(n) || 0;
    return v.toLocaleString();
  }

  function setStatus(el, msg, kind = "") {
    if (!el) return;
    el.textContent = msg || "";
    el.className = `status${kind ? " " + kind : ""}`;
  }

  async function checkAuth() {
    if (!authToken) return false;
    try {
      const me = await api("/api/auth/me");
      currentUser = me.username;
      isAdmin = Boolean(me.is_admin);
      if (adminWho) adminWho.textContent = me.username + (isAdmin ? " · admin" : "");
      return true;
    } catch {
      setAuth(null);
      currentUser = null;
      isAdmin = false;
      return false;
    }
  }

  async function doLogin() {
    const username = document.getElementById("loginUsername")?.value?.trim();
    const password = document.getElementById("loginPassword")?.value || "";
    const err = document.getElementById("loginError");
    if (err) err.hidden = true;
    try {
      const data = await api("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ username, password }),
      });
      setAuth(data.token);
      currentUser = data.username;
      isAdmin = Boolean(data.is_admin);
      await boot();
    } catch (e) {
      if (err) {
        err.textContent = e.message || "Login failed";
        err.hidden = false;
      }
    }
  }

  async function logout() {
    try {
      await api("/api/auth/logout", { method: "POST" });
    } catch (_) {
      /* ignore */
    }
    setAuth(null);
    location.href = "/";
  }

  function bindNav() {
    document.querySelectorAll(".nav button[data-view]").forEach((btn) => {
      btn.addEventListener("click", () => {
        view = btn.dataset.view;
        document.querySelectorAll(".nav button[data-view]").forEach((b) => b.classList.toggle("active", b === btn));
        selectedConversationId = null;
        render();
      });
    });
  }

  async function loadUsers(group) {
    const q = group ? `?group=${encodeURIComponent(group)}` : "";
    users = await api(`/api/admin/users${q}`);
  }

  async function loadConfigChoices() {
    try {
      const cfg = await api("/api/config");
      llmChoices = Array.isArray(cfg.llm_choices) ? cfg.llm_choices : [];
    } catch {
      llmChoices = [];
    }
  }

  async function loadSettings() {
    appSettings = await api("/api/admin/settings");
  }

  function renderUserList() {
    listTitle.textContent = "Users";
    listToolbar.innerHTML = "";
    const search = document.createElement("input");
    search.placeholder = "Filter username…";
    search.id = "userFilter";
    const group = document.createElement("select");
    group.id = "groupFilter";
    group.innerHTML = `<option value="">All groups</option><option value="(ungrouped)">(ungrouped)</option>`;
    const groups = [...new Set(users.map((u) => u.group_name).filter(Boolean))].sort();
    groups.forEach((g) => {
      const opt = document.createElement("option");
      opt.value = g;
      opt.textContent = g;
      group.appendChild(opt);
    });
    const addBtn = document.createElement("button");
    addBtn.type = "button";
    addBtn.className = "btn btn-primary";
    addBtn.textContent = "+ User";
    addBtn.addEventListener("click", () => renderCreateUser());
    listToolbar.append(search, group, addBtn);

    const paint = () => {
      const needle = (search.value || "").trim().toLowerCase();
      const g = group.value;
      listBody.innerHTML = "";
      users
        .filter((u) => !needle || u.username.includes(needle))
        .filter((u) => {
          if (!g) return true;
          if (g === "(ungrouped)") return !u.group_name;
          return u.group_name === g;
        })
        .forEach((u) => {
          const btn = document.createElement("button");
          btn.type = "button";
          btn.className = "user-item" + (u.id === selectedUserId ? " active" : "");
          const exhausted = u.token_limit > 0 && u.tokens_used >= u.token_limit;
          const role = u.role || (u.is_admin ? "admin" : "student");
          btn.innerHTML = `
            <div class="name">${escapeHtml(u.username)}
              <span class="badge ${role === "admin" ? "admin" : ""}">${escapeHtml(role)}</span>
              ${exhausted ? '<span class="badge warn">exhausted</span>' : ""}
            </div>
            <div class="meta">${escapeHtml(u.group_name || "ungrouped")} · ${fmtTokens(u.tokens_used)}/${fmtTokens(u.token_limit)} · ${u.conversation_count} chats</div>
          `;
          btn.addEventListener("click", () => {
            selectedUserId = u.id;
            selectedConversationId = null;
            renderUserDetail(u.id);
            paint();
          });
          listBody.appendChild(btn);
        });
    };
    search.addEventListener("input", paint);
    group.addEventListener("change", async () => {
      await loadUsers(group.value || undefined);
      paint();
    });
    paint();
  }

  function modeOptions(selected) {
    return MODES.map(
      ([v, label]) => `<option value="${v}" ${selected === v ? "selected" : ""}>${label}</option>`
    ).join("");
  }

  function roleOptions(selected) {
    return ROLES.map(
      ([v, label]) => `<option value="${v}" ${selected === v ? "selected" : ""}>${label}</option>`
    ).join("");
  }

  function llmOptions(selected, includeBlank = true) {
    const opts = [];
    if (includeBlank) opts.push(`<option value="">App default</option>`);
    llmChoices.forEach((c) => {
      opts.push(
        `<option value="${escapeAttr(c.id)}" ${selected === c.id ? "selected" : ""}>${escapeHtml(c.label)}</option>`
      );
    });
    if (selected && !llmChoices.some((c) => c.id === selected)) {
      opts.push(`<option value="${escapeAttr(selected)}" selected>${escapeHtml(selected)} (saved)</option>`);
    }
    return opts.join("");
  }

  async function renderUserDetail(userId) {
    detailTitle.textContent = "User";
    detailBody.innerHTML = `<p class="status">Loading…</p>`;
    try {
      const user = await api(`/api/admin/users/${userId}`);
      const convos = await api(`/api/admin/users/${userId}/conversations`);
      detailBody.innerHTML = `
        <div class="grid-2">
          <div class="field"><label>Username</label><input id="uUsername" value="${escapeAttr(user.username)}" disabled /></div>
          <div class="field"><label>Role</label><select id="uRole">${roleOptions(user.role || (user.is_admin ? "admin" : "student"))}</select></div>
          <div class="field"><label>Group</label><input id="uGroup" value="${escapeAttr(user.group_name || "")}" placeholder="e.g. morning, cohort-a" /></div>
          <div class="field"><label>Token limit</label><input id="uLimit" type="number" min="0" value="${user.token_limit}" /></div>
          <div class="field"><label>Tokens used</label><input id="uUsed" type="number" min="0" value="${user.tokens_used}" /></div>
          <div class="field"><label>Default mode (tester/admin)</label><select id="uMode"><option value="">App default</option>${modeOptions(user.default_response_mode)}</select></div>
          <div class="field"><label>Default LLM (tester/admin)</label><select id="uLlm">${llmOptions(user.default_llm_choice, true)}</select></div>
          <div class="field"><label>New password (optional)</label><input id="uPassword" type="password" placeholder="Leave blank to keep" /></div>
        </div>
        <p style="font-size:12px;color:#64748b;margin-bottom:10px;">Students ignore per-user mode/model — they use the <em>Student defaults</em> under Default model / mode.</p>
        <div class="field"><label>Admin notes</label><textarea id="uNotes" rows="4" placeholder="Instructor notes about this account…">${escapeHtml(user.admin_notes || "")}</textarea></div>
        <div class="actions">
          <button type="button" class="btn btn-primary" id="saveUserBtn">Save user</button>
          <button type="button" class="btn btn-secondary" id="resetTokensBtn">Reset tokens used</button>
          <button type="button" class="btn btn-secondary" id="clearGroupBtn">Clear group</button>
        </div>
        <div id="userStatus" class="status"></div>
        <h3 style="margin:18px 0 8px;font-size:14px;">Transcripts (${convos.length})</h3>
        <div id="convoList"></div>
        <div id="transcriptPanel" style="margin-top:12px;"></div>
      `;
      const status = document.getElementById("userStatus");
      document.getElementById("saveUserBtn").addEventListener("click", async () => {
        try {
          const body = {
            token_limit: Number(document.getElementById("uLimit").value),
            tokens_used: Number(document.getElementById("uUsed").value),
            role: document.getElementById("uRole").value,
            group_name: document.getElementById("uGroup").value,
            admin_notes: document.getElementById("uNotes").value,
            default_response_mode: document.getElementById("uMode").value || null,
            clear_default_response_mode: !document.getElementById("uMode").value,
            default_llm_choice: document.getElementById("uLlm").value || null,
            clear_default_llm_choice: !document.getElementById("uLlm").value,
          };
          const pw = document.getElementById("uPassword").value;
          if (pw) body.password = pw;
          await api(`/api/admin/users/${userId}`, { method: "PATCH", body: JSON.stringify(body) });
          setStatus(status, "Saved.", "ok");
          await loadUsers();
          renderUserList();
          selectedUserId = userId;
        } catch (e) {
          setStatus(status, e.message, "err");
        }
      });
      document.getElementById("resetTokensBtn").addEventListener("click", async () => {
        try {
          await api(`/api/admin/users/${userId}`, {
            method: "PATCH",
            body: JSON.stringify({ reset_tokens: true }),
          });
          setStatus(status, "Tokens reset.", "ok");
          await loadUsers();
          renderUserDetail(userId);
          renderUserList();
        } catch (e) {
          setStatus(status, e.message, "err");
        }
      });
      document.getElementById("clearGroupBtn").addEventListener("click", async () => {
        try {
          await api(`/api/admin/users/${userId}`, {
            method: "PATCH",
            body: JSON.stringify({ clear_group: true }),
          });
          setStatus(status, "Group cleared.", "ok");
          await loadUsers();
          renderUserDetail(userId);
          renderUserList();
        } catch (e) {
          setStatus(status, e.message, "err");
        }
      });

      const convoList = document.getElementById("convoList");
      if (!convos.length) {
        convoList.innerHTML = `<p class="meta">No conversations yet.</p>`;
      } else {
        convos.forEach((c) => {
          const btn = document.createElement("button");
          btn.type = "button";
          btn.className = "convo-item" + (c.id === selectedConversationId ? " active" : "");
          btn.innerHTML = `
            <div class="name">${escapeHtml(c.title || "Untitled")}</div>
            <div class="meta">${escapeHtml(c.scenario_slug || "no scenario")} · ${c.message_count} msgs · ${escapeHtml(c.updated_at)}</div>
          `;
          btn.addEventListener("click", () => {
            selectedConversationId = c.id;
            renderTranscript(userId, c.id);
            renderUserDetail(userId);
          });
          convoList.appendChild(btn);
        });
      }
      if (selectedConversationId) {
        await renderTranscript(userId, selectedConversationId);
      }
    } catch (e) {
      detailBody.innerHTML = `<p class="status err">${escapeHtml(e.message)}</p>`;
    }
  }

  async function renderTranscript(userId, conversationId) {
    const panel = document.getElementById("transcriptPanel");
    if (!panel) return;
    panel.innerHTML = `<p class="status">Loading transcript…</p>`;
    try {
      const data = await api(`/api/admin/users/${userId}/conversations/${conversationId}`);
      const msgs = (data.messages || [])
        .map(
          (m) => `
          <div class="msg ${escapeAttr(m.role)}">
            <div class="role">${escapeHtml(m.role)}</div>
            <div class="content">${escapeHtml(m.content || "")}</div>
          </div>`
        )
        .join("");
      panel.innerHTML = `
        <div class="actions" style="margin-bottom:8px;">
          <a class="btn btn-secondary" href="/api/admin/users/${userId}/conversations/${conversationId}/download?format=txt" id="dlTxt">Download .txt</a>
          <a class="btn btn-secondary" href="/api/admin/users/${userId}/conversations/${conversationId}/download?format=md" id="dlMd">Download .md</a>
          <a class="btn btn-secondary" href="/api/admin/users/${userId}/conversations/${conversationId}/download?format=json" id="dlJson">Download .json</a>
        </div>
        <div class="transcript">${msgs || "<em>Empty transcript</em>"}</div>
      `;
      // Attach auth via fetch-download because <a> cannot send Bearer header
      ["dlTxt", "dlMd", "dlJson"].forEach((id) => {
        const a = document.getElementById(id);
        if (!a) return;
        a.addEventListener("click", async (ev) => {
          ev.preventDefault();
          const fmt = id === "dlJson" ? "json" : id === "dlMd" ? "md" : "txt";
          try {
            const r = await fetch(
              `/api/admin/users/${userId}/conversations/${conversationId}/download?format=${fmt}`,
              { headers: authHeaders() }
            );
            if (!r.ok) throw new Error("Download failed");
            const blob = await r.blob();
            const cd = r.headers.get("Content-Disposition") || "";
            const match = /filename="?([^"]+)"?/.exec(cd);
            const filename = match?.[1] || `transcript.${fmt}`;
            const url = URL.createObjectURL(blob);
            const link = document.createElement("a");
            link.href = url;
            link.download = filename;
            link.click();
            URL.revokeObjectURL(url);
          } catch (e) {
            window.alert(e.message || "Download failed");
          }
        });
      });
    } catch (e) {
      panel.innerHTML = `<p class="status err">${escapeHtml(e.message)}</p>`;
    }
  }

  function renderCreateUser() {
    detailTitle.textContent = "Create user";
    detailBody.innerHTML = `
      <div class="grid-2">
        <div class="field"><label>Username</label><input id="cUsername" /></div>
        <div class="field"><label>Password</label><input id="cPassword" type="password" /></div>
        <div class="field"><label>Token limit</label><input id="cLimit" type="number" value="15000" /></div>
        <div class="field"><label>Group</label><input id="cGroup" placeholder="optional" /></div>
        <div class="field"><label>Role</label><select id="cRole">${roleOptions("student")}</select></div>
        <div class="field"><label>Default mode (tester/admin)</label><select id="cMode"><option value="">App default</option>${modeOptions(null)}</select></div>
        <div class="field"><label>Default LLM (tester/admin)</label><select id="cLlm">${llmOptions(null, true)}</select></div>
      </div>
      <div class="field"><label>Admin notes</label><textarea id="cNotes" rows="3"></textarea></div>
      <div class="actions"><button type="button" class="btn btn-primary" id="createUserBtn">Create</button></div>
      <div id="createStatus" class="status"></div>
    `;
    document.getElementById("createUserBtn").addEventListener("click", async () => {
      const status = document.getElementById("createStatus");
      try {
        const created = await api("/api/admin/users", {
          method: "POST",
          body: JSON.stringify({
            username: document.getElementById("cUsername").value,
            password: document.getElementById("cPassword").value,
            token_limit: Number(document.getElementById("cLimit").value),
            group_name: document.getElementById("cGroup").value || null,
            admin_notes: document.getElementById("cNotes").value || null,
            role: document.getElementById("cRole").value,
            default_response_mode: document.getElementById("cMode").value || null,
            default_llm_choice: document.getElementById("cLlm").value || null,
          }),
        });
        setStatus(status, `Created ${created.username}`, "ok");
        await loadUsers();
        selectedUserId = created.id;
        renderUserList();
        renderUserDetail(created.id);
      } catch (e) {
        setStatus(status, e.message, "err");
      }
    });
  }

  async function renderTokens() {
    listTitle.textContent = "Token monitor";
    listToolbar.innerHTML = "";
    detailTitle.textContent = "Usage";
    detailBody.innerHTML = `<p class="status">Loading…</p>`;
    try {
      const data = await api("/api/admin/tokens");
      listBody.innerHTML = "";
      (data.users || [])
        .slice()
        .sort((a, b) => b.tokens_used - a.tokens_used)
        .forEach((u) => {
          const btn = document.createElement("button");
          btn.type = "button";
          btn.className = "user-item";
          const pct = u.token_limit > 0 ? Math.min(100, Math.round((100 * u.tokens_used) / u.token_limit)) : 0;
          btn.innerHTML = `
            <div class="name">${escapeHtml(u.username)}</div>
            <div class="meta">${fmtTokens(u.tokens_used)} / ${fmtTokens(u.token_limit)} (${pct}%) · ${escapeHtml(u.group_name || "ungrouped")}</div>
          `;
          btn.addEventListener("click", () => {
            view = "users";
            document.querySelectorAll(".nav button[data-view]").forEach((b) =>
              b.classList.toggle("active", b.dataset.view === "users")
            );
            selectedUserId = u.id;
            render();
          });
          listBody.appendChild(btn);
        });

      const groups = Object.entries(data.by_group || {})
        .map(
          ([name, g]) => `
          <div class="stat">
            <div class="label">${escapeHtml(name)}</div>
            <div class="value" style="font-size:16px;">${g.users} users</div>
            <div class="meta">${fmtTokens(g.tokens_used)} / ${fmtTokens(g.token_limit)}</div>
          </div>`
        )
        .join("");

      detailBody.innerHTML = `
        <div class="stats">
          <div class="stat"><div class="label">Users</div><div class="value">${data.user_count}</div></div>
          <div class="stat"><div class="label">Tokens used</div><div class="value">${fmtTokens(data.total_tokens_used)}</div></div>
          <div class="stat"><div class="label">Token pool</div><div class="value">${fmtTokens(data.total_token_limit)}</div></div>
          <div class="stat"><div class="label">Exhausted</div><div class="value">${data.exhausted_users}</div></div>
        </div>
        <h3 style="font-size:14px;margin-bottom:8px;">By group</h3>
        <div class="stats">${groups || "<p class='meta'>No groups assigned yet.</p>"}</div>
      `;
    } catch (e) {
      detailBody.innerHTML = `<p class="status err">${escapeHtml(e.message)}</p>`;
    }
  }

  async function renderAppKeys() {
    listTitle.textContent = "App-wide keys";
    listToolbar.innerHTML = "";
    listBody.innerHTML = `<p style="padding:14px;color:#64748b;font-size:13px;">Keys stored here are available to every user as platform models (billed against their shared interview budget).</p>`;
    detailTitle.textContent = "Providers";
    detailBody.innerHTML = `<p class="status">Loading…</p>`;
    try {
      const data = await api("/api/admin/app-keys");
      const byProvider = Object.fromEntries((data.keys || []).map((k) => [k.provider, k]));
      detailBody.innerHTML = PROVIDERS.map((p) => {
        const existing = byProvider[p.id] || {};
        return `
          <div class="provider-card" data-provider="${p.id}">
            <h4>${p.label} ${existing.has_key ? '<span class="badge">configured</span>' : ""}</h4>
            <div class="field"><label>API key</label>
              <input class="app-key" type="password" placeholder="${existing.has_key ? existing.api_key_masked || "••••" : p.placeholder}" value="" data-has="${existing.has_key ? "1" : "0"}" />
            </div>
            <div class="field"><label>Base URL (optional)</label>
              <input class="app-base" value="${escapeAttr(existing.base_url || "")}" placeholder="leave blank for provider default" />
            </div>
            <label style="font-size:12px;color:#64748b;display:flex;gap:6px;align-items:center;">
              <input type="checkbox" class="app-clear" /> Clear key
            </label>
          </div>`;
      }).join("") + `
        <div class="actions"><button type="button" class="btn btn-primary" id="saveAppKeys">Save app keys</button></div>
        <div id="appKeyStatus" class="status"></div>
        <p style="margin-top:12px;font-size:12px;color:#64748b;">After saving, open <strong>Default model / mode</strong> to pick an app-wide default that uses these keys.</p>
      `;
      document.getElementById("saveAppKeys").addEventListener("click", async () => {
        const status = document.getElementById("appKeyStatus");
        try {
          const keys = [...detailBody.querySelectorAll(".provider-card")].map((card) => {
            const provider = card.dataset.provider;
            const keyInput = card.querySelector(".app-key");
            const clear = card.querySelector(".app-clear")?.checked;
            let api_key = keyInput.value.trim();
            if (clear) api_key = "";
            else if (!api_key && keyInput.dataset.has === "1") api_key = "__UNCHANGED__";
            return {
              provider,
              api_key,
              base_url: card.querySelector(".app-base").value.trim() || null,
            };
          });
          await api("/api/admin/app-keys", { method: "POST", body: JSON.stringify({ keys }) });
          setStatus(status, "App keys saved.", "ok");
          await loadConfigChoices();
        } catch (e) {
          setStatus(status, e.message, "err");
        }
      });
    } catch (e) {
      detailBody.innerHTML = `<p class="status err">${escapeHtml(e.message)}</p>`;
    }
  }

  async function renderDefaults() {
    listTitle.textContent = "Defaults";
    listToolbar.innerHTML = "";
    listBody.innerHTML = `<p style="padding:14px;color:#64748b;font-size:13px;">App-wide defaults apply to every user unless that user has a personal override. Choose an <em>App · …</em> model after configuring app-wide keys to make the shared key the platform default.</p>`;
    detailTitle.textContent = "App-wide default model / mode";
    detailBody.innerHTML = `<p class="status">Loading…</p>`;
    try {
      await loadSettings();
      await loadConfigChoices();
      detailBody.innerHTML = `
        <h3 style="font-size:14px;margin-bottom:8px;">Tester / admin defaults</h3>
        <p style="font-size:12px;color:#64748b;margin-bottom:10px;">Used when a tester has no personal override. Testers can still change mode/model in chat.</p>
        <div class="field">
          <label>Default response mode</label>
          <select id="appMode">${modeOptions(appSettings.default_response_mode || "vector")}</select>
        </div>
        <div class="field">
          <label>Default LLM model</label>
          <select id="appLlm">
            <option value="">Auto (Ollama / env)</option>
            ${llmOptions(appSettings.default_llm_choice, false)}
          </select>
        </div>
        <h3 style="font-size:14px;margin:16px 0 8px;">Student defaults (all students)</h3>
        <p style="font-size:12px;color:#64748b;margin-bottom:10px;">Students cannot see or change mode/model. These settings apply to every student account.</p>
        <div class="field">
          <label>Student response mode</label>
          <select id="studentMode">${modeOptions(appSettings.student_default_response_mode || "vector")}</select>
        </div>
        <div class="field">
          <label>Student LLM model</label>
          <select id="studentLlm">
            <option value="">Auto (Ollama / env)</option>
            ${llmOptions(appSettings.student_default_llm_choice, false)}
          </select>
        </div>
        <div class="actions">
          <button type="button" class="btn btn-primary" id="saveDefaults">Save defaults</button>
          <button type="button" class="btn btn-secondary" id="clearLlmDefault">Clear tester LLM default</button>
          <button type="button" class="btn btn-secondary" id="clearStudentLlmDefault">Clear student LLM default</button>
        </div>
        <div id="defaultsStatus" class="status"></div>
      `;
      document.getElementById("saveDefaults").addEventListener("click", async () => {
        const status = document.getElementById("defaultsStatus");
        try {
          const llm = document.getElementById("appLlm").value;
          const studentLlm = document.getElementById("studentLlm").value;
          appSettings = await api("/api/admin/settings", {
            method: "PATCH",
            body: JSON.stringify({
              default_response_mode: document.getElementById("appMode").value,
              default_llm_choice: llm || null,
              clear_default_llm_choice: !llm,
              student_default_response_mode: document.getElementById("studentMode").value,
              student_default_llm_choice: studentLlm || null,
              clear_student_default_llm_choice: !studentLlm,
            }),
          });
          setStatus(status, "Defaults saved.", "ok");
        } catch (e) {
          setStatus(status, e.message, "err");
        }
      });
      document.getElementById("clearLlmDefault").addEventListener("click", async () => {
        const status = document.getElementById("defaultsStatus");
        try {
          appSettings = await api("/api/admin/settings", {
            method: "PATCH",
            body: JSON.stringify({ clear_default_llm_choice: true }),
          });
          document.getElementById("appLlm").value = "";
          setStatus(status, "Tester LLM default cleared.", "ok");
        } catch (e) {
          setStatus(status, e.message, "err");
        }
      });
      document.getElementById("clearStudentLlmDefault").addEventListener("click", async () => {
        const status = document.getElementById("defaultsStatus");
        try {
          appSettings = await api("/api/admin/settings", {
            method: "PATCH",
            body: JSON.stringify({ clear_student_default_llm_choice: true }),
          });
          document.getElementById("studentLlm").value = "";
          setStatus(status, "Student LLM default cleared.", "ok");
        } catch (e) {
          setStatus(status, e.message, "err");
        }
      });
    } catch (e) {
      detailBody.innerHTML = `<p class="status err">${escapeHtml(e.message)}</p>`;
    }
  }

  async function render() {
    if (view === "users") {
      await loadUsers();
      renderUserList();
      if (selectedUserId) renderUserDetail(selectedUserId);
      else {
        detailTitle.textContent = "Details";
        detailBody.innerHTML = `<p style="color:#64748b;font-size:14px;">Select a user to manage notes, group, tokens, defaults, and transcripts.</p>`;
      }
    } else if (view === "tokens") {
      await renderTokens();
    } else if (view === "appkeys") {
      await renderAppKeys();
    } else if (view === "defaults") {
      await renderDefaults();
    }
  }

  function escapeHtml(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }
  function escapeAttr(s) {
    return escapeHtml(s).replace(/'/g, "&#39;");
  }

  async function boot() {
    const ok = await checkAuth();
    if (!ok) {
      hide(adminShell);
      hide(denyGate);
      show(loginGate);
      return;
    }
    if (!isAdmin) {
      hide(adminShell);
      hide(loginGate);
      show(denyGate);
      const denyText = document.getElementById("denyText");
      if (denyText) denyText.textContent = `Signed in as ${currentUser}, but this account is not an admin.`;
      return;
    }
    hide(loginGate);
    hide(denyGate);
    show(adminShell);
    await loadConfigChoices();
    await render();
  }

  document.getElementById("loginBtn")?.addEventListener("click", doLogin);
  document.getElementById("loginPassword")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") doLogin();
  });
  document.getElementById("logoutBtn")?.addEventListener("click", logout);
  document.getElementById("denyLogout")?.addEventListener("click", logout);
  bindNav();
  boot();
})();
