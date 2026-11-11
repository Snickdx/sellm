/**
 * Shared fetch helpers for the unified student shell.
 * Auth token key matches chat.js / admin: auth_token
 */
(function (global) {
  const AUTH_TOKEN_KEY = "auth_token";

  function getToken() {
    return localStorage.getItem(AUTH_TOKEN_KEY);
  }

  function setToken(token) {
    if (token) localStorage.setItem(AUTH_TOKEN_KEY, token);
    else localStorage.removeItem(AUTH_TOKEN_KEY);
  }

  function authHeaders(extra) {
    const headers = Object.assign({}, extra || {});
    const token = getToken();
    if (token) headers.Authorization = `Bearer ${token}`;
    return headers;
  }

  async function parseError(response) {
    let detail = `Request failed (${response.status})`;
    try {
      const data = await response.json();
      if (typeof data.detail === "string") detail = data.detail;
      else if (Array.isArray(data.detail)) {
        detail = data.detail.map((d) => d.msg || JSON.stringify(d)).join("; ");
      }
    } catch (_) {
      /* ignore */
    }
    return detail;
  }

  async function request(path, options) {
    const opts = options || {};
    const headers = authHeaders(
      opts.body instanceof FormData
        ? opts.headers
        : Object.assign({ "Content-Type": "application/json" }, opts.headers || {}),
    );
    if (opts.body instanceof FormData) {
      delete headers["Content-Type"];
    }
    const response = await fetch(path, Object.assign({}, opts, { headers }));
    if (!response.ok) throw new Error(await parseError(response));
    if (response.status === 204) return null;
    const text = await response.text();
    if (!text) return null;
    try {
      return JSON.parse(text);
    } catch (_) {
      return text;
    }
  }

  function canDeleteExitSession(user, createdById) {
    if (!user) return false;
    if (user.role === "admin" || user.is_admin) return true;
    return createdById != null && createdById === user.user_id;
  }

  global.SellmApi = {
    AUTH_TOKEN_KEY,
    getToken,
    setToken,
    authHeaders,
    request,
    canDeleteExitSession,
    login(username, password) {
      return request("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ username, password }),
      }).then((data) => data.token);
    },
    me() {
      return request("/api/auth/me");
    },
    logout() {
      return request("/api/auth/logout", { method: "POST" }).catch(() => null);
    },
    searchRoster(q) {
      const params = new URLSearchParams({ q, available_only: "true" });
      return request(`/api/roster/search?${params}`);
    },
    claimGroup(body) {
      return request("/api/roster/claim", {
        method: "POST",
        body: JSON.stringify(body),
      });
    },
    myTeams() {
      return request("/api/me/teams");
    },
    teamDetail(teamId) {
      return request(`/api/teams/${teamId}`);
    },
    teamRepos(teamId) {
      return request(`/api/teams/${teamId}/repositories`);
    },
    setupGroup(body) {
      return request("/api/me/group-setup", {
        method: "POST",
        body: JSON.stringify(
          Object.assign(
            {
              scenario_slug: null,
              branch: null,
              team_id: null,
              analyze_now: true,
            },
            body,
          ),
        ),
      });
    },
    myGroup() {
      return request("/api/me/group");
    },
    updateGroupMembers(memberIds) {
      return request("/api/me/group/members", {
        method: "PUT",
        body: JSON.stringify({ member_ids: memberIds }),
      });
    },
    listScenarios() {
      return request("/api/scenarios");
    },
    listExitSessions(teamId) {
      return request(`/api/teams/${teamId}/exit-sessions`);
    },
    createExitSession(teamId, body) {
      return request(`/api/teams/${teamId}/exit-session`, {
        method: "POST",
        body: JSON.stringify(body || {}),
      });
    },
    fetchExitSession(sessionId) {
      return request(`/api/exit-sessions/${sessionId}`);
    },
    deleteExitSession(sessionId) {
      return request(`/api/exit-sessions/${sessionId}`, { method: "DELETE" });
    },
    consentExitSession(sessionId, granted) {
      return request(`/api/exit-sessions/${sessionId}/consent`, {
        method: "POST",
        body: JSON.stringify({ granted: granted !== false }),
      });
    },
    startExitSession(sessionId) {
      return request(`/api/exit-sessions/${sessionId}/start`, { method: "POST" });
    },
    nextExitQuestion(sessionId) {
      return request(`/api/exit-sessions/${sessionId}/next`, { method: "POST" });
    },
    submitExitAnswer(sessionId, text, requestProbe) {
      return request(`/api/exit-sessions/${sessionId}/answers`, {
        method: "POST",
        body: JSON.stringify({ text, request_probe: !!requestProbe }),
      });
    },
    submitProbeAnswer(sessionId, text) {
      return request(`/api/exit-sessions/${sessionId}/answers/probe`, {
        method: "POST",
        body: JSON.stringify({ text }),
      });
    },
    finishExitSession(sessionId) {
      return request(`/api/exit-sessions/${sessionId}/finish`, { method: "POST" });
    },
    fetchExitReport(sessionId) {
      return request(`/api/exit-sessions/${sessionId}/report`);
    },
    fetchPolicy() {
      return request("/api/policy");
    },
    fetchVoiceStatus(sessionId) {
      return request(`/api/exit-sessions/${sessionId}/voice`);
    },
    startVoiceRecording(sessionId) {
      return request(`/api/exit-sessions/${sessionId}/voice/recording/start`, {
        method: "POST",
      });
    },
    stopVoiceRecording(sessionId) {
      return request(`/api/exit-sessions/${sessionId}/voice/recording/stop`, {
        method: "POST",
      });
    },
    async uploadVoiceRecording(sessionId, blob, filename) {
      const body = new FormData();
      body.append("file", blob, filename || `exit-${sessionId}.webm`);
      return request(`/api/exit-sessions/${sessionId}/voice/recording/upload`, {
        method: "POST",
        body,
      });
    },
    async fetchRecordingObjectUrl(sessionId) {
      const response = await fetch(`/api/exit-sessions/${sessionId}/recording`, {
        headers: authHeaders(),
      });
      if (!response.ok) {
        throw new Error(
          response.status === 404 ? "No recording available" : `Recording failed (${response.status})`,
        );
      }
      return URL.createObjectURL(await response.blob());
    },
  };
})(window);
