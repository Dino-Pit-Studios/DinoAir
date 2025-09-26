#!/usr/bin/env python3
"""
GitHub Security Permissions Diagnostic

This script checks permissions, settings, and potential issues preventing
access to security features in GitHub repositories.
"""

import json
import os
import sys
from typing import Any

import requests
from github import Github, GithubException


class GitHubSecurityDiagnostic:
    """Diagnose GitHub security access issues."""

    def __init__(self, token: str = None):
        """Initialize with GitHub token."""
        self.token = token or os.getenv("GITHUB_TOKEN")
        if not self.token:
            raise ValueError("GitHub token required")

        self.headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        try:
            from github import Auth

            auth = Auth.Token(self.token)
            self.github = Github(auth=auth)
        except ImportError:
            self.github = Github(self.token)

        self.user = self.github.get_user()
        print(f"✅ Authenticated as: {self.user.login}")

    def check_token_scopes(self) -> dict[str, Any]:
        """Check what scopes the token has."""
        try:
            response = requests.get("https://api.github.com/user", headers=self.headers, timeout=10)
            scopes = response.headers.get("X-OAuth-Scopes", "").split(", ")
            scopes = [scope.strip() for scope in scopes if scope.strip()]

            print(f"🔑 Token Scopes: {', '.join(scopes) if scopes else 'None listed'}")

            # Check required scopes for security features
            required_scopes = {
                "repo": "Full repository access (required for private repos)",
                "security_events": "Security events access (for security alerts)",
                "admin:org": "Organization admin (for org-level security)",
                "read:org": "Organization read access",
            }

            missing_scopes = []
            for scope, description in required_scopes.items():
                if scope not in scopes:
                    missing_scopes.append(f"{scope} - {description}")

            if missing_scopes:
                print("❌ Missing potentially required scopes:")
                for scope in missing_scopes:
                    print(f"   - {scope}")
            else:
                print("✅ All potentially required scopes present")

            return {"scopes": scopes, "missing": missing_scopes}

        except Exception as e:
            print(f"❌ Error checking token scopes: {e}")
            return {"scopes": [], "missing": []}

    def check_repository_access(self, repo_name: str) -> dict[str, Any]:
        """Check repository access and permissions."""
        try:
            repo = self.github.get_repo(repo_name)

            # Get repository details
            repo_info = {
                "name": repo.full_name,
                "private": repo.private,
                "owner_type": "Organization" if repo.organization else "User",
                "permissions": {},
            }

            # Check permissions
            try:
                permissions = repo.get_permissions(self.user)
                repo_info["permissions"] = {
                    "admin": permissions.admin,
                    "maintain": permissions.maintain if hasattr(permissions, "maintain") else False,
                    "push": permissions.push,
                    "triage": permissions.triage if hasattr(permissions, "triage") else False,
                    "pull": permissions.pull,
                }
            except (GithubException, AttributeError) as e:
                print(f"⚠️  Could not retrieve detailed permissions: {e}")
                print("⚠️  Could not retrieve detailed permissions")

            print(f"📁 Repository: {repo_info['name']}")
            print(f"   Private: {repo_info['private']}")
            print(f"   Owner Type: {repo_info['owner_type']}")
            print(f"   Permissions: {repo_info['permissions']}")

            return repo_info

        except GithubException as e:
            print(f"❌ Error accessing repository: {e}")
            return {}

    def check_security_features_status(self, repo_name: str) -> dict[str, Any]:
        """Check which security features are enabled."""
        try:
            url = f"https://api.github.com/repos/{repo_name}"
            response = requests.get(url, headers=self.headers, timeout=10)

            if response.status_code != 200:
                print(f"❌ Cannot fetch repository details: HTTP {response.status_code}")
                return {}

            data = response.json()
            security_analysis = data.get("security_and_analysis", {})

            features = {
                "advanced_security": security_analysis.get("advanced_security", {}).get("status"),
                "secret_scanning": security_analysis.get("secret_scanning", {}).get("status"),
                "secret_scanning_push_protection": security_analysis.get(
                    "secret_scanning_push_protection", {}
                ).get("status"),
                "dependabot_security_updates": security_analysis.get(
                    "dependabot_security_updates", {}
                ).get("status"),
                "private_vulnerability_reporting": security_analysis.get(
                    "private_vulnerability_reporting", {}
                ).get("status"),
            }

            print("🔒 Security Features Status:")
            for feature, status in features.items():
                status_icon = (
                    "✅" if status == "enabled" else "❌" if status == "disabled" else "❓"
                )
                print(
                    f"   {status_icon} {feature.replace('_', ' ').title()}: {status or 'unknown'}"
                )

            return features

        except Exception as e:
            print(f"❌ Error checking security features: {e}")
            return {}

    def test_security_endpoints(self, repo_name: str) -> dict[str, Any]:
        """Test access to each security endpoint."""
        endpoints = {
            "code_scanning": (f"https://api.github.com/repos/{repo_name}/code-scanning/alerts"),
            "secret_scanning": (f"https://api.github.com/repos/{repo_name}/secret-scanning/alerts"),
            "dependabot": (f"https://api.github.com/repos/{repo_name}/dependabot/alerts"),
            "vulnerability_alerts": (
                f"https://api.github.com/repos/{repo_name}/vulnerability-alerts"
            ),
        }

        results = {}
        print("🧪 Testing Security Endpoints:")

        for endpoint_name, url in endpoints.items():
            display_name = endpoint_name.replace("_", " ").title()
            try:
                response = requests.get(url, headers=self.headers, timeout=10)
                results[endpoint_name] = {
                    "status_code": response.status_code,
                    "accessible": response.status_code == 200,
                    "error": None,
                }

                if response.status_code == 200:
                    data = response.json()
                    count = len(data) if isinstance(data, list) else 1
                    results[endpoint_name]["count"] = count
                    icon = "✅"
                    message = f"Accessible ({count} items)"
                elif response.status_code == 403:
                    icon = "🔒"
                    message = "Forbidden (insufficient permissions)"
                elif response.status_code == 404:
                    icon = "❓"
                    message = "Not found (feature not enabled or no data)"
                else:
                    icon = "❌"
                    message = f"HTTP {response.status_code}"

                print(f"   {icon} {display_name}: {message}")

            except Exception as e:
                results[endpoint_name] = {
                    "status_code": None,
                    "accessible": False,
                    "error": str(e),
                }
                print(f"   ❌ {display_name}: Error - {e}")

        return results

    def check_organization_settings(self, repo_name: str) -> dict[str, Any]:
        """Check organization-level security settings if applicable."""
        try:
            repo = self.github.get_repo(repo_name)
            if not repo.organization:
                print("ℹ️  Repository is not part of an organization")
                return {}

            org_name = repo.organization.login
            print(f"🏢 Checking organization: {org_name}")

            # Check organization membership
            try:
                org = self.github.get_organization(org_name)
                membership = org.get_membership(self.user.login)
                print(f"   Membership Role: {membership.role}")
                print(f"   Membership State: {membership.state}")

                return {
                    "organization": org_name,
                    "membership_role": membership.role,
                    "membership_state": membership.state,
                }

            except GithubException as e:
                print(f"   ❌ Cannot check organization membership: {e}")
                return {"organization": org_name, "error": str(e)}

        except Exception as e:
            print(f"❌ Error checking organization settings: {e}")
            return {}

    def run_full_diagnostic(self, repo_name: str) -> dict[str, Any]:
        """Run complete diagnostic."""
        print(f"🔍 Running Security Diagnostic for {repo_name}")
        print("=" * 60)

        results = {
            "timestamp": requests.get("https://api.github.com/", timeout=10).headers.get("Date"),
            "repository": repo_name,
            "token_scopes": self.check_token_scopes(),
            "repository_access": self.check_repository_access(repo_name),
            "security_features": self.check_security_features_status(repo_name),
            "endpoint_tests": self.test_security_endpoints(repo_name),
            "organization": self.check_organization_settings(repo_name),
        }

        print("\n📋 Diagnostic Summary:")
        print("=" * 30)

        # Provide recommendations
        recommendations = []

        if not results["repository_access"].get("permissions", {}).get("admin", False):
            recommendations.append("Consider requesting admin access to the repository")

        if "security_events" not in results["token_scopes"].get("scopes", []):
            recommendations.append("Token may need 'security_events' scope for security alerts")

        if not any(results["endpoint_tests"][ep]["accessible"] for ep in results["endpoint_tests"]):
            recommendations.append("No security endpoints accessible - check feature enablement")

        if recommendations:
            print("💡 Recommendations:")
            for i, rec in enumerate(recommendations, 1):
                print(f"   {i}. {rec}")
        else:
            print("✅ No immediate issues detected")

        return results


def main():
    """Main diagnostic function."""
    try:
        diagnostic = GitHubSecurityDiagnostic()
        repo_name = "dinoopitstudios/DinoAir"

        results = diagnostic.run_full_diagnostic(repo_name)

        # Save diagnostic results
        with open("security_diagnostic.json", "w") as f:
            json.dump(results, f, indent=2)
        print("\n💾 Full diagnostic saved to security_diagnostic.json")

        return results

    except Exception as e:
        print(f"❌ Diagnostic failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
