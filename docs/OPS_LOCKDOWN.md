# Ops lockdown (M0)

Run this checklist on any reachable sellm deploy **before** relying on code hardening alone.

## 1. Seeded default accounts

Default usernames (`nick`, `wayne`, `claudine`, `snick`) historically used `badPassword1`.

1. Log in as a known-good admin (not a default password).
2. Reset or disable every seeded account password via Admin → Users or:

```bash
python -m setup.users.manage_users
```

3. Confirm `nick` / `badPassword1` (and other defaults) no longer authenticate.
4. Do **not** set `ALLOW_DEFAULT_SEED_USERS=1` on production.

## 2. Secrets encryption key

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Set `SECRETS_ENCRYPTION_KEY` in the host env and restart. Confirm Settings / app API keys still load. Re-keying without migrating stored ciphertext invalidates existing keys.

## 3. GitHub token

- Prefer **unset** `GITHUB_TOKEN` for student-facing deploys that only need public repos.
- If set, use a fine-scoped PAT limited to the assignment org(s) listed in `GITHUB_ALLOWED_ORGS`.
- Never use a broad org admin PAT for student ingest.

## 4. Database / Neo4j defaults

- Change Neo4j and Postgres passwords away from compose defaults (`password`, `sellm`).
- Do not publish Neo4j/Postgres ports to the public internet; keep them on a private network.
- Prefer Postgres in production over SQLite on ephemeral disk.

## 5. Smoke

1. Cohort (non-seed) user can log in and chat.
2. Known-good admin can open Admin and Exit interview instructor paths.
3. `GET /api/config` without `Authorization` returns `401` (after M1 deploy).
