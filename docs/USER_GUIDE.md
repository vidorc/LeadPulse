# LeadPulse — User Guide

LeadPulse helps a sales team capture leads, qualify them automatically, work them
through a pipeline, follow up on a schedule, and — most importantly — catch the
deals that are quietly going cold before they're lost. This guide explains the
concepts and walks through the day-to-day workflows.

It is written for the people using LeadPulse to sell: reps, managers, and team
owners. No code required.

---

## Core concepts

**Organization.** Your company's workspace. All your data — leads, deals,
sequences, alerts — lives inside it and is invisible to other organizations. The
person who signs up becomes the **owner**.

**Roles.** Four levels of access, from most to least privileged:
`owner > admin > manager > agent`. Anyone can work leads and deals. Some
configuration actions — creating follow-up sequences, setting SLA policies,
overriding a lead's decision, and running a leak scan on demand — require
**manager or above**.

**Lead.** An inbound contact: a name, contact details, the source they came
from, and their message. When a lead arrives, LeadPulse automatically qualifies
it with AI — extracting intent, budget, timeline, location, and urgency, scoring
it 0–100, and assigning a decision.

**Decision.** What the system thinks of a lead after qualification:
`hot_lead`, `warm_lead`, `cold_lead`, or `manual_review`. Low-confidence or
ambiguous leads are routed to a review queue for a human to decide.

**Opportunity.** A deal in progress, optionally linked to the lead it came from.
It has a value, an owner, and a **stage**.

**Pipeline stages.** The path a deal travels:
`new → contacted → qualified → proposal_sent → negotiation → won` (or `lost`).
`won` and `lost` are final.

**Proposal and meeting.** Things attached to an opportunity. A proposal can be
drafted and then sent. A meeting is scheduled and then completed (or it lapses).

**Follow-up sequence.** A reusable, timed series of touches (typically emails).
Each step has a delay measured from enrollment — for example day 1, day 3, day
7. Enroll a lead and LeadPulse sends each step automatically at the right time.

**SLA policy.** Your definition of "too slow" for a given kind of leak. It is a
setting, not code: pick a leak type, a threshold in hours, and a severity.

**Revenue leak alert.** A flag LeadPulse raises when something breaches an SLA —
a lead nobody contacted, a deal that stopped moving, a meeting that passed
uncompleted, or a sent proposal with no follow-up. Alerts are how you find
revenue slipping away in time to act.

**Timeline.** Every meaningful action on a lead or deal is recorded as an
immutable event, so you always have a complete, ordered history of what happened
and when.

---

## Getting started

1. **Sign up.** Create your organization and your owner account. You receive
   access immediately.
2. **Log in.** Returning users sign in with email and password. If you belong to
   more than one organization, you can specify which one to enter.
3. You stay signed in via a short-lived session that refreshes automatically.
   Logging out ends the session everywhere.

---

## Workflow 1 — Capture and qualify a lead

1. **A lead arrives.** Create it with at least a name and a source (where it came
   from — website, referral, a campaign, etc.). Add email, phone, and the lead's
   message if you have them.
2. **Automatic qualification runs in the background.** Within moments, LeadPulse
   enriches the lead: intent, budget, timeline, location, urgency, a 0–100 score,
   a short AI summary, and a decision. You don't wait on this — the lead is saved
   right away and the details fill in shortly after.
3. **Hot leads get surfaced.** If the lead qualifies as hot, the team is notified
   automatically so someone can act fast.
4. **Ambiguous leads go to the review queue.** When the system isn't confident,
   the lead is flagged for human review instead of guessing.
5. **Review and override (managers).** Open the review queue, read the lead and
   its AI summary, and set the right decision yourself. Your override clears the
   review flag and is recorded on the lead's timeline with your name and a note.
6. **Check the history.** Every lead has a timeline showing exactly what
   happened — received, AI-processed, decision assigned, routed, overridden, and
   so on.

Tip: a lead's status moves through `new → qualifying → qualified` (or
`manual_review`) automatically. Once a rep owns it, it becomes `assigned`, and
ultimately `converted` or `lost`.

---

## Workflow 2 — Create an opportunity and move it through stages

1. **Create the opportunity.** Give it a title, optionally link the lead it came
   from, and set a value and an owner. It starts at stage `new`.
2. **Advance the stage** as the deal progresses: `contacted`, `qualified`,
   `proposal_sent`, `negotiation`, then `won` or `lost`. Each move is timestamped
   and recorded on the timeline. The moment of the last stage change is what
   "stalled" is measured against — so keeping stages current is what keeps your
   leak alerts accurate.
3. **Add and send a proposal.** Attach a proposal (title and amount) to the
   opportunity as a draft, then mark it sent when it goes out. Sending stamps the
   send time, which starts the clock on the "cold proposal" check.
4. **Schedule and complete meetings.** Schedule a meeting with a title and a
   time. After it happens, mark it completed. A scheduled meeting whose time has
   passed without being completed is exactly what the "missed meeting" leak
   detects.
5. **Close it out.** Move the deal to `won` or `lost`; that records the close
   time and takes it out of the "stalled" watch.

---

## Workflow 3 — Set up a follow-up sequence

Sequences automate the steady cadence that wins deals nobody has time to chase
by hand. Creating a sequence requires **manager or above**.

1. **Create the sequence.** Give it a name and define ordered steps. For each
   step set a delay in hours from the moment of enrollment, and (for email steps)
   a subject and body. A classic cadence is day 1 (24h), day 3 (72h), day 7
   (168h), day 14 (336h).
2. **Enroll a lead.** Enroll the lead into the sequence. LeadPulse schedules the
   first step automatically; each step, when its time comes, sends the message
   and schedules the next one. Enrolling a lead that's already actively enrolled
   does nothing — no double-touches.
3. **Stop when a rep engages.** When the lead replies or a rep picks them up,
   cancel the lead's follow-ups. This cancels the active enrollment and any
   pending scheduled steps, so you never keep auto-emailing someone you're
   already talking to.

Sequences run entirely on their own schedule once enrolled — no manual sending.

---

## Workflow 4 — Configure SLA policies and review leak alerts

This is the heart of LeadPulse: catching revenue leaking out through inaction.

### Set your SLA policies (manager or above)

For each leak type, set a threshold in hours and a severity. You define what
"too slow" means for your team; there is one policy per leak type:

| Leak type | What it catches | Example threshold |
|-----------|-----------------|-------------------|
| Lead ignored (`lead_ignored`) | a new lead nobody has contacted | 24 hours |
| Opportunity stalled (`opp_stalled`) | a deal whose stage hasn't changed | 168 hours (7 days) |
| Meeting missed (`meeting_missed`) | a scheduled meeting that passed without being completed | 0 hours (any overdue meeting) |
| Proposal cold (`proposal_cold`) | a sent proposal with no follow-up | 72 hours |

Set each policy's severity (low / medium / high) and choose whether a breach
should also raise an in-app notification (`notify`). Mark a policy inactive to
pause it without deleting it.

### Review and resolve alerts

LeadPulse scans for breaches automatically every few minutes. Managers can also
trigger a scan on demand. To work alerts:

1. **Open the alerts list.** Alerts show newest first, each with the leak type,
   the affected lead/deal/meeting/proposal, severity, and a plain-language
   detail like "No contact within 24h of creation." Filter by status (open,
   resolved, dismissed).
2. **Act on the underlying problem.** Contact the ignored lead, advance the
   stalled deal, complete or reschedule the meeting, follow up on the cold
   proposal.
3. **Resolve the alert.** Mark it resolved once handled; the resolution time is
   recorded.

You won't get duplicate noise: a single ongoing problem raises one open alert,
not a new one every scan.

---

## Workflow 5 — Read the dashboard

The dashboard summary gives you the at-a-glance health of your pipeline — lead
counts broken down by status and decision, and how many leads are waiting in the
review queue. Use it to answer "what needs attention right now":

- A growing **review queue** means leads waiting on a human decision.
- A cluster of **hot leads** means act fast — those are notified to the team too.
- Rising **open leak alerts** mean revenue is slipping; work the alerts list.

Pair the dashboard (the "what" and "how many") with the alerts list (the
"what's going wrong") and each entity's timeline (the "what happened") to run
your day.

---

## Tips and good habits

- **Keep stages current.** Leak detection trusts your pipeline. A deal you're
  actively working but haven't advanced will look "stalled." Move the stage when
  reality moves.
- **Mark meetings completed.** An un-completed past meeting is treated as missed.
- **Cancel follow-ups when you engage.** It prevents the awkward automated email
  landing after you've already replied in person.
- **Tune thresholds to your business.** A high-velocity inbound team might set
  "lead ignored" to a few hours; a considered enterprise sale might allow days.
  The policies are yours to set.
- **Use the timeline for accountability.** Overrides, assignments, and every
  stage change are recorded with who did what and when.
