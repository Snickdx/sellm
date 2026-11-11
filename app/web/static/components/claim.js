/**
 * Claim group + login landing (port of LandingPage.tsx).
 */
(function (global) {
  const MIN = 3;
  const MAX = 4;

  let mounted = false;
  let selected = [];
  let searchTimer = null;

  function $(id) {
    return document.getElementById(id);
  }

  function el(html) {
    const t = document.createElement("template");
    t.innerHTML = html.trim();
    return t.content.firstElementChild;
  }

  function renderSelected() {
    const box = $("claimSelected");
    const count = $("claimSelectedCount");
    if (count) count.textContent = `Selected ${selected.length}/${MAX} (need ${MIN}–${MAX})`;
    if (!box) return;
    if (!selected.length) {
      box.innerHTML = '<p class="hint">No members selected yet.</p>';
      return;
    }
    box.innerHTML = "";
    const ul = document.createElement("ul");
    ul.className = "consent-checklist";
    selected.forEach((row) => {
      const li = document.createElement("li");
      li.className = "claim-chip";
      li.innerHTML = `<span>${escapeHtml(row.display_name)}<span class="hint"> · ${escapeHtml(row.email)}</span></span>`;
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "ghost danger";
      btn.textContent = "Remove";
      btn.addEventListener("click", () => {
        selected = selected.filter((s) => s.id !== row.id);
        renderSelected();
        updateClaimButton();
      });
      li.appendChild(btn);
      ul.appendChild(li);
    });
    box.appendChild(ul);
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function updateClaimButton() {
    const btn = $("claimSubmit");
    const name = ($("claimGroupName")?.value || "").trim();
    const search = $("claimSearch");
    if (search) search.disabled = selected.length >= MAX;
    if (!btn) return;
    btn.disabled = selected.length < MIN || selected.length > MAX || !name;
  }

  function showResult(result) {
    const formWrap = $("claimFormWrap");
    const resultWrap = $("claimResultWrap");
    if (formWrap) formWrap.hidden = true;
    if (resultWrap) {
      resultWrap.hidden = false;
      resultWrap.innerHTML = `
        <p class="lede">Save these credentials now. The password is shown only once. Sign in on the right with the same details.</p>
        <div class="surface claim-cred-box">
          <p class="hint" style="margin:0 0 8px">Group · ${escapeHtml(result.group_name)}</p>
          <p style="margin:0 0 6px"><strong>Username</strong><br><code>${escapeHtml(result.username)}</code></p>
          <p style="margin:0 0 6px"><strong>Password</strong><br><code>${escapeHtml(result.password)}</code></p>
          <p class="hint" style="margin:10px 0 0">Members: ${escapeHtml((result.members || []).join(", "))}</p>
        </div>`;
    }
    const title = $("claimTitle");
    if (title) title.textContent = "Group claimed";
    const userInput = $("landingUsername");
    const passInput = $("landingPassword");
    if (userInput) userInput.value = result.username || "";
    if (passInput) passInput.value = result.password || "";
  }

  function bindOnce() {
    if (mounted) return;
    mounted = true;

    const search = $("claimSearch");
    const hits = $("claimHits");
    search?.addEventListener("input", () => {
      const q = search.value.trim();
      clearTimeout(searchTimer);
      if (q.length < 2) {
        if (hits) hits.innerHTML = "";
        return;
      }
      searchTimer = setTimeout(async () => {
        try {
          const rows = await global.SellmApi.searchRoster(q);
          const taken = new Set(selected.map((s) => s.id));
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
            btn.innerHTML = `<strong>${escapeHtml(row.display_name)}</strong><span class="hint">${escapeHtml(row.email)}</span>`;
            btn.addEventListener("click", () => {
              if (selected.length >= MAX || selected.some((s) => s.id === row.id)) return;
              selected = selected.concat([row]);
              search.value = "";
              hits.innerHTML = "";
              renderSelected();
              updateClaimButton();
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

    $("claimGroupName")?.addEventListener("input", updateClaimButton);

    $("claimForm")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const err = $("claimError");
      const btn = $("claimSubmit");
      const groupName = ($("claimGroupName")?.value || "").trim();
      if (selected.length < MIN || selected.length > MAX) {
        if (err) {
          err.hidden = false;
          err.textContent = `Select ${MIN}–${MAX} classmates (you + 2 or 3 others).`;
        }
        return;
      }
      if (!groupName) {
        if (err) {
          err.hidden = false;
          err.textContent = "Enter a group name.";
        }
        return;
      }
      if (err) err.hidden = true;
      if (btn) {
        btn.disabled = true;
        btn.textContent = "Claiming…";
      }
      try {
        const claimed = await global.SellmApi.claimGroup({
          group_name: groupName,
          member_ids: selected.map((s) => s.id),
        });
        showResult(claimed);
      } catch (e) {
        if (err) {
          err.hidden = false;
          err.textContent = e instanceof Error ? e.message : "Claim failed";
        }
      } finally {
        if (btn) {
          btn.textContent = "Claim shared credentials";
          updateClaimButton();
        }
      }
    });

    $("landingLoginForm")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const err = $("landingLoginError");
      const btn = $("landingLoginBtn");
      const username = ($("landingUsername")?.value || "").trim();
      const password = $("landingPassword")?.value || "";
      if (err) err.hidden = true;
      if (btn) {
        btn.disabled = true;
        btn.textContent = "Signing in…";
      }
      try {
        const token = await global.SellmApi.login(username, password);
        await global.SellmRouter.onLoggedIn(token);
      } catch (e) {
        if (err) {
          err.hidden = false;
          err.textContent = e instanceof Error ? e.message : "Authentication failed";
        }
      } finally {
        if (btn) {
          btn.disabled = false;
          btn.textContent = "Log in";
        }
      }
    });
  }

  function mount() {
    bindOnce();
    renderSelected();
    updateClaimButton();
  }

  global.SellmClaim = { mount };
})(window);
