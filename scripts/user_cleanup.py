#!/usr/bin/env python3
"""
Instruqt User Cleanup via CSP JWT Auth

Deletes the user created by user_provision.py from the sandbox account.
Run this BEFORE sandbox deallocation so the account switch still works.

Usage in Instruqt (cleanup-sandbox script):
  export INFOBLOX_EMAIL="$INFOBLOX_EMAIL"
  export INFOBLOX_PASSWORD="$INFOBLOX_PASSWORD"
  export INSTRUQT_PARTICIPANT_ID="$INSTRUQT_PARTICIPANT_ID"
  python3 user_cleanup.py

Environment Variables:
  INFOBLOX_EMAIL    - Required. Admin email for CSP JWT auth.
  INFOBLOX_PASSWORD - Required. Admin password for CSP JWT auth.
  CSP_URL           - CSP base URL (default: csp.infoblox.com)

Input Files (from allocation + user_provision):
  sandbox_id.txt   - Account UUID for account switching
  user_id.txt      - CSP user ID to delete
  user_email.txt   - For logging only
"""

import os
import sys
import requests


def read_file(filename):
    """Read a single-line txt file, return None if missing."""
    try:
        with open(filename, "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        return None


# === Config ===
CSP_URL = f"https://{os.environ.get('CSP_URL', 'csp.infoblox.com')}"
INFOBLOX_EMAIL = os.environ.get("INFOBLOX_EMAIL")
INFOBLOX_PASSWORD = os.environ.get("INFOBLOX_PASSWORD")

if not INFOBLOX_EMAIL or not INFOBLOX_PASSWORD:
    print("❌ Set INFOBLOX_EMAIL and INFOBLOX_PASSWORD", flush=True)
    sys.exit(1)

# === Read files ===
sandbox_id = read_file("sandbox_id.txt")
user_id = read_file("user_id.txt")
user_email = read_file("user_email.txt") or "unknown"

if not sandbox_id:
    print("⚠️ sandbox_id.txt not found, nothing to clean up", flush=True)
    sys.exit(0)

if not user_id:
    print("⚠️ user_id.txt not found, no user to delete", flush=True)
    sys.exit(0)

print(f"🧹 Deleting user {user_email} (ID: {user_id})", flush=True)
print(f"   From sandbox: {sandbox_id}", flush=True)

# === Step 1: Authenticate ===
print("🔐 Authenticating...", flush=True)
auth_resp = requests.post(
    f"{CSP_URL}/v2/session/users/sign_in",
    json={"email": INFOBLOX_EMAIL, "password": INFOBLOX_PASSWORD}
)
auth_resp.raise_for_status()
jwt = auth_resp.json()["jwt"]
headers = {"Authorization": f"Bearer {jwt}", "Content-Type": "application/json"}
print("✅ Authenticated", flush=True)

# === Step 2: Switch to sandbox account ===
print(f"🔁 Switching to sandbox {sandbox_id}...", flush=True)
switch_resp = requests.post(
    f"{CSP_URL}/v2/session/account_switch",
    headers=headers,
    json={"id": f"identity/accounts/{sandbox_id}"}
)
switch_resp.raise_for_status()
jwt = switch_resp.json()["jwt"]
headers["Authorization"] = f"Bearer {jwt}"
print("✅ Switched", flush=True)

# === Step 3: Delete user ===
print(f"🗑️ Deleting user {user_id}...", flush=True)
del_resp = requests.delete(f"{CSP_URL}/v2/users/{user_id}", headers=headers)

if del_resp.status_code in (200, 204):
    print(f"✅ User {user_email} deleted", flush=True)
elif del_resp.status_code == 404:
    print(f"⚠️ User {user_email} not found (already deleted?)", flush=True)
else:
    print(f"❌ Delete failed (HTTP {del_resp.status_code}): {del_resp.text[:200]}", flush=True)
    sys.exit(1)

print(f"\n{'='*60}", flush=True)
print("✅ User cleanup complete", flush=True)
print(f"{'='*60}", flush=True)
