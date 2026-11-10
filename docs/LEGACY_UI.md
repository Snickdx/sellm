# Legacy chat UI

`app/web/static/components/chat.js` is the pre-React stakeholder chat surface.

- Prefer the React SPA under `/course/` for new exit-interview and course features.
- Only apply security / critical bugfixes to `chat.js` until it is retired.
- XSS hardening (attribute escaping, http(s) link allowlist, reflection `textContent`) must stay intact if you edit this file.
