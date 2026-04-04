#!/usr/bin/env python3
"""
Instruqt Sandbox Allocation via Broker API

Allocates a pre-created CSP sandbox from the Broker and saves all
IDs to text files for use by subsequent lifecycle scripts.

Usage in Instruqt (setup-sandbox script):
  export BROKER_API_TOKEN="<token>"
  python3 allocation_broker_subtenant.py

Environment Variables (Instruqt provides most automatically):
  BROKER_API_URL          - Broker endpoint (default: https://api-sandbox-broker.highvelocitynetworking.com/v1)
  BROKER_API_TOKEN        - Required. API token for the Broker.
  INSTRUQT_PARTICIPANT_ID - Required. Unique per student (provided by Instruqt).
  INSTRUQT_TRACK_SLUG     - Lab identifier (provided by Instruqt).
  SANDBOX_NAME_PREFIX     - Filter sandboxes by name prefix (default: "lab")

Output Files:
  subtenant_id.txt      - CSP ID (e.g., 2026838)
  external_id.txt       - Account UUID (e.g., 588424ea-ac7c-4fb3-...)
  sandbox_id.txt        - Same as external_id (for backward compat)
  sandbox_name.txt      - Human name (e.g., lab-adventure-0086)
  sfdc_account_id.txt   - Salesforce ID (e.g., 001SAND15956299f9d)
  sandbox_env.sh        - Source-able env vars for bash scripts
"""

import os
import sys
import time
import random
import requests

# ----------------------------------
# Configuration
# ----------------------------------
BROKER_API_URL = os.environ.get(
    "BROKER_API_URL",
    "https://api-sandbox-broker.highvelocitynetworking.com/v1"
)
BROKER_API_TOKEN = os.environ.get("BROKER_API_TOKEN")
INSTRUQT_SANDBOX_ID = os.environ.get("INSTRUQT_PARTICIPANT_ID")
INSTRUQT_TRACK_ID = os.environ.get("INSTRUQT_TRACK_SLUG", "unknown-lab")
SANDBOX_NAME_PREFIX = os.environ.get("SANDBOX_NAME_PREFIX", "lab")

# Startup jitter
time.sleep(random.uniform(1, 5))

# ----------------------------------
# Validation
# ----------------------------------
if not BROKER_API_TOKEN:
    print("❌ BROKER_API_TOKEN environment variable not set", flush=True)
    sys.exit(1)

if not INSTRUQT_SANDBOX_ID:
    print("❌ INSTRUQT_PARTICIPANT_ID not found (are you running in Instruqt?)", flush=True)
    sys.exit(1)

print(f"🎓 Student: {INSTRUQT_SANDBOX_ID}", flush=True)
print(f"📚 Lab: {INSTRUQT_TRACK_ID}", flush=True)
if SANDBOX_NAME_PREFIX:
    print(f"🔍 Filter: '{SANDBOX_NAME_PREFIX}*'", flush=True)

# ----------------------------------
# Allocate Sandbox
# ----------------------------------
headers = {
    "Authorization": f"Bearer {BROKER_API_TOKEN}",
    "Content-Type": "application/json",
    "X-Instruqt-Sandbox-ID": INSTRUQT_SANDBOX_ID,
    "X-Instruqt-Track-ID": INSTRUQT_TRACK_ID,
}
if SANDBOX_NAME_PREFIX:
    headers["X-Sandbox-Name-Prefix"] = SANDBOX_NAME_PREFIX

max_retries = 5
allocation_response = None

for attempt in range(max_retries):
    try:
        print(f"🔄 Allocation attempt {attempt + 1}/{max_retries}...", flush=True)
        resp = requests.post(
            f"{BROKER_API_URL}/allocate",
            headers=headers,
            timeout=(5, 30),
        )

        if resp.status_code in (200, 201):
            allocation_response = resp.json()
            emoji = "✅" if resp.status_code == 201 else "🔄"
            print(f"{emoji} Sandbox allocated (HTTP {resp.status_code})", flush=True)
            break
        elif resp.status_code == 409:
            print("❌ Pool exhausted: No sandboxes available", flush=True)
            sys.exit(1)
        elif resp.status_code == 403:
            print("⚠️ Rate limited, waiting...", flush=True)
            time.sleep(10)
        elif resp.status_code in {500, 502, 503, 504}:
            print(f"⚠️ Server error {resp.status_code}, retrying...", flush=True)
            time.sleep(min(2 ** attempt + random.uniform(0, 1), 30))
        else:
            print(f"❌ HTTP {resp.status_code}: {resp.text}", flush=True)
            sys.exit(1)

    except requests.exceptions.Timeout:
        print("⚠️ Timeout, retrying...", flush=True)
        time.sleep(min(2 ** attempt + random.uniform(0, 1), 30))
    except Exception as e:
        print(f"⚠️ Error: {e}", flush=True)
        time.sleep(min(2 ** attempt + random.uniform(0, 1), 30))
else:
    print("❌ Allocation failed after all retries", flush=True)
    sys.exit(1)

# ----------------------------------
# Extract IDs
# ----------------------------------
sandbox_id = allocation_response.get("sandbox_id", "")
external_id = allocation_response.get("external_id", "")
sandbox_name = allocation_response.get("name", "")
expires_at = allocation_response.get("expires_at", 0)
sfdc_account_id = allocation_response.get("sfdc_account_id", "")

if not sandbox_id or not external_id:
    print(f"❌ Invalid response: {allocation_response}", flush=True)
    sys.exit(1)

# Strip path prefix from external_id
if "/" in external_id:
    external_id = external_id.split("/")[-1]

# ----------------------------------
# Save to Files
# ----------------------------------
files = {
    "subtenant_id.txt": sandbox_id,
    "external_id.txt": external_id,
    "sandbox_id.txt": external_id,
    "sandbox_name.txt": sandbox_name,
    "sfdc_account_id.txt": sfdc_account_id,
}

for filename, value in files.items():
    with open(filename, "w") as f:
        f.write(value)
    print(f"✅ {filename}: {value}", flush=True)

# ----------------------------------
# Export Environment Variables
# ----------------------------------
with open("sandbox_env.sh", "w") as f:
    f.write("#!/bin/bash\n")
    f.write("# Auto-generated by allocation_broker_subtenant.py\n")
    f.write(f"export STUDENT_TENANT={sandbox_name}\n")
    f.write(f"export CSP_ACCOUNT_ID={external_id}\n")
    f.write(f"export BROKER_SANDBOX_ID={sandbox_id}\n")
    f.write(f"export SFDC_ACCOUNT_ID={sfdc_account_id}\n")

print(f"\n💡 Instruqt: set-var STUDENT_TENANT {sandbox_name}", flush=True)
print(f"   set-var CSP_ACCOUNT_ID {external_id}", flush=True)
print(f"   set-var BROKER_SANDBOX_ID {sandbox_id}", flush=True)
print(f"   set-var SFDC_ACCOUNT_ID {sfdc_account_id}", flush=True)

# ----------------------------------
# Summary
# ----------------------------------
print(f"\n{'='*60}", flush=True)
print("🎉 Sandbox Allocation Complete!", flush=True)
print(f"   Name:       {sandbox_name}", flush=True)
print(f"   CSP ID:     {sandbox_id}", flush=True)
print(f"   Account ID: {external_id}", flush=True)
print(f"   SFDC ID:    {sfdc_account_id}", flush=True)
print(f"   Expires:    {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(expires_at))}", flush=True)
print(f"{'='*60}", flush=True)
