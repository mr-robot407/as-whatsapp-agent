# Migration notes — as-whatsapp-agent

The WhatsApp agent shares its DynamoDB CRM (`as-email-contacts`) and its
Razorpay + Google Calendar credentials with the email agent. Deploying the
WhatsApp stack does **not** create a new CRM table; it references the existing
one by name.

## Prerequisites

- Email agent stack (`as-email-agent`) is already deployed in `ap-south-1`.
- DynamoDB table `as-email-contacts` exists with `contact_id` (PK), `sk` (SK),
  and the `GSI-EMAIL` + `GSI-PHONE` global secondary indexes.
- Secrets Manager entries exist:
  - `as-email-agent/razorpay`  (shared)
  - `as-email-agent/google-oauth` (shared)

## First-time deployment

```bash
cp .env.example .env
# Fill Anthropic + Meta placeholders. Razorpay stays as placeholder.
make build
make deploy   # creates: as-whatsapp-agent stack
```

After deploy, capture outputs and register the webhook:

```bash
aws cloudformation describe-stacks --stack-name as-whatsapp-agent \
  --query "Stacks[0].Outputs" --region ap-south-1
# Paste WebhookUrl into Meta developer console → Webhooks → WhatsApp.
```

## Populating secrets

```bash
# Meta credentials (once Studio hands them over)
aws secretsmanager create-secret --name as-whatsapp-agent/meta --region ap-south-1 \
  --secret-string '{"access_token":"...","app_secret":"...","verify_token":"...","waba_id":"1615402749911697","phone_number_id":"1254221294446336"}'

# Anthropic
aws secretsmanager create-secret --name as-whatsapp-agent/anthropic --region ap-south-1 \
  --secret-string '{"api_key":"sk-ant-..."}'
```

## Schema — event types this agent adds to `as-email-contacts`

| Type | Written by | Purpose |
|---|---|---|
| `WHATSAPP_INBOUND`        | `src/inbound/app.py`      | Every accepted webhook message |
| `WHATSAPP_STATUS`         | `src/inbound/app.py`      | Meta send / delivered / read callbacks |
| `STATE_TRANSITION`        | State handlers            | Router transitions |
| `LLM_REPLY_SENT`          | `src/shared/answering.py` | Successful LLM reply |
| `LLM_FALLBACK`            | `src/shared/answering.py` | LLM path failed → copy-library fallback |
| `HUMAN_TAKEOVER_SET`      | `src/shared/consent.py`   | Partner muted the agent |
| `HUMAN_TAKEOVER_CLEARED`  | `src/shared/consent.py`   | Mute released |
| `VENDOR_INTRO_CAPTURED`   | S1.20b                    | Vendor submission recorded |
| `CAREER_INTEREST`         | S1.40                     | Career applicant recorded |
| `PRESS_CAPTURE`           | S1.51                     | Press enquiry recorded |
| `PAYMENT_CAPTURED`        | Razorpay webhook          | Discovery/Discussion/Walkthrough fee paid |
| `BOOKING_CREATED`         | Discovery/Discussion/Walkthrough handlers | Slot booked in Google Calendar |
| `IDLE_REMINDER_SENT`      | Funnel idle cron          | 24h idle sweep sent a template |
| `OPT_OUT`                 | `src/shared/consent.py`   | STOP / unsubscribe |

## PROFILE row fields added

- `human_takeover_until`  — ISO deadline while agent is muted for this contact
- `human_takeover_actor`  — who set the mute (audit)
- `current_state`         — active state_id
- `last_state_change_at`  — for idle sweeps
- `idle_reminder_sent`    — one-shot flag per idle sweep

## Parity with email agent

| Concern | Email agent | WhatsApp agent |
|---|---|---|
| LLM classifier            | Claude Haiku, inline in inbound handler                    | Claude Haiku in router pre-dispatch (`src/shared/llm.py`) |
| LLM reply generator       | Not present                                                | Present (`src/shared/llm.py`) with prompt caching + KB    |
| Orchestration             | Pure Python workflow (no Step Functions)                   | Pure Python router + state registry (no Step Functions)   |
| Style guard               | `assert_clean()` before every send                         | Same, and also over every LLM output                      |
| DND scope                 | Per-channel; STOP fans out to all three                    | Same; adds `human_takeover_until` for per-contact mute    |
| Kill switch               | SSM `/as-email-agent/AGENT_ENABLED`                        | SSM `/as-whatsapp-agent/AGENT_ENABLED`                    |
| Copy library              | `templates/copy.json`                                       | `config/copy_library.json`                                 |
| Secrets home              | `as-email-agent/*`                                          | `as-whatsapp-agent/*` plus shared `as-email-agent/*`       |
