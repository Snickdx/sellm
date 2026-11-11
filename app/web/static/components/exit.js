/**
 * Exit interview hub / live / review (port of ExitInterviewPage.tsx).
 */
(function (global) {
  const SCORED = new Set(["lecturer_review", "finalized"]);
  const WRAP = new Set(["closing", "processing"]);
  const STATUS_LABELS = {
    scheduled: "Scheduled",
    consent: "Awaiting consent",
    introductions: "Starting",
    student_turn: "In progress",
    question: "In progress",
    optional_probe: "In progress",
    response: "In progress",
    evidence_recorded: "In progress",
    next_student: "In progress",
    closing: "Closing — audit pending",
    processing: "Audit in progress",
    lecturer_review: "Completed",
    finalized: "Finalized",
    paused: "Paused",
  };
  const COMPETENCY_LABELS = {
    special_feature_pattern: "Special-feature pattern",
    design_to_code: "Design to code",
    feature_ownership: "Feature ownership",
    testing: "Testing",
    verification: "Verification",
    requirements: "Requirements",
    architecture: "Architecture",
    code: "Code",
    ai_engineering: "AI engineering",
  };

  let state = {
    teamId: null,
    teams: [],
    team: null,
    repo: null,
    sessions: [],
    selectedPastId: null,
    pastDetail: null,
    hubReport: null,
    hubScreen: "list", // mobile: "list" | "detail" separate screens
    session: null,
    report: null,
    tab: "hub",
    busy: false,
    error: null,
    intervieweeName: "",
    answer: "",
    sttBase: "",
    viewIndex: 0,
    probePrompt: null,
    policy: null,
    pendingSession: null,
    consentChecked: false,
    voice: null,
  };
  let advancing = false;
  let finishing = false;
  let bound = false;

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

  function formatWhen(iso) {
    if (!iso) return "";
    try {
      return new Date(iso).toLocaleString();
    } catch (_) {
      return iso;
    }
  }

  function formatStatus(status) {
    if (!status) return "—";
    return STATUS_LABELS[status] || status.replace(/_/g, " ");
  }

  function formatCompetency(name) {
    return COMPETENCY_LABELS[name] || String(name || "").replace(/_/g, " ");
  }

  function isScored(status) {
    return !!status && SCORED.has(status);
  }
  function isWrapping(status) {
    return !!status && WRAP.has(status);
  }
  function isDone(status) {
    return isScored(status) || isWrapping(status);
  }
  function isNextCommand(text) {
    const t = text.trim().toLowerCase().replace(/[.!,?]+$/g, "");
    return t === "next" || t === "next question" || t === "go next";
  }

  function repoReady() {
    return Boolean(state.repo && state.repo.index_status === "ready");
  }

  function scenarioReady() {
    return Boolean((state.team?.scenario_slug || "").trim());
  }

  function setupReady() {
    return scenarioReady() && repoReady();
  }

  function canStartInterview() {
    return (
      !state.busy &&
      setupReady() &&
      Boolean(state.intervieweeName.trim()) &&
      memberOptions().length > 0
    );
  }

  function syncStartSubmit() {
    const submit = $("exitStartSubmit");
    if (submit) submit.disabled = !canStartInterview();
  }

  function setError(msg) {
    state.error = msg;
    const el = $("exitError");
    if (!el) return;
    if (!msg) {
      el.hidden = true;
      el.textContent = "";
    } else {
      el.hidden = false;
      el.textContent = msg;
    }
  }

  function setBusy(v) {
    state.busy = v;
  }

  function orderedQuestions(session) {
    const qs = session?.questions || [];
    return qs.slice().sort((a, b) => (a.sequence || 0) - (b.sequence || 0));
  }

  function destroyVoice() {
    if (state.voice) {
      try {
        state.voice.destroy();
      } catch (_) {
        /* ignore */
      }
      state.voice = null;
    }
  }

  async function refreshHub(preferId) {
    if (!state.teamId) return;
    const [team, repos, sessions] = await Promise.all([
      global.SellmApi.teamDetail(state.teamId),
      global.SellmApi.teamRepos(state.teamId).catch(() => []),
      global.SellmApi.listExitSessions(state.teamId),
    ]);
    state.team = team;
    state.sessions = sessions || [];
    const latest = (repos || [])[0] || null;
    state.repo = latest;

    const pick =
      preferId ||
      state.selectedPastId ||
      (state.sessions[0] && state.sessions[0].id) ||
      null;
    state.selectedPastId = pick;
    if (pick) {
      try {
        state.pastDetail = await global.SellmApi.fetchExitSession(pick);
        if (isScored(state.pastDetail.status)) {
          try {
            state.hubReport = await global.SellmApi.fetchExitReport(pick);
          } catch (_) {
            state.hubReport = null;
          }
        } else {
          state.hubReport = null;
        }
      } catch (_) {
        state.pastDetail = null;
        state.hubReport = null;
      }
    } else {
      state.pastDetail = null;
      state.hubReport = null;
    }
  }

  function openConsentFor(detail) {
    state.pendingSession = detail;
    state.consentChecked = detail.consent_status === "granted";
    state.report = null;
    state.probePrompt = null;
    renderConsentModal(true);
  }

  async function beginLiveSession(detail) {
    let next = detail;
    if (next.consent_status !== "granted") {
      next = await global.SellmApi.consentExitSession(next.id, true);
    }
    if (!isDone(next.status) && next.status !== "question" && next.status !== "optional_probe") {
      next = await global.SellmApi.startExitSession(next.id);
    }
    state.session = next;
    state.pastDetail = next;
    state.selectedPastId = next.id;
    state.probePrompt = null;
    state.consentChecked = false;
    state.pendingSession = null;
    state.tab = "live";
    state.viewIndex = 0;
    state.answer = "";
    state.sttBase = "";
    renderConsentModal(false);
    await refreshHub(next.id);
    render();
  }

  async function openLive(id) {
    setBusy(true);
    setError(null);
    try {
      const detail = await global.SellmApi.fetchExitSession(id);
      state.pastDetail = detail;
      state.selectedPastId = id;
      if (isScored(detail.status)) {
        state.session = detail;
        state.viewIndex = 0;
        try {
          state.report = await global.SellmApi.fetchExitReport(detail.id);
        } catch (_) {
          state.report = null;
        }
        state.tab = "live";
        render();
        return;
      }
      if (isWrapping(detail.status)) {
        state.session = detail;
        state.report = null;
        state.viewIndex = 0;
        state.tab = "live";
        render();
        if (detail.status === "closing") maybeAutoFinish();
        return;
      }
      if (detail.consent_status !== "granted") {
        openConsentFor(detail);
        return;
      }
      await beginLiveSession(detail);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to open interview");
      render();
    } finally {
      setBusy(false);
    }
  }

  async function onStartInterview(event) {
    event.preventDefault();
    if (!state.teamId || !state.intervieweeName.trim() || !setupReady()) return;
    setBusy(true);
    setError(null);
    try {
      const created = await global.SellmApi.createExitSession(state.teamId, {
        participant_names: [state.intervieweeName.trim()],
        questions_per_student: 3,
      });
      state.intervieweeName = "";
      closeStartModal();
      openConsentFor(created);
      await refreshHub(created.id);
      render();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Start failed");
      render();
    } finally {
      setBusy(false);
    }
  }

  async function onConfirmConsent() {
    if (!state.pendingSession || !state.consentChecked) return;
    setBusy(true);
    setError(null);
    try {
      await beginLiveSession(state.pendingSession);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start interview");
      render();
    } finally {
      setBusy(false);
    }
  }

  function onTranscript(text, isFinal) {
    if (isFinal && isNextCommand(text)) {
      state.answer = state.sttBase;
      void onVoiceNext();
      return;
    }
    if (!isFinal && isNextCommand(text)) {
      state.answer = state.sttBase;
      syncAnswerField();
      return;
    }
    if (isFinal) {
      state.sttBase = `${state.sttBase} ${text}`.trim();
      state.answer = state.sttBase;
    } else {
      state.answer = `${state.sttBase} ${text}`.trim();
    }
    syncAnswerField();
  }

  function syncAnswerField() {
    const ta = $("exitAnswer");
    if (ta && document.activeElement !== ta) ta.value = state.answer;
  }

  async function onVoiceNext() {
    if (!state.session || isDone(state.session.status) || isWrapping(state.session.status) || advancing) {
      return;
    }
    const qs = orderedQuestions(state.session);
    const currentId = state.session.current_question_id;
    const currentIdx = qs.findIndex((q) => q.id === currentId);
    const viewingCurrent = state.viewIndex === currentIdx || currentIdx < 0;
    if (!viewingCurrent && state.viewIndex < qs.length - 1) {
      state.viewIndex = Math.min(state.viewIndex + 1, qs.length - 1);
      renderLiveBody();
      return;
    }
    advancing = true;
    setBusy(true);
    setError(null);
    try {
      const next = await global.SellmApi.nextExitQuestion(state.session.id);
      state.session = next;
      state.probePrompt = null;
      state.answer = "";
      state.sttBase = "";
      const nqs = orderedQuestions(next);
      const nidx = nqs.findIndex((q) => q.id === next.current_question_id);
      state.viewIndex = nidx >= 0 ? nidx : Math.max(0, nqs.length - 1);
      render();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not advance");
      render();
    } finally {
      advancing = false;
      setBusy(false);
      maybeAutoFinish();
    }
  }

  async function onAnswer(event) {
    event.preventDefault();
    if (!state.session) return;
    if (isNextCommand(state.answer)) {
      state.answer = "";
      state.sttBase = "";
      void onVoiceNext();
      return;
    }
    if (!state.answer.trim()) return;
    setBusy(true);
    setError(null);
    try {
      if (state.session.status === "optional_probe") {
        state.session = await global.SellmApi.submitProbeAnswer(state.session.id, state.answer.trim());
        state.probePrompt = null;
      } else {
        state.session = await global.SellmApi.submitExitAnswer(
          state.session.id,
          state.answer.trim(),
          false,
        );
        state.probePrompt = state.session.probe_prompt || null;
      }
      state.answer = "";
      state.sttBase = "";
      const qs = orderedQuestions(state.session);
      const idx = qs.findIndex((q) => q.id === state.session.current_question_id);
      if (idx >= 0) state.viewIndex = idx;
      render();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Answer failed");
      render();
    } finally {
      setBusy(false);
      maybeAutoFinish();
    }
  }

  function maybeAutoFinish() {
    if (
      state.session &&
      state.session.status === "closing" &&
      state.tab === "live" &&
      !state.busy &&
      !finishing
    ) {
      void onEndInterview();
    }
  }

  async function onEndInterview() {
    if (!state.session || finishing) return;
    finishing = true;
    setBusy(true);
    setError(null);
    try {
      try {
        if (state.voice) await state.voice.stopAndUpload();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not save video recording");
      }
      const result = await global.SellmApi.finishExitSession(state.session.id);
      try {
        state.report = await global.SellmApi.fetchExitReport(result.session.id);
      } catch (_) {
        state.report = null;
      }
      state.session = result.session;
      state.probePrompt = null;
      destroyVoice();
      await refreshHub(result.session.id);
      state.tab = "live";
      render();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Finish failed");
      render();
    } finally {
      finishing = false;
      setBusy(false);
    }
  }

  async function onDeleteInterview(id) {
    const label =
      (state.sessions.find((s) => s.id === id)?.participant_names || []).join(", ") ||
      "this interview";
    if (!window.confirm(`Delete ${label}? This cannot be undone.`)) return;
    setBusy(true);
    setError(null);
    try {
      await global.SellmApi.deleteExitSession(id);
      if (state.session?.id === id) {
        destroyVoice();
        state.session = null;
        state.report = null;
        state.probePrompt = null;
        state.tab = "hub";
      }
      if (state.selectedPastId === id) {
        state.selectedPastId = null;
        state.pastDetail = null;
        state.hubScreen = "list";
      }
      await refreshHub(null);
      render();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
      render();
    } finally {
      setBusy(false);
    }
  }

  function competencyLine(scores) {
    if (!scores?.length) return "No scores yet";
    return scores
      .map((c) => `${formatCompetency(c.name)}: ${c.score == null ? "—" : `${c.score}/${c.max_score}`}`)
      .join(" · ");
  }

  function reportSummaryHtml(report) {
    if (!report?.assessments?.length) {
      return '<p class="hint">No provisional assessment stored for this interview.</p>';
    }
    return `<div class="report-summary">${report.assessments
      .map((a) => {
        const comps = a.provisional_scores?.competencies || [];
        const warnings = a.evidence?.coverage_warnings || [];
        return `<article class="report-card">
          <header><strong>${escapeHtml(a.display_name)}</strong>
          <span>${a.provisional ? "Provisional" : "Final"} · ${escapeHtml(a.review_status)}</span></header>
          <p class="report-scores">${escapeHtml(competencyLine(comps))}</p>
          ${
            warnings.length
              ? `<ul class="report-warnings">${warnings.map((w) => `<li>${escapeHtml(w)}</li>`).join("")}</ul>`
              : ""
          }
        </article>`;
      })
      .join("")}</div>`;
  }

  function isMobileExit() {
    return window.matchMedia("(max-width: 720px)").matches;
  }

  function syncExitHeaderChrome() {
    const view = $("view-exit");
    const back = $("exitBackBtn");
    if (!view) return;
    view.classList.remove("child-screen-list", "child-screen-detail", "child-screen-live");
    let screen = "list";
    if (state.tab === "live" && state.session) screen = "live";
    else if (isMobileExit() && state.hubScreen === "detail") screen = "detail";
    else screen = "list";
    view.classList.add(`child-screen-${screen}`);
    if (back) {
      // Live always has a header back (repo toolbar removed); detail only on mobile.
      const showBack = screen === "live" || (isMobileExit() && screen === "detail");
      back.hidden = !showBack;
      back.setAttribute("aria-label", "Back to interviews");
    }
  }

  function bindExitBackBtn() {
    const back = $("exitBackBtn");
    if (!back || back.dataset.bound === "1") return;
    back.dataset.bound = "1";
    back.addEventListener("click", () => {
      if (state.tab === "live" && state.session) {
        destroyVoice();
        state.session = null;
        state.report = null;
        state.probePrompt = null;
        state.tab = "hub";
        state.hubScreen = "list";
        render();
        return;
      }
      state.hubScreen = "list";
      renderHub();
      syncExitHeaderChrome();
    });
  }

  function renderHub() {
    const root = $("exitMain");
    if (!root) return;
    const sessions = state.sessions;
    const selected = sessions.find((s) => s.id === state.selectedPastId) || null;
    const user = global.SellmRouter.getUser();
    const canDelete = global.SellmApi.canDeleteExitSession(user, selected?.created_by_id);
    const mobile = isMobileExit();
    if (!mobile) state.hubScreen = selected ? "detail" : "list";
    else if (state.hubScreen === "detail" && !selected) state.hubScreen = "list";

    const teamSwitcher =
      state.teams.length > 1
        ? `<label class="hint" style="display:block;padding:10px 14px 0;margin:0">
            Group
            <select id="exitTeamSelect" aria-label="Group" style="display:block;margin-top:4px;width:100%;max-width:280px">
              ${state.teams
                .map(
                  (t) =>
                    `<option value="${escapeHtml(t.id)}" ${t.id === state.teamId ? "selected" : ""}>${escapeHtml(t.name)}</option>`,
                )
                .join("")}
            </select>
          </label>`
        : "";
    const listHtml = !sessions.length
      ? `<p class="hint" style="padding:14px;margin:0">No interviews yet. Set scenario and repository on <a href="/group" data-nav="group">Group</a>, then use Start interview.</p>`
      : sessions
          .map((s) => {
            const active = s.id === state.selectedPastId;
            const label = (s.participant_names || []).join(", ") || s.id.slice(0, 8);
            return `<button type="button" class="interview-hub-item${active ? " active" : ""}" data-id="${escapeHtml(s.id)}">
              <strong>${escapeHtml(label)}</strong>
              <span>${escapeHtml(formatStatus(s.status))}${s.created_at ? ` · ${escapeHtml(formatWhen(s.created_at))}` : ""}</span>
            </button>`;
          })
          .join("");

    let detailHtml = '<p class="hint">Select an interview, or start a new one.</p>';
    if (selected) {
      const d = state.pastDetail;
      detailHtml = `
        <div class="stack" style="max-width:none;gap:12px">
          <div>
            <h2 style="margin-bottom:6px">${escapeHtml((selected.participant_names || []).join(", ") || "Interview")}</h2>
            <div class="live-meta">
              <span>Status: ${escapeHtml(formatStatus(selected.status))}</span>
              <span>Consent: ${escapeHtml(selected.consent_status)}</span>
              ${selected.created_at ? `<span>Started: ${escapeHtml(formatWhen(selected.created_at))}</span>` : ""}
            </div>
          </div>
          ${
            d
              ? `<p class="hint" style="margin:0">Questions: ${d.questions.length} · Unanswered: ${d.unanswered_question_ids.length} · Interviewee: ${escapeHtml(d.current_participant_name || d.participants[0]?.display_name || "—")}</p>
                 ${
                   d.participants.length
                     ? `<ul class="consent-checklist">${d.participants
                         .map(
                           (p) =>
                             `<li>${escapeHtml(p.display_name || `User ${p.user_id}`)} · consent ${escapeHtml(p.consent_status)}</li>`,
                         )
                         .join("")}</ul>`
                     : ""
                 }
                 ${isWrapping(selected.status) ? `<p class="audit-banner" role="status">Closing — provisional audit pending. Open to finish scoring.</p>` : ""}
                 ${
                   isScored(selected.status)
                     ? `<div><h3 style="margin:8px 0 6px;font-size:0.95rem">Provisional summary</h3>${
                         state.hubReport
                           ? reportSummaryHtml(state.hubReport)
                           : '<p class="hint">Loading report summary…</p>'
                       }</div>`
                     : ""
                 }`
              : '<p class="hint">Loading details…</p>'
          }
          <div class="live-actions">
            <button type="button" id="exitOpenLive" ${state.busy || !state.selectedPastId ? "disabled" : ""}>
              ${
                isWrapping(selected.status)
                  ? "Complete audit"
                  : isScored(selected.status)
                    ? "View interview"
                    : "Continue interview"
              }
            </button>
            ${
              canDelete
                ? `<button type="button" class="ghost danger" id="exitDelete" ${state.busy || !state.selectedPastId ? "disabled" : ""}>Delete interview</button>`
                : ""
            }
          </div>
        </div>`;
    }

    const screenClass =
      mobile && state.hubScreen === "detail" ? "child-screen-detail" : "child-screen-list";

    root.innerHTML = `
      <div class="interview-hub ${screenClass}">
        <section class="interview-hub-list" aria-label="Past interviews">
          <div class="interview-hub-list-header">Past interviews</div>
          ${teamSwitcher}
          ${listHtml}
        </section>
        <section class="interview-hub-detail" aria-label="Interview details">${detailHtml}</section>
      </div>
      ${
        !mobile || state.hubScreen === "list"
          ? `<button type="button" class="fab-labeled" id="exitFabStart">+ Start interview</button>`
          : ""
      }`;

    $("exitTeamSelect")?.addEventListener("change", (e) => {
      global.SellmRouter.navigate(`/teams/${e.target.value}/exit`);
    });
    root.querySelectorAll(".interview-hub-item").forEach((btn) => {
      btn.addEventListener("click", async () => {
        state.selectedPastId = btn.getAttribute("data-id");
        state.hubScreen = "detail";
        setBusy(true);
        try {
          state.pastDetail = await global.SellmApi.fetchExitSession(state.selectedPastId);
          if (isScored(state.pastDetail.status)) {
            try {
              state.hubReport = await global.SellmApi.fetchExitReport(state.selectedPastId);
            } catch (_) {
              state.hubReport = null;
            }
          } else state.hubReport = null;
        } catch (_) {
          state.pastDetail = null;
        } finally {
          setBusy(false);
          renderHub();
        }
      });
    });
    $("exitOpenLive")?.addEventListener("click", () => {
      if (state.selectedPastId) void openLive(state.selectedPastId);
    });
    $("exitDelete")?.addEventListener("click", () => {
      if (state.selectedPastId) void onDeleteInterview(state.selectedPastId);
    });
    $("exitFabStart")?.addEventListener("click", () => openStartModal());
    syncExitHeaderChrome();
  }

  function renderReview() {
    const root = $("exitMain");
    const session = state.session;
    if (!root || !session) return;
    const qs = orderedQuestions(session);
    destroyVoice();
    root.innerHTML = `
      <section class="surface live-interview review-interview">
        <div class="live-toolbar">
          <div>
            <h2 style="margin-bottom:6px">Interview review</h2>
            <div class="live-meta">
              <span>${escapeHtml(formatStatus(session.status))}</span>
              <span>Interviewee: ${escapeHtml(session.current_participant_name || session.participants[0]?.display_name || "—")}</span>
              <span>${qs.length} questions · ${session.unanswered_question_ids.length} unanswered</span>
            </div>
          </div>
        </div>
        <div class="review-layout">
          <section class="review-panel">
            <h3>Recording</h3>
            <div id="exitRecordingPlayer"><p class="hint">Loading recording…</p></div>
          </section>
          <section class="review-panel">
            <h3>Provisional summary</h3>
            ${state.report ? reportSummaryHtml(state.report) : '<p class="hint">No report available.</p>'}
          </section>
          <section class="review-panel review-transcripts">
            <h3>Question &amp; answer transcript</h3>
            ${
              qs.length
                ? qs
                    .map((q, idx) => {
                      const path = q.code_refs?.path
                        ? `<p class="hint" style="margin:4px 0 0">${escapeHtml(String(q.code_refs.path))}${
                            Array.isArray(q.code_refs.line_range)
                              ? `:${q.code_refs.line_range[0]}-${q.code_refs.line_range[1]}`
                              : ""
                          }</p>`
                        : "";
                      const answers = q.answers?.length
                        ? q.answers
                            .map(
                              (a) =>
                                `<p class="past-answer">${a.is_probe ? "Probe: " : "Answer: "}${escapeHtml(a.text)}</p>`,
                            )
                            .join("")
                        : '<p class="hint">No answer recorded.</p>';
                      return `<article class="transcript-item">
                        <header>Q${idx + 1}. ${escapeHtml(formatCompetency(q.competency))} · ${escapeHtml(q.difficulty)} · ${escapeHtml(q.status)}</header>
                        <p class="transcript-q">${escapeHtml(q.prompt)}</p>
                        ${path}${answers}
                      </article>`;
                    })
                    .join("")
                : '<p class="hint">No questions in this session.</p>'
            }
          </section>
          <section class="review-panel">
            <h3>Full report</h3>
            ${
              state.report
                ? `<div class="formatted-report">${reportSummaryHtml(state.report)}</div>`
                : '<p class="hint">No report available.</p>'
            }
          </section>
        </div>
      </section>`;

    void (async () => {
      const box = $("exitRecordingPlayer");
      if (!box) return;
      try {
        const status = await global.SellmApi.fetchVoiceStatus(session.id).catch(() => null);
        if (status?.recording_status === "processing") {
          box.innerHTML = '<p class="hint">Recording still processing — refresh in a moment.</p>';
        }
        try {
          const url = await global.SellmApi.fetchRecordingObjectUrl(session.id);
          box.innerHTML = `<video class="review-video" src="${url}" controls playsinline></video>`;
        } catch (err) {
          if (status?.recording_status === "processing") {
            box.innerHTML = '<p class="hint">Recording still processing — refresh in a moment.</p>';
          } else {
            box.innerHTML = `<p class="hint">${escapeHtml(err instanceof Error ? err.message : "No recording available")}</p>`;
          }
        }
      } catch (err) {
        box.innerHTML = `<p class="hint">${escapeHtml(err instanceof Error ? err.message : "No recording available")}</p>`;
      }
    })();
  }

  function renderLiveBody() {
    // used for light updates; full live uses renderLive
    renderLive();
  }

  function renderLive() {
    const root = $("exitMain");
    const session = state.session;
    if (!root || !session) return;
    const wrappingUp = isWrapping(session.status);
    const qs = orderedQuestions(session);
    const currentId = session.current_question_id;
    const currentIdx = qs.findIndex((q) => q.id === currentId);
    if (state.viewIndex < 0 || state.viewIndex >= qs.length) {
      state.viewIndex = currentIdx >= 0 ? currentIdx : 0;
    }
    const viewed = qs[state.viewIndex] || null;
    const viewingCurrent = viewed && viewed.id === currentId;
    const canAnswer =
      !wrappingUp &&
      viewingCurrent &&
      (session.status === "question" || session.status === "optional_probe");

    const needVoice = !wrappingUp && session.consent_status === "granted";
    const prevSessionId = root.dataset.voiceSession;
    if (!needVoice || (prevSessionId && prevSessionId !== session.id)) {
      destroyVoice();
    }
    const preservedVoice =
      state.voice && needVoice ? $("exitVoiceMount")?.querySelector(".video-room") : null;

    root.innerHTML = `
      <section class="surface live-interview">
        <div class="live-toolbar">
          <div>
            <h2 style="margin-bottom:6px">${wrappingUp ? "Closing interview" : "Live interview"}</h2>
            <div class="live-meta">
              <span>${escapeHtml(formatStatus(session.status))}</span>
              <span>Interviewee: ${escapeHtml(session.current_participant_name || session.participants[0]?.display_name || "—")}</span>
              ${!wrappingUp ? '<span class="recording-pill">Recording</span>' : '<span class="audit-pill">Audit</span>'}
            </div>
          </div>
          <button type="button" id="exitEndBtn" ${state.busy ? "disabled" : ""}>
            ${
              state.busy || session.status === "processing"
                ? "Running audit…"
                : wrappingUp
                  ? "Complete audit"
                  : "End interview"
            }
          </button>
        </div>
        ${
          wrappingUp
            ? `<p class="audit-banner" role="status">${
                session.status === "processing"
                  ? "Audit in progress — scoring answers and preparing the provisional report."
                  : "Closing — questions are done. Provisional audit will run next (save recording, then score)."
              }</p>`
            : ""
        }
        <div class="live-main">
          <aside class="live-camera" id="exitVoiceMount"></aside>
          <div class="live-work">
            ${
              wrappingUp
                ? '<p class="hint">You can still browse prior questions below. Complete the audit to see the provisional report and recording playback.</p>'
                : ""
            }
            ${
              qs.length
                ? `<div class="question-nav">
                    <button type="button" class="ghost" id="exitPrevQ" ${state.busy || state.viewIndex <= 0 ? "disabled" : ""}>Previous</button>
                    <span class="question-pos">${state.viewIndex + 1} / ${qs.length}</span>
                    <button type="button" class="ghost" id="exitNextQ" ${state.busy || state.viewIndex >= qs.length - 1 ? "disabled" : ""}>Next</button>
                    ${
                      !viewingCurrent
                        ? `<button type="button" class="ghost" id="exitJumpCurrent" ${state.busy || !currentId ? "disabled" : ""}>Jump to current</button>`
                        : ""
                    }
                  </div>`
                : ""
            }
            ${
              viewed
                ? `<article class="bubble persona">
                    <header>${escapeHtml(formatCompetency(viewed.competency))} · ${escapeHtml(viewed.difficulty)}${viewed.hypothetical ? " · hypothetical" : ""}${!viewingCurrent ? ` · ${escapeHtml(viewed.status)}` : ""}</header>
                    <p>${escapeHtml(viewed.prompt)}</p>
                    ${
                      viewed.code_refs?.path
                        ? `<footer>${escapeHtml(String(viewed.code_refs.path))}${
                            Array.isArray(viewed.code_refs.line_range)
                              ? `:${viewed.code_refs.line_range[0]}-${viewed.code_refs.line_range[1]}`
                              : ""
                          } @ ${escapeHtml(String(viewed.code_refs.sha || "").slice(0, 7))}</footer>`
                        : ""
                    }
                  </article>`
                : ""
            }
            ${state.probePrompt && viewingCurrent ? `<p class="hint">Probe: ${escapeHtml(state.probePrompt)}</p>` : ""}
            ${
              canAnswer
                ? `<form class="chat-compose live-answer" id="exitAnswerForm">
                    <textarea id="exitAnswer" rows="5" ${state.busy ? "disabled" : ""}
                      placeholder="${escapeHtml(
                        session.current_participant_name
                          ? `Speak or type as ${session.current_participant_name}… (or Skip for alternative)`
                          : "Speak or type your answer… (or Skip for alternative)",
                      )}"
                    >${escapeHtml(state.answer)}</textarea>
                    <div class="live-answer-actions">
                      <button type="submit" ${state.busy || !state.answer.trim() ? "disabled" : ""}>
                        ${session.status === "optional_probe" ? "Submit probe" : "Submit answer"}
                      </button>
                      <button type="button" class="ghost" id="exitSkipQ" ${state.busy ? "disabled" : ""}>
                        ${session.status === "optional_probe" ? "Skip probe" : "Skip for alternative"}
                      </button>
                    </div>
                  </form>`
                : ""
            }
            ${
              viewed && !viewingCurrent
                ? viewed.answers?.length
                  ? `<div class="live-actions" style="flex-direction:column;align-items:stretch">${viewed.answers
                      .map(
                        (a) =>
                          `<p class="past-answer">${a.is_probe ? "Probe: " : ""}${escapeHtml(a.text)}</p>`,
                      )
                      .join("")}</div>`
                  : '<p class="hint">No answer recorded for this question.</p>'
                : ""
            }
            ${!session.current_question_id && !qs.length ? '<p class="hint">Preparing questions…</p>' : ""}
          </div>
        </div>
      </section>`;

    root.dataset.voiceSession = needVoice ? session.id : "";
    $("exitEndBtn")?.addEventListener("click", () => void onEndInterview());
    $("exitPrevQ")?.addEventListener("click", () => {
      state.viewIndex = Math.max(0, state.viewIndex - 1);
      renderLive();
    });
    $("exitNextQ")?.addEventListener("click", () => {
      state.viewIndex = Math.min(state.viewIndex + 1, qs.length - 1);
      renderLive();
    });
    $("exitJumpCurrent")?.addEventListener("click", () => {
      if (currentIdx >= 0) {
        state.viewIndex = currentIdx;
        renderLive();
      }
    });
    $("exitSkipQ")?.addEventListener("click", () => void onVoiceNext());
    $("exitAnswer")?.addEventListener("input", (e) => {
      state.answer = e.target.value;
      state.sttBase = e.target.value;
      const btn = $("exitAnswerForm")?.querySelector('button[type="submit"]');
      if (btn) btn.disabled = state.busy || !state.answer.trim();
    });
    $("exitAnswerForm")?.addEventListener("submit", (e) => void onAnswer(e));

    const mount = $("exitVoiceMount");
    if (needVoice && mount) {
      if (preservedVoice) {
        mount.appendChild(preservedVoice);
      } else if (!state.voice) {
        state.voice = global.SellmExitVoice.createVoiceRoom({
          root: mount,
          sessionId: session.id,
          autoStart: true,
          onTranscript: wrappingUp ? null : onTranscript,
        });
      }
    }
  }

  function memberOptions() {
    const names = (state.team?.participant_names || []).map((n) => String(n || "").trim()).filter(Boolean);
    return [...new Set(names)];
  }

  function fillIntervieweeSelect() {
    const select = $("exitIntervieweeName");
    if (!select) return;
    const names = memberOptions();
    const previous = state.intervieweeName.trim();
    select.innerHTML =
      `<option value="">Select a group member</option>` +
      names.map((n) => `<option value="${escapeHtml(n)}">${escapeHtml(n)}</option>`).join("");
    if (previous && names.includes(previous)) {
      select.value = previous;
    } else {
      state.intervieweeName = "";
      select.value = "";
    }
    const membersHint = $("exitStartMembersHint");
    if (membersHint) membersHint.hidden = names.length > 0;
  }

  function openStartModal() {
    const modal = $("exitStartModal");
    if (modal) modal.hidden = false;
    fillIntervieweeSelect();
    const select = $("exitIntervieweeName");
    if (select) select.focus();
    const setupHint = $("exitStartSetupHint");
    if (setupHint) setupHint.hidden = setupReady();
    syncStartSubmit();
  }

  function closeStartModal() {
    const modal = $("exitStartModal");
    if (modal) modal.hidden = true;
  }

  function renderConsentModal(show) {
    const modal = $("exitConsentModal");
    if (!modal) return;
    modal.hidden = !show;
    if (!show) return;
    const policy = state.policy;
    $("exitConsentTitle").textContent = policy?.consent?.title || "Consent";
    $("exitConsentSummary").textContent =
      policy?.consent?.summary ||
      "Confirm consent before the interview and any recording begin.";
    const ul = $("exitConsentBullets");
    if (ul) {
      ul.innerHTML = (policy?.consent?.bullets || [])
        .map((b) => `<li>${escapeHtml(b)}</li>`)
        .join("");
    }
    const check = $("exitConsentCheck");
    if (check) check.checked = state.consentChecked;
    const start = $("exitConsentStart");
    if (start) start.disabled = state.busy || !state.consentChecked;
  }

  function render() {
    setError(state.error);
    bindExitBackBtn();
    const title = $("exitHeaderTitle");
    const sub = $("exitHeaderSubtitle");
    if (title) {
      title.textContent =
        state.tab === "live" && state.session
          ? isScored(state.session.status)
            ? "Interview review"
            : "Live interview"
          : state.hubScreen === "detail" && isMobileExit()
            ? "Interview"
            : "Exit interviews";
    }
    if (sub) {
      if (!state.team?.name) {
        sub.textContent = "Start interview and review past sessions";
      } else if (!scenarioReady() && !repoReady()) {
        sub.textContent = `${state.team.name} · set scenario & repo in Group`;
      } else if (!scenarioReady()) {
        sub.textContent = `${state.team.name} · set scenario in Group`;
      } else if (!repoReady()) {
        sub.textContent = `${state.team.name} · repo not ready`;
      } else {
        sub.textContent = state.team.name;
      }
    }
    if (state.tab === "hub") {
      destroyVoice();
      renderHub();
    } else if (state.session && isScored(state.session.status)) {
      renderReview();
      syncExitHeaderChrome();
    } else if (state.session) {
      renderLive();
      syncExitHeaderChrome();
    } else {
      state.tab = "hub";
      renderHub();
    }
  }

  function bindModals() {
    if (bound) return;
    bound = true;
    bindExitBackBtn();
    $("exitStartClose")?.addEventListener("click", closeStartModal);
    $("exitStartCancel")?.addEventListener("click", closeStartModal);
    $("exitStartModal")?.addEventListener("click", (e) => {
      if (e.target === e.currentTarget) {
        closeStartModal();
        return;
      }
      if (e.target.closest?.('a[href="/group"]')) closeStartModal();
    });
    $("exitIntervieweeName")?.addEventListener("change", (e) => {
      state.intervieweeName = e.target.value;
      syncStartSubmit();
    });
    $("exitStartForm")?.addEventListener("submit", (e) => {
      if (!setupReady()) {
        e.preventDefault();
        const setupHint = $("exitStartSetupHint");
        if (setupHint) setupHint.hidden = false;
        syncStartSubmit();
        return;
      }
      void onStartInterview(e);
    });

    $("exitConsentClose")?.addEventListener("click", () => {
      if (state.busy) return;
      state.pendingSession = null;
      state.consentChecked = false;
      renderConsentModal(false);
    });
    $("exitConsentCancel")?.addEventListener("click", () => {
      if (state.busy) return;
      state.pendingSession = null;
      state.consentChecked = false;
      renderConsentModal(false);
    });
    $("exitConsentModal")?.addEventListener("click", (e) => {
      if (e.target === e.currentTarget && !state.busy) {
        state.pendingSession = null;
        state.consentChecked = false;
        renderConsentModal(false);
      }
    });
    $("exitConsentCheck")?.addEventListener("change", (e) => {
      state.consentChecked = e.target.checked;
      const start = $("exitConsentStart");
      if (start) start.disabled = state.busy || !state.consentChecked;
    });
    $("exitConsentStart")?.addEventListener("click", () => void onConfirmConsent());
  }

  async function mount({ teamId } = {}) {
    bindModals();
    setError(null);
    try {
      if (!state.policy) {
        state.policy = await global.SellmApi.fetchPolicy().catch(() => null);
      }
      state.teams = await global.SellmApi.myTeams();
      if (!state.teams.length) {
        state.teamId = null;
        state.team = null;
        state.tab = "hub";
        const root = $("exitMain");
        if (root) {
          root.innerHTML =
            '<p class="hint" style="padding:20px">No group yet. Claim a group from the landing page, then set scenario and repository on <a href="/group" data-nav="group">Group</a>.</p>';
        }
        return;
      }
      const preferred = teamId && state.teams.some((t) => t.id === teamId) ? teamId : state.teams[0].id;
      if (teamId && preferred !== teamId) {
        global.SellmRouter.navigate(`/teams/${preferred}/exit`, { replace: true });
        return;
      }
      if (!teamId && state.teams.length) {
        // keep /exit without forcing team URL
      }
      state.teamId = preferred;
      if (state.tab !== "live") state.tab = "hub";
      await refreshHub(state.selectedPastId);
      render();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load exit interviews");
      render();
    }
  }

  async function mountPolicy() {
    const root = $("view-policy");
    if (!root) return;
    try {
      const policy = await global.SellmApi.fetchPolicy();
      state.policy = policy;
      root.innerHTML = `
        <div class="policy-panel surface" style="padding:20px;overflow:auto;height:100%">
          <h1 style="margin:0 0 8px">${escapeHtml(policy.consent?.title || "Course policy")}</h1>
          <p class="lede">${escapeHtml(policy.consent?.summary || "")}</p>
          <ul class="consent-checklist">${(policy.consent?.bullets || [])
            .map((b) => `<li>${escapeHtml(b)}</li>`)
            .join("")}</ul>
          <h2 style="margin:18px 0 6px;font-size:1rem">Retention</h2>
          <p class="hint">${escapeHtml(policy.retention?.summary || "")}</p>
          <p class="hint">${escapeHtml(policy.retention?.deletion || "")}</p>
          <p style="margin-top:16px"><a href="/exit" data-nav="exit">← Back to exit interviews</a></p>
        </div>`;
    } catch (err) {
      root.innerHTML = `<p class="error" style="padding:20px">${escapeHtml(err instanceof Error ? err.message : "Failed to load policy")}</p>`;
    }
  }

  global.SellmExit = { mount, mountPolicy };
})(window);
