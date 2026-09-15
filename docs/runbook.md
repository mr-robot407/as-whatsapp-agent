# Runbook — as-whatsapp-agent

## Rollback

```bash
aws cloudformation list-stack-resources --stack-name as-whatsapp-agent --region ap-south-1
git checkout <previous-commit>
make deploy
```

## Alarms to configure (post-deploy)

| Alarm | Metric | Threshold |
|---|---|---|
| InboundErrors    | Lambda Errors (InboundFunction)    | > 0 in 5 min |
| FunnelErrors     | Lambda Errors (FunnelFunction)     | > 0 in 5 min |
| CampaignErrors   | Lambda Errors (CampaignsFunction)  | > 0 in 5 min |
| HooksErrors      | Lambda Errors (HooksFunction)      | > 0 in 5 min |
| DLQDepth         | SQS NumberOfMessagesSent (as-whatsapp-dlq) | > 0 |
| MetaSendFailure  | Custom metric — 4xx/5xx from Graph API | > 0.5% |
| SignatureReject  | Custom metric — X-Hub-Signature mismatch | > 0 |
| LLMFallbackRate  | Custom metric — LLM_FALLBACK events   | > 20% of LLM_REPLY_SENT |
| StyleGuardBlock  | Custom metric — style_guard violations| > 0 in 5 min |
| KillSwitchOff    | SSM `/as-whatsapp-agent/AGENT_ENABLED` = false | Alert |

## Day-1 Decision Log

| # | Decision | Options | Owner | Status |
|---|---|---|---|---|
| 1  | Meta System User token   | Fresh System User vs re-use of email agent's Meta app | Studio      | OPEN |
| 2  | DLT aggregator           | Jio · Airtel · Vi · Tata · Route · Gupshup            | Studio      | OPEN |
| 3  | DLT principal entity     | Register `Shreenu and Ranjeet Design LLP` — PAN, address, GST | Studio | OPEN |
| 4  | Header ID                | `ATSHRN` (proposed) — confirm availability with aggregator | Studio  | OPEN |
| 5  | GA4 custom dimension     | `utm_campaign` scoped to Event, not User             | Engineering | OPEN |
| 6  | Hook images (S2.00)      | 3–4 plates, 1080×1080, ≤5 MB, brand-approved         | Studio      | OPEN |
| 7  | Booking-slot cap         | Confirm max discovery calls/day and windows          | Partners    | OPEN |
| 8  | LLM enablement           | Ship with LLM_ENABLED=false; flip to true after smoke tests + Anthropic key populated | Engineering | OPEN |
| 9  | Anthropic key storage    | Secrets Manager `as-whatsapp-agent/anthropic` — `{ "api_key": "sk-ant-…" }` | Engineering | OPEN |
| 10 | Human-takeover UX        | Dashboard button to `set_human_takeover(contact_id, hours=24)` | Engineering | OPEN |
| 11 | Razorpay merchant        | PLACEHOLDER — reuse email-agent secret pending confirmation | Partners | PLACEHOLDER |
| 12 | Meta template approval   | Submit 7 templates; poll status daily; block launch until all 7 APPROVED | Studio | OPEN |

## Go-Live Checklist

- [ ] AWS account onboarded (`ap-south-1`, account 664106307979)
- [ ] Meta System User token + app secret in `as-whatsapp-agent/meta` secret
      (keys: `access_token`, `app_secret`, `verify_token`, `waba_id`, `phone_number_id`)
- [ ] Anthropic API key in `as-whatsapp-agent/anthropic` secret (key: `api_key`)
      — required only if LLM answering is enabled
- [ ] SSM `/as-whatsapp-agent/AGENT_ENABLED` = `true`
- [ ] SSM `/as-whatsapp-agent/LLM_ENABLED` = `false` at first deploy;
      flip to `true` after smoke test — see below
- [ ] All 7 Meta templates APPROVED
- [ ] DLT principal entity registered; per-template DLT IDs synced via
      `scripts/dlt_sync.py`
- [ ] WhatsApp Flows for S1.14b + S1.19.CAP published; Flow IDs in
      `config/flows_registry.json`
- [ ] Google Calendar OAuth refresh token in `as-email-agent/google-oauth`
      (shared with email agent)
- [ ] Razorpay credentials reachable in `as-email-agent/razorpay` — PLACEHOLDER
      until Partners confirm
- [ ] Hook images uploaded to `s3://as-whatsapp-media/hooks/`
- [ ] `UNSUBSCRIBE_URL` set to `${WebhookUrl}/webhook/unsubscribe` post-deploy
- [ ] CRM ingestion complete (`scripts/ingest_crm.py`)
- [ ] Webhook URL registered in Meta developer console; verification
      handshake returns `hub.challenge`
- [ ] Signature-verification smoke test passes (replay
      `tests/events/webhook_message_text.json` with valid `X-Hub-Signature-256`)
- [ ] DLQ alarm active in CloudWatch
- [ ] GA4 `utm_campaign` custom dimension created

## LLM smoke test — enabling the answering layer

Once the Anthropic key is in Secrets Manager AND `AGENT_ENABLED` is `true`:

```bash
# 1. Flip the feature flag
aws ssm put-parameter --name /as-whatsapp-agent/LLM_ENABLED \
  --value "true" --type String --overwrite --region ap-south-1

# 2. Send test messages from your own WhatsApp number:
#    - "What is the discovery call?"     → KB-grounded answer, ≤3 sentences
#    - "How much is the walkthrough?"    → quotes ₹3,540 / ₹7,080
#    - "Give me Shreenu's number"        → refusal, no partner number leaked
#    - "Are you a bot?"                  → X.PERSONHOOD_QUERY verbatim body
#    - "When will you review my vendor submission?" → vendor SLA per KB

# 3. Watch LLM logs for 15 min:
aws logs tail /aws/lambda/as-whatsapp-inbound --follow --region ap-south-1 | \
  grep -E "llm\.|LLM_"

# 4. Revert if StyleGuardBlock fires or LLMFallbackRate > 20%:
aws ssm put-parameter --name /as-whatsapp-agent/LLM_ENABLED \
  --value "false" --type String --overwrite --region ap-south-1
```

## Human takeover (per-contact mute)

When a partner takes over a conversation manually and does not want the agent
to reply on top:

```python
import consent
consent.set_human_takeover(contact_id, hours=24, actor="ranjeet", note="handling directly")
# Clear:
consent.clear_human_takeover(contact_id, actor="ranjeet")
```

The router checks `consent.is_human_takeover_active()` before every dispatch;
inbound events are still written for the audit log.

## Emergency — stop everything

```bash
aws ssm put-parameter --name /as-whatsapp-agent/AGENT_ENABLED \
  --value "false" --type String --overwrite --region ap-south-1
aws events disable-rule --name as-whatsapp-campaigns-cron --region ap-south-1
aws events disable-rule --name as-whatsapp-reminders-cron --region ap-south-1
aws events disable-rule --name as-whatsapp-idle-cron --region ap-south-1
```

## Re-enable

```bash
aws ssm put-parameter --name /as-whatsapp-agent/AGENT_ENABLED \
  --value "true" --type String --overwrite --region ap-south-1
aws events enable-rule --name as-whatsapp-campaigns-cron --region ap-south-1
aws events enable-rule --name as-whatsapp-reminders-cron --region ap-south-1
aws events enable-rule --name as-whatsapp-idle-cron --region ap-south-1
```

## DLQ triage

```bash
aws sqs receive-message --queue-url $(aws sqs get-queue-url \
  --queue-name as-whatsapp-dlq --query QueueUrl --output text) \
  --max-number-of-messages 10 --wait-time-seconds 5
```

Root-cause fix, then re-drive.

## Contact purge SOP

When a contact demands full data deletion:

1. Confirm `OPT_OUT` event exists; if not, write one via the dashboard.
2. Delete every non-PROFILE event for the contact.
3. Retain the PROFILE row with `dnd.whatsapp = dnd.email = dnd.phone = true`
   so a future ingest cannot re-onboard the contact.
