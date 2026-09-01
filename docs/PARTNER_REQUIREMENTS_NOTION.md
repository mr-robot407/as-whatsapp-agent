# Atelier Shreenu — WhatsApp Concierge Agent · Partner Requirements

**Prepared for** Architect Ranjeet Mukherjee and the studio team
**Prepared by** Addroit Inc
**Channel** WhatsApp — +91 95602 06195
**Companion project** as-email-agent (already live)

> **How to use this page** — one field per row. Please fill the **Value** column, tick the **Status** checkbox when done, and drop a note under **Notes / Blockers** if something needs a call. Anything already handled by the email agent is marked ♻️ *reuse* — please just confirm; no need to re-source it.

---

## 0 · Sign-off snapshot

| Section | Owner | Target date | Done |
|---|---|---|---|
| 1 · Meta / WhatsApp Cloud API | Studio + Engg | 2026-09-08 | ☐ |
| 2 · TRAI / DLT registration | Studio (via aggregator) | 2026-09-15 | ☐ |
| 3 · Google Calendar (reuse) | Studio | 2026-09-03 | ☐ |
| 4 · Partner internal contact details | Ranjeet | 2026-09-03 | ☐ |
| 5 · Analytics (GA4) | Studio + Engg | 2026-09-10 | ☐ |
| 6 · Studio decisions (Appendix B) | Partners | 2026-09-08 | ☐ |
| 7 · Creative assets | Studio | 2026-09-12 | ☐ |
| 8 · Legal / policy | Studio | 2026-09-15 | ☐ |

---

## 1 · Meta / WhatsApp Cloud API

The studio's WhatsApp Business Account and Cloud API app must exist before Engineering can wire the webhook.

### 1.1 Business account

| Field | Value | Status |
|---|---|---|
| Meta Business Manager ID | 1205405625998390 | ✅ |
| Meta Business Manager account name | Atelier Shreenu | ✅ |
| Business verification status (Meta) | Pending | ☐ |
| Two-factor auth enabled on Business Manager | Yes / No | ☐ |
| Admins listed on Business Manager (name + email) | Shreenu Mukherjee — *email TBD* | ☐ |

### 1.2 WhatsApp Business Account (WABA)

| Field | Value | Status |
|---|---|---|
| WABA ID | 1615402749911697 | ✅ |
| Display name (fixed) | Atelier Shreenu | ✅ |
| Phone number (fixed) | +91 95602 06195 | ✅ |
| Phone Number ID (Cloud API) |  | ☐ |
| Number registration status | Registered / Pending OTP | ☐ |
| Messaging tier (Tier 1 / 2 / 3 / Unlimited) |  | ☐ |
| Business profile description | *Atelier Shreenu — Architecture and Interior Design. By appointment. Gurugram.* | ✅ |
| Business address | Palam Vihar, Gurugram — 122017 | ✅ |
| Business email | info@ateliershreenu.com | ✅ |
| Business website | https://ateliershreenu.com | ✅ |
| Avatar file uploaded (AS monogram on parchment) |  | ☐ |

### 1.3 Cloud API app (developers.facebook.com)

| Field | Value | Status |
|---|---|---|
| Meta App ID |  | ☐ |
| Meta App name |  | ☐ |
| App mode | Live | ☐ |
| System User created inside Business Manager (name) |  | ☐ |
| System User → WABA asset assignment | Full control | ☐ |
| Long-lived System User access token (never expires) |  | ☐ |
| App secret (Settings → Basic) |  | ☐ |
| Webhook verify token *(you invent this — any random string)* |  | ☐ |
| Webhooks subscribed | `messages`, `message_status`, `message_template_status_update` | ☐ |

> ⚠️ **Access token & app secret must be shared via 1Password / AWS Secrets Manager, never by WhatsApp or email.** Engineering will create the Secrets Manager entry and grant you the write link.

### 1.4 Green tick (blue-badge equivalent)

| Field | Value | Status |
|---|---|---|
| Green tick applied for? | Yes / No / After 1,000 conversations (recommended) | ☐ |
| Supporting evidence ready (press, brand assets, PAN) | Yes / No | ☐ |

---

## 2 · TRAI / DLT registration (India)

Every Marketing template dispatched from +91 95602 06195 needs a DLT template ID before it can go out. This runs in parallel to the Meta template-approval track.

### 2.1 Aggregator selection

| Field | Value | Status |
|---|---|---|
| Chosen telecom aggregator | Jio / Airtel / VI / Tata / BSNL / Route Mobile / Gupshup / other: ___ | ☐ |
| Reason for choice |  | ☐ |
| Aggregator account owner (email) |  | ☐ |

### 2.2 Principal Entity registration

| Field | Value | Status |
|---|---|---|
| Principal Entity ID (post-registration) |  | ☐ |
| Registered entity name | Shreenu and Ranjeet Design LLP | ✅ |
| Registered PAN |  | ☐ |
| Registered address | Palam Vihar, Gurugram — 122017 | ✅ |
| Authorised signatory (name + designation) |  | ☐ |
| Signatory phone (for OTP) |  | ☐ |

### 2.3 Header / Sender ID

| Field | Value | Status |
|---|---|---|
| Header ID (recommended: **ATSHRN**) |  | ☐ |
| Alternative header IDs (if primary rejected) | ATSHRN1, ASHRENU, ATSHRNU | ☐ |
| Approval status |  | ☐ |

### 2.4 DLT template registrations

Engineering will draft each template body verbatim from the directive and share for approval. Please forward each to the aggregator; the DLT template IDs come back per template.

| Template (§ ref) | Category | DLT template ID | Status |
|---|---|---|---|
| `OUTREACH_HOOK` (§S2.00) | Marketing |  | ☐ |
| `PROJECT_DISC_OFFER` (§S1.17) | Service Explicit |  | ☐ |
| `WALKTHROUGH_OFFER` (§S1.19) | Service Explicit |  | ☐ |
| `OOH_ACK` (§X.OOH) | Service Implicit |  | ☐ |
| `IDLE_REMINDER` (§X.IDLE) | Service Implicit |  | ☐ |
| `BOOKING_REMINDER_24H` (§S1.16/S1.18/S1.19a) | Service Implicit |  | ☐ |
| `BOOKING_REMINDER_2H_PARTNER` (§S1.16 internal) | Service Implicit |  | ☐ |

---

## 3 · Google Calendar ♻️ *reuse from email agent*

The WhatsApp agent uses the **same** service account and the **same** calendar as the email agent. Nothing new to create — just confirm.

| Field | Value | Status |
|---|---|---|
| Google Workspace account | ateliershreenu@gmail.com | ♻️ ☐ confirm |
| Bookings calendar name | Atelier Shreenu — Bookings | ♻️ ☐ confirm |
| Calendar shared with Ranjeet | ranjeet.mukherjee@gmail.com — read/write | ♻️ ☐ confirm |
| Service account impersonating ateliershreenu@gmail.com | *email agent's Secrets Manager entry* | ♻️ ☐ confirm |
| Any new writers to add? |  | ☐ |

---

## 4 · Partner internal notification details

Used only for internal / partner-only messages (never sent to a Client). Chief use: the T-2h partner reminder at S1.16 that carries the Client's callback number.

| Field | Value | Status |
|---|---|---|
| Ranjeet's direct WhatsApp (for T-2h reminders) | +91 95601 07193 | ☐ confirm |
| Ranjeet's fallback email | ranjeet.mukherjee@gmail.com | ☐ confirm |
| Backup partner contact (for holiday coverage) |  | ☐ |
| Should Shreenu receive internal notifications too? | Yes / No — none per §1.1 | ☐ |

---

## 5 · Analytics (GA4)

Rule D (§3.4) requires GA4 to have `utm_campaign` configured **before** the first WhatsApp campaign fires; otherwise attribution is lost.

| Field | Value | Status |
|---|---|---|
| GA4 property ID for ateliershreenu.com | 543504017 | ✅ |
| GA4 measurement ID (G-XXXXXXX) | G-GN7NVMP4TN | ✅ |
| Admin access granted to engineering? (email) | ateliershreenu@gmail.com | ☐ pending grant |
| `utm_campaign` custom dimension configured? | **No** — ⚠️ blocker per Rule D §3.4, must be configured before first campaign fires | ☐ |
| GTM container (if any) | GTM-THQH822B | ✅ |

---

## 6 · Studio decisions (Appendix B open items)

Small policy calls that shape copy and pacing. Defaults shown; please confirm or overrule.

| Decision | Default (recommended) | Studio choice | Status |
|---|---|---|---|
| Editorial digest cadence | Quarterly | Quarterly / Monthly | ☐ |
| Discovery-call daily cap | 4 per day | ___ per day | ☐ |
| Discovery-call slot length | 10 minutes | ___ min | ☐ |
| Partner available windows for bookings calendar | Tue & Thu mornings 10:00–13:00 IST |  | ☐ |
| Bookings blackout dates (2026) | Studio public holidays |  | ☐ |
| Internship intake cap (concurrent) | 4 | ___ | ☐ |
| Career capture: junior / senior / intern roles enabled? | All three | ______ | ☐ |
| Follow / Save / Recommend triad order (§7.1) | Follow → Save → Recommend | *invariant unless studio overrules* | ☐ |
| Outreach frequency cap | ≤4 Marketing templates per recipient per calendar year | ___ | ☐ |
| First-outreach-batch size | 500 recipients over 10 days | ___ | ☐ |

---

## 7 · Creative assets

Assets Engineering cannot generate — must come from the studio.

### 7.1 Outreach hook images (S2.00)

Requirement: 3–4 approved plates, **1080 × 1080 px**, PNG or JPG, ≤ 5 MB each.

| Plate # | Working title | File uploaded? | Notes |
|---|---|---|---|
| 1 |  | ☐ |  |
| 2 |  | ☐ |  |
| 3 |  | ☐ |  |
| 4 (optional persona-matched) |  | ☐ |  |

### 7.2 vCard (E.VC)

| Asset | Requirement | Status |
|---|---|---|
| Avatar / logo for vCard payload | AS monogram — 512×512 PNG on parchment | ☐ |
| Studio landline (if any) to include | Yes / No — leave blank if none | ☐ |

### 7.3 Studio location share

| Asset | Requirement | Status |
|---|---|---|
| Google Maps place link | https://maps.app.goo.gl/K9vaZmpCLdMnyJ8r6 | ✅ |
| Confirm Palam Vihar pin is correct on maps | ☐ | ☐ |

### 7.4 Copy sanity check

| Item | Status |
|---|---|
| Ranjeet has read Section 05–07 message bodies verbatim in `docs/AS_WhatsApp_Agent_Training_v8_FINAL.md` | ☐ |
| Any single-word tweaks the studio wants applied? *List below.* | ☐ |

---

## 8 · Legal / policy

| Item | Owner | Status |
|---|---|---|
| Privacy policy on ateliershreenu.com updated to name WhatsApp as a channel | Studio | ☐ |
| Privacy policy names the DLT sender ID (ATSHRN) | Studio | ☐ |
| Terms of engagement reference the 90-day fee-credit clause | Studio (already in Pre-Signing Fee Schedule) | ☐ confirm |
| STOP / opt-out policy paragraph on the website | Studio | ☐ |
| Retention: consent records kept for 3 years post opt-out | Engineering *(honours §8.2)* | ✅ |

---

## 9 · Post-verification checklist (Engineering fills)

*Ranjeet does not need to fill this section — for internal tracking only.*

- [ ] Meta credentials placed in AWS Secrets Manager path `as-whatsapp-agent/meta`
- [ ] DLT credentials placed in AWS Secrets Manager path `as-whatsapp-agent/dlt`
- [ ] Google Calendar credentials confirmed at path `as-email-agent/google-oauth`
- [ ] `scripts/register_meta_templates.py` run — template IDs written to `config/templates_registry.json`
- [ ] `scripts/publish_flows.py` run — Flow IDs written to `config/flows_registry.json`
- [ ] `scripts/ingest_crm.py` run — 174,719 contacts loaded into `as-email-contacts`
- [ ] Webhook URL registered in Meta developer console
- [ ] First S2.00 broadcast dry-run to 10 opt-in test numbers
- [ ] CloudWatch alarms wired for webhook 5xx, DLQ depth, DND-violation counter, template-quality dip
- [ ] Green-tick submission drafted (post-1,000 conversations)

---

## 10 · Questions for the studio to answer at kickoff

1. Do we want the outreach hook image to rotate per recipient, or use one fixed plate for the first campaign?
2. Should vendor/service-provider approaches (S1.20) generate an internal digest to `info@ateliershreenu.com`, or stay silent in DynamoDB until pulled?
3. Is press capture (S1.51) to notify Ranjeet only, or Ranjeet + Shreenu?
4. Any brand words to add to the disallowed-phrase guard beyond *passionate* / *commission*?
5. Public holidays 2026 the studio observes — should Engineering pull from the Indian public holidays calendar, or does the studio maintain its own list?

---

*Please return this filled page to Engineering. Fields with an empty **Value** column will block the go-live checklist.*
