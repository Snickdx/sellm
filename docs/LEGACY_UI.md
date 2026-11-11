# Student UI notes

Student surfaces live in the unified vanilla shell:

- `app/web/templates/index.html` — single document for claim/login, requirements chat, exit interviews, and policy
- `app/web/static/components/` — `router.js`, `claim.js`, `chat.js`, `exit.js`, `exit-voice.js`, `api.js`

Admin stays on `app/web/templates/admin.html` + `admin.js`.

The former React SPA under `frontend/` was removed. Old `/course/*` bookmarks redirect into the shell (`/`, `/exit`, `/teams/{id}/exit`, etc.).

XSS hardening in `chat.js` (attribute escaping, http(s) link allowlist, reflection `textContent`) must stay intact if you edit that file.
