#!/usr/bin/env python3
"""
Instruqt Sandbox Deallocation via Broker API

Marks the allocated sandbox for deletion in the Broker.
The Broker's background worker will then:
  1. Run NIOSXaaS cleanup (delete services)
  2. Delete the CSP subtenant account
  3. Remove the record from DynamoDB

Usage in Instruqt (cleanup-sandbox script, AFTER user_cleanup.py):
  export BROKER_API_TOKEN="$BROKER_API_TOKEN"
  export INSTRUQT_PARTICIPANT_ID="$INSTRUQT_PARTICIPANT_ID"
  python3 deallocation_broker_subtenant.py

Environment Variables:
  BROKER_API_URL          - Broker endpoint (default: https://api-sandbox-broker.highvelocitynetworking.com/v1)
  BROKER_API_TOKEN        - Required. API token for the Broker.
  INSTRUQT_PARTICIPANT_ID - Required. Same value used during allocation.

Input Files (from allocation_broker_subtenant.py):
  subtenant_id.txt  - Broker sandbox ID (CSP ID)
"""

import os
import sys
import requests

# === Config ===
BROKER_API_URL = os.environ.get(
    "BROKER_API_URL",
    "https://api-sandbox-broker.highvelocitynetworking.com/v1"
)
BROKER_API_TOKEN = os.environ.get("BROKER_API_TOKEN")
INSTRUQT_SANDBOX_ID = os.environ.get("INSTRUQT_PARTICIPANT_ID")

if not BROKER_API_TOKEN:
    print("❌ BROKER_API_TOKEN not set", flush=True)
    sys.exit(1)

if not INSTRUQT_SANDBOX_ID:
    print("❌ INSTRUQT_PARTICIPANT_ID not set", flush=True)
    sys.exit(1)

# === Read subtenant_id ===
try:
    with open("subtenant_id.txt", "r") as f:
        subtenant_id = f.read().strip()
except FileNotFoundError:
    print("⚠️ subtenant_id.txt not found, nothing to deallocate", flush=True)
    sys.exit(0)

if not subtenant_id:
    print("⚠️ subtenant_id.txt is empty, nothing to deallocate", flush=True)
    sys.exit(0)

print(f"🧹 Marking sandbox for deletion...", flush=True)
print(f"   Broker Sandbox ID: {subtenant_id}", flush=True)
print(f"   Student: {INSTRUQT_SANDBOX_ID}", flush=True)

# === Mark for Deletion ===
headers = {
    "Authorization": f"Bearer {BROKER_API_TOKEN}",
    "X-Instruqt-Sandbox-ID": INSTRUQT_SANDBOX_ID,
    "Content-Type": "application/json",
}

try:
    resp = requests.post(
        f"{BROKER_API_URL}/sandboxes/{subtenant_id}/mark-for-deletion",
        headers=headers,
        timeout=(5, 15),
    )

    if resp.status_code == 200:
        result = resp.json()
        print(f"✅ Sandbox marked for deletion", flush=True)
        print(f"   Status: {result.get('status', 'unknown')}", flush=True)
        print(f"   Cleanup will run within ~5 minutes", flush=True)

    elif resp.status_code == 404:
        print(f"⚠️ Sandbox {subtenant_id} not found (already cleaned up?)", flush=True)

    elif resp.status_code == 403:
        try:
            error = resp.json()
            msg = error.get("detail", {}).get("message", "Unknown")
            code = error.get("detail", {}).get("code", "")
            print(f"❌ Authorization error: {msg} ({code})", flush=True)
        except Exception:
            print(f"❌ Authorization error (HTTP 403): {resp.text}", flush=True)
        sys.exit(1)

    else:
        print(f"❌ Failed: HTTP {resp.status_code}", flush=True)
        print(f"   Response: {resp.text}", flush=True)
        sys.exit(1)

except requests.exceptions.RequestException as e:
    print(f"❌ Network error: {e}", flush=True)
    sys.exit(1)

print(f"\n{'='*60}", flush=True)
print("✅ Sandbox deallocation requested", flush=True)
print(f"{'='*60}", flush=True)
