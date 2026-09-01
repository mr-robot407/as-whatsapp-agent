#!/usr/bin/env python3
"""Google OAuth setup — one-time interactive flow to obtain a refresh_token.

Requires a Google Cloud OAuth2 client (Desktop app) — download the
client_secret.json from GCP Console → APIs & Services → Credentials.

Usage:
  python3 scripts/gauth.py --client-secret /path/to/client_secret.json
  python3 scripts/gauth.py --client-secret … --write-secret
"""

from __future__ import annotations

import argparse
import json
import os
import sys

SCOPES = ["https://www.googleapis.com/auth/calendar"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--client-secret", required=True)
    ap.add_argument("--write-secret", action="store_true",
                    help="Upsert into AWS Secrets Manager at as-email-agent/google-oauth")
    ap.add_argument("--secret-arn",
                    default=os.environ.get("GOOGLE_OAUTH_SECRET_ARN", "as-email-agent/google-oauth"))
    args = ap.parse_args()

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("error: pip install google-auth-oauthlib", file=sys.stderr)
        return 2

    flow = InstalledAppFlow.from_client_secrets_file(args.client_secret, SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")

    payload = {
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "refresh_token": creds.refresh_token,
    }
    print(json.dumps(payload, indent=2))

    if args.write_secret:
        import boto3
        sm = boto3.client("secretsmanager")
        try:
            sm.put_secret_value(SecretId=args.secret_arn, SecretString=json.dumps(payload))
        except sm.exceptions.ResourceNotFoundException:
            sm.create_secret(Name=args.secret_arn, SecretString=json.dumps(payload))
        print(f"wrote to {args.secret_arn}", file=sys.stderr)
    else:
        print("\n(dry-run — pass --write-secret to upsert into Secrets Manager)", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
