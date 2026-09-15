# Atelier Shreenu — WhatsApp Concierge Agent

Serverless AWS implementation of the WhatsApp Concierge Agent for Atelier Shreenu
(+91 95602 06195). Companion to `as-email-agent`; both agents share one
DynamoDB CRM (`as-email-contacts`), one Razorpay merchant account, and one Google
Calendar (`ateliershreenu@gmail.com`).

Authoritative behaviour is defined in `docs/AS_WhatsApp_Agent_Training_v8_FINAL.md`.

## Stack

| Layer            | Service                                     |
|------------------|---------------------------------------------|
| Ingress          | API Gateway → Lambda (`src/inbound/`)       |
| Orchestration    | Python state machine in `src/shared/router.py` (parity with email agent) |
| LLM              | Anthropic Claude Haiku (`src/shared/llm.py`) with prompt caching, gated by SSM flag |
| Data             | Amazon DynamoDB (`as-email-contacts`, shared) |
| Media            | Amazon S3 (`as-whatsapp-media`)             |
| Scheduling       | Amazon EventBridge (slow-drip broadcast)    |
| Secrets          | AWS Secrets Manager                         |
| Alarms           | Amazon CloudWatch                           |
| Payments         | Razorpay Payment Links (shared consumer)    |
| Calendar         | Google Calendar API (Free/Busy + Events)    |
| Messaging        | WhatsApp Cloud API (Meta)                   |
| Compliance       | TRAI / DLT registered templates             |

## Layout

- `DATABASE/`      — CRM CSV/JSON exports (phone-only + both-channel).
- `config/`        — fees, disallowed phrases, classifier labels, copy library,
                     Meta template registry, DLT template registry.
- `docs/`          — training directive, runbook, migration notes.
- `flows/`         — WhatsApp Flows JSON (S1.14b, S1.19.CAP autofill captures).
- `media/`         — hook images, vCard avatar, map preview assets.
- `scripts/`       — dev utilities (ingest CRM, register templates, publish
                     flows, DLT sync, Google OAuth refresh).
- `src/inbound/`   — Meta webhook consumer with signature verification.
- `src/funnel/`    — S1.* state handlers (inbound conversation).
- `src/campaigns/` — S2.* state handlers (outreach broadcast).
- `src/hooks/`     — Razorpay webhook, Calendar sync, IG growth writer.
- `src/shared/`    — CRM client, WA client, style guard, link builder,
                     window guard, calendar client, Razorpay validator,
                     consent writer, identity resolver, `llm.py`
                     (Anthropic classifier + reply generator with prompt
                     caching), `answering.py` (LLM-answering helper),
                     intent-aware `router.py`, state handlers under `states/`.
- `src/dashboard/` — read views for the studio.
- `templates/`     — Meta-approved template bodies (marketing / utility).
- `terraform/`     — infrastructure as code.
- `tests/`         — unit tests and sample Meta webhook events.

## First-run checklist

1. `cp .env.example .env` and fill values from Secrets Manager.
2. `scripts/gauth.py`             — generate Google refresh token (reuse email).
3. `scripts/register_meta_templates.py`  — upload each template JSON.
4. `scripts/publish_flows.py`     — publish Flows for S1.14b and S1.19.CAP.
5. `scripts/dlt_sync.py`          — sync DLT template IDs into config.
6. `scripts/ingest_crm.py`        — load DATABASE/ CSVs into DynamoDB.
7. `make deploy`                  — SAM package + deploy.
8. Register the deployed webhook URL in the Meta developer console.

## Non-negotiable rules

- Never claim personhood (§3.2).
- No emojis except 📍 and 📅 (§3.2).
- No copy improvisation — bodies come verbatim from `config/copy_library.json` (§3.2).
- Free-form replies only inside the 24-hour service window; otherwise send
  an approved template (§2.3).
- Every outreach message carries a one-tap STOP (§8.2).
- Partner's direct number (+91 95601 07193) is never disclosed to a Client
  at any state, including S1.16 (§5).
- Payment amounts must match ₹1,770 / ₹3,540 / ₹7,080 exactly — validated
  by the shared Razorpay webhook consumer (§9.2).
