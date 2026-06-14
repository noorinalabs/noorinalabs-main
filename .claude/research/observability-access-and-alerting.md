# Observability Access + Alerting — Design & Comparison Spike

**Author:** ObsAlertSpike (research spike, P5W1)
**Date:** 2026-06-14
**Audience:** owner + deploy team (Weronika Zielinska / Aisha Idrissi own Caddy; user-service team owns RBAC endpoints)
**Status:** design proposal — no issues filed yet (proposed list at the end)

---

## 0. Ground truth — what is actually deployed today

Verified against `noorinalabs-deploy/` at HEAD (not from the ontology, which still
says "Promtail" — the stack migrated Promtail → Grafana **Alloy** in deploy#132).

| Component | Image / version | How it's reached today | Host port binding |
|-----------|-----------------|------------------------|-------------------|
| Caddy reverse proxy | `caddy:2-alpine` | public | **`0.0.0.0:80,443`** (only public surface) |
| Grafana | `grafana/grafana:11.6.0` | `https://isnad.{BASE_DOMAIN}/grafana` (sub-path), Grafana's own login | `expose 3000` (internal only) |
| Prometheus | `prom/prometheus:v3.4.0`, 30d retention | SSH tunnel | `127.0.0.1:9090` (loopback) |
| Loki | `grafana/loki:2.9.10`, 7d retention, `auth_enabled: false` | SSH tunnel + Grafana datasource | `127.0.0.1:3100` (loopback) |
| Alloy (log shipper) | `grafana/alloy:v1.16.1` | n/a (docker SD → loki.write) | internal |
| Alertmanager | `prom/alertmanager:v0.28.1` | SSH tunnel | `127.0.0.1:9093` (loopback) |
| Blackbox exporter | `prom/blackbox-exporter:v0.25.0` | internal scrape | internal |
| node / postgres exporters | — | internal scrape | `127.0.0.1:9100/9187` (loopback) |

**Security baseline is already correct.** Every observability backend
(Prometheus, Loki, Alertmanager, the exporters) binds to `127.0.0.1` — they are
reachable only via SSH tunnel, never from the internet. The *only* public surface
is Caddy (80/443). The PART 1 requirement "never expose Prometheus/Loki/
Alertmanager raw ports publicly" is therefore **already satisfied** and must be
preserved by any change below — we expose only an auth-gated Grafana.

### Grafana config today (`compose/docker-compose.prod.yml` ~L669)
```yaml
GF_SECURITY_ADMIN_USER: ${GRAFANA_ADMIN_USER:-admin}
GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_ADMIN_PASSWORD:?...}
GF_SERVER_ROOT_URL: https://isnad.${BASE_DOMAIN}/grafana
GF_SERVER_SERVE_FROM_SUB_PATH: "true"
```
Datasources are provisioned (`infra/grafana/provisioning/datasources/datasource.yml`):
Prometheus (default) **and Loki** are both wired. Loki even has a `derivedFields`
trace-link from `request_id` → Prometheus. So **searchable logs already exist** —
they just sit behind Grafana's own (single shared admin) login on a public URL.

### user-service auth/RBAC today (verified in `noorinalabs-user-service/`)
- JWTs are **RS256**, verified against `JWT_PUBLIC_KEY`; public JWKS at
  `users.{BASE_DOMAIN}/.well-known/jwks.json`.
- Role hierarchy (`src/app/services/rbac.py`): `admin=40 > researcher=30 > reader=20 > trial=10`.
- A ready-made `require_admin` dependency exists (`src/app/dependencies.py`,
  `AdminUserDep`) — but it reads the **`Authorization: Bearer` header**, not a cookie.
- user-service is an OAuth **client** (consumes Google/etc. via
  `/auth/oauth/{provider}/callback`). It is **NOT an OAuth/OIDC authorization
  server** — there is no `/authorize` + `/token` + `/userinfo` IdP surface.
- Refresh/CSRF cookies are `HttpOnly; SameSite=Lax`, **host-only on `users.*`** —
  they are NOT sent to `isnad.*` or a new `grafana.*` host.

### Caddy vhost family / carve-out contract (important for PART 1)
`caddy/Caddyfile` runs three vhosts: `{BASE_DOMAIN}` (landing),
`isnad.{BASE_DOMAIN}` (frontend + isnad-graph API + `/grafana`), and
`users.{BASE_DOMAIN}` (pure user-service API). The isnad↔users split is a
load-bearing contract (deploy#220 / #245): `/metrics` is `respond 403` on both
public vhosts, CSP on `users.*` is `default-src 'none'`, and the
`user-service-health` carve-out is **currently drifted/missing** (deploy#449 —
the `/api/v1/user-service/health` blackbox probe is RED on stg right now). Any
new auth flow that touches `isnad.*` must respect that vhost's CSP
(`connect-src 'self' https://users.{BASE_DOMAIN}`) and the carve-out ordering
(specific `handle` before the `/api/*` catch-all).

---

## PART 1 — Admin-gated observability access

**Owner decision (given):** expose Grafana + Loki log search at a public,
auth-gated URL, **admins only**.

### What "Loki log search" means here
Loki has no UI of its own. The search surface is **Grafana → Explore → Loki
datasource** (LogQL), which is already provisioned. Gating Grafana therefore
gates log search too — the owner gets *searchable* logs (LogQL, live tail,
label filters, the `request_id` trace-link), not just the 3 pre-built
dashboards. No separate Loki exposure is needed or wanted.

### The crux: browsers send cookies, not Bearer tokens
The existing `require_admin` dependency authenticates a **`Bearer` JWT**. But a
browser *navigating* to a Grafana URL sends only **cookies** scoped to that host
— and today's auth cookies are host-only on `users.*`. So no option that relies
on "the browser already carries an admin credential to the Grafana host" works
out of the box. Every viable design has to solve **"what credential does the
gate see, and how does an un-logged-in admin get one."** This shapes the options.

### Option comparison

#### (a) Caddy `forward_auth` → user-service, verify admin role  ★ RECOMMENDED (as end state)
Caddy intercepts every request to the Grafana host, sub-requests a user-service
endpoint, and only proxies through on a 2xx.

```
# new vhost
grafana.{$BASE_DOMAIN} {
    forward_auth user-service:8000 {
        uri /auth/forward-auth
        copy_headers X-Auth-User X-Auth-Roles
    }
    reverse_proxy grafana:3000
    header { Strict-Transport-Security ...; -Server }
}
```

What has to be built:
1. **user-service `GET /auth/forward-auth`** — a **cookie-based** (not Bearer)
   variant of `require_admin`. Reads a session cookie, validates it, checks
   `user_has_minimum_role(roles, "admin")`. Returns `200` + `X-Auth-User: <email>`
   / `X-Auth-Roles: admin` on success; `401` if no/invalid session; `403` if
   authenticated-but-not-admin.
2. **A cookie the gate can actually see.** Today's refresh cookie is host-only on
   `users.*`. Two sub-choices:
   - (a1) On login/OAuth-callback, additionally set a **domain-scoped**
     `Domain=.{BASE_DOMAIN}; HttpOnly; Secure; SameSite=Lax` admin-session cookie
     so it is sent to `grafana.{BASE_DOMAIN}` too. Smallest surface, but broadens
     cookie scope to all subdomains → **needs a security review** (mitigated:
     HttpOnly so JS can't read it; only `/auth/forward-auth` validates it; bind it
     to the session and keep TTL short).
   - (a2) Keep `users.*` host-only and run forward-auth as a redirect dance
     (Caddy `handle_response` 401 → `redir` to a `users.*` login that round-trips
     and sets the domain cookie). More moving parts; (a1) is cleaner.
3. **Grafana auth-proxy mode** so the verified admin is auto-logged-in (no second
   Grafana password prompt):
   ```yaml
   GF_AUTH_PROXY_ENABLED: "true"
   GF_AUTH_PROXY_HEADER_NAME: X-WEBAUTH-USER     # Caddy copies X-Auth-User → this
   GF_AUTH_PROXY_HEADER_PROPERTY: username
   GF_AUTH_PROXY_AUTO_SIGN_UP: "true"
   GF_AUTH_DISABLE_LOGIN_FORM: "true"            # the ONLY way in is via the proxy
   # keep GF_SECURITY_ADMIN_* as break-glass (reachable via SSH tunnel only)
   ```
   Grafana org-role can be defaulted to `Admin` (single-owner nonprofit) or
   header-mapped from `X-Auth-Roles` later.
4. **Caddy `handle_response`** on 401 → redirect the browser to the
   frontend login (`https://isnad.{BASE_DOMAIN}/login?return=...`) so an
   un-logged-in admin gets a login page, not a bare 401.

- **Pros:** true RBAC integration — the gate IS user-service's `admin` role;
  per-admin identity in Grafana; one login (SSO-like); honors the owner's exact
  ask ("only admin-**role** users"); no new IdP to build; reuses `require_admin`
  logic.
- **Cons:** requires coordinated user-service + deploy changes; the domain-scoped
  cookie needs a security review; auth-proxy trust means Grafana MUST be
  unreachable except through Caddy (already true — `expose 3000`, not published).

#### (b) Grafana's own admin login + Caddy `basic_auth`
Add `basic_auth` in front of Grafana; keep `GF_SECURITY_ADMIN_*`.
- **Pros:** near-zero effort, no app changes, ships in one small deploy PR;
  immediately gives an auth gate on a public URL.
- **Cons:** **not** RBAC-integrated — "admins" = whoever holds two shared static
  secrets, not user-service `admin` role; no per-admin identity; secret rotation
  is manual; double login (basic-auth then Grafana). Conflicts with the owner's
  "admin-**role** users" wording and with the repo's
  *prefer-correct-over-expedient* posture (memory: pre-launch, do the right fix).
- **Verdict:** acceptable **interim** only if logs are needed before (a) lands.

#### (c) Grafana OAuth with user-service as IdP (`generic_oauth`)
Grafana's `generic_oauth` against user-service acting as an OIDC provider, with
`role_attribute_path` mapping the `admin` claim → Grafana Admin.
- **Pros:** cleanest "real SSO" on paper; per-admin identity; role mapping native.
- **Cons:** **user-service is not an OAuth/OIDC server today** — it's a client.
  This means building a full `/authorize` + `/token` + `/userinfo` (+ consent)
  authorization-server surface in user-service. Large effort, large new attack
  surface, for a single-owner nonprofit. **Over-engineered** for the need.
- **Verdict:** reject for now; revisit only if the platform later needs OIDC for
  multiple downstream apps (then it's worth building once).

### PART 1 recommendation
**Adopt (a): Caddy `forward_auth` → user-service `/auth/forward-auth` + Grafana
auth-proxy, on a dedicated `grafana.{BASE_DOMAIN}` vhost, using a domain-scoped
admin-session cookie (a1).** Use a dedicated vhost rather than the existing
`isnad.*/grafana` sub-path so the auth gate doesn't entangle the isnad.* CSP /
carve-out contract, and DNS/TLS stays clean (Caddy auto-TLS issues for the new
host automatically). Loki search = Grafana Explore (no separate exposure). Keep
all backends on `127.0.0.1`.

If the owner wants logs **this week**, ship **(b) basic_auth as a one-PR interim**
and treat (a) as the immediate follow-up — but (a) is the correct end state and
should not be skipped given the "admin-role" requirement.

**Migration note:** once `grafana.{BASE_DOMAIN}` is live and gated, the old
`isnad.{BASE_DOMAIN}/grafana` sub-path handler should be removed (or made a
redirect) so there is exactly one, gated, Grafana entrypoint.

---

## PART 2 — Alerting integration

**Owner steer:** explore broadly, prioritize FREE-TIER / NONPROFIT incentives.
**Constraint:** one Hetzner VPS, small budget, effectively a single on-call
person (the owner). The receiver plugs into the **existing Alertmanager v0.28.1**.

### Current state (important — most of the work is already done)
Alertmanager is **already wired to a Slack receiver** for both `default` and
`critical` routes (`infra/alertmanager/alertmanager.{stg,prod}.yml`), using the
`api_url_file: /etc/alertmanager/slack_webhook_url` secret-file pattern. The
webhook file currently contains the literal `<unset>`, so alerts route to
nowhere. **Slack delivery is therefore one secret away from working** — no config
change needed, just set `SLACK_WEBHOOK_URL` in the GitHub Environment.

Alertmanager v0.28.1 has **native receivers** for: `slack_configs`,
`telegram_configs`, `discord_configs`, `email_configs`, `pagerduty_configs`,
`opsgenie_configs`, `pushover_configs`, `webhook_configs`, plus SNS/WeChat/VictorOps.
This matters: native = a few lines of YAML; non-native (ntfy, Twilio SMS) = a
small bridge service.

### Channel comparison

| Channel | Free tier / nonprofit | AM integration effort | Escalation / reach | Notes |
|---------|----------------------|------------------------|--------------------|-------|
| **Slack** | Free workspace OK; free plan limits history (90d) | **Done** (native, already wired — set secret) | Chat + mobile push (push for alerts is not super reliable on free) | Zero added effort; already the configured receiver |
| **Telegram** | Fully free, no limits | Low — native `telegram_configs`, BotFather token + chat_id, `bot_token_file` fits the secret-file pattern | Reliable **instant phone push** via the app; no SMS cost | Best free phone-push option; no per-message cost |
| **Discord** | Fully free | Low — native `discord_configs` (webhook URL) | Chat + mobile push | Equivalent to Slack/Telegram; pick by where owner lives |
| **Email** | Free via SMTP (Gmail app-pw, or a transactional free tier) | Low — native `email_configs` | Inbox (no real-time escalation) | Ideal **independent backup** path — different infra than chat |
| **ntfy.sh** | Free public server; **self-hostable on the same VPS** (OSS) | Medium — Alertmanager `webhook_configs` → small format bridge (AM JSON ≠ ntfy body) | Phone push via app; can do priority | Great nonprofit fit (self-host = no third party), but needs a tiny adapter |
| **Pushover** | **$5 one-time** per platform (not free, but cheap, no subscription) | Low-medium — `pushover_configs` (native) | Reliable phone push, priority/retry (emergency ack) | Cheapest reliable push *with ack/retry*; good escalation upgrade |
| **Healthchecks.io** | Free 20 checks; **explicit nonprofit discount** | Medium — it's a **dead-man's switch**, not an AM receiver; cron on VPS pings it | Alerts when a heartbeat STOPS (push/email/etc.) | **Complement, not replacement** — catches "Prometheus/Alertmanager/the box itself died" which AM can't self-report |
| **Grafana OnCall (OSS)** | Free, self-hostable; already have Grafana | **High** — separate service (engine + Redis) on a small VPS; AM → OnCall integration | On-call schedules + escalation chains; mobile push; phone/SMS only via BYO Twilio | ⚠️ **Grafana Labs put OnCall OSS into maintenance/deprecation (2025), steering to Grafana IRM cloud.** Do not bet the nonprofit on it. |
| **PagerDuty** | Free tier (≤5 users, limited); has a **nonprofit program** | Low — native `pagerduty_configs` (routing key) | Full escalation + **phone call / SMS**, schedules, ack | Strong real escalation, but heavyweight for a 1-person nonprofit; free tier is limited |
| **Opsgenie** (Atlassian) | Free tier ≤5 users (SMS/phone limited on free) | Low — native `opsgenie_configs` | Escalation + push; SMS/phone on paid | Comparable to PagerDuty; less generous free SMS |
| **Twilio SMS** | **Pay-per-message** (not free) | Medium-high — no native AM receiver; needs `webhook_configs` → bridge → Twilio API | Real **SMS** to any phone, no app needed | Most universal reach, but ongoing cost + custom glue; reserve for "must get an SMS" |

### PART 2 recommendation
For a single-owner nonprofit on one VPS, full PagerDuty/OnCall escalation
machinery is over-scoped. The real need is *"reliably notify the owner's phone
when the box breaks, with an independent backup, and a way to know if the watcher
itself died."*

- **Primary: Telegram** (`telegram_configs`) — free, native, instant phone push,
  no SMS cost, no extra service to host, fits the existing `*_file` secret
  pattern. (If the owner would rather stay in Slack, **just set the already-wired
  Slack webhook secret** — that's the zero-effort path and a legitimate primary;
  Telegram wins on push reliability/cost.)
- **Backup: Email** (`email_configs`) — an **independent delivery path** so a
  Slack/Telegram outage doesn't blind the owner. Native, ~free.
- **Strongly-recommended complement: Healthchecks.io** (nonprofit discount) as a
  **dead-man's switch** — a cron on the VPS pings it; if Prometheus/Alertmanager/
  the whole VPS dies, Alertmanager cannot alert you *about itself*. Healthchecks
  catches that blind spot. This is the single highest-value add beyond a chat
  receiver.
- **Future upgrade path (only if/when real escalation is needed):** Pushover
  ($5 one-time, native, ack/retry) or the PagerDuty nonprofit program. Skip
  Grafana OnCall OSS due to its deprecation.

### Live test case (use the alerts already firing on stg)
The brief notes **4 critical alerts currently firing on stg: 3 blackbox-probe +
1 alembic-gate.** These map to rules in `infra/prometheus/alerts.yml`:
`BlackboxProbeFailing` / `BlackboxUnexpectedStatus` (note: the
`user-service-health` probe is red because of the **deploy#449** Caddy carve-out
drift) and `UserServiceAlembicGateFailure` / `UserServiceAlembicGateStale`.
**Validation step:** set the chosen receiver secret on the `staging` GitHub
Environment, redeploy stg, and confirm all 4 currently-firing alerts land in the
channel within one `repeat_interval` (stg critical = 1h, but `group_wait` 30s
means the first delivery is near-immediate). This is a real end-to-end test, not
a synthetic one. (Separately, deploy#449 should be fixed so that probe goes
green — but its firing is convenient proof the pipeline delivers.)

---

## Recommended-approach summary

- **PART 1:** Expose **only** Grafana, on a new `grafana.{BASE_DOMAIN}` vhost,
  behind **Caddy `forward_auth` → user-service `/auth/forward-auth`** (new
  cookie-based admin check reusing the `admin` role) with **Grafana auth-proxy**
  for single-sign-on, using a **domain-scoped admin-session cookie** (security
  review required). Loki search = Grafana Explore (Loki datasource already
  provisioned). Keep Prometheus/Loki/Alertmanager on `127.0.0.1` (already true).
  Optional one-PR `basic_auth` interim if logs are needed before the RBAC path
  lands.
- **PART 2:** **Telegram** as primary alert channel (free, native, phone push) —
  or just set the already-wired **Slack** secret for the zero-effort path —
  **Email** as an independent backup, and **Healthchecks.io** (nonprofit
  discount) as a dead-man's switch for the monitor itself. Avoid Grafana OnCall
  OSS (deprecated); reserve Pushover/PagerDuty-nonprofit for future real
  escalation.

---

## Proposed GitHub issues (sequenced — NOT yet created)

**PART 2 first** (cheapest, highest immediate value, no app changes):

1. **noorinalabs-deploy** — *"Activate alerting: set Telegram (primary) + Email
   (backup) receivers in Alertmanager"* — add `telegram_configs` + `email_configs`
   to `alertmanager.{stg,prod}.yml` via `*_file` secrets; set
   `TELEGRAM_BOT_TOKEN` / chat-id + SMTP secrets in the `staging`/`production`
   GitHub Environments; verify the 4 stg alerts deliver. (If owner prefers Slack
   primary: scope shrinks to "set `SLACK_WEBHOOK_URL` secret + verify.")
2. **noorinalabs-deploy** — *"Add Healthchecks.io dead-man's switch for the
   monitoring stack"* — cron/systemd-timer on the VPS pings a Healthchecks check;
   apply nonprofit discount; document in RUNBOOK.
3. **noorinalabs-deploy** — *"Fix deploy#449 user-service-health Caddy carve-out"*
   (already filed as **deploy#449** — link, don't duplicate) so the red
   blackbox probe goes green after alerting is live.

**PART 1** (RBAC-gated Grafana — coordinated cross-repo, sequence matters):

4. **noorinalabs-main (meta-issue)** — *"Admin-gated public Grafana + Loki log
   search"* — cross-repo umbrella linking the user-service + deploy issues below.
5. **noorinalabs-user-service** — *"Add cookie-based `GET /auth/forward-auth`
   admin-verification endpoint"* — cookie variant of `require_admin`; returns
   200 + `X-Auth-User`/`X-Auth-Roles` or 401/403; tests in `tests/test_rbac.py`.
6. **noorinalabs-user-service** — *"Emit domain-scoped (`Domain=.{BASE_DOMAIN}`)
   admin-session cookie on login/OAuth-callback"* — **must include a security
   review** of broadening cookie scope to subdomains. (Hard-dep of #5 being
   usable from a browser.)
7. **noorinalabs-deploy** — *"Add gated `grafana.{BASE_DOMAIN}` vhost with
   `forward_auth` + Grafana auth-proxy"* — new Caddyfile vhost, DNS record,
   `GF_AUTH_PROXY_*` + `GF_AUTH_DISABLE_LOGIN_FORM` in compose, `handle_response`
   401→login redirect; depends on #5/#6.
8. **noorinalabs-deploy** — *"Retire `isnad.*/grafana` sub-path after gated vhost
   is live"* — remove or redirect the old un-gated sub-path so there's one
   entrypoint; depends on #7.
9. *(optional, only if logs needed before #5–#8)* **noorinalabs-deploy** —
   *"Interim: `basic_auth` in front of Grafana"* — one-PR stopgap, removed when #7 lands.

---

## Open questions for the owner

1. **Primary alert channel:** Telegram (recommended — free phone push) or just
   activate the **already-wired Slack** (zero effort)? Where do you actually
   watch for pages — phone app, Slack, email?
2. **PART 1 RBAC now, or basic_auth interim first?** The correct end state (a)
   is a coordinated user-service + deploy change; basic_auth (b) ships in one PR
   today but isn't role-integrated. Do you want logs immediately, or wait for the
   proper gate?
3. **Domain-scoped cookie acceptable?** Option (a) needs an admin-session cookie
   scoped `Domain=.{BASE_DOMAIN}` so it reaches `grafana.*`. Are you OK
   broadening cookie scope to all subdomains (with HttpOnly + short TTL +
   security review), or do you want the redirect-dance variant (a2) that keeps
   cookies host-only?
4. **Dead-man's switch:** OK to depend on a third party (Healthchecks.io free /
   nonprofit) for "the monitor died" detection, or prefer fully self-hosted
   (ntfy + a local heartbeat)?
5. **Grafana org role:** default every gated admin to Grafana **Admin** (simplest
   for single-owner), or map `X-Auth-Roles` → Grafana role for future
   multi-admin/least-privilege?
