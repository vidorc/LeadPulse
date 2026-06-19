# LeadPulse — API Reference

Base URL: all versioned endpoints are mounted under `/api/v1`. Health probes
live at the root. Interactive OpenAPI docs are served at `/docs`.

## Authentication

LeadPulse uses JWT bearer auth. Obtain tokens via `signup` or `login`, then send
the access token on every protected call:

```
Authorization: Bearer <access_token>
```

- **Access tokens** are short-lived (~15 minutes, `ACCESS_TOKEN_EXPIRE_MINUTES`).
- **Refresh tokens** are long-lived (~14 days, `REFRESH_TOKEN_EXPIRE_DAYS`),
  persisted server-side, and revocable. Use `refresh` to rotate.
- The token does **not** carry your role. The server resolves your current role
  and active membership from the database on every request, so revocations and
  role changes take effect immediately.

**Public endpoints** (no auth): `POST /auth/signup`, `POST /auth/login`,
`POST /auth/refresh`, and all `GET /health/*`. `POST /auth/logout` takes a
refresh token in the body rather than a bearer header. Everything else requires
a valid access token.

### Roles

Roles are ranked `OWNER > ADMIN > MANAGER > AGENT`. Endpoints that mutate shared
configuration require **manager or above** (noted per endpoint as
`min role: manager`). All other authenticated endpoints accept any active
member.

### Common status codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 201 | Created |
| 204 | Success, no content (logout) |
| 400 | Validation / business error (e.g. email already exists) |
| 401 | Missing/invalid/expired token, or bad credentials |
| 403 | Authenticated but below the required role, or no membership in the org |
| 404 | Resource not found (or not in your tenant) |
| 422 | Request body failed schema validation |
| 429 | Rate limit exceeded (includes `Retry-After`) |
| 503 | Readiness probe: a dependency is down |

---

## Quick start (curl)

```bash
BASE=http://localhost:8000/api/v1

# 1. Sign up — creates an org and its OWNER, returns a token pair
TOKENS=$(curl -s -X POST $BASE/auth/signup \
  -H 'Content-Type: application/json' \
  -d '{
        "email": "owner@acme.test",
        "password": "supersecret123",
        "org_name": "Acme Sales",
        "full_name": "Dana Owner"
      }')

# 2. Extract the access token (jq shown; any JSON tool works)
ACCESS=$(echo "$TOKENS" | jq -r .access_token)

# 3. Call a protected endpoint
curl -s $BASE/leads/ -H "Authorization: Bearer $ACCESS"

# 4. Create a lead
curl -s -X POST $BASE/leads/ \
  -H "Authorization: Bearer $ACCESS" \
  -H 'Content-Type: application/json' \
  -d '{"name":"Jordan Buyer","email":"jordan@lead.test","source":"website","message":"Need 50 seats by Q3"}'
```

---

## Auth — `/api/v1/auth`

### POST `/auth/signup`
Create a new organization and its first user (always `OWNER`). Returns a token
pair. Public.

Request body (`SignupRequest`):

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `email` | string (email) | yes | valid email |
| `password` | string | yes | 8–128 chars |
| `org_name` | string | yes | 1–255 chars |
| `full_name` | string | no | ≤255 chars |

Response `201` (`TokenResponse`): `{ access_token, refresh_token, token_type }`
(`token_type` is `"bearer"`).
Errors: `400` if a user with that email already exists.

### POST `/auth/login`
Authenticate and receive a token pair. Public.

Request body (`LoginRequest`):

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `email` | string (email) | yes | |
| `password` | string | yes | 1–128 chars |
| `org_id` | integer | no | selects the org when the user belongs to several; otherwise the sole membership is used |

Response `200` (`TokenResponse`). Errors: `401` with a uniform
`"Invalid credentials"` message (no user enumeration).

### POST `/auth/refresh`
Rotate a refresh token: validates it, revokes the old `jti`, and issues a new
pair. Public.

Request body (`RefreshRequest`): `{ refresh_token: string }`.
Response `200` (`TokenResponse`). Errors: `401` (revoked, unknown, expired, or
wrong token type).

### POST `/auth/logout`
Revoke a refresh token. Best-effort and idempotent.

Request body (`RefreshRequest`): `{ refresh_token: string }`.
Response `204` (no content).

### GET `/auth/me`
Return the current authenticated user. Auth required.

Response `200` (`UserResponse`): `{ id, email, full_name?, is_active }`.
Errors: `404` if the user record is missing.

---

## Leads — `/api/v1/leads`

All endpoints require auth.

### POST `/leads/`
Create a lead and offload AI qualification to the async plane (tenant-scoped).

Request body (`LeadCreate`):

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `name` | string | yes | 1–255 chars |
| `phone` | string | no | ≤64 chars |
| `email` | string (email) | no | |
| `source` | string | yes | 1–64 chars |
| `message` | string | no | ≤10,000 chars |

Response `201` (`LeadResponse`, see below). The new lead starts in status `new`;
qualification fields populate asynchronously after the worker runs.

### GET `/leads/`
List all leads in your org. Response `200`: `list[LeadResponse]`.

### GET `/leads/review-queue`
List leads flagged for human review. Response `200`: `list[LeadResponse]`.

### GET `/leads/dashboard/summary`
Aggregate counts for the dashboard. Response `200`: an object of summary counts
(e.g. totals by status/decision and review-queue size).

### GET `/leads/{lead_id}`
Fetch one lead. Response `200` (`LeadResponse`). Errors: `404` if not found or
not in your tenant.

### POST `/leads/{lead_id}/override`
Manually set a lead's decision, clearing the review flag and recording a
`HUMAN_OVERRIDE` timeline event. **min role: manager.**

Request body (`LeadOverride`):

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `decision` | enum `LeadDecision` | yes | `hot_lead` / `warm_lead` / `cold_lead` / `manual_review` |
| `review_notes` | string | no | ≤10,000 chars |

Response `200` (`LeadResponse`). Errors: `404`.

### GET `/leads/{lead_id}/events`
Return the lead's immutable timeline. Response `200`: `list[EventResponse]`.
Errors: `404` if the lead is not in your tenant.

**`LeadResponse` fields:** `id`, `org_id`, `name?`, `phone?`, `email?`,
`source?`, `status` (`LeadStatus`), `message?`, `intent?` (`Intent`), `budget?`,
`budget_amount?` (number), `timeline?`, `location?`, `urgency?` (`Urgency`),
`score?` (int), `ai_summary?`, `decision?` (`LeadDecision`), `next_action?`,
`action_result?`, `requires_human_review` (bool), `review_notes?`, `owner_id?`,
`team_id?`, `created_at?`, `updated_at?`, `processed_at?`.

**`EventResponse` fields:** `id`, `entity_type` (`EntityType`), `entity_id`,
`event_type` (string), `payload?` (object), `actor?`, `occurred_at`.

Enum values — `LeadStatus`: `new`, `qualifying`, `qualified`, `manual_review`,
`assigned`, `converted`, `lost`. `Intent`: `purchase`, `inquiry`, `support`,
`spam`, `unknown`. `Urgency`: `high`, `medium`, `low`.

---

## Opportunities — `/api/v1/opportunities`

All endpoints require auth.

### POST `/opportunities/`
Create a deal (starts in stage `new`, stamps `stage_changed_at`, emits
`OPPORTUNITY_CREATED`).

Request body (`OpportunityCreate`):

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `title` | string | yes | 1–255 chars |
| `lead_id` | integer | no | link to a lead |
| `value_amount` | number | no | ≥ 0 |
| `owner_id` | integer | no | |
| `team_id` | integer | no | |

Response `201` (`OpportunityResponse`).

### GET `/opportunities/`
List opportunities in your org. Response `200`: `list[OpportunityResponse]`.

### GET `/opportunities/{opp_id}`
Fetch one. Response `200` (`OpportunityResponse`). Errors: `404`.

### POST `/opportunities/{opp_id}/stage`
Transition pipeline stage (updates `stage_changed_at`, sets `closed_at` on
terminal stages, emits `STAGE_CHANGED`). Idempotent if the stage is unchanged.

Request body (`OpportunityStageUpdate`): `{ stage: OpportunityStage }`.
Response `200` (`OpportunityResponse`). Errors: `404`.

### POST `/opportunities/{opp_id}/proposals`
Add a draft proposal to an opportunity.

Request body (`ProposalCreate`):

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `title` | string | yes | 1–255 chars |
| `amount` | number | no | ≥ 0 |

Response `201` (`ProposalResponse`). Errors: `404` (opportunity not found).

### POST `/opportunities/proposals/{proposal_id}/send`
Mark a proposal `sent` (stamps `sent_at`, emits `PROPOSAL_SENT`). This is the
event leak detection's `PROPOSAL_COLD` rule measures against.

Response `200` (`ProposalResponse`). Errors: `404`.

### POST `/opportunities/{opp_id}/meetings`
Schedule a meeting (status `scheduled`, emits `MEETING_SCHEDULED`).

Request body (`MeetingCreate`): `{ title: string (1–255), scheduled_at:
datetime }`.
Response `201` (`MeetingResponse`). Errors: `404` (opportunity not found).

### POST `/opportunities/meetings/{meeting_id}/complete`
Mark a meeting `completed` (emits `MEETING_COMPLETED`).
Response `200` (`MeetingResponse`). Errors: `404`.

**`OpportunityResponse` fields:** `id`, `org_id`, `lead_id?`, `title`, `stage`
(`OpportunityStage`), `value_amount?`, `currency`, `owner_id?`, `team_id?`,
`stage_changed_at`, `closed_at?`, `created_at`, `updated_at`.

**`ProposalResponse` fields:** `id`, `opportunity_id`, `title`, `amount?`,
`status` (`ProposalStatus`), `sent_at?`.

**`MeetingResponse` fields:** `id`, `opportunity_id`, `title`, `scheduled_at`,
`status` (`MeetingStatus`).

Enum values — `OpportunityStage`: `new`, `contacted`, `qualified`,
`proposal_sent`, `negotiation`, `won`, `lost` (`won`/`lost` are terminal).
`ProposalStatus`: `draft`, `sent`, `accepted`, `rejected`, `expired`.
`MeetingStatus`: `scheduled`, `completed`, `no_show`, `cancelled`.

---

## Follow-Up Engine — `/api/v1/follow-ups`

### POST `/follow-ups/sequences`
Create a follow-up sequence with ordered steps. **min role: manager.**

Request body (`SequenceCreate`):

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `name` | string | yes | 1–255 chars |
| `steps` | array of step | yes | at least 1 step |

Each step (`SequenceStepCreate`):

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `delay_hours` | integer | yes | 0 … 8760 (1 year), measured from enrollment |
| `action` | string | no | default `"email"`, ≤64 chars |
| `subject` | string | no | ≤255 chars |
| `body` | string | no | |

Response `201` (`SequenceResponse`).

### GET `/follow-ups/sequences`
List sequences in your org. Response `200`: `list[SequenceResponse]`. Auth.

### POST `/follow-ups/enroll`
Enroll a lead into a sequence; schedules the first step as a durable
`ScheduledJob`. Enrolling a lead already actively enrolled returns the existing
enrollment (idempotent). Auth.

Request body (`EnrollRequest`): `{ lead_id: integer, sequence_id: integer }`.
Response `201` (`EnrollmentResponse`). Errors: `404` if the lead or sequence is
not in your tenant.

### POST `/follow-ups/leads/{lead_id}/cancel`
Cancel all active enrollments for a lead and their pending scheduled jobs (use
when a rep engages the lead). Auth.
Response `200`: `{ "cancelled_enrollments": <int> }`.

**`SequenceResponse` fields:** `id`, `org_id`, `name`, `is_active`, `steps`
(array of `{ id, step_order, delay_hours, action, subject?, body? }`).

**`EnrollmentResponse` fields:** `id`, `sequence_id`, `lead_id`, `status`
(`EnrollmentStatus`: `active`/`completed`/`cancelled`), `current_step`,
`enrolled_at`, `completed_at?`.

---

## Revenue Leak Detection — `/api/v1/leak-detection`

### PUT `/leak-detection/policies`
Create or update the SLA policy for a leak type (one per type per org —
upsert). **min role: manager.**

Request body (`SLAPolicyUpsert`):

| Field | Type | Required | Constraints / default |
|-------|------|----------|------------------------|
| `leak_type` | enum `LeakType` | yes | `lead_ignored` / `opp_stalled` / `meeting_missed` / `proposal_cold` |
| `threshold_hours` | integer | yes | 0 … 8760 |
| `severity` | enum `LeakSeverity` | no | default `medium` (`low`/`medium`/`high`) |
| `is_active` | boolean | no | default `true` |
| `notify` | boolean | no | default `true` (enqueue an in-app notification on breach) |

Response `200` (`SLAPolicyResponse`).

### GET `/leak-detection/policies`
List your org's SLA policies. Response `200`: `list[SLAPolicyResponse]`. Auth.

### GET `/leak-detection/alerts`
List leak alerts, newest first. Auth.

Query params: `status` (optional, `LeakAlertStatus`: `open`/`resolved`/
`dismissed`) filters by alert status.
Response `200`: `list[LeakAlertResponse]`.

### POST `/leak-detection/alerts/{alert_id}/resolve`
Mark an alert `resolved` (stamps `resolved_at`). Auth.
Response `200` (`LeakAlertResponse`). Errors: `404` if not in your tenant.

### POST `/leak-detection/scan`
Run the SLA scanner on demand (it also runs every 5 minutes via beat).
**min role: manager.**
Response `200`: `{ "policies_scanned": <int>, "alerts_created": <int> }`.

**`SLAPolicyResponse` fields:** `id`, `org_id`, `leak_type`, `threshold_hours`,
`severity`, `is_active`, `notify`.

**`LeakAlertResponse` fields:** `id`, `leak_type` (`LeakType`), `entity_type`
(`EntityType`), `entity_id`, `severity` (`LeakSeverity`), `status`
(`LeakAlertStatus`), `detail?`, `detected_at`, `resolved_at?`.

---

## Health — root (no prefix, public)

### GET `/health` and GET `/health/live`
Liveness. Always `200` `{ "status": "alive", "service": "LeadPulse" }` while the
process is running. No dependency checks.

### GET `/health/ready` and GET `/health/readiness`
Readiness. Checks PostgreSQL (`SELECT 1`) and Redis (`PING`). Returns `200`
`{ "status": "ready", "checks": { "database": "ok", "redis": "ok" } }` when both
pass, or `503` with `"status": "not_ready"` and a per-check error breakdown
otherwise.

### GET `/`
Service banner: `{ "service": "LeadPulse", "status": "running", "docs": "/docs" }`.
