# LEADPULSE → PRODUCTION EXECUTION PROMPT

You are the Founding CTO, Principal Architect, Staff Backend Engineer, Staff Frontend Engineer, DevOps Engineer, QA Lead, Product Designer, and Security Engineer.

You have access to the existing LeadPulse repository.

Your first task is NOT to write code.

Your first task is to audit the entire repository.

---

## PHASE 1 — REPOSITORY AUDIT

Analyze:

* folder structure
* architecture
* dependencies
* database models
* API routes
* services
* workflows
* frontend
* docker configuration
* tests
* security

Create:

AUDIT_REPORT.md

Include:

### Current State

* what exists
* what works
* what is incomplete

### Technical Debt

* duplicated logic
* poor abstractions
* missing tests
* security risks
* scalability concerns

### Missing Components

* authentication
* RBAC
* audit logs
* observability
* billing
* workflow execution
* notification systems

### Recommended Refactors

Rank:

* Critical
* Important
* Nice to have

DO NOT IMPLEMENT YET.

---

# PHASE 2 — PRODUCT REVIEW

Evaluate whether the current LeadPulse architecture supports:

* Lead Capture
* Lead Qualification
* WhatsApp Automation
* Follow-Up Automation
* Revenue Leak Detection
* Analytics
* Team Collaboration

Identify:

* architectural bottlenecks
* domain model problems
* future scaling risks

Generate:

PRODUCT_REVIEW.md

---

# PHASE 3 — TARGET ARCHITECTURE

Transform LeadPulse into:

Revenue Recovery Platform

Core modules:

## Lead Capture

Sources:

* Facebook Leads
* Google Forms
* Webhooks
* CSV Import
* Manual Entry

---

## Lead Routing

Assign:

* agent
* team
* territory

---

## Follow-Up Engine

Support:

* reminders
* workflows
* scheduled follow-ups
* escalation rules

---

## Revenue Leak Detection

Detect:

* ignored leads
* stalled opportunities
* overdue follow-ups
* missed meetings

---

## Dashboard

Show:

* revenue at risk
* leads ignored
* opportunities stalled
* response times
* team performance

---

# PHASE 4 — IMPLEMENTATION PLAN

Create:

IMPLEMENTATION_PLAN.md

Break work into:

Sprint 1
Sprint 2
Sprint 3
Sprint 4

Each sprint must contain:

* objectives
* deliverables
* risks
* dependencies

---

# PHASE 5 — REPOSITORY RESTRUCTURE

Only after approval:

Restructure project into:

backend/

frontend/

docs/

infra/

tests/

---

Backend:

api/
core/
db/
models/
schemas/
services/
workflows/
tasks/

Frontend:

features/
components/
hooks/
pages/
services/

---

# PHASE 6 — PRODUCTION REQUIREMENTS

Implement:

Authentication

Authorization

JWT

RBAC

Rate Limiting

Audit Logs

Error Handling

Observability

Structured Logging

Health Checks

Metrics

Docker

CI/CD

Database Migrations

Secrets Management

Environment Validation

---

# PHASE 7 — TESTING

Minimum:

Backend Coverage:
80%+

Frontend Coverage:
70%+

Integration Tests

Workflow Tests

API Tests

---

# PHASE 8 — UI/UX

Design style:

* Linear
* Vercel
* Arc
* Raycast

Requirements:

* dark mode
* responsive
* keyboard shortcuts
* command palette
* loading states
* error states
* accessibility

---

# PHASE 9 — FINAL DELIVERABLE

The final result must be:

* fully runnable
* dockerized
* production ready
* documented
* tested

Deliver:

SETUP.md

DEPLOYMENT.md

ARCHITECTURE.md

API_REFERENCE.md

USER_GUIDE.md

---

IMPORTANT

Before writing code:

1. Audit repository.
2. Challenge assumptions.
3. Identify flaws.
4. Create implementation plan.

Do not jump directly into coding.

Act like a founding engineering team building a startup, not a code generator.
