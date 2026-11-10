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
  let selectedTeamId = null;
  let scenariosCache = null;
  let llmChoices = [];
  let appSettings = null;
  let selectedRoleDefaults = "student";
  let roleDraft = null;

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

  function setLayout(mode) {
    if (!adminShell) return;
    adminShell.classList.toggle("with-list", mode === "list");
    adminShell.classList.toggle("users-wide", mode === "users");
    const fab = document.getElementById("createTeamFab");
    if (fab) fab.hidden = mode !== "list";
  }

  function syncViewTabs() {
    document.querySelectorAll("[data-view]").forEach((b) => {
      const on = b.dataset.view === view;
      b.classList.toggle("active", on);
      if (b.getAttribute("role") === "tab") b.setAttribute("aria-selected", on ? "true" : "false");
    });
  }

  function setView(next) {
    view = next;
    selectedConversationId = null;
    if (view !== "teams") {
      selectedTeamId = null;
      closeTeamCreateModal();
    }
    syncViewTabs();
    const url = new URL(location.href);
    url.searchParams.set("view", view);
    history.replaceState(null, "", url);
    closeNav();
    render();
  }

  function openNav() {
    if (!adminShell) return;
    adminShell.classList.add("nav-open");
    document.getElementById("navToggle")?.setAttribute("aria-expanded", "true");
  }

  function closeNav() {
    if (!adminShell) return;
    adminShell.classList.remove("nav-open");
    document.getElementById("navToggle")?.setAttribute("aria-expanded", "false");
  }

  function bindNav() {
    document.querySelectorAll("[data-view]").forEach((btn) => {
      btn.addEventListener("click", () => setView(btn.dataset.view));
    });
    document.getElementById("navToggle")?.addEventListener("click", openNav);
    document.getElementById("navClose")?.addEventListener("click", closeNav);
    document.getElementById("navBackdrop")?.addEventListener("click", closeNav);
  }

  async function loadUsers(group) {
    const q = group ? `?group=${encodeURIComponent(group)}` : "";
    users = await api(`/api/admin/users${q}`);
  }

  let llmChoicesLoaded = false;
  async function loadConfigChoices(force = false) {
    if (llmChoicesLoaded && !force) return;
    try {
      const cfg = await api("/api/config");
      llmChoices = Array.isArray(cfg.llm_choices) ? cfg.llm_choices : [];
      llmChoicesLoaded = true;
    } catch {
      llmChoices = [];
      llmChoicesLoaded = false;
    }
  }

  async function loadSettings() {
    appSettings = await api("/api/admin/settings");
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

  function llmOptions(selected, includeBlank = true, blankLabel = "Role default") {
    const opts = [];
    if (includeBlank) opts.push(`<option value="">${escapeHtml(blankLabel)}</option>`);
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

  function modeLabel(id) {
    const hit = MODES.find(([v]) => v === id);
    return hit ? hit[1] : id || "—";
  }

  function llmLabel(id) {
    if (!id) return "Auto / role default";
    const hit = llmChoices.find((c) => c.id === id);
    return hit ? hit.label : id;
  }

  async function refreshUsersView(keepSelected = true) {
    const sel = keepSelected ? selectedUserId : null;
    await loadSettings();
    await loadUsers();
    selectedUserId = sel;
    await renderUsersGrid();
  }

  function roleDefaultsFromSettings(settings) {
    const s = settings || {};
    return {
      student: {
        mode: s.student_default_response_mode || "vector",
        llm: s.student_default_llm_choice || "",
        budget: Number(s.student_token_limit || 15000),
      },
      tester: {
        mode: s.default_response_mode || "vector",
        llm: s.default_llm_choice || "",
        budget: Number(s.tester_token_limit || 15000),
      },
      admin: {
        mode: s.admin_default_response_mode || "",
        llm: s.admin_default_llm_choice || "",
        budget: Number(s.admin_token_limit || 50000),
      },
    };
  }

  function roleDefaultsMarkup() {
    roleDraft = roleDefaultsFromSettings(appSettings);
    if (!["student", "tester", "admin"].includes(selectedRoleDefaults)) {
      selectedRoleDefaults = "student";
    }
    return `
      <div class="role-defaults">
        <div class="role-defaults-top">
          <div class="role-toggle" role="group" aria-label="Role defaults">
            <button type="button" data-role="student" class="${selectedRoleDefaults === "student" ? "active" : ""}">Student</button>
            <button type="button" data-role="tester" class="${selectedRoleDefaults === "tester" ? "active" : ""}">Tester</button>
            <button type="button" data-role="admin" class="${selectedRoleDefaults === "admin" ? "active" : ""}">Admin</button>
          </div>
          <span class="hint" id="roleDefaultsHint">Applies to all users of this role without overrides.</span>
        </div>
        <div class="role-defaults-fields">
          <div class="field"><label>Mode</label><select id="roleMode"></select></div>
          <div class="field"><label>LLM</label><select id="roleLlm"></select></div>
          <div class="field"><label>Budget</label><input id="roleBudget" type="number" min="0" /></div>
          <div class="actions"><button type="button" class="btn btn-primary" id="saveRoleDefaultsBtn">Save</button></div>
        </div>
        <div id="roleDefaultsStatus" class="status"></div>
      </div>
    `;
  }

  function captureRoleDraft() {
    if (!roleDraft) roleDraft = roleDefaultsFromSettings(appSettings);
    const modeEl = document.getElementById("roleMode");
    const llmEl = document.getElementById("roleLlm");
    const budgetEl = document.getElementById("roleBudget");
    if (!modeEl || !llmEl || !budgetEl) return;
    roleDraft[selectedRoleDefaults] = {
      mode: modeEl.value,
      llm: llmEl.value,
      budget: Number(budgetEl.value),
    };
  }

  function fillRoleDefaultsForm(role) {
    if (!roleDraft) roleDraft = roleDefaultsFromSettings(appSettings);
    selectedRoleDefaults = role;
    const draft = roleDraft[role] || { mode: "vector", llm: "", budget: 15000 };
    const modeEl = document.getElementById("roleMode");
    const llmEl = document.getElementById("roleLlm");
    const budgetEl = document.getElementById("roleBudget");
    if (!modeEl || !llmEl || !budgetEl) return;

    if (role === "admin") {
      modeEl.innerHTML = `<option value="">Same as tester</option>${modeOptions(draft.mode || null)}`;
      llmEl.innerHTML = `<option value="">Same as tester</option>${llmOptions(draft.llm || null, false)}`;
    } else {
      modeEl.innerHTML = modeOptions(draft.mode || "vector");
      llmEl.innerHTML = `<option value="">Auto</option>${llmOptions(draft.llm || null, false)}`;
    }
    modeEl.value = draft.mode || "";
    llmEl.value = draft.llm || "";
    budgetEl.value = Number(draft.budget || 0);

    document.querySelectorAll(".role-toggle button").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.role === role);
    });
    const hint = document.getElementById("roleDefaultsHint");
    if (hint) hint.textContent = `Applies to all ${role}s without overrides.`;
  }

  function bindRoleDefaultsPanel() {
    document.querySelectorAll(".role-toggle button").forEach((btn) => {
      btn.addEventListener("click", () => {
        captureRoleDraft();
        fillRoleDefaultsForm(btn.dataset.role);
      });
    });
    document.getElementById("saveRoleDefaultsBtn")?.addEventListener("click", () => {
      captureRoleDraft();
      saveRoleDefaults(selectedRoleDefaults);
    });
    fillRoleDefaultsForm(selectedRoleDefaults);
  }

  async function saveRoleDefaults(role) {
    const status = document.getElementById("roleDefaultsStatus");
    try {
      captureRoleDraft();
      const draft = (roleDraft && roleDraft[role]) || {};
      let body = { apply_budgets: true };
      if (role === "student") {
        body = {
          ...body,
          student_default_response_mode: draft.mode || "vector",
          student_default_llm_choice: draft.llm || null,
          clear_student_default_llm_choice: !draft.llm,
          student_token_limit: Number(draft.budget),
        };
      } else if (role === "tester") {
        body = {
          ...body,
          default_response_mode: draft.mode || "vector",
          default_llm_choice: draft.llm || null,
          clear_default_llm_choice: !draft.llm,
          tester_token_limit: Number(draft.budget),
        };
      } else {
        body = {
          ...body,
          admin_default_response_mode: draft.mode || null,
          clear_admin_default_response_mode: !draft.mode,
          admin_default_llm_choice: draft.llm || null,
          clear_admin_default_llm_choice: !draft.llm,
          admin_token_limit: Number(draft.budget),
        };
      }
      appSettings = await api("/api/admin/settings", { method: "PATCH", body: JSON.stringify(body) });
      roleDraft = roleDefaultsFromSettings(appSettings);
      fillRoleDefaultsForm(role);
      setStatus(status, `${role} defaults saved. Budget applied to non-override users.`, "ok");
      await loadUsers();
      if (document.getElementById("usersGridBody")) paintUsersTable();
    } catch (e) {
      setStatus(status, e.message, "err");
    }
  }

  function paintUsersTable() {
    const tableBody = document.getElementById("usersGridBody");
    const search = document.getElementById("userFilter");
    const group = document.getElementById("groupFilter");
    const roleFilter = document.getElementById("roleFilter");
    if (!tableBody) return;
    const needle = (search?.value || "").trim().toLowerCase();
    const g = group?.value || "";
    const roleNeedle = roleFilter?.value || "";
    const rows = users
      .filter((u) => !needle || u.username.includes(needle))
      .filter((u) => {
        if (!g) return true;
        if (g === "(ungrouped)") return !u.group_name;
        return u.group_name === g;
      })
      .filter((u) => !roleNeedle || (u.role || (u.is_admin ? "admin" : "student")) === roleNeedle);

    tableBody.innerHTML = rows
      .map((u) => {
        const role = u.role || (u.is_admin ? "admin" : "student");
        const exhausted = u.token_limit > 0 && u.tokens_used >= u.token_limit;
        const modeVal = u.default_response_mode || "";
        const llmVal = u.default_llm_choice || "";
        return `
          <tr data-id="${u.id}" class="${u.id === selectedUserId ? "selected" : ""}">
            <td>
              <strong>${escapeHtml(u.username)}</strong>
              ${exhausted ? '<span class="badge warn">exhausted</span>' : ""}
              <div class="meta" style="font-size:11px;color:#64748b;">${escapeHtml(u.group_name || "ungrouped")} · ${u.conversation_count} chats</div>
            </td>
            <td>
              <select class="u-role" data-id="${u.id}">${roleOptions(role)}</select>
            </td>
            <td>
              <div class="cell-with-badge">
                <select class="u-mode" data-id="${u.id}">
                  <option value="">Role (${escapeHtml(modeLabel(u.role_default_response_mode))})</option>
                  ${modeOptions(modeVal)}
                </select>
                ${u.mode_is_override ? '<span class="badge override">override</span>' : '<span class="badge inherit">role</span>'}
              </div>
            </td>
            <td>
              <div class="cell-with-badge">
                <select class="u-llm" data-id="${u.id}">
                  ${llmOptions(llmVal, true, `Role (${llmLabel(u.role_default_llm_choice)})`)}
                </select>
                ${u.llm_is_override ? '<span class="badge override">override</span>' : '<span class="badge inherit">role</span>'}
              </div>
            </td>
            <td>
              <div class="cell-stack">
                <div class="cell-with-badge">
                  <input class="u-budget" data-id="${u.id}" type="number" min="0" value="${u.token_limit}" style="width:100px;" />
                  ${u.budget_is_override ? '<span class="badge override">override</span>' : '<span class="badge inherit">role</span>'}
                </div>
                <div class="meta" style="font-size:11px;color:#64748b;">used ${fmtTokens(u.tokens_used)} · role ${fmtTokens(u.role_token_limit)}</div>
              </div>
            </td>
            <td>
              <div class="cell-actions">
                <button type="button" class="btn-xs primary u-save" data-id="${u.id}">Save</button>
                <button type="button" class="btn-xs u-reset" data-id="${u.id}" title="Reset mode, LLM, and budget to role defaults">Reset</button>
                <button type="button" class="btn-xs u-edit" data-id="${u.id}">More</button>
              </div>
            </td>
          </tr>`;
      })
      .join("");

    if (!rows.length) {
      tableBody.innerHTML = `<tr><td colspan="6" style="color:#64748b;padding:16px;">No users match.</td></tr>`;
    }

    tableBody.querySelectorAll(".u-save").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const id = Number(btn.dataset.id);
        const status = document.getElementById("usersGridStatus");
        try {
          const modeEl = tableBody.querySelector(`.u-mode[data-id="${id}"]`);
          const llmEl = tableBody.querySelector(`.u-llm[data-id="${id}"]`);
          const budgetEl = tableBody.querySelector(`.u-budget[data-id="${id}"]`);
          const roleEl = tableBody.querySelector(`.u-role[data-id="${id}"]`);
          const current = users.find((x) => x.id === id);
          const budget = Number(budgetEl.value);
          const body = {
            role: roleEl.value,
            default_response_mode: modeEl.value || null,
            clear_default_response_mode: !modeEl.value,
            default_llm_choice: llmEl.value || null,
            clear_default_llm_choice: !llmEl.value,
          };
          if (current && budget === Number(current.role_token_limit)) {
            body.reset_budget_to_role = true;
          } else {
            body.token_limit = budget;
            body.budget_is_override = true;
          }
          await api(`/api/admin/users/${id}`, { method: "PATCH", body: JSON.stringify(body) });
          setStatus(status, `Saved ${current?.username || id}.`, "ok");
          await loadUsers();
          paintUsersTable();
          if (selectedUserId === id) await renderSelectedUserEditor(id);
        } catch (e) {
          setStatus(status, e.message, "err");
        }
      });
    });

    tableBody.querySelectorAll(".u-reset").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const id = Number(btn.dataset.id);
        const status = document.getElementById("usersGridStatus");
        try {
          await api(`/api/admin/users/${id}`, {
            method: "PATCH",
            body: JSON.stringify({ reset_defaults_to_role: true }),
          });
          setStatus(status, "Reset to role defaults.", "ok");
          await loadUsers();
          paintUsersTable();
          if (selectedUserId === id) await renderSelectedUserEditor(id);
        } catch (e) {
          setStatus(status, e.message, "err");
        }
      });
    });

    tableBody.querySelectorAll(".u-edit").forEach((btn) => {
      btn.addEventListener("click", async () => {
        selectedUserId = Number(btn.dataset.id);
        selectedConversationId = null;
        paintUsersTable();
        await openUserDetailModal(selectedUserId);
      });
    });
  }

  function closeUserDetailModal() {
    const modal = document.getElementById("userDetailModal");
    const body = document.getElementById("userDetailModalBody");
    if (modal) {
      modal.classList.remove("open");
      modal.setAttribute("aria-hidden", "true");
    }
    if (body) body.innerHTML = "";
    selectedConversationId = null;
  }

  async function openUserDetailModal(userId) {
    const modal = document.getElementById("userDetailModal");
    if (!modal) {
      await renderSelectedUserEditor(userId);
      return;
    }
    modal.classList.add("open");
    modal.setAttribute("aria-hidden", "false");
    await renderSelectedUserEditor(userId);
  }

  async function renderUsersGrid() {
    detailTitle.textContent = "Users";
    detailBody.innerHTML = `<p class="status">Loading…</p>`;
    try {
      await loadSettings();
      await loadConfigChoices();
      const groups = [...new Set(users.map((u) => u.group_name).filter(Boolean))].sort();
      detailBody.innerHTML = `
        ${roleDefaultsMarkup()}
        <div class="users-toolbar">
          <input id="userFilter" placeholder="Filter username…" />
          <select id="groupFilter">
            <option value="">All groups</option>
            <option value="(ungrouped)">(ungrouped)</option>
            ${groups.map((g) => `<option value="${escapeAttr(g)}">${escapeHtml(g)}</option>`).join("")}
          </select>
          <select id="roleFilter">
            <option value="">All roles</option>
            <option value="student">Student</option>
            <option value="tester">Tester</option>
            <option value="admin">Admin</option>
          </select>
          <button type="button" class="btn btn-primary" id="addUserBtn">+ User</button>
        </div>
        <div id="usersGridStatus" class="status"></div>
        <div class="users-table-wrap">
          <table class="users-grid">
            <thead>
              <tr>
                <th>User</th>
                <th>Role</th>
                <th>Mode</th>
                <th>LLM</th>
                <th>Budget</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody id="usersGridBody"></tbody>
          </table>
        </div>
      `;
      bindRoleDefaultsPanel();
      document.getElementById("userFilter")?.addEventListener("input", paintUsersTable);
      document.getElementById("groupFilter")?.addEventListener("change", paintUsersTable);
      document.getElementById("roleFilter")?.addEventListener("change", paintUsersTable);
      document.getElementById("addUserBtn")?.addEventListener("click", () => renderCreateUser());
      paintUsersTable();
    } catch (e) {
      detailBody.innerHTML = `<p class="status err">${escapeHtml(e.message)}</p>`;
    }
  }

  async function renderSelectedUserEditor(userId) {
    const modalBody = document.getElementById("userDetailModalBody");
    const modalTitle = document.getElementById("userDetailModalTitle");
    const host = modalBody || document.getElementById("userEditor");
    if (!host) return;
    host.innerHTML = `<p class="status">Loading…</p>`;
    try {
      const user = await api(`/api/admin/users/${userId}`);
      const convos = await api(`/api/admin/users/${userId}/conversations`);
      if (modalTitle) modalTitle.textContent = `${user.username} · notes & transcripts`;
      if (!selectedConversationId && convos.length) selectedConversationId = convos[0].id;
      host.innerHTML = `
        <div class="user-detail-shell">
          <div class="user-detail-form">
            <div class="user-detail-fields">
              <div class="field"><label>Group</label><input id="uGroup" value="${escapeAttr(user.group_name || "")}" placeholder="e.g. morning, cohort-a" /></div>
              <div class="field"><label>Tokens used</label><input id="uUsed" type="number" min="0" value="${user.tokens_used}" /></div>
              <div class="field"><label>New password (optional)</label><input id="uPassword" type="password" placeholder="Leave blank to keep" /></div>
              <div class="field"><label>Effective</label>
                <div class="effective-meta">
                  ${escapeHtml(modeLabel(user.effective_response_mode))} · ${escapeHtml(llmLabel(user.effective_llm_choice))} · ${fmtTokens(user.token_limit)} tokens
                  ${user.budget_is_override || user.mode_is_override || user.llm_is_override ? " (has overrides)" : " (from role)"}
                </div>
              </div>
            </div>
            <div class="field field-notes"><label>Admin notes</label><textarea id="uNotes" rows="2" placeholder="Instructor notes…">${escapeHtml(user.admin_notes || "")}</textarea></div>
            <div class="actions">
              <button type="button" class="btn btn-primary" id="saveUserBtn">Save details</button>
              <button type="button" class="btn btn-secondary" id="resetTokensBtn">Reset tokens used</button>
              <button type="button" class="btn btn-secondary" id="resetDefaultsBtn">Reset mode/LLM/budget to role</button>
              <button type="button" class="btn btn-secondary" id="clearGroupBtn">Clear group</button>
              <button type="button" class="btn btn-secondary" id="closeEditorBtn">Close</button>
            </div>
            <div id="userStatus" class="status"></div>
          </div>
          <div class="user-detail-transcripts">
            <h3>Transcripts (${convos.length})</h3>
            <div class="transcript-master-detail">
              <div id="convoList" class="transcript-master"></div>
              <div id="transcriptPanel" class="transcript-detail"></div>
            </div>
          </div>
        </div>
      `;
      const status = document.getElementById("userStatus");
      document.getElementById("saveUserBtn").addEventListener("click", async () => {
        try {
          const body = {
            group_name: document.getElementById("uGroup").value,
            tokens_used: Number(document.getElementById("uUsed").value),
            admin_notes: document.getElementById("uNotes").value,
          };
          const pw = document.getElementById("uPassword").value;
          if (pw) body.password = pw;
          await api(`/api/admin/users/${userId}`, { method: "PATCH", body: JSON.stringify(body) });
          setStatus(status, "Saved.", "ok");
          await loadUsers();
          paintUsersTable();
        } catch (e) {
          setStatus(status, e.message, "err");
        }
      });
      document.getElementById("resetTokensBtn").addEventListener("click", async () => {
        try {
          await api(`/api/admin/users/${userId}`, { method: "PATCH", body: JSON.stringify({ reset_tokens: true }) });
          setStatus(status, "Tokens reset.", "ok");
          await loadUsers();
          paintUsersTable();
          await renderSelectedUserEditor(userId);
        } catch (e) {
          setStatus(status, e.message, "err");
        }
      });
      document.getElementById("resetDefaultsBtn").addEventListener("click", async () => {
        try {
          await api(`/api/admin/users/${userId}`, {
            method: "PATCH",
            body: JSON.stringify({ reset_defaults_to_role: true }),
          });
          setStatus(status, "Defaults reset to role.", "ok");
          await loadUsers();
          paintUsersTable();
          await renderSelectedUserEditor(userId);
        } catch (e) {
          setStatus(status, e.message, "err");
        }
      });
      document.getElementById("clearGroupBtn").addEventListener("click", async () => {
        try {
          await api(`/api/admin/users/${userId}`, { method: "PATCH", body: JSON.stringify({ clear_group: true }) });
          setStatus(status, "Group cleared.", "ok");
          await loadUsers();
          paintUsersTable();
          await renderSelectedUserEditor(userId);
        } catch (e) {
          setStatus(status, e.message, "err");
        }
      });
      document.getElementById("closeEditorBtn").addEventListener("click", () => {
        selectedUserId = null;
        closeUserDetailModal();
        paintUsersTable();
      });

      const convoList = document.getElementById("convoList");
      const transcriptPanel = document.getElementById("transcriptPanel");
      if (!convos.length) {
        convoList.innerHTML = `<p class="meta" style="font-size:12px;color:#64748b;padding:14px;">No conversations yet.</p>`;
        if (transcriptPanel) {
          transcriptPanel.innerHTML = `<div class="empty-transcript">No transcripts for this user.</div>`;
        }
      } else {
        convos.forEach((c) => {
          const btn = document.createElement("button");
          btn.type = "button";
          btn.className = "convo-item" + (c.id === selectedConversationId ? " active" : "");
          btn.innerHTML = `
            <div class="name">${escapeHtml(c.title || "Untitled")}</div>
            <div class="meta">${escapeHtml(c.scenario_slug || "no scenario")} · ${c.message_count} msgs · ${escapeHtml(c.updated_at)}</div>
          `;
          btn.addEventListener("click", async () => {
            selectedConversationId = c.id;
            convoList.querySelectorAll(".convo-item").forEach((el) => el.classList.remove("active"));
            btn.classList.add("active");
            await renderTranscript(userId, c.id);
          });
          convoList.appendChild(btn);
        });
        if (selectedConversationId) await renderTranscript(userId, selectedConversationId);
        else if (transcriptPanel) {
          transcriptPanel.innerHTML = `<div class="empty-transcript">Select a conversation.</div>`;
        }
      }
    } catch (e) {
      host.innerHTML = `<p class="status err">${escapeHtml(e.message)}</p>`;
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
        <div class="actions">
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
    const host = document.getElementById("userEditor") || detailBody;
    const wrap = document.createElement("div");
    wrap.className = "user-editor";
    wrap.innerHTML = `
      <h3 style="font-size:14px;margin-bottom:10px;">Create user</h3>
      <p style="font-size:12px;color:#64748b;margin-bottom:10px;">Leave budget blank to inherit the role default. Mode/LLM blank also inherit.</p>
      <div class="grid-2">
        <div class="field"><label>Username</label><input id="cUsername" /></div>
        <div class="field"><label>Password</label><input id="cPassword" type="password" /></div>
        <div class="field"><label>Budget override (optional)</label><input id="cLimit" type="number" min="0" placeholder="Role default" /></div>
        <div class="field"><label>Group</label><input id="cGroup" placeholder="optional" /></div>
        <div class="field"><label>Role</label><select id="cRole">${roleOptions("student")}</select></div>
        <div class="field"><label>Mode override</label><select id="cMode"><option value="">Role default</option>${modeOptions(null)}</select></div>
        <div class="field"><label>LLM override</label><select id="cLlm">${llmOptions(null, true)}</select></div>
      </div>
      <div class="field"><label>Admin notes</label><textarea id="cNotes" rows="3"></textarea></div>
      <div class="actions">
        <button type="button" class="btn btn-primary" id="createUserBtn">Create</button>
        <button type="button" class="btn btn-secondary" id="cancelCreateBtn">Cancel</button>
      </div>
      <div id="createStatus" class="status"></div>
    `;
    if (host.id === "userEditor") {
      host.innerHTML = "";
      host.appendChild(wrap);
    } else {
      detailBody.prepend(wrap);
    }
    document.getElementById("cancelCreateBtn")?.addEventListener("click", () => {
      if (host.id === "userEditor") host.innerHTML = "";
      else wrap.remove();
    });
    document.getElementById("createUserBtn").addEventListener("click", async () => {
      const status = document.getElementById("createStatus");
      try {
        const limitRaw = document.getElementById("cLimit").value;
        const payload = {
          username: document.getElementById("cUsername").value,
          password: document.getElementById("cPassword").value,
          group_name: document.getElementById("cGroup").value || null,
          admin_notes: document.getElementById("cNotes").value || null,
          role: document.getElementById("cRole").value,
          default_response_mode: document.getElementById("cMode").value || null,
          default_llm_choice: document.getElementById("cLlm").value || null,
        };
        if (limitRaw !== "") {
          payload.token_limit = Number(limitRaw);
          payload.budget_is_override = true;
        }
        const created = await api("/api/admin/users", {
          method: "POST",
          body: JSON.stringify(payload),
        });
        setStatus(status, `Created ${created.username}`, "ok");
        selectedUserId = created.id;
        await refreshUsersView(true);
      } catch (e) {
        setStatus(status, e.message, "err");
      }
    });
  }

  async function renderTokens() {
    detailTitle.textContent = "Token monitor";
    detailBody.innerHTML = `<p class="status">Loading…</p>`;
    try {
      const data = await api("/api/admin/tokens");
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

      const ranked = (data.users || [])
        .slice()
        .sort((a, b) => b.tokens_used - a.tokens_used)
        .map((u) => {
          const pct = u.token_limit > 0 ? Math.min(100, Math.round((100 * u.tokens_used) / u.token_limit)) : 0;
          return `
            <button type="button" class="user-item token-user" data-id="${u.id}">
              <div class="name">${escapeHtml(u.username)}
                <span class="badge">${escapeHtml(u.role || (u.is_admin ? "admin" : "student"))}</span>
              </div>
              <div class="meta">${fmtTokens(u.tokens_used)} / ${fmtTokens(u.token_limit)} (${pct}%) · ${escapeHtml(u.group_name || "ungrouped")}</div>
            </button>`;
        })
        .join("");

      detailBody.innerHTML = `
        <div class="stats">
          <div class="stat"><div class="label">Users</div><div class="value">${data.user_count}</div></div>
          <div class="stat"><div class="label">Tokens used</div><div class="value">${fmtTokens(data.total_tokens_used)}</div></div>
          <div class="stat"><div class="label">Token pool</div><div class="value">${fmtTokens(data.total_token_limit)}</div></div>
          <div class="stat"><div class="label">Exhausted</div><div class="value">${data.exhausted_users}</div></div>
        </div>
        <h3 style="font-size:14px;margin:16px 0 8px;">By group</h3>
        <div class="stats">${groups || "<p class='meta'>No groups assigned yet.</p>"}</div>
        <h3 style="font-size:14px;margin:16px 0 8px;">By user</h3>
        <div id="tokenUserList" class="token-user-grid">${ranked || "<p class='meta'>No users.</p>"}</div>
      `;
      detailBody.querySelectorAll(".token-user").forEach((btn) => {
        btn.addEventListener("click", () => {
          selectedUserId = Number(btn.dataset.id);
          setView("users");
        });
      });
    } catch (e) {
      detailBody.innerHTML = `<p class="status err">${escapeHtml(e.message)}</p>`;
    }
  }

  async function renderAppKeys() {
    detailTitle.textContent = "App-wide keys";
    detailBody.innerHTML = `<p class="status">Loading…</p>`;
    try {
      const data = await api("/api/admin/app-keys");
      const byProvider = Object.fromEntries((data.keys || []).map((k) => [k.provider, k]));
      const cards = PROVIDERS.map((p) => {
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
      }).join("");
      detailBody.innerHTML = `
        <div class="app-keys-grid">${cards}</div>
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
          await loadConfigChoices(true);
        } catch (e) {
          setStatus(status, e.message, "err");
        }
      });
      const hint = document.createElement("p");
      hint.style.cssText = "margin-bottom:12px;font-size:13px;color:#64748b;";
      hint.textContent =
        "Keys stored here are available to every user as platform models (billed against their shared interview budget).";
      detailBody.prepend(hint);
    } catch (e) {
      detailBody.innerHTML = `<p class="status err">${escapeHtml(e.message)}</p>`;
    }
  }

  async function renderDefaults() {
    detailTitle.textContent = "Role defaults";
    detailBody.innerHTML = `<p class="status">Loading…</p>`;
    try {
      await loadSettings();
      await loadConfigChoices();
      detailBody.innerHTML = roleDefaultsMarkup();
      bindRoleDefaultsPanel();
    } catch (e) {
      detailBody.innerHTML = `<p class="status err">${escapeHtml(e.message)}</p>`;
    }
  }

  function parseNameLines(raw) {
    return String(raw || "")
      .split(/[\n,]+/)
      .map((s) => s.trim())
      .filter(Boolean);
  }

  async function loadScenarios() {
    if (scenariosCache) return scenariosCache;
    try {
      scenariosCache = await api("/api/scenarios");
    } catch {
      scenariosCache = [];
    }
    return scenariosCache;
  }

  function scenarioSelectHtml(scenarios, selected, id) {
    const opts = [`<option value="">(none)</option>`].concat(
      (scenarios || []).map((s) => {
        const slug = s.slug || "";
        const label = s.title ? `${s.title} (${slug})` : slug;
        const sel = slug === (selected || "") ? "selected" : "";
        return `<option value="${escapeAttr(slug)}" ${sel}>${escapeHtml(label)}</option>`;
      })
    );
    return `<select id="${id}">${opts.join("")}</select>`;
  }

  function closeTeamCreateModal() {
    const modal = document.getElementById("teamCreateModal");
    const body = document.getElementById("teamCreateModalBody");
    if (modal) {
      modal.classList.remove("open");
      modal.setAttribute("aria-hidden", "true");
    }
    if (body) body.innerHTML = "";
  }

  async function openTeamCreateModal(students, scenarios) {
    const modal = document.getElementById("teamCreateModal");
    const body = document.getElementById("teamCreateModalBody");
    if (!modal || !body) return;
    const ownerOptions = (students || [])
      .map(
        (u) =>
          `<option value="${escapeAttr(u.username)}">${escapeHtml(u.username)}</option>`
      )
      .join("");
    body.innerHTML = `
      <p style="font-size:13px;color:#64748b;margin:0 0 12px;">
        Group name, scenario, repository (no commit hash), member names, and one student login.
      </p>
      <div class="team-detail-grid">
        <div class="field"><label>Group name</label><input id="teamName" placeholder="Team Alpha" /></div>
        <div class="field"><label>Scenario</label>${scenarioSelectHtml(scenarios, "", "teamScenario")}</div>
        <div class="field field-span"><label>Repository URL</label><input id="teamRepo" placeholder="https://github.com/org/repo or fixture://demo" /></div>
        <div class="field field-span"><label>Group member names</label>
          <textarea id="teamParticipantNames" rows="3" placeholder="Alex Rivera&#10;Jordan Lee"></textarea>
        </div>
        <div class="field field-span"><label>Student login</label>
          <select id="teamOwner">${ownerOptions || "<option value=\"\">No student accounts</option>"}</select>
        </div>
      </div>
      <div class="actions" style="margin-top:12px;">
        <button type="button" class="btn btn-primary" id="createTeamBtn">Create group</button>
        <button type="button" class="btn btn-secondary" id="cancelCreateTeamBtn">Cancel</button>
      </div>
      <div id="teamStatus" class="status"></div>
    `;
    modal.classList.add("open");
    modal.setAttribute("aria-hidden", "false");
    const status = document.getElementById("teamStatus");
    document.getElementById("cancelCreateTeamBtn")?.addEventListener("click", closeTeamCreateModal);
    document.getElementById("createTeamBtn")?.addEventListener("click", async () => {
      try {
        const name = document.getElementById("teamName")?.value.trim();
        const owner = document.getElementById("teamOwner")?.value.trim();
        const scenario = document.getElementById("teamScenario")?.value.trim();
        const githubUrl = document.getElementById("teamRepo")?.value.trim();
        const participantNames = parseNameLines(document.getElementById("teamParticipantNames")?.value);
        if (!name || !owner) {
          setStatus(status, "Group name and student login are required.", "err");
          return;
        }
        const created = await api("/api/admin/teams", {
          method: "POST",
          body: JSON.stringify({
            name,
            owner_username: owner,
            scenario_slug: scenario || null,
            github_url: githubUrl || null,
            participant_names: participantNames,
          }),
        });
        if (created?.id) selectedTeamId = created.id;
        closeTeamCreateModal();
        await renderTeams();
      } catch (e) {
        setStatus(status, e.message, "err");
      }
    });
  }

  function paintTeamDetail(team, students, scenarios) {
    if (!team) {
      detailTitle.textContent = "Group setup";
      detailBody.innerHTML = `<p style="color:#64748b;font-size:14px;">Select a team, or use <strong>Create group</strong> to add one.</p>`;
      return;
    }
    detailTitle.textContent = team.name || "Group setup";
    const members = (team.members || []).map((m) => m.username);
    const studentNames = new Set((students || []).map((u) => u.username));
    const selectedLogin =
      members.find((name) => studentNames.has(name)) || members[0] || "";
    const loginOptions =
      (students || [])
        .map((u) => {
          const sel = u.username === selectedLogin ? "selected" : "";
          return `<option value="${escapeAttr(u.username)}" ${sel}>${escapeHtml(u.username)}</option>`;
        })
        .join("") || `<option value="">No student accounts</option>`;
    const namesText = (team.participant_names || []).join("\n");
    const repoUrl = team.repository?.github_url || "";
    const repoStatus = team.repository
      ? `${team.repository.repo}@${String(team.repository.commit_sha || "").slice(0, 7)} · ${team.repository.index_status}`
      : "No repository yet";
    detailBody.innerHTML = `
      <p class="meta" style="margin:0 0 12px;">id <code>${escapeHtml(team.id)}</code> · ${escapeHtml(repoStatus)}</p>
      <div class="team-detail-grid">
        <div class="field"><label>Group name</label><input id="editTeamName" value="${escapeAttr(team.name)}" /></div>
        <div class="field"><label>Scenario</label>${scenarioSelectHtml(scenarios, team.scenario_slug || "", "editTeamScenario")}</div>
        <div class="field field-span"><label>Repository URL</label><input id="editTeamRepo" value="${escapeAttr(repoUrl)}" placeholder="https://github.com/org/repo" /></div>
        <div class="field field-span"><label>Group member names</label>
          <textarea id="editTeamNames" rows="3">${escapeHtml(namesText)}</textarea>
        </div>
        <div class="field field-span"><label>Student login</label>
          <select id="editTeamLogin">${loginOptions}</select>
        </div>
      </div>
      <div class="actions" style="margin-top:12px;">
        <button type="button" class="btn btn-primary" id="saveTeamDetailsBtn">Save group details</button>
        <button type="button" class="btn btn-secondary" id="deleteTeamBtn">Delete team</button>
        <a class="btn btn-secondary" href="/teams/${encodeURIComponent(team.id)}/exit">Open interview</a>
      </div>
      <div id="teamMemberStatus" class="status"></div>
    `;
    document.getElementById("saveTeamDetailsBtn")?.addEventListener("click", async () => {
      const ms = document.getElementById("teamMemberStatus");
      try {
        const username = document.getElementById("editTeamLogin")?.value.trim();
        if (!username) {
          setStatus(ms, "Pick one student login.", "err");
          return;
        }
        await api(`/api/admin/teams/${encodeURIComponent(team.id)}`, {
          method: "PATCH",
          body: JSON.stringify({
            name: document.getElementById("editTeamName")?.value.trim(),
            scenario_slug: document.getElementById("editTeamScenario")?.value.trim() || null,
            github_url: document.getElementById("editTeamRepo")?.value.trim() || null,
            participant_names: parseNameLines(document.getElementById("editTeamNames")?.value),
          }),
        });
        await api(`/api/admin/teams/${encodeURIComponent(team.id)}/members`, {
          method: "PUT",
          body: JSON.stringify({ usernames: [username] }),
        });
        setStatus(ms, "Group details saved.", "ok");
        await renderTeams();
      } catch (e) {
        setStatus(ms, e.message, "err");
      }
    });
    document.getElementById("deleteTeamBtn")?.addEventListener("click", async () => {
      const ms = document.getElementById("teamMemberStatus");
      if (!confirm("Delete this team?")) return;
      try {
        await api(`/api/admin/teams/${encodeURIComponent(team.id)}`, { method: "DELETE" });
        selectedTeamId = null;
        await renderTeams();
      } catch (e) {
        setStatus(ms, e.message, "err");
      }
    });
  }

  async function renderTeams() {
    listTitle.textContent = "Teams";
    detailTitle.textContent = "Group setup";
    listToolbar.innerHTML = "";
    listBody.innerHTML = `<p class="status">Loading…</p>`;
    detailBody.innerHTML = `<p class="status">Loading…</p>`;
    const fab = document.getElementById("createTeamFab");
    if (fab) fab.hidden = false;
    try {
      const [teams, userRows, scenarios] = await Promise.all([
        api("/api/admin/teams"),
        api("/api/admin/users"),
        loadScenarios(),
      ]);
      const students = (userRows || []).filter((u) => (u.role || "student") === "student");
      if (selectedTeamId && !(teams || []).some((t) => t.id === selectedTeamId)) {
        selectedTeamId = null;
      }
      if (!selectedTeamId && (teams || []).length) selectedTeamId = teams[0].id;

      listBody.innerHTML =
        (teams || [])
          .map((t) => {
            const members = (t.members || []).map((m) => m.username).join(", ") || "—";
            const repo = t.repository;
            const repoMeta = repo
              ? `${repo.repo || "repo"} · ${repo.index_status}`
              : "no repo";
            const active = t.id === selectedTeamId ? " active" : "";
            return `
            <button type="button" class="user-item team-item${active}" data-id="${escapeAttr(t.id)}">
              <div class="name">${escapeHtml(t.name)}</div>
              <div class="meta">${escapeHtml(t.scenario_slug || "no scenario")} · ${escapeHtml(repoMeta)} · ${escapeHtml(members)}</div>
            </button>`;
          })
          .join("") || `<p class="meta" style="padding:12px;">No teams yet. Use Create group.</p>`;

      const selected = (teams || []).find((t) => t.id === selectedTeamId) || null;
      paintTeamDetail(selected, students, scenarios);

      listBody.querySelectorAll(".team-item").forEach((btn) => {
        btn.addEventListener("click", () => {
          selectedTeamId = btn.dataset.id;
          listBody.querySelectorAll(".team-item").forEach((el) => el.classList.remove("active"));
          btn.classList.add("active");
          const team = (teams || []).find((t) => t.id === selectedTeamId);
          paintTeamDetail(team, students, scenarios);
        });
      });

      if (fab) {
        fab.onclick = () => openTeamCreateModal(students, scenarios);
      }
    } catch (e) {
      listBody.innerHTML = `<p class="status err">${escapeHtml(e.message)}</p>`;
      detailBody.innerHTML = `<p class="status err">${escapeHtml(e.message)}</p>`;
    }
  }

  async function renderRoster() {
    listTitle.textContent = "Class roster";
    detailTitle.textContent = "Student status";
    listToolbar.innerHTML = `
      <button type="button" class="btn" id="importRosterBtn">Import classlist.csv</button>
      <button type="button" class="btn btn-secondary" id="uploadRosterBtn">Upload CSV</button>
      <input type="file" id="rosterFile" accept=".csv,text/csv" hidden />
    `;
    listBody.innerHTML = `<p class="meta" style="padding:12px;">Loading…</p>`;
    detailBody.innerHTML = `<p class="meta">Import the class list, then track who has claimed a group account.</p>`;
    try {
      const data = await api("/api/admin/roster");
      const students = data.students || [];
      listToolbar.insertAdjacentHTML(
        "beforeend",
        `<span class="meta" style="margin-left:8px;">${data.total || 0} students · ${data.claimed || 0} claimed · ${data.groups || 0} groups</span>`,
      );
      listBody.innerHTML =
        students
          .map((s) => {
            const badge =
              s.status === "claimed"
                ? `<span class="badge">claimed</span>`
                : `<span class="badge admin">available</span>`;
            return `<button type="button" class="list-item" data-roster-id="${escapeAttr(s.id)}">
              <strong>${escapeHtml(s.display_name)}</strong>
              <span class="meta">${escapeHtml(s.student_number)} · ${escapeHtml(s.email || "—")}</span>
              ${badge}
            </button>`;
          })
          .join("") || `<p class="meta" style="padding:12px;">No roster yet. Import classlist.csv.</p>`;

      const showStudent = (id) => {
        const s = students.find((row) => row.id === id);
        if (!s) return;
        detailTitle.textContent = s.display_name;
        detailBody.innerHTML = `
          <div class="stack">
            <p><strong>Student ID</strong><br/>${escapeHtml(s.student_number)}</p>
            <p><strong>Email</strong><br/>${escapeHtml(s.email || "—")}</p>
            <p><strong>Status</strong><br/>${escapeHtml(s.status)}</p>
            <p><strong>Group</strong><br/>${escapeHtml(s.group_name || "—")}</p>
            <p><strong>Claimed account</strong><br/>${escapeHtml(s.account_username || "—")}</p>
            <p><strong>Team id</strong><br/><code>${escapeHtml(s.team_id || "—")}</code></p>
            <p><strong>Claimed at</strong><br/>${escapeHtml(s.claimed_at || "—")}</p>
          </div>`;
      };

      listBody.querySelectorAll("[data-roster-id]").forEach((btn) => {
        btn.addEventListener("click", () => showStudent(btn.getAttribute("data-roster-id")));
      });
      if (students[0]) showStudent(students[0].id);

      const fileInput = document.getElementById("rosterFile");
      document.getElementById("importRosterBtn")?.addEventListener("click", async () => {
        if (!confirm("Import/refresh from repo classlist.csv on the server?")) return;
        try {
          await api("/api/admin/roster/import", { method: "POST" });
          await renderRoster();
        } catch (e) {
          detailBody.innerHTML = `<p class="status err">${escapeHtml(e.message)}</p>`;
        }
      });
      document.getElementById("uploadRosterBtn")?.addEventListener("click", () => fileInput?.click());
      fileInput?.addEventListener("change", async () => {
        const file = fileInput.files?.[0];
        if (!file) return;
        const body = new FormData();
        body.append("file", file);
        try {
          const r = await fetch("/api/admin/roster/import-upload", {
            method: "POST",
            headers: authHeaders(false),
            body,
          });
          const text = await r.text();
          if (!r.ok) throw new Error(text || r.statusText);
          await renderRoster();
        } catch (e) {
          detailBody.innerHTML = `<p class="status err">${escapeHtml(e.message)}</p>`;
        } finally {
          fileInput.value = "";
        }
      });
    } catch (e) {
      listBody.innerHTML = `<p class="status err">${escapeHtml(e.message)}</p>`;
      detailBody.innerHTML = `<p class="status err">${escapeHtml(e.message)}</p>`;
    }
  }

  async function render() {
    if (view === "users") {
      setLayout("users");
      await loadUsers();
      await renderUsersGrid();
    } else if (view === "roster") {
      setLayout("list");
      await renderRoster();
    } else if (view === "teams") {
      setLayout("list");
      await renderTeams();
    } else if (view === "tokens") {
      setLayout("plain");
      await renderTokens();
    } else if (view === "appkeys") {
      setLayout("plain");
      await renderAppKeys();
    } else if (view === "defaults") {
      setLayout("plain");
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
    const params = new URLSearchParams(window.location.search);
    const initial = params.get("view");
    if (initial && ["users", "roster", "teams", "tokens", "appkeys", "defaults"].includes(initial)) {
      view = initial;
    }
    syncViewTabs();
    await loadConfigChoices();
    await render();
  }

  document.getElementById("loginBtn")?.addEventListener("click", doLogin);
  document.getElementById("loginPassword")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") doLogin();
  });
  document.getElementById("logoutBtn")?.addEventListener("click", logout);
  document.getElementById("denyLogout")?.addEventListener("click", logout);
  document.getElementById("userDetailModalClose")?.addEventListener("click", () => {
    selectedUserId = null;
    closeUserDetailModal();
    paintUsersTable();
  });
  document.getElementById("userDetailModal")?.addEventListener("click", (e) => {
    if (e.target === e.currentTarget) {
      selectedUserId = null;
      closeUserDetailModal();
      paintUsersTable();
    }
  });
  document.getElementById("teamCreateModalClose")?.addEventListener("click", closeTeamCreateModal);
  document.getElementById("teamCreateModal")?.addEventListener("click", (e) => {
    if (e.target === e.currentTarget) closeTeamCreateModal();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    const teamModal = document.getElementById("teamCreateModal");
    if (teamModal?.classList.contains("open")) {
      closeTeamCreateModal();
      return;
    }
    const modal = document.getElementById("userDetailModal");
    if (modal?.classList.contains("open")) {
      selectedUserId = null;
      closeUserDetailModal();
      paintUsersTable();
    }
  });
  bindNav();
  boot();
})();
