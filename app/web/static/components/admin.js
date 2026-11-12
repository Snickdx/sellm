(() => {
  const PROVIDERS = [
    { id: "openai", label: "OpenAI", placeholder: "sk-..." },
    { id: "anthropic", label: "Anthropic", placeholder: "sk-ant-..." },
    { id: "gemini", label: "Gemini", placeholder: "AIza..." },
    { id: "groq", label: "Groq", placeholder: "gsk_..." },
    { id: "openrouter", label: "OpenRouter", placeholder: "sk-or-..." },
  ];
  const MODES = [
    ["any", "Any (unbounded)"],
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
  let selectedUserIds = new Set();
  let selectedConversationId = null;
  let selectedTeamId = null;
  let selectedRosterId = null;
  let scenariosCache = null;
  let llmChoices = [];
  let appSettings = null;
  let selectedRoleDefaults = "student";
  let roleDraft = null;
  let roleModePicker = null;
  let roleLlmPicker = null;
  const userAllowlistPickers = new Map();

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
    if (view !== "roster") {
      selectedRosterId = null;
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

  function parseAllowlist(raw) {
    if (raw == null || raw === "") return [];
    return String(raw)
      .split(",")
      .map((p) => p.trim())
      .filter(Boolean);
  }

  function serializeAllowlist(values) {
    const cleaned = [];
    const seen = new Set();
    (values || []).forEach((v) => {
      const value = String(v || "").trim();
      if (!value) return;
      const key = value.toLowerCase();
      if (seen.has(key)) return;
      seen.add(key);
      cleaned.push(value);
    });
    if (!cleaned.length) return "";
    if (cleaned.some((v) => v.toLowerCase() === "any")) return "any";
    return cleaned.join(",");
  }

  function roleOptions(selected) {
    return ROLES.map(
      ([v, label]) => `<option value="${v}" ${selected === v ? "selected" : ""}>${label}</option>`
    ).join("");
  }

  function modeCatalog() {
    return MODES.map(([id, label]) => ({ id, label }));
  }

  function llmCatalog(extraIds = []) {
    const opts = [{ id: "any", label: "Any (unbounded)" }];
    const seen = new Set(["any"]);
    llmChoices.forEach((c) => {
      const id = String(c.id || "").trim();
      if (!id || seen.has(id.toLowerCase())) return;
      seen.add(id.toLowerCase());
      opts.push({ id, label: c.label || id });
    });
    (extraIds || []).forEach((id) => {
      const value = String(id || "").trim();
      if (!value || value === "any" || seen.has(value.toLowerCase())) return;
      seen.add(value.toLowerCase());
      opts.push({ id: value, label: `${value} (saved)` });
    });
    return opts;
  }

  function modeLabel(raw) {
    const parts = parseAllowlist(raw);
    if (!parts.length) return "—";
    if (parts.some((p) => p.toLowerCase() === "any")) return "Any (unbounded)";
    return parts
      .map((id) => {
        const hit = MODES.find(([v]) => v === id);
        return hit ? hit[1] : id;
      })
      .join(", ");
  }

  function llmLabel(raw) {
    const parts = parseAllowlist(raw);
    if (!parts.length) return "Auto / role default";
    if (parts.some((p) => p.toLowerCase() === "any")) return "Any (unbounded)";
    return parts
      .map((id) => {
        const hit = llmChoices.find((c) => c.id === id);
        return hit ? hit.label : id;
      })
      .join(", ");
  }

  /**
   * Chip + autocomplete allowlist picker (Mode / LLM).
   * options: [{ id, label }], selected: raw csv or id[].
   * Returns { getValues, getSerialized, setSerialized }.
   */
  function mountAllowlistPicker(root, { options = [], selected = "", placeholder = "Add…", portal = false } = {}) {
    if (!root) return { getValues: () => [], getSerialized: () => "", setSerialized: () => {} };
    const catalog = (options || [])
      .map((o) => ({
        id: String(o.id || "").trim(),
        label: String(o.label || o.id || "").trim(),
      }))
      .filter((o) => o.id && o.label);
    const byId = new Map(catalog.map((o) => [o.id.toLowerCase(), o]));
    const selectedRows = [];
    const seen = new Set();

    function addValue(id, { silent = false } = {}) {
      const key = String(id || "").trim();
      if (!key) return false;
      if (key.toLowerCase() === "any") {
        selectedRows.splice(0, selectedRows.length, { id: "any", label: byId.get("any")?.label || "Any (unbounded)" });
        seen.clear();
        seen.add("any");
        if (!silent) render();
        return true;
      }
      if (seen.has("any")) {
        selectedRows.splice(0, selectedRows.length);
        seen.clear();
      }
      if (seen.has(key.toLowerCase())) return false;
      const opt = byId.get(key.toLowerCase()) || { id: key, label: key };
      seen.add(key.toLowerCase());
      selectedRows.push(opt);
      if (!silent) render();
      return true;
    }

    parseAllowlist(selected).forEach((id) => addValue(id, { silent: true }));

    root.classList.add("name-picker", "allowlist-picker");
    root.innerHTML = `<div class="name-picker-badges" data-badges></div>`;
    const badgesEl = root.querySelector("[data-badges]");
    const suggestEl = document.createElement("ul");
    suggestEl.className = "name-suggest";
    suggestEl.hidden = true;
    if (!portal) root.appendChild(suggestEl);
    const input = document.createElement("input");
    input.type = "search";
    input.className = "name-picker-input";
    input.placeholder = placeholder;
    input.setAttribute("autocomplete", "off");
    input.setAttribute("aria-autocomplete", "list");
    badgesEl.appendChild(input);

    let activeIndex = -1;
    let filtered = [];

    function getValues() {
      return selectedRows.map((r) => r.id);
    }

    function getSerialized() {
      return serializeAllowlist(getValues());
    }

    function setSerialized(raw) {
      selectedRows.splice(0, selectedRows.length);
      seen.clear();
      parseAllowlist(raw).forEach((id) => addValue(id, { silent: true }));
      render();
    }

    function placeSuggest() {
      if (!portal) return;
      const rect = root.getBoundingClientRect();
      suggestEl.style.position = "fixed";
      suggestEl.style.left = `${Math.round(rect.left)}px`;
      suggestEl.style.top = `${Math.round(rect.bottom + 4)}px`;
      suggestEl.style.width = `${Math.max(Math.round(rect.width), 200)}px`;
      suggestEl.style.right = "auto";
      suggestEl.style.zIndex = "1200";
    }

    function hideSuggest() {
      suggestEl.hidden = true;
      suggestEl.innerHTML = "";
      activeIndex = -1;
      filtered = [];
      if (portal && suggestEl.parentNode) suggestEl.remove();
    }

    function removeValue(id) {
      const idx = selectedRows.findIndex((r) => r.id.toLowerCase() === String(id).toLowerCase());
      if (idx < 0) return;
      selectedRows.splice(idx, 1);
      seen.delete(String(id).toLowerCase());
      render();
    }

    function render() {
      badgesEl.querySelectorAll(".name-badge").forEach((el) => el.remove());
      selectedRows.forEach((row) => {
        const badge = document.createElement("span");
        badge.className = "name-badge";
        badge.innerHTML = `<span>${escapeHtml(row.label)}</span>`;
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "name-badge-remove";
        btn.setAttribute("aria-label", `Remove ${row.label}`);
        btn.textContent = "×";
        btn.addEventListener("click", () => {
          removeValue(row.id);
          input.focus();
        });
        badge.appendChild(btn);
        badgesEl.insertBefore(badge, input);
      });
      input.placeholder = selectedRows.length ? "Add…" : placeholder;
    }

    function matchSuggestions(q) {
      const query = String(q || "").trim().toLowerCase();
      return catalog
        .filter((o) => {
          if (seen.has(o.id.toLowerCase())) return false;
          if (!query) return true;
          return `${o.label} ${o.id}`.toLowerCase().includes(query);
        })
        .slice(0, 10);
    }

    function paintActive() {
      suggestEl.querySelectorAll("button").forEach((btn, i) => {
        btn.setAttribute("aria-selected", i === activeIndex ? "true" : "false");
      });
    }

    function showSuggest(q) {
      filtered = matchSuggestions(q);
      activeIndex = filtered.length ? 0 : -1;
      if (!filtered.length) {
        hideSuggest();
        return;
      }
      if (portal && !suggestEl.parentNode) document.body.appendChild(suggestEl);
      placeSuggest();
      suggestEl.hidden = false;
      suggestEl.innerHTML = "";
      filtered.forEach((row, i) => {
        const li = document.createElement("li");
        const btn = document.createElement("button");
        btn.type = "button";
        btn.setAttribute("aria-selected", i === activeIndex ? "true" : "false");
        btn.innerHTML = `<strong>${escapeHtml(row.label)}</strong>`;
        btn.addEventListener("mousedown", (e) => {
          e.preventDefault();
          addValue(row.id);
          input.value = "";
          hideSuggest();
          input.focus();
        });
        li.appendChild(btn);
        suggestEl.appendChild(li);
      });
    }

    input.addEventListener("input", () => showSuggest(input.value));
    input.addEventListener("focus", () => showSuggest(input.value));
    input.addEventListener("blur", () => setTimeout(hideSuggest, 120));
    input.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown" && filtered.length) {
        e.preventDefault();
        activeIndex = (activeIndex + 1) % filtered.length;
        paintActive();
        return;
      }
      if (e.key === "ArrowUp" && filtered.length) {
        e.preventDefault();
        activeIndex = (activeIndex - 1 + filtered.length) % filtered.length;
        paintActive();
        return;
      }
      if (e.key === "Escape") {
        hideSuggest();
        return;
      }
      if (e.key === "Backspace" && !input.value && selectedRows.length) {
        removeValue(selectedRows[selectedRows.length - 1].id);
        return;
      }
      if ((e.key === "Enter" || e.key === "Tab") && filtered.length && activeIndex >= 0) {
        e.preventDefault();
        addValue(filtered[activeIndex].id);
        input.value = "";
        hideSuggest();
      }
    });
    if (portal) {
      window.addEventListener("scroll", () => {
        if (!suggestEl.hidden) placeSuggest();
      }, true);
      window.addEventListener("resize", () => {
        if (!suggestEl.hidden) placeSuggest();
      });
    }

    render();
    return { getValues, getSerialized, setSerialized };
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
          <div class="field"><label>Mode</label><div id="roleMode" class="allowlist-picker"></div><div class="field-hint">Chip multi-select · Any = unbounded</div></div>
          <div class="field"><label>LLM</label><div id="roleLlm" class="allowlist-picker"></div><div class="field-hint">Chip multi-select · Any = unbounded</div></div>
          <div class="field"><label>Budget</label><input id="roleBudget" type="number" min="0" /></div>
          <div class="actions"><button type="button" class="btn btn-primary" id="saveRoleDefaultsBtn">Save</button></div>
        </div>
        <div id="roleDefaultsStatus" class="status"></div>
      </div>
    `;
  }

  function captureRoleDraft() {
    if (!roleDraft) roleDraft = roleDefaultsFromSettings(appSettings);
    const budgetEl = document.getElementById("roleBudget");
    if (!budgetEl || !roleModePicker || !roleLlmPicker) return;
    roleDraft[selectedRoleDefaults] = {
      mode: roleModePicker.getSerialized(),
      llm: roleLlmPicker.getSerialized(),
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

    const modeSelected = draft.mode || (role === "admin" ? "" : "vector");
    const llmSelected = draft.llm || "";
    roleModePicker = mountAllowlistPicker(modeEl, {
      options: modeCatalog(),
      selected: modeSelected,
      placeholder: "Add mode…",
    });
    roleLlmPicker = mountAllowlistPicker(llmEl, {
      options: llmCatalog(parseAllowlist(llmSelected)),
      selected: llmSelected,
      placeholder: "Add LLM…",
    });
    budgetEl.value = Number(draft.budget || 0);

    document.querySelectorAll(".role-toggle button").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.role === role);
    });
    const hint = document.getElementById("roleDefaultsHint");
    if (hint) {
      hint.textContent =
        role === "admin"
          ? "Applies to admins without overrides. Empty Mode/LLM = same as tester."
          : `Applies to all ${role}s without overrides. Multi-select allowed combinations.`;
    }
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

  function syncUsersDeleteButton() {
    const btn = document.getElementById("deleteUsersBtn");
    const countEl = document.getElementById("usersSelectedCount");
    const n = selectedUserIds.size;
    if (countEl) countEl.textContent = n ? `${n} selected` : "";
    if (btn) {
      btn.disabled = n === 0;
      btn.textContent = n > 1 ? `Delete ${n}` : "Delete selected";
    }
    const selectAll = document.getElementById("usersSelectAll");
    if (selectAll) {
      const boxes = [...document.querySelectorAll(".u-select")];
      const checked = boxes.filter((b) => b.checked).length;
      selectAll.checked = boxes.length > 0 && checked === boxes.length;
      selectAll.indeterminate = checked > 0 && checked < boxes.length;
    }
  }

  async function resetUserPassword(userId, statusEl) {
    const user = users.find((u) => u.id === userId);
    const label = user?.username || String(userId);
    if (!confirm(`Reset password for ${label}? The new password is shown only once.`)) return;
    try {
      const result = await api(`/api/admin/users/${userId}/reset-password`, { method: "POST" });
      setStatus(
        statusEl,
        `${result.message} Username: ${result.username} · Password: ${result.password}`,
        "ok",
      );
    } catch (e) {
      setStatus(statusEl, e.message, "err");
    }
  }

  async function deleteSelectedUsers() {
    const status = document.getElementById("usersGridStatus");
    const ids = [...selectedUserIds];
    if (!ids.length) return;
    const names = ids
      .map((id) => users.find((u) => u.id === id)?.username || String(id))
      .slice(0, 8);
    const more = ids.length > names.length ? ` (+${ids.length - names.length} more)` : "";
    const ok = window.confirm(
      `Delete ${ids.length} user${ids.length === 1 ? "" : "s"}?\n\n${names.join(", ")}${more}\n\nThis removes their chats, keys, and group membership. Cannot be undone.`
    );
    if (!ok) return;
    const btn = document.getElementById("deleteUsersBtn");
    if (btn) btn.disabled = true;
    try {
      const result = await api("/api/admin/users/bulk-delete", {
        method: "POST",
        body: JSON.stringify({ user_ids: ids }),
      });
      const deleted = Array.isArray(result?.deleted) ? result.deleted : [];
      const skipped = Array.isArray(result?.skipped) ? result.skipped : [];
      const failed = Array.isArray(result?.failed) ? result.failed : [];
      selectedUserIds = new Set();
      if (selectedUserId && deleted.includes(selectedUserId)) {
        selectedUserId = null;
        closeUserDetailModal();
      }
      await loadUsers();
      paintUsersTable();
      const parts = [];
      if (deleted.length) parts.push(`Deleted ${deleted.length}`);
      if (skipped.length) parts.push(`skipped ${skipped.length} (self)`);
      if (failed.length) parts.push(`failed ${failed.length}`);
      const kind = failed.length ? "err" : "ok";
      setStatus(status, parts.join(" · ") || "No changes.", kind);
      if (failed.length) {
        const detail = failed
          .slice(0, 3)
          .map((f) => `${f.id}: ${f.detail}`)
          .join("; ");
        setStatus(status, `${parts.join(" · ")}. ${detail}`, "err");
      }
    } catch (e) {
      setStatus(status, e.message, "err");
      syncUsersDeleteButton();
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

    const visibleIds = new Set(rows.map((u) => u.id));
    selectedUserIds = new Set([...selectedUserIds].filter((id) => visibleIds.has(id) || users.some((u) => u.id === id)));

    tableBody.innerHTML = rows
      .map((u) => {
        const role = u.role || (u.is_admin ? "admin" : "student");
        const exhausted = u.token_limit > 0 && u.tokens_used >= u.token_limit;
        const modeVal = u.default_response_mode || "";
        const llmVal = u.default_llm_choice || "";
        const isSelf =
          Boolean(currentUser) &&
          String(u.username || "").trim().toLowerCase() === String(currentUser).trim().toLowerCase();
        return `
          <tr data-id="${u.id}" class="${u.id === selectedUserId ? "selected" : ""}${selectedUserIds.has(u.id) ? " checked" : ""}">
            <td class="col-check">
              <input type="checkbox" class="u-select" data-id="${u.id}" ${selectedUserIds.has(u.id) ? "checked" : ""} ${isSelf ? "disabled title=\"You cannot delete your own account\"" : ""} />
            </td>
            <td>
              <strong>${escapeHtml(u.username)}</strong>
              ${exhausted ? '<span class="badge warn">exhausted</span>' : ""}
              <div class="meta" style="font-size:11px;color:#64748b;">${u.conversation_count} chats</div>
            </td>
            <td>
              ${
                u.group_name
                  ? `<span class="badge">${escapeHtml(u.group_name)}</span>`
                  : `<span class="meta" style="color:#94a3b8;">ungrouped</span>`
              }
            </td>
            <td>
              <select class="u-role" data-id="${u.id}">${roleOptions(role)}</select>
            </td>
            <td>
              <div class="cell-with-badge cell-allowlist">
                <div class="u-mode allowlist-picker" data-id="${u.id}" title="Role default: ${escapeAttr(modeLabel(u.role_default_response_mode))}"></div>
                ${u.mode_is_override ? '<span class="badge override">override</span>' : '<span class="badge inherit">role</span>'}
                ${!u.mode_is_override ? `<div class="meta allowlist-inherit">Role: ${escapeHtml(modeLabel(u.role_default_response_mode))}</div>` : ""}
              </div>
            </td>
            <td>
              <div class="cell-with-badge cell-allowlist">
                <div class="u-llm allowlist-picker" data-id="${u.id}" title="Role default: ${escapeAttr(llmLabel(u.role_default_llm_choice))}"></div>
                ${u.llm_is_override ? '<span class="badge override">override</span>' : '<span class="badge inherit">role</span>'}
                ${!u.llm_is_override ? `<div class="meta allowlist-inherit">Role: ${escapeHtml(llmLabel(u.role_default_llm_choice))}</div>` : ""}
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
                <button type="button" class="btn-xs u-reset-pw" data-id="${u.id}" title="Generate a new password (shown once)">Password</button>
                <button type="button" class="btn-xs u-edit" data-id="${u.id}">More</button>
              </div>
            </td>
          </tr>`;
      })
      .join("");

    if (!rows.length) {
      tableBody.innerHTML = `<tr><td colspan="8" style="color:#64748b;padding:16px;">No users match.</td></tr>`;
    }

    tableBody.querySelectorAll(".u-select").forEach((box) => {
      box.addEventListener("change", () => {
        const id = Number(box.dataset.id);
        if (box.checked) selectedUserIds.add(id);
        else selectedUserIds.delete(id);
        box.closest("tr")?.classList.toggle("checked", box.checked);
        syncUsersDeleteButton();
      });
    });
    syncUsersDeleteButton();

    userAllowlistPickers.clear();
    rows.forEach((u) => {
      const modeRoot = tableBody.querySelector(`.u-mode[data-id="${u.id}"]`);
      const llmRoot = tableBody.querySelector(`.u-llm[data-id="${u.id}"]`);
      const modeVal = u.default_response_mode || "";
      const llmVal = u.default_llm_choice || "";
      if (modeRoot) {
        userAllowlistPickers.set(
          `${u.id}-mode`,
          mountAllowlistPicker(modeRoot, {
            options: modeCatalog(),
            selected: modeVal,
            placeholder: "Add mode…",
            portal: true,
          })
        );
      }
      if (llmRoot) {
        userAllowlistPickers.set(
          `${u.id}-llm`,
          mountAllowlistPicker(llmRoot, {
            options: llmCatalog(parseAllowlist(llmVal)),
            selected: llmVal,
            placeholder: "Add LLM…",
            portal: true,
          })
        );
      }
    });

    tableBody.querySelectorAll(".u-save").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const id = Number(btn.dataset.id);
        const status = document.getElementById("usersGridStatus");
        try {
          const budgetEl = tableBody.querySelector(`.u-budget[data-id="${id}"]`);
          const roleEl = tableBody.querySelector(`.u-role[data-id="${id}"]`);
          const current = users.find((x) => x.id === id);
          const budget = Number(budgetEl.value);
          const modeAllow = userAllowlistPickers.get(`${id}-mode`)?.getSerialized() || "";
          const llmAllow = userAllowlistPickers.get(`${id}-llm`)?.getSerialized() || "";
          const body = {
            role: roleEl.value,
            default_response_mode: modeAllow || null,
            clear_default_response_mode: !modeAllow,
            default_llm_choice: llmAllow || null,
            clear_default_llm_choice: !llmAllow,
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

    tableBody.querySelectorAll(".u-reset-pw").forEach((btn) => {
      btn.addEventListener("click", () => {
        void resetUserPassword(Number(btn.dataset.id), document.getElementById("usersGridStatus"));
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
      await loadConfigChoices();
      const groups = [...new Set(users.map((u) => u.group_name).filter(Boolean))].sort();
      detailBody.innerHTML = `
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
          <button type="button" class="btn btn-danger" id="deleteUsersBtn" disabled>Delete selected</button>
          <span id="usersSelectedCount" class="meta" style="font-size:12px;color:#64748b;"></span>
        </div>
        <div id="usersGridStatus" class="status"></div>
        <div class="users-table-wrap">
          <table class="users-grid">
            <thead>
              <tr>
                <th class="col-check"><input type="checkbox" id="usersSelectAll" title="Select all visible" /></th>
                <th>User</th>
                <th>Claimed group</th>
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
      document.getElementById("userFilter")?.addEventListener("input", paintUsersTable);
      document.getElementById("groupFilter")?.addEventListener("change", paintUsersTable);
      document.getElementById("roleFilter")?.addEventListener("change", paintUsersTable);
      document.getElementById("addUserBtn")?.addEventListener("click", () => renderCreateUser());
      document.getElementById("usersSelectAll")?.addEventListener("change", (e) => {
        const on = e.target.checked;
        document.querySelectorAll(".u-select:not(:disabled)").forEach((box) => {
          box.checked = on;
          const id = Number(box.dataset.id);
          if (on) selectedUserIds.add(id);
          else selectedUserIds.delete(id);
          box.closest("tr")?.classList.toggle("checked", on);
        });
        syncUsersDeleteButton();
      });
      document.getElementById("deleteUsersBtn")?.addEventListener("click", () => void deleteSelectedUsers());
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
              <button type="button" class="btn btn-secondary" id="resetUserPwBtn">Reset password</button>
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
      document.getElementById("resetUserPwBtn")?.addEventListener("click", () => {
        void resetUserPassword(userId, status);
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
      <p style="font-size:12px;color:#64748b;margin-bottom:10px;">Leave budget blank to inherit the role default. Empty Mode/LLM chips also inherit.</p>
      <div class="grid-2">
        <div class="field"><label>Username</label><input id="cUsername" /></div>
        <div class="field"><label>Password</label><input id="cPassword" type="password" /></div>
        <div class="field"><label>Budget override (optional)</label><input id="cLimit" type="number" min="0" placeholder="Role default" /></div>
        <div class="field"><label>Group</label><input id="cGroup" placeholder="optional" /></div>
        <div class="field"><label>Role</label><select id="cRole">${roleOptions("student")}</select></div>
        <div class="field"><label>Mode override</label><div id="cMode" class="allowlist-picker"></div><div class="field-hint">None selected = role default</div></div>
        <div class="field"><label>LLM override</label><div id="cLlm" class="allowlist-picker"></div><div class="field-hint">None selected = role default</div></div>
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
    const cModePicker = mountAllowlistPicker(document.getElementById("cMode"), {
      options: modeCatalog(),
      selected: "",
      placeholder: "Add mode…",
    });
    const cLlmPicker = mountAllowlistPicker(document.getElementById("cLlm"), {
      options: llmCatalog(),
      selected: "",
      placeholder: "Add LLM…",
    });
    document.getElementById("cancelCreateBtn")?.addEventListener("click", () => {
      if (host.id === "userEditor") host.innerHTML = "";
      else wrap.remove();
    });
    document.getElementById("createUserBtn").addEventListener("click", async () => {
      const status = document.getElementById("createStatus");
      try {
        const limitRaw = document.getElementById("cLimit").value;
        const modeAllow = cModePicker.getSerialized();
        const llmAllow = cLlmPicker.getSerialized();
        const payload = {
          username: document.getElementById("cUsername").value,
          password: document.getElementById("cPassword").value,
          group_name: document.getElementById("cGroup").value || null,
          admin_notes: document.getElementById("cNotes").value || null,
          role: document.getElementById("cRole").value,
          default_response_mode: modeAllow || null,
          default_llm_choice: llmAllow || null,
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

  /**
   * Badge + autocomplete picker for class-list students.
   * selected/catalog: [{ id, display_name, email? }]
   * Returns { getMemberIds }.
   */
  function mountRosterMemberPicker(root, { selected: initial = [], catalog = [] } = {}) {
    if (!root) return { getMemberIds: () => [] };
    const selected = [];
    const seen = new Set();
    (initial || []).forEach((row) => {
      const id = String(row?.id || "").trim();
      const display_name = String(row?.display_name || "").trim();
      if (!id || !display_name || seen.has(id)) return;
      seen.add(id);
      selected.push({
        id,
        display_name,
        email: String(row?.email || "").trim(),
      });
    });

    const students = (catalog || [])
      .map((s) => ({
        id: String(s.id || "").trim(),
        display_name: String(s.display_name || s.name || "").trim(),
        email: String(s.email || s.meta || "").trim(),
      }))
      .filter((s) => s.id && s.display_name);

    root.classList.add("name-picker");
    root.innerHTML = `
      <div class="name-picker-badges" data-badges></div>
      <ul class="name-suggest" data-suggest hidden></ul>
    `;
    const badgesEl = root.querySelector("[data-badges]");
    const suggestEl = root.querySelector("[data-suggest]");
    const input = document.createElement("input");
    input.type = "search";
    input.className = "name-picker-input";
    input.placeholder = selected.length ? "Add from class list…" : "Search class list…";
    input.setAttribute("autocomplete", "off");
    input.setAttribute("aria-autocomplete", "list");
    badgesEl.appendChild(input);

    let activeIndex = -1;
    let filtered = [];

    function getMemberIds() {
      return selected.map((s) => s.id);
    }

    function hideSuggest() {
      suggestEl.hidden = true;
      suggestEl.innerHTML = "";
      activeIndex = -1;
      filtered = [];
    }

    function removeMember(id) {
      const idx = selected.findIndex((s) => s.id === id);
      if (idx < 0) return;
      selected.splice(idx, 1);
      seen.delete(id);
      renderBadges();
    }

    function renderBadges() {
      badgesEl.querySelectorAll(".name-badge").forEach((el) => el.remove());
      selected.forEach((row) => {
        const badge = document.createElement("span");
        badge.className = "name-badge";
        badge.innerHTML = `<span>${escapeHtml(row.display_name)}</span>`;
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "name-badge-remove";
        btn.setAttribute("aria-label", `Remove ${row.display_name}`);
        btn.textContent = "×";
        btn.addEventListener("click", () => {
          removeMember(row.id);
          input.focus();
        });
        badge.appendChild(btn);
        badgesEl.insertBefore(badge, input);
      });
      input.placeholder = selected.length ? "Add from class list…" : "Search class list…";
    }

    function addMember(row) {
      if (!row?.id || seen.has(row.id)) return false;
      seen.add(row.id);
      selected.push({
        id: row.id,
        display_name: row.display_name,
        email: row.email || "",
      });
      input.value = "";
      hideSuggest();
      renderBadges();
      return true;
    }

    function matchSuggestions(q) {
      const query = String(q || "").trim().toLowerCase();
      if (!query) return [];
      return students
        .filter((s) => {
          if (seen.has(s.id)) return false;
          const hay = `${s.display_name} ${s.email}`.toLowerCase();
          return hay.includes(query);
        })
        .slice(0, 8);
    }

    function renderSuggest(q) {
      filtered = matchSuggestions(q);
      if (!filtered.length) {
        hideSuggest();
        return;
      }
      activeIndex = 0;
      suggestEl.hidden = false;
      suggestEl.innerHTML = "";
      filtered.forEach((row, i) => {
        const li = document.createElement("li");
        const btn = document.createElement("button");
        btn.type = "button";
        btn.setAttribute("aria-selected", i === activeIndex ? "true" : "false");
        btn.innerHTML = `<strong>${escapeHtml(row.display_name)}</strong>${
          row.email ? `<span class="hint">${escapeHtml(row.email)}</span>` : ""
        }`;
        btn.addEventListener("mousedown", (e) => {
          e.preventDefault();
          addMember(row);
          input.focus();
        });
        li.appendChild(btn);
        suggestEl.appendChild(li);
      });
    }

    function markActive() {
      [...suggestEl.querySelectorAll("button")].forEach((btn, i) => {
        btn.setAttribute("aria-selected", i === activeIndex ? "true" : "false");
      });
    }

    input.addEventListener("input", () => {
      renderSuggest(input.value.trim());
    });

    input.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown" && filtered.length) {
        e.preventDefault();
        activeIndex = (activeIndex + 1) % filtered.length;
        markActive();
        return;
      }
      if (e.key === "ArrowUp" && filtered.length) {
        e.preventDefault();
        activeIndex = (activeIndex - 1 + filtered.length) % filtered.length;
        markActive();
        return;
      }
      if (e.key === "Escape") {
        hideSuggest();
        return;
      }
      if (e.key === "Backspace" && !input.value && selected.length) {
        removeMember(selected[selected.length - 1].id);
        return;
      }
      if ((e.key === "Enter" || e.key === "Tab") && filtered.length && activeIndex >= 0) {
        e.preventDefault();
        addMember(filtered[activeIndex]);
      }
    });

    input.addEventListener("blur", () => {
      setTimeout(hideSuggest, 120);
    });

    renderBadges();
    return { getMemberIds };
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

  async function openTeamCreateModal(students, scenarios, rosterCatalog) {
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
        Group name, scenario, repository (no commit hash), class-list members, and one student login.
      </p>
      <div class="team-detail-grid">
        <div class="field"><label>Group name</label><input id="teamName" placeholder="Team Alpha" /></div>
        <div class="field"><label>Scenario</label>${scenarioSelectHtml(scenarios, "", "teamScenario")}</div>
        <div class="field field-span"><label>Repository URL</label><input id="teamRepo" placeholder="https://github.com/org/repo or fixture://demo" /></div>
        <div class="field field-span"><label>Group members</label>
          <div id="teamRosterMembers"></div>
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
    const memberPicker = mountRosterMemberPicker(document.getElementById("teamRosterMembers"), {
      selected: [],
      catalog: rosterCatalog || [],
    });
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
        const rosterMemberIds = memberPicker.getMemberIds();
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
            roster_member_ids: rosterMemberIds,
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

  function generateTempPassword(length = 12) {
    const alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789";
    const bytes = new Uint8Array(length);
    crypto.getRandomValues(bytes);
    return [...bytes].map((b) => alphabet[b % alphabet.length]).join("");
  }

  function paintTeamDetail(team, students, scenarios, rosterCatalog) {
    if (!team) {
      detailTitle.textContent = "Group setup";
      detailBody.innerHTML = `<p style="color:#64748b;font-size:14px;">Select a team, or use <strong>Create group</strong> to add one.</p>`;
      return;
    }
    detailTitle.textContent = team.name || "Group setup";
    let studentAccounts = [...(students || [])];
    const members = (team.members || []).map((m) => m.username);
    const studentNames = new Set(studentAccounts.map((u) => u.username));
    const selectedLogin =
      members.find((name) => studentNames.has(name)) || members[0] || "";
    const initialLoginOptions =
      studentAccounts
        .map((u) => {
          const sel = u.username === selectedLogin ? "selected" : "";
          return `<option value="${escapeAttr(u.username)}" data-id="${escapeAttr(String(u.id))}" ${sel}>${escapeHtml(u.username)}</option>`;
        })
        .join("") || `<option value="">No student accounts</option>`;
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
        <div class="field field-span"><label>Group members</label>
          <div id="editTeamMembers"></div>
        </div>
        <div class="field field-span"><label>Student login</label>
          <div class="team-login-row">
            <select id="editTeamLogin">${initialLoginOptions}</select>
            <button type="button" class="btn btn-secondary" id="resetTeamLoginPwBtn">Reset password</button>
            <button type="button" class="btn btn-secondary" id="createTeamLoginBtn">Create login</button>
          </div>
        </div>
      </div>
      <div class="actions" style="margin-top:12px;">
        <button type="button" class="btn btn-primary" id="saveTeamDetailsBtn">Save group details</button>
        <button type="button" class="btn btn-secondary" id="deleteTeamBtn">Delete team</button>
        <a class="btn btn-secondary" href="/teams/${encodeURIComponent(team.id)}/exit">Open interview</a>
      </div>
      <div id="teamMemberStatus" class="status"></div>
    `;
    const memberPicker = mountRosterMemberPicker(document.getElementById("editTeamMembers"), {
      selected: team.roster_members || [],
      catalog: rosterCatalog || [],
    });
    const loginSelect = document.getElementById("editTeamLogin");
    const refreshLoginOptions = (preferUsername) => {
      if (!loginSelect) return;
      const current = preferUsername || loginSelect.value || selectedLogin;
      loginSelect.innerHTML =
        studentAccounts
          .map((u) => {
            const sel = u.username === current ? "selected" : "";
            return `<option value="${escapeAttr(u.username)}" data-id="${escapeAttr(String(u.id))}" ${sel}>${escapeHtml(u.username)}</option>`;
          })
          .join("") || `<option value="">No student accounts</option>`;
      if (preferUsername) loginSelect.value = preferUsername;
    };
    document.getElementById("saveTeamDetailsBtn")?.addEventListener("click", async () => {
      const ms = document.getElementById("teamMemberStatus");
      try {
        const username = loginSelect?.value.trim();
        if (!username) {
          setStatus(ms, "Pick one student login.", "err");
          return;
        }
        const rosterIds = memberPicker.getMemberIds();
        await api(`/api/admin/teams/${encodeURIComponent(team.id)}`, {
          method: "PATCH",
          body: JSON.stringify({
            name: document.getElementById("editTeamName")?.value.trim(),
            scenario_slug: document.getElementById("editTeamScenario")?.value.trim() || null,
            github_url: document.getElementById("editTeamRepo")?.value.trim() || null,
            roster_member_ids: rosterIds,
          }),
        });
        await api(`/api/admin/teams/${encodeURIComponent(team.id)}/members`, {
          method: "PUT",
          body: JSON.stringify({ usernames: [username] }),
        });
        setStatus(ms, `Group details saved · ${rosterIds.length} member${rosterIds.length === 1 ? "" : "s"}.`, "ok");
        selectedTeamId = team.id;
        await renderTeams();
      } catch (e) {
        setStatus(ms, e.message, "err");
      }
    });
    document.getElementById("resetTeamLoginPwBtn")?.addEventListener("click", async () => {
      const ms = document.getElementById("teamMemberStatus");
      const username = loginSelect?.value.trim();
      const user = studentAccounts.find((u) => u.username === username);
      if (!user?.id) {
        setStatus(ms, "Pick a student login first.", "err");
        return;
      }
      await resetUserPassword(user.id, ms);
    });
    document.getElementById("createTeamLoginBtn")?.addEventListener("click", async () => {
      const ms = document.getElementById("teamMemberStatus");
      const suggested =
        (document.getElementById("editTeamName")?.value || team.name || "group")
          .trim()
          .toLowerCase()
          .replace(/[^a-z0-9]+/g, "")
          .slice(0, 16) || "student";
      const username = window.prompt("New student login username:", suggested);
      if (!username || !username.trim()) return;
      const password = generateTempPassword();
      try {
        const created = await api("/api/admin/users", {
          method: "POST",
          body: JSON.stringify({
            username: username.trim(),
            password,
            role: "student",
            group_name: document.getElementById("editTeamName")?.value.trim() || team.name || null,
          }),
        });
        studentAccounts = [...studentAccounts.filter((u) => u.id !== created.id), created].sort((a, b) =>
          String(a.username).localeCompare(String(b.username))
        );
        refreshLoginOptions(created.username);
        setStatus(
          ms,
          `Created login ${created.username}. Password (shown once): ${password}. Click Save group details to assign it to this team.`,
          "ok",
        );
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
      const [teams, userRows, scenarios, roster] = await Promise.all([
        api("/api/admin/teams"),
        api("/api/admin/users"),
        loadScenarios(),
        api("/api/admin/roster").catch(() => null),
      ]);
      const students = (userRows || []).filter((u) => (u.role || "student") === "student");
      const rosterCatalog = (roster?.students || [])
        .map((s) => ({
          id: s.id,
          display_name: s.display_name,
          email: s.email || "",
        }))
        .filter((s) => s.id && s.display_name);
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
      paintTeamDetail(selected, students, scenarios, rosterCatalog);

      listBody.querySelectorAll(".team-item").forEach((btn) => {
        btn.addEventListener("click", () => {
          selectedTeamId = btn.dataset.id;
          listBody.querySelectorAll(".team-item").forEach((el) => el.classList.remove("active"));
          btn.classList.add("active");
          const team = (teams || []).find((t) => t.id === selectedTeamId);
          paintTeamDetail(team, students, scenarios, rosterCatalog);
        });
      });

      if (fab) {
        fab.onclick = () => openTeamCreateModal(students, scenarios, rosterCatalog);
      }
    } catch (e) {
      listBody.innerHTML = `<p class="status err">${escapeHtml(e.message)}</p>`;
      detailBody.innerHTML = `<p class="status err">${escapeHtml(e.message)}</p>`;
    }
  }

  async function renderRoster() {
    listTitle.textContent = "Class roster";
    detailTitle.textContent = "Student status";
    const fab = document.getElementById("createTeamFab");
    if (fab) fab.hidden = true;
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
            return `<button type="button" class="user-item" data-roster-id="${escapeAttr(s.id)}">
              <div class="name">${escapeHtml(s.display_name)} ${badge}</div>
              <div class="meta">${escapeHtml(s.student_number)} · ${escapeHtml(s.email || "—")}</div>
            </button>`;
          })
          .join("") || `<p class="meta" style="padding:12px;">No roster yet. Import classlist.csv.</p>`;

      const showStudent = (id) => {
        const s = students.find((row) => row.id === id);
        if (!s) return;
        selectedRosterId = s.id;
        listBody.querySelectorAll(".user-item").forEach((el) => {
          el.classList.toggle("active", el.getAttribute("data-roster-id") === s.id);
        });
        detailTitle.textContent = s.display_name;
        const claimed = s.status === "claimed" && s.claim_id;
        detailBody.innerHTML = `
          <div class="team-detail-grid">
            <div class="field"><label>Student ID</label><div>${escapeHtml(s.student_number)}</div></div>
            <div class="field"><label>Email</label><div>${escapeHtml(s.email || "—")}</div></div>
            <div class="field"><label>Status</label><div>${escapeHtml(s.status)}</div></div>
            ${
              claimed
                ? `<div class="field"><label>Group</label>
                    <input id="rosterGroupName" value="${escapeAttr(s.group_name || "")}" /></div>
                  <div class="field"><label>Claimed account</label><div>${escapeHtml(s.account_username || "—")}</div></div>
                  <div class="field field-span"><label>Team id</label><div><code>${escapeHtml(s.team_id || "—")}</code></div></div>
                  <div class="field field-span"><label>Claimed at</label><div>${escapeHtml(s.claimed_at || "—")}</div></div>`
                : `<div class="field"><label>Group</label><div>—</div></div>
                   <p class="meta field-span">This student has not claimed a group yet.</p>`
            }
          </div>
          ${
            claimed
              ? `<div class="actions" style="margin-top:12px;">
                  <button type="button" class="btn btn-primary" id="rosterSaveGroupBtn">Save group name</button>
                  <button type="button" class="btn btn-secondary" id="rosterResetPwBtn">Reset password</button>
                  <button type="button" class="btn btn-secondary" id="rosterDeleteGroupBtn">Delete group</button>
                </div>
                <div id="rosterGroupStatus" class="status"></div>`
              : ""
          }`;

        if (!claimed) return;
        const status = document.getElementById("rosterGroupStatus");
        document.getElementById("rosterSaveGroupBtn")?.addEventListener("click", async () => {
          try {
            const name = document.getElementById("rosterGroupName")?.value.trim();
            if (!name || name.length < 2) {
              setStatus(status, "Group name is required.", "err");
              return;
            }
            await api(`/api/admin/roster/groups/${encodeURIComponent(s.claim_id)}`, {
              method: "PATCH",
              body: JSON.stringify({ group_name: name }),
            });
            selectedRosterId = s.id;
            await renderRoster();
          } catch (e) {
            setStatus(status, e.message, "err");
          }
        });
        document.getElementById("rosterResetPwBtn")?.addEventListener("click", async () => {
          if (!confirm(`Reset password for ${s.account_username}? The new password is shown only once.`)) return;
          try {
            const result = await api(
              `/api/admin/roster/groups/${encodeURIComponent(s.claim_id)}/reset-password`,
              { method: "POST" },
            );
            setStatus(
              status,
              `${result.message} Username: ${result.username} · Password: ${result.password}`,
              "ok",
            );
          } catch (e) {
            setStatus(status, e.message, "err");
          }
        });
        document.getElementById("rosterDeleteGroupBtn")?.addEventListener("click", async () => {
          if (
            !confirm(
              `Delete group "${s.group_name || ""}"? Members become available again. The shared login (${s.account_username || "account"}) is kept.`,
            )
          ) {
            return;
          }
          try {
            await api(`/api/admin/roster/groups/${encodeURIComponent(s.claim_id)}`, {
              method: "DELETE",
            });
            selectedRosterId = s.id;
            await renderRoster();
          } catch (e) {
            setStatus(status, e.message, "err");
          }
        });
      };

      listBody.querySelectorAll("[data-roster-id]").forEach((btn) => {
        btn.addEventListener("click", () => showStudent(btn.getAttribute("data-roster-id")));
      });
      if (selectedRosterId && students.some((s) => s.id === selectedRosterId)) {
        showStudent(selectedRosterId);
      } else if (students[0]) {
        showStudent(students[0].id);
      }

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
