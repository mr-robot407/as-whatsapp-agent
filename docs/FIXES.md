# Fixes & known issues — as-whatsapp-agent

## Fixed

- **`exceptions.py` `import copy`** — imported Python's `copy` stdlib but
  called `copy_library.get(...)`. Would `NameError` on every X.FALLBACK,
  X.HUMAN_REQUEST, or X.PERSONHOOD_QUERY dispatch. Now imports `copy_library`.
- **Empty ASL files under `statemachines/`** — never referenced by
  `template.yaml`. Deleted; orchestration is pure Python in
  `src/shared/router.py`, matching the email agent's pattern.
- **Empty behavioural spec** — `docs/AS_WhatsApp_Agent_Training_v8_FINAL.md`
  was 0 bytes despite the README declaring it authoritative. Populated from
  the source `.docx` at repo root.
- **Empty runbook, MIGRATION, FIXES** — populated to match the email agent's
  operational structure.

## Known limitations

- **LLM answering ships gated off.** `LLM_ENABLED_PARAM` defaults to `false`.
  Flip it to `true` only after the Anthropic secret is populated and the
  smoke test in the runbook passes.
- **Razorpay is a placeholder.** `.env.example` lists `REPLACE_ME`
  credentials; production Razorpay lives in the email agent's secret.
  Partners must confirm before payment flows are live.
- **Meta credentials pending.** Studio hands over the System User token +
  app secret; `as-whatsapp-agent/meta` must be populated before webhook
  registration.
- **No integration tests yet.** Only unit tests. End-to-end funnel walk
  and outreach dispatch tests are Phase 5.
- **CI/CD is manual.** `make deploy` from a developer machine; no GitHub
  Actions pipeline yet.

## Deferred to Phase 5

- Per-channel conversation transcript for the LLM (currently `last_turns=[]`).
- Vendor-specific KB shard so the LLM answers empanelment questions with
  richer detail without ballooning the client-facing KB.
- Dashboard button for `set_human_takeover(contact_id, hours=24)`.
- Redrive script for the DLQ.
- Contact-purge script.
