"""API Gateway entrypoint for the Meta WhatsApp webhook.

GET /webhook/whatsapp
    Verification handshake — return `hub.challenge` iff `hub.verify_token`
    matches the value stored in Secrets Manager (`as-whatsapp-agent/meta`).

POST /webhook/whatsapp
    Message delivery — verify `X-Hub-Signature-256`, parse the payload,
    write inbound events to DynamoDB, and dispatch to the funnel.

Return 200 on all recognised requests (Meta retries otherwise). Return 403
on signature/verify-token mismatch. Return 400 on malformed input.
"""

from __future__ import annotations

import base64
import json
import os
from typing import Any

import crm
import identity
import killswitch
import router
import wa_client
from signature import verify as verify_signature


def handler(event: dict, context) -> dict:
    method = event.get("httpMethod", "").upper()
    if method == "GET":
        return _handle_verification(event)
    if method == "POST":
        return _handle_messages(event)
    return _reply(405, "method not allowed")


# ─── GET verification handshake ──────────────────────────────────────────────

def _handle_verification(event: dict) -> dict:
    """Meta calls this once when you register the webhook URL.

    Query args (all in ``hub.*``): mode, verify_token, challenge.
    Success = 200 with challenge as body.
    """
    params = event.get("queryStringParameters") or {}
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge", "")
    if mode != "subscribe":
        return _reply(400, "unsupported hub.mode")
    try:
        expected = wa_client.verify_token()
    except Exception as exc:  # noqa: BLE001
        print(f"handler: cannot read verify_token from Secrets Manager: {exc!r}")
        return _reply(500, "verify_token unavailable")
    if token != expected:
        print("handler: verify_token mismatch — rejecting subscribe")
        return _reply(403, "verify_token mismatch")
    print("handler: webhook verification OK")
    return _reply(200, challenge, content_type="text/plain")


# ─── POST message delivery ───────────────────────────────────────────────────

def _handle_messages(event: dict) -> dict:
    raw_body = _raw_body(event)
    signature_header = _header(event, "x-hub-signature-256")

    try:
        app_secret = wa_client.app_secret()
    except Exception as exc:  # noqa: BLE001
        print(f"handler: cannot read app_secret: {exc!r}")
        return _reply(500, "app_secret unavailable")

    if not verify_signature(app_secret, raw_body, signature_header):
        print("handler: X-Hub-Signature-256 verification failed — rejecting")
        return _reply(403, "signature mismatch")

    if not killswitch.is_enabled():
        # Return 200 so Meta stops retrying, but do no work.
        print("handler: killswitch disabled — acknowledging without processing")
        return _reply(200, "ok")

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        print(f"handler: malformed JSON body: {exc!r}")
        return _reply(400, "malformed json")

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            if change.get("field") != "messages":
                continue
            _process_change(change.get("value", {}))

    return _reply(200, "ok")


# ─── Payload parsing / routing ───────────────────────────────────────────────

def _process_change(value: dict) -> None:
    """Handle a single `changes.value` block containing messages/statuses/contacts."""
    contact_names = _contact_name_index(value.get("contacts", []))

    for message in value.get("messages", []):
        try:
            _process_message(message, contact_names)
        except Exception as exc:  # noqa: BLE001
            # Never let one bad message poison the batch — Meta already delivered
            # this webhook and won't retry a 200 response. DLQ catches Lambda-level
            # failure, so log the exception and move on.
            print(f"handler: message dispatch failed {message.get('id')}: {exc!r}")

    for status in value.get("statuses", []):
        try:
            _process_status(status)
        except Exception as exc:  # noqa: BLE001
            print(f"handler: status dispatch failed {status.get('id')}: {exc!r}")


def _process_message(message: dict, contact_names: dict[str, str]) -> None:
    wa_message_id = message.get("id", "")
    from_wa_id = message.get("from", "")
    msg_type = message.get("type", "unknown")

    if not wa_message_id or not from_wa_id:
        print(f"handler: skipping message with missing id/from: {message!r}")
        return

    if crm.message_processed(wa_message_id):
        print(f"handler: duplicate message {wa_message_id} — already processed")
        return

    phone_e164 = identity.e164_from_wa_id(from_wa_id)
    name = contact_names.get(from_wa_id, "")
    contact_id, created = crm.get_or_create_by_phone(phone_e164, name=name)

    crm.write_event(
        contact_id,
        "WHATSAPP_INBOUND",
        {
            "wa_message_id": wa_message_id,
            "wa_id": from_wa_id,
            "msg_type": msg_type,
            "raw": _summarise_message(message),
            "profile_name": name,
            "profile_created": created,
        },
    )

    _dispatch_to_funnel(contact_id, message)


def _process_status(status: dict) -> None:
    """Meta status callbacks (sent / delivered / read / failed) — record only."""
    wa_message_id = status.get("id", "")
    recipient = status.get("recipient_id", "")
    if not wa_message_id or not recipient:
        return
    contact = crm.resolve_by_phone(identity.e164_from_wa_id(recipient))
    if not contact:
        return
    crm.write_event(
        contact["contact_id"],
        "WHATSAPP_STATUS",
        {
            "wa_message_id": wa_message_id,
            "status": status.get("status", ""),
            "timestamp": status.get("timestamp", ""),
            "errors": status.get("errors", []),
        },
    )


def _dispatch_to_funnel(contact_id: str, message: dict) -> None:
    """Dispatch to the state router (Phase 2a)."""
    wa_id = message.get("from", "")
    next_state = router.route(contact_id, wa_id, message)
    print(f"handler: routed contact={contact_id} → {next_state}")


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _contact_name_index(contacts: list[dict]) -> dict[str, str]:
    """Return {wa_id: display_name} from the payload's contacts block."""
    index: dict[str, str] = {}
    for c in contacts:
        wa_id = c.get("wa_id", "")
        name = c.get("profile", {}).get("name", "")
        if wa_id and name:
            index[wa_id] = name
    return index


def _summarise_message(message: dict) -> dict[str, Any]:
    """Return a compact projection safe to store in DynamoDB (no giant media blobs)."""
    msg_type = message.get("type", "unknown")
    summary: dict[str, Any] = {"type": msg_type, "timestamp": message.get("timestamp", "")}
    if msg_type == "text":
        summary["text"] = message.get("text", {}).get("body", "")[:1024]
    elif msg_type == "button":
        summary["button_text"] = message.get("button", {}).get("text", "")
        summary["button_payload"] = message.get("button", {}).get("payload", "")
    elif msg_type == "interactive":
        interactive = message.get("interactive", {})
        summary["interactive_type"] = interactive.get("type", "")
        if interactive.get("type") == "button_reply":
            summary["reply_id"] = interactive.get("button_reply", {}).get("id", "")
            summary["reply_title"] = interactive.get("button_reply", {}).get("title", "")
        elif interactive.get("type") == "list_reply":
            summary["reply_id"] = interactive.get("list_reply", {}).get("id", "")
            summary["reply_title"] = interactive.get("list_reply", {}).get("title", "")
        elif interactive.get("type") == "nfm_reply":
            # WhatsApp Flow response
            summary["flow_response"] = interactive.get("nfm_reply", {}).get("response_json", "")[:2048]
    elif msg_type in ("image", "video", "audio", "document"):
        media = message.get(msg_type, {})
        summary["media_id"] = media.get("id", "")
        summary["mime_type"] = media.get("mime_type", "")
        summary["caption"] = media.get("caption", "")[:512]
    elif msg_type == "location":
        loc = message.get("location", {})
        summary["latitude"] = loc.get("latitude")
        summary["longitude"] = loc.get("longitude")
        summary["name"] = loc.get("name", "")
    elif msg_type == "contacts":
        summary["contact_count"] = len(message.get("contacts", []))
    return summary


def _raw_body(event: dict) -> bytes:
    body = event.get("body", "") or ""
    if event.get("isBase64Encoded"):
        return base64.b64decode(body)
    return body.encode("utf-8")


def _header(event: dict, name: str) -> str:
    """Case-insensitive header lookup for API Gateway REST events."""
    headers = event.get("headers") or {}
    name_lower = name.lower()
    for k, v in headers.items():
        if k.lower() == name_lower:
            return v or ""
    return ""


def _reply(status: int, body: str, content_type: str = "text/plain") -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": content_type},
        "body": body,
        "isBase64Encoded": False,
    }
