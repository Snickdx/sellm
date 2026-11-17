# Student UI notes

Student and admin surfaces are **multi-page Jinja templates** with cookie sessions (`sellm_session` HttpOnly), not a client History-API shell.

## Templates

- `app/web/templates/base.html` — shared head / PWA meta
- `app/web/templates/shell.html` — student nav + main block
- `app/web/templates/landing.html` — claim + sign-in (`/`, `/login`, `/claim`)
- `app/web/templates/group.html`, `req.html`, `exit.html`, `exit_session.html`, `policy.html`
- `app/web/templates/admin_base.html` + `admin/workspace.html` — classic interactive admin (`admin.js`) inside the shared course shell; flat `/admin/*` URLs select the active tab

CSS: `static/components/shell.css`, `admin.css`.

## Routes (HTML)

| Path | Page |
|------|------|
| `/`, `/login`, `/claim` | Landing (redirect to `/group` if cookie user) |
| `/group` | Group settings (SSR) |
| `/req` | Requirements chat shell + `chat.js` |
| `/exit`, `/teams/{id}/exit` | Exit hub / session |
| `/policy` | Policy document (SSR) |
| `/admin` | → `/admin/users` |
| `/admin/users`, `/admin/users/{id}`, … | Admin sections |
| `/admin/login` | Admin sign-in form |

JSON APIs under `/api/*` remain for chat, exit machine, voice, and admin mutations. Browser `fetch` uses `credentials: "include"`; Bearer tokens in `localStorage` are still accepted.

Old `/course/*` bookmarks redirect into these paths. Legacy `?view=` on `/admin` redirects to flat admin URLs.

XSS hardening in `chat.js` (attribute escaping, http(s) link allowlist, reflection `textContent`) must stay intact if you edit that file.
