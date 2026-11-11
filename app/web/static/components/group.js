/**
 * Group settings: roster members + repository URL.
 */
(function (global) {
  const MIN = 3;
  const MAX = 4;

  let state = {
    group: null,
    selected: [],
    githubUrl: "",
    groupName: "",
    busy: false,
    hint: "",
    error: null,
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
    state.selected = (group?.members || []).map((m) => ({
      id: m.id,
      display_name: m.display_name,
      email: m.email || "",
    }));
    const repo = group?.repository;
    if (repo?.github_url) state.githubUrl = repo.github_url;
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
    btn.disabled = state.busy || !state.githubUrl.trim() || !state.groupName.trim();
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
    if (saveRepo) saveRepo.textContent = state.busy ? "Saving…" : "Save repository";
  }

  async function load() {
    setBusy(true);
    state.error = null;
    state.hint = "";
    render();
    try {
      const group = await global.SellmApi.myGroup();
      syncFromGroup(group);
    } catch (err) {
      state.group = null;
      state.selected = [];
      state.error = err instanceof Error ? err.message : "Could not load group";
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
    if (!state.githubUrl.trim() || !state.groupName.trim()) return;
    setBusy(true);
    state.error = null;
    state.hint = "";
    render();
    try {
      const result = await global.SellmApi.setupGroup({
        name: state.groupName.trim(),
        github_url: state.githubUrl.trim(),
        team_id: state.group?.team_id || null,
      });
      if (result?.team || result?.repository) {
        const refreshed = await global.SellmApi.myGroup().catch(() => null);
        if (refreshed) syncFromGroup(refreshed);
        else {
          state.group = {
            ...(state.group || {}),
            group_name: result.team?.name || state.groupName,
            team_id: result.team?.id || state.group?.team_id,
            repository: result.repository,
            participant_names: result.team?.participant_names || state.group?.participant_names || [],
          };
          state.groupName = state.group.group_name;
          if (result.repository?.github_url) state.githubUrl = result.repository.github_url;
        }
      }
      state.hint = "Repository saved.";
    } catch (err) {
      state.error = err instanceof Error ? err.message : "Could not save repository";
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
    $("groupGithubUrl")?.addEventListener("input", (e) => {
      state.githubUrl = e.target.value;
      syncRepoSaveEnabled();
    });
    $("groupMembersForm")?.addEventListener("submit", (e) => void onSaveMembers(e));
    $("groupRepoForm")?.addEventListener("submit", (e) => void onSaveRepo(e));

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
