#!/usr/bin/env python3
"""
GitHub Token Scope Checker

Check what scopes your GitHub token has and what might be needed.
"""

import os

import requests


def check_token_detailed():
    """Check token scopes in detail."""
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        print("❌ No GITHUB_TOKEN environment variable set")
        return

    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}

    # Make a request to see scopes
    response = requests.get("https://api.github.com/user", headers=headers, timeout=10)

    print(f"Response Status: {response.status_code}")
    print("Response Headers:")
    for key, value in response.headers.items():
        if "scope" in key.lower() or "oauth" in key.lower():
            print(f"  {key}: {value}")

    if response.status_code == 200:
        user_data = response.json()
        print(f"\nAuthenticated as: {user_data.get('login', 'Unknown')}")
        print(f"Account Type: {user_data.get('type', 'Unknown')}")

    # Check what scopes we actually have
    scopes_header = response.headers.get("X-OAuth-Scopes", "")
    accepted_scopes = response.headers.get("X-Accepted-OAuth-Scopes", "")

    # Redact sensitive scope information for security
    scopes_display = "*** REDACTED ***" if scopes_header else "None visible"
    accepted_display = "*** REDACTED ***" if accepted_scopes else "None listed"

    print(f"\nCurrent Scopes: {scopes_display}")
    print(f"Accepted Scopes for /user endpoint: {accepted_display}")

    # Test repository access specifically
    repo_response = requests.get(
        "https://api.github.com/repos/dinoopitstudios/DinoAir", headers=headers, timeout=10
    )
    print(f"\nRepository Access Test: HTTP {repo_response.status_code}")

    if repo_response.status_code == 200:
        repo_data = repo_response.json()
        print(f"Repository: {repo_data.get('full_name')}")
        print(f"Private: {repo_data.get('private')}")
        print(f"Permissions: {repo_data.get('permissions', {})}")

    # Required scopes for security features
    print("\n🔐 Required Scopes for Security Features:")
    print("   - repo: Full repository access (required for security alerts)")
    print("   - security_events: Access to security events")
    print("   - admin:org: Organization administration (if org repo)")
    print("   - read:org: Organization read access")

    print("\n📋 To create a token with correct scopes:")
    print("   1. Go to: https://github.com/settings/tokens")
    print("   2. Click 'Generate new token (classic)'")
    print("   3. Select these scopes:")
    print("      ☑️ repo (Full control of private repositories)")
    print("      ☑️ security_events (Read and write security events)")
    print("      ☑️ admin:org (Full control of orgs and teams)")
    print("      ☑️ read:org (Read org and team membership)")


if __name__ == "__main__":
    check_token_detailed()
