/**
 * Group settings: scenario, repository, and roster members.
 */
(function (global) {
  const MIN = 3;
  const MAX = 4;

  const CLAIM_CREDS_KEY = "sellm_claim_creds";

  let state = {
    group: null,
    selected: [],
    scenarios: [],
    githubUrl: "",
    groupName: "",
    scenarioSlug: "",
    busy: false,
    hint: "",
    error: null,
    passwordOnce: null,
    claimCreds: null,
    fallbackUsername: "",
  };
  let bound = false;
  let searchTimer = null;

  function $(id) {
    return document.getElementById(id);
  }

  function escapeHtml(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function setBusy(v) {
    state.busy = v;
  }

  function repoReady() {
    const repo = state.group?.repository;
    return Boolean(repo && repo.index_status === "ready");
  }

  function syncFromGroup(group) {
    state.group = group;
    state.groupName = group?.group_name || "";
    state.scenarioSlug = group?.scenario_slug || state.scenarioSlug || "";
    state.selected = (group?.members || []).map((m) => ({
      id: m.id,
      display_name: m.display_name,
      email: m.email || "",
    }));
    const repo = group?.repository;
    if (repo?.github_url) state.githubUrl = repo.github_url;
  }

  function fillScenarioSelect() {
    const select = $("groupScenario");
    if (!select) return;
    const preferred = state.scenarioSlug;
    select.innerHTML = "";
    if (!state.scenarios.length) {
      const empty = document.createElement("option");
      empty.value = "";
      empty.textContent = "No scenarios available";
      select.appendChild(empty);
      select.disabled = true;
      return;
    }
    select.disabled = state.busy;
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = "Select a scenario";
    select.appendChild(placeholder);
    state.scenarios.forEach((s) => {
      const opt = document.createElement("option");
      opt.value = s.slug;
      opt.textContent = s.title || s.slug;
      select.appendChild(opt);
    });
    if (preferred && [...select.options].some((o) => o.value === preferred)) {
      select.value = preferred;
      state.scenarioSlug = preferred;
    } else {
      select.value = "";
    }
  }

  function renderSelected() {
    const box = $("groupSelected");
    const count = $("groupSelectedCount");
    if (count) {
      count.textContent = state.group?.can_edit_members
        ? `Selected ${state.selected.length}/${MAX} (need ${MIN}–${MAX})`
        : "Members";
    }
    if (!box) return;
    if (!state.selected.length) {
      box.innerHTML = state.group?.can_edit_members
        ? '<p class="hint">No members selected yet. Search ungrouped classmates below.</p>'
        : '<p class="hint">No roster members linked to this group.</p>';
      return;
    }
    box.innerHTML = "";
    const ul = document.createElement("ul");
    ul.className = "consent-checklist";
    state.selected.forEach((row) => {
      const li = document.createElement("li");
      li.className = "claim-chip";
      li.innerHTML = `<span>${escapeHtml(row.display_name)}${
        row.email ? `<span class="hint"> · ${escapeHtml(row.email)}</span>` : ""
      }</span>`;
      if (state.group?.can_edit_members) {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "ghost danger";
        btn.textContent = "Remove";
        btn.disabled = state.busy;
        btn.addEventListener("click", () => {
          state.selected = state.selected.filter((s) => s.id !== row.id);
          renderSelected();
          syncMemberSaveEnabled();
        });
        li.appendChild(btn);
      }
      ul.appendChild(li);
    });
    box.appendChild(ul);
  }

  function syncMemberSaveEnabled() {
    const btn = $("groupMembersSave");
    const search = $("groupSearch");
    if (search) search.disabled = state.busy || state.selected.length >= MAX || !state.group?.can_edit_members;
    if (!btn) return;
    const ok =
      state.group?.can_edit_members &&
      state.selected.length >= MIN &&
      state.selected.length <= MAX &&
      !state.busy;
    btn.disabled = !ok;
  }

  function syncRepoSaveEnabled() {
    const btn = $("groupRepoSave");
    if (!btn) return;
    btn.disabled =
      state.busy ||
      !state.githubUrl.trim() ||
      !state.groupName.trim() ||
      !state.scenarioSlug.trim();
  }

  function readClaimCreds() {
    try {
      const raw = sessionStorage.getItem(CLAIM_CREDS_KEY);
      if (!raw) return null;
      const creds = JSON.parse(raw);
      if (!creds?.username || !creds?.password) return null;
      return creds;
    } catch (_) {
      return null;
    }
  }

  function clearClaimCreds() {
    try {
      sessionStorage.removeItem(CLAIM_CREDS_KEY);
    } catch (_) {
      /* ignore */
    }
    state.claimCreds = null;
  }

  function loginUsername() {
    return String(
      state.group?.account_username ||
        global.SellmRouter?.getUser?.()?.username ||
        state.fallbackUsername ||
        "",
    ).trim();
  }

  function renderAccount() {
    const username = loginUsername();
    const userEl = $("groupLoginUsername");
    if (userEl) userEl.textContent = username || "—";
    const resetBtn = $("groupResetPassword");
    if (resetBtn) {
      resetBtn.disabled = Boolean(state.busy) || !username;
      resetBtn.textContent = state.busy ? "Working…" : "Reset password";
    }

    const once = $("groupPasswordOnce");
    if (once) {
      if (state.passwordOnce) {
        once.hidden = false;
        once.innerHTML = `<div class="claim-cred-box" style="margin-top:8px">
          <p class="lede" style="margin:0 0 8px">${escapeHtml(state.passwordOnce.message || "Save this password now. It is shown only once.")}</p>
          <p style="margin:0 0 6px"><strong>Username</strong><br><code>${escapeHtml(state.passwordOnce.username || username)}</code></p>
          <p style="margin:0"><strong>Password</strong><br><code>${escapeHtml(state.passwordOnce.password || "")}</code></p>
        </div>`;
      } else {
        once.hidden = true;
        once.innerHTML = "";
      }
    }

    const banner = $("groupCredBanner");
    if (!banner) return;
    const creds = state.claimCreds;
    const matches = Boolean(creds?.username && username && creds.username === username);
    if (!matches) {
      banner.hidden = true;
      banner.innerHTML = "";
      return;
    }
    banner.hidden = false;
    banner.innerHTML = `
      <h2 style="margin:0 0 8px;font-size:1rem">Record your credentials</h2>
      <p class="lede" style="margin:0 0 10px">Your group was just claimed. Save this username and password now — the password will not be shown again.</p>
      <div class="claim-cred-box">
        <p class="hint" style="margin:0 0 8px">Group · ${escapeHtml(creds.group_name || state.groupName || "")}</p>
        <p style="margin:0 0 6px"><strong>Username</strong><br><code>${escapeHtml(creds.username)}</code></p>
        <p style="margin:0 0 10px"><strong>Password</strong><br><code>${escapeHtml(creds.password)}</code></p>
        <button type="button" class="ghost" id="groupCredDismiss">I saved these</button>
      </div>`;
    $("groupCredDismiss")?.addEventListener("click", () => {
      clearClaimCreds();
      renderAccount();
    });
  }

  function render() {
    const err = $("groupError");
    if (err) {
      if (state.error) {
        err.hidden = false;
        err.textContent = state.error;
      } else {
        err.hidden = true;
        err.textContent = "";
      }
    }
    const hint = $("groupHint");
    if (hint) {
      hint.hidden = !state.hint;
      hint.textContent = state.hint || "";
    }
    const nameInput = $("groupNameInput");
    if (nameInput && document.activeElement !== nameInput) nameInput.value = state.groupName;
    const urlInput = $("groupGithubUrl");
    if (urlInput && document.activeElement !== urlInput) urlInput.value = state.githubUrl;
    fillScenarioSelect();
    renderAccount();

    const membersPanel = $("groupMembersPanel");
    const noClaim = $("groupNoClaim");
    if (membersPanel) membersPanel.hidden = !state.group?.can_edit_members;
    if (noClaim) {
      noClaim.hidden = Boolean(state.group?.can_edit_members);
      if (state.group && !state.group.can_edit_members) {
        const names = state.group.participant_names || [];
        noClaim.innerHTML = names.length
          ? `<p class="hint">Interview names: ${escapeHtml(names.join(", "))}. Member roster edits are only available for groups claimed from classmates.</p>`
          : `<p class="hint">Member roster edits are only available for groups claimed from classmates.</p>`;
      }
    }

    const status = $("groupRepoStatus");
    if (status) {
      const repo = state.group?.repository;
      if (repo) {
        status.innerHTML = `<span class="repo-toolbar-status${repoReady() ? " ready" : ""}">${escapeHtml(
          repo.repo || "repo",
        )}${repo.commit_sha ? `@${escapeHtml(String(repo.commit_sha).slice(0, 7))}` : ""} · ${escapeHtml(
          repo.index_status || "",
        )}</span>${
          repo.index_error ? `<span class="error repo-toolbar-hint">${escapeHtml(repo.index_error)}</span>` : ""
        }`;
      } else {
        status.innerHTML = '<span class="hint">No repository saved yet.</span>';
      }
    }

    renderSelected();
    syncMemberSaveEnabled();
    syncRepoSaveEnabled();
    const saveMembers = $("groupMembersSave");
    if (saveMembers) saveMembers.textContent = state.busy ? "Saving…" : "Save members";
    const saveRepo = $("groupRepoSave");
    if (saveRepo) saveRepo.textContent = state.busy ? "Saving…" : "Save settings";
  }

  async function load() {
    setBusy(true);
    state.error = null;
    state.hint = "";
    state.passwordOnce = null;
    state.claimCreds = readClaimCreds();
    render();
    try {
      const me = await global.SellmApi.me().catch(() => null);
      state.fallbackUsername = String(me?.username || "").trim();
      const [group, scenarios] = await Promise.all([
        global.SellmApi.myGroup(),
        global.SellmApi.listScenarios().catch(() => []),
      ]);
      state.scenarios = scenarios || [];
      syncFromGroup(group);
      if (!state.group.account_username && state.fallbackUsername) {
        state.group.account_username = state.fallbackUsername;
      }
    } catch (err) {
      state.group = null;
      state.selected = [];
      state.error = err instanceof Error ? err.message : "Could not load group";
      try {
        state.scenarios = await global.SellmApi.listScenarios();
      } catch (_) {
        state.scenarios = [];
      }
    } finally {
      setBusy(false);
      render();
    }
  }

  async function onResetPassword() {
    const username = loginUsername();
    if (!username) return;
    if (
      !confirm(
        `Reset password for ${username}? The new password is shown only once — save it before leaving this page.`,
      )
    ) {
      return;
    }
    setBusy(true);
    state.error = null;
    state.hint = "";
    state.passwordOnce = null;
    render();
    try {
      const result = await global.SellmApi.resetGroupPassword();
      state.passwordOnce = result;
      state.hint = "Password reset. Record the new password below.";
      clearClaimCreds();
    } catch (err) {
      state.error = err instanceof Error ? err.message : "Could not reset password";
    } finally {
      setBusy(false);
      render();
    }
  }

  async function onSaveMembers(event) {
    event.preventDefault();
    if (!state.group?.can_edit_members) return;
    if (state.selected.length < MIN || state.selected.length > MAX) {
      state.error = `Select ${MIN}–${MAX} classmates.`;
      render();
      return;
    }
    setBusy(true);
    state.error = null;
    state.hint = "";
    render();
    try {
      const group = await global.SellmApi.updateGroupMembers(state.selected.map((s) => s.id));
      syncFromGroup(group);
      state.hint = "Members updated.";
    } catch (err) {
      state.error = err instanceof Error ? err.message : "Could not save members";
    } finally {
      setBusy(false);
      render();
    }
  }

  async function onSaveRepo(event) {
    event.preventDefault();
    if (!state.githubUrl.trim() || !state.groupName.trim() || !state.scenarioSlug.trim()) return;
    setBusy(true);
    state.error = null;
    state.hint = "";
    render();
    try {
      const result = await global.SellmApi.setupGroup({
        name: state.groupName.trim(),
        github_url: state.githubUrl.trim(),
        scenario_slug: state.scenarioSlug.trim(),
        team_id: state.group?.team_id || null,
      });
      if (result?.team || result?.repository) {
        const refreshed = await global.SellmApi.myGroup().catch(() => null);
        if (refreshed) syncFromGroup(refreshed);
        else {
          state.group = {
            ...(state.group || {}),
            group_name: result.team?.name || state.groupName,
            scenario_slug: result.team?.scenario_slug || state.scenarioSlug,
            team_id: result.team?.id || state.group?.team_id,
            repository: result.repository,
            participant_names: result.team?.participant_names || state.group?.participant_names || [],
          };
          state.groupName = state.group.group_name;
          state.scenarioSlug = state.group.scenario_slug || state.scenarioSlug;
          if (result.repository?.github_url) state.githubUrl = result.repository.github_url;
        }
      }
      state.hint = "Group settings saved.";
    } catch (err) {
      state.error = err instanceof Error ? err.message : "Could not save settings";
    } finally {
      setBusy(false);
      render();
    }
  }

  function bind() {
    if (bound) return;
    bound = true;

    $("groupNameInput")?.addEventListener("input", (e) => {
      state.groupName = e.target.value;
      syncRepoSaveEnabled();
    });
    $("groupScenario")?.addEventListener("change", (e) => {
      state.scenarioSlug = e.target.value;
      syncRepoSaveEnabled();
    });
    $("groupGithubUrl")?.addEventListener("input", (e) => {
      state.githubUrl = e.target.value;
      syncRepoSaveEnabled();
    });
    $("groupMembersForm")?.addEventListener("submit", (e) => void onSaveMembers(e));
    $("groupRepoForm")?.addEventListener("submit", (e) => void onSaveRepo(e));
    $("groupResetPassword")?.addEventListener("click", () => void onResetPassword());

    const search = $("groupSearch");
    const hits = $("groupHits");
    search?.addEventListener("input", () => {
      const q = search.value.trim();
      clearTimeout(searchTimer);
      if (q.length < 2 || !state.group?.can_edit_members) {
        if (hits) hits.innerHTML = "";
        return;
      }
      searchTimer = setTimeout(async () => {
        try {
          const rows = await global.SellmApi.searchRoster(q);
          const taken = new Set(state.selected.map((s) => s.id));
          const list = rows.filter((r) => !taken.has(r.id));
          if (!hits) return;
          hits.innerHTML = "";
          if (!list.length) return;
          const ul = document.createElement("ul");
          ul.className = "claim-hits";
          list.forEach((row) => {
            const li = document.createElement("li");
            const btn = document.createElement("button");
            btn.type = "button";
            btn.className = "ghost claim-hit";
            btn.innerHTML = `<strong>${escapeHtml(row.display_name)}</strong><span class="hint">${escapeHtml(
              row.email || "",
            )}</span>`;
            btn.addEventListener("click", () => {
              if (state.selected.length >= MAX || state.selected.some((s) => s.id === row.id)) return;
              state.selected = state.selected.concat([row]);
              search.value = "";
              hits.innerHTML = "";
              renderSelected();
              syncMemberSaveEnabled();
            });
            li.appendChild(btn);
            ul.appendChild(li);
          });
          hits.appendChild(ul);
        } catch (_) {
          if (hits) hits.innerHTML = "";
        }
      }, 200);
    });
  }

  async function mount() {
    bind();
    await load();
  }

  global.SellmGroup = { mount };
})(window);
