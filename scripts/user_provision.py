#!/usr/bin/env python3
"""
Instruqt User Provisioning via CSP JWT Auth

Reads sandbox details from txt files (created by allocation_broker_subtenant.py),
constructs user email from sandbox name, generates a strong password,
creates the user on the CSP sandbox account, and saves credentials.

Usage in Instruqt (setup-sandbox script, AFTER allocation):
  python3 user_provision.py

  # Delete user (cleanup-sandbox script):
  python3 user_provision.py --delete

Environment Variables:
  INFOBLOX_EMAIL    - Required. Admin email for CSP JWT auth.
  INFOBLOX_PASSWORD - Required. Admin password for CSP JWT auth.
  CSP_URL           - CSP base URL (default: csp.infoblox.com)
  USER_DOMAIN       - Domain for user email (default: infoblox.lab)

Input Files (from allocation_broker_subtenant.py):
  sandbox_id.txt        - Account UUID for account switching
  sandbox_name.txt      - Used to construct username
  sfdc_account_id.txt   - SFDC ID (saved to credentials)

Output Files:
  user_email.txt        - Generated login email
  user_password.txt     - Generated password
  user_id.txt           - CSP user ID (for cleanup/deletion)
  user_credentials.sh   - Source-able credentials for bash
"""

import os
import sys
import time
import random
import string
import requests


def generate_password(length=16):
    """Generate a strong password that meets CSP criteria.

    CSP requires: uppercase, lowercase, digits, and 2+ special characters.
    """
    upper = random.choices(string.ascii_uppercase, k=3)
    lower = random.choices(string.ascii_lowercase, k=5)
    digits = random.choices(string.digits, k=4)
    specials = random.choices("!@#$%&", k=4)

    password = upper + lower + digits + specials
    random.shuffle(password)
    return "".join(password)


def read_file(filename):
    """Read a single-line txt file, exit if missing."""
    try:
        with open(filename, "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        print(f"❌ {filename} not found. Run allocation_broker_subtenant.py first.", flush=True)
        sys.exit(1)


def authenticate(base_url, email, password):
    """Authenticate with CSP and return JWT headers."""
    resp = requests.post(
        f"{base_url}/v2/session/users/sign_in",
        json={"email": email, "password": password}
    )
    resp.raise_for_status()
    jwt = resp.json()["jwt"]
    return {"Authorization": f"Bearer {jwt}", "Content-Type": "application/json"}


def switch_account(base_url, headers, account_id):
    """Switch to sandbox account and return new JWT headers."""
    resp = requests.post(
        f"{base_url}/v2/session/account_switch",
        headers=headers,
        json={"id": f"identity/accounts/{account_id}"}
    )
    resp.raise_for_status()
    jwt = resp.json()["jwt"]
    return {"Authorization": f"Bearer {jwt}", "Content-Type": "application/json"}


def get_groups(base_url, headers):
    """Fetch user and admin group IDs."""
    resp = requests.get(f"{base_url}/v2/groups", headers=headers)
    resp.raise_for_status()
    groups = resp.json().get("results", [])
    user_gid = next((g["id"] for g in groups if g.get("name") == "user"), None)
    admin_gid = next((g["id"] for g in groups if g.get("name") == "act_admin"), None)
    return user_gid, admin_gid


def get_user_id_by_email(base_url, headers, email):
    """Look up existing user by email, return user_id or None."""
    resp = requests.get(
        f"{base_url}/v2/users?_filter=email==\"{email}\"",
        headers=headers
    )
    if resp.status_code == 200:
        results = resp.json().get("results", [])
        if results:
            uid = results[0].get("id", "")
            return uid.split("/")[-1] if "/" in uid else uid
    return None


def create_user(base_url, headers, name, email, user_gid, admin_gid):
    """Create user with retries. Returns user_id or None."""
    payload = {
        "name": name,
        "email": email,
        "type": "interactive",
        "group_ids": [user_gid, admin_gid]
    }

    for attempt in range(5):
        try:
            resp = requests.post(f"{base_url}/v2/users", headers=headers, json=payload)
            if resp.status_code == 409:
                print("  ⚠️ User already exists, looking up ID...", flush=True)
                return get_user_id_by_email(base_url, headers, email)
            resp.raise_for_status()
            uid = resp.json().get("result", {}).get("id", "")
            return uid.split("/")[-1] if "/" in uid else uid
        except requests.RequestException as e:
            print(f"  ⚠️ Attempt {attempt + 1} failed: {e}", flush=True)
            time.sleep((2 ** attempt) + random.random())

    return None


def set_password(base_url, headers, user_id, password):
    """Set user password. Returns True on success."""
    resp = requests.post(
        f"{base_url}/v2/users/{user_id}/password",
        headers=headers,
        json={"new_password": password}
    )
    return resp.status_code == 200


def delete_user(base_url, headers, user_id):
    """Delete user by ID. Returns True on success."""
    resp = requests.delete(f"{base_url}/v2/users/{user_id}", headers=headers)
    return resp.status_code in (200, 204)


# ==============================================================
# Main
# ==============================================================
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Provision or delete a user on the allocated sandbox")
    parser.add_argument("--delete", action="store_true", help="Delete the user instead of creating")
    args = parser.parse_args()

    # --- Config ---
    CSP_URL = f"https://{os.environ.get('CSP_URL', 'csp.infoblox.com')}"
    INFOBLOX_EMAIL = os.environ.get("INFOBLOX_EMAIL")
    INFOBLOX_PASSWORD = os.environ.get("INFOBLOX_PASSWORD")
    USER_DOMAIN = os.environ.get("USER_DOMAIN", "infoblox.lab")

    if not INFOBLOX_EMAIL or not INFOBLOX_PASSWORD:
        print("❌ Set INFOBLOX_EMAIL and INFOBLOX_PASSWORD", flush=True)
        sys.exit(1)

    # --- Read allocation files + env vars ---
    sandbox_id = read_file("sandbox_id.txt")
    sandbox_name = read_file("sandbox_name.txt")
    sfdc_account_id = read_file("sfdc_account_id.txt")

    PARTICIPANT_ID = os.environ.get("INSTRUQT_PARTICIPANT_ID")
    if not PARTICIPANT_ID:
        print("❌ INSTRUQT_PARTICIPANT_ID not set", flush=True)
        sys.exit(1)

    # --- Construct user credentials (participant_id is unique per student) ---
    user_email = f"{PARTICIPANT_ID}@{USER_DOMAIN}"
    user_password = generate_password()

    print(f"📋 Sandbox:  {sandbox_name}", flush=True)
    print(f"📋 SFDC ID:  {sfdc_account_id}", flush=True)
    print(f"📋 User:     {user_email}", flush=True)
    print()

    # --- Step 1: Authenticate ---
    print("🔐 Authenticating with CSP...", flush=True)
    headers = authenticate(CSP_URL, INFOBLOX_EMAIL, INFOBLOX_PASSWORD)
    print("✅ Authenticated", flush=True)

    # --- Step 2: Switch to sandbox account ---
    print(f"🔁 Switching to sandbox {sandbox_id}...", flush=True)
    headers = switch_account(CSP_URL, headers, sandbox_id)
    print("✅ Switched", flush=True)
    time.sleep(2)

    # --- DELETE mode ---
    if args.delete:
        user_id = read_file("user_id.txt")
        print(f"\n🗑️ Deleting user {user_email} (ID: {user_id})...", flush=True)
        if delete_user(CSP_URL, headers, user_id):
            print("✅ User deleted", flush=True)
        else:
            print("❌ Delete failed", flush=True)
            sys.exit(1)
        sys.exit(0)

    # --- CREATE mode ---
    # Step 3: Get groups
    print("👥 Fetching groups...", flush=True)
    user_gid, admin_gid = get_groups(CSP_URL, headers)
    if not user_gid or not admin_gid:
        print("❌ Could not find required groups", flush=True)
        sys.exit(1)
    print("✅ Groups found", flush=True)

    # Step 4: Create user
    print(f"👤 Creating user {user_email}...", flush=True)
    user_id = create_user(CSP_URL, headers, PARTICIPANT_ID, user_email, user_gid, admin_gid)
    if not user_id:
        print("❌ User creation failed", flush=True)
        sys.exit(1)
    print(f"✅ User created (ID: {user_id})", flush=True)

    # Step 5: Set password
    print("🔑 Setting password...", flush=True)
    if set_password(CSP_URL, headers, user_id, user_password):
        print("✅ Password set", flush=True)
    else:
        print("❌ Password set failed", flush=True)
        sys.exit(1)

    # --- Save credentials ---
    files = {
        "user_email.txt": user_email,
        "user_password.txt": user_password,
        "user_id.txt": user_id,
    }
    for filename, value in files.items():
        with open(filename, "w") as f:
            f.write(value)

    with open("user_credentials.sh", "w") as f:
        f.write("#!/bin/bash\n")
        f.write("# Auto-generated by user_provision.py\n")
        f.write(f"export CSP_USER_EMAIL='{user_email}'\n")
        f.write(f"export CSP_USER_PASSWORD='{user_password}'\n")
        f.write(f"export CSP_USER_ID='{user_id}'\n")
        f.write(f"export SFDC_ACCOUNT_ID='{sfdc_account_id}'\n")

    # --- Summary ---
    print(f"\n{'='*60}", flush=True)
    print("🎉 User Provisioning Complete!", flush=True)
    print(f"   Sandbox:  {sandbox_name}", flush=True)
    print(f"   SFDC ID:  {sfdc_account_id}", flush=True)
    print(f"   Email:    {user_email}", flush=True)
    print(f"   Password: {user_password}", flush=True)
    print(f"   User ID:  {user_id}", flush=True)
    print(f"\n   Login at: https://csp.infoblox.com", flush=True)
    print(f"\n   Instruqt:", flush=True)
    print(f"     set-var CSP_USER_EMAIL '{user_email}'", flush=True)
    print(f"     set-var CSP_USER_PASSWORD '{user_password}'", flush=True)
    print(f"{'='*60}", flush=True)
