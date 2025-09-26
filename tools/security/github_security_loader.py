#!/usr/bin/env python3
"""
GitHub Security Issues Loader

This script fetches security issues from GitHub repositories using the GitHub API.
Requires a Personal Access Token (PAT) with appropriate scopes.

Usage:
    # Set environment variable first:
    # $env:GITHUB_TOKEN="your_github_pat_here"

    python github_security_loader.py
"""

import json
import os
import sys
from datetime import datetime
from typing import Any

from github import Github, GithubException


class GitHubSecurityLoader:
    """Load security issues from GitHub repositories."""

    def __init__(self, token: str | None = None):
        """
        Initialize the GitHub Security Loader.

        Args:
            token: GitHub Personal Access Token. If None, will try to read from environment.
        """
        self.token = token or os.getenv("GITHUB_TOKEN")
        if not self.token:
            raise ValueError(
                "GitHub token not provided. Set GITHUB_TOKEN environment variable or pass token parameter."
            )

        try:
            from github import Auth

            auth = Auth.Token(self.token)
            self.github = Github(auth=auth)
            # Test authentication
            self.user = self.github.get_user()
            print(f"✅ Authenticated as: {self.user.login}")
        except ImportError:
            # Fallback for older PyGithub versions
            self.github = Github(self.token)
            self.user = self.github.get_user()
            print(f"✅ Authenticated as: {self.user.login}")
        except GithubException as e:
            raise ValueError(f"Failed to authenticate with GitHub: {e}")

    def get_repository_security_advisories(self, repo_name: str) -> list[dict[str, Any]]:
        """
        Get security advisories for a specific repository.

        Args:
            repo_name: Repository name in format "owner/repo"

        Returns:
            List of security advisory dictionaries
        """
        try:
            repo = self.github.get_repo(repo_name)
            advisories = []

            # Note: Repository-specific security advisories require special permissions
            # For now, we'll return empty list as this requires repository admin access
            print(f"ℹ️  Repository security advisories require admin access for {repo_name}")
            return advisories

        except GithubException as e:
            print(f"❌ Error fetching advisories for {repo_name}: {e}")
            return []

    def get_code_scanning_alerts(self, repo_name: str) -> list[dict[str, Any]]:
        """
        Get code scanning alerts (e.g., from CodeQL) for a repository.

        Args:
            repo_name: Repository name in format "owner/repo"

        Returns:
            List of code scanning alert dictionaries
        """
        try:
            repo = self.github.get_repo(repo_name)
            alerts = []

            # Get code scanning alerts
            for alert in repo.get_code_scanning_alerts():
                alert_data = {
                    "number": alert.number,
                    "state": alert.state,
                    "rule_id": alert.rule.id,
                    "rule_name": alert.rule.name,
                    "rule_severity": alert.rule.severity,
                    "rule_description": alert.rule.description,
                    "tool_name": alert.tool.name,
                    "tool_version": alert.tool.version,
                    "created_at": alert.created_at.isoformat() if alert.created_at else None,
                    "updated_at": alert.updated_at.isoformat() if alert.updated_at else None,
                    "url": alert.html_url,
                    "instances": [],
                }

                # Get alert instances (specific locations)
                for instance in alert.instances:
                    instance_data = {
                        "ref": instance.ref,
                        "state": instance.state,
                        "commit_sha": instance.commit_sha,
                        "location": (
                            {
                                "path": instance.location.path,
                                "start_line": instance.location.start_line,
                                "end_line": instance.location.end_line,
                                "start_column": instance.location.start_column,
                                "end_column": instance.location.end_column,
                            }
                            if instance.location
                            else None
                        ),
                        "message": instance.message.text if instance.message else None,
                    }
                    alert_data["instances"].append(instance_data)

                alerts.append(alert_data)

            return alerts

        except GithubException as e:
            print(f"❌ Error fetching code scanning alerts for {repo_name}: {e}")
            return []

    def get_secret_scanning_alerts(self, repo_name: str) -> list[dict[str, Any]]:
        """
        Get secret scanning alerts for a repository.

        Args:
            repo_name: Repository name in format "owner/repo"

        Returns:
            List of secret scanning alert dictionaries
        """
        try:
            repo = self.github.get_repo(repo_name)
            alerts = []

            # Get secret scanning alerts
            for alert in repo.get_secret_scanning_alerts():
                alert_data = {
                    "number": alert.number,
                    "state": alert.state,
                    "secret_type": alert.secret_type,
                    "secret_type_display_name": alert.secret_type_display_name,
                    "created_at": alert.created_at.isoformat() if alert.created_at else None,
                    "updated_at": alert.updated_at.isoformat() if alert.updated_at else None,
                    "url": alert.html_url,
                    "locations": [],
                }

                # Get secret locations
                for location in alert.locations:
                    location_data = {
                        "type": location.type,
                        "path": location.details.get("path") if location.details else None,
                        "start_line": (
                            location.details.get("start_line") if location.details else None
                        ),
                        "end_line": location.details.get("end_line") if location.details else None,
                        "start_column": (
                            location.details.get("start_column") if location.details else None
                        ),
                        "end_column": (
                            location.details.get("end_column") if location.details else None
                        ),
                    }
                    alert_data["locations"].append(location_data)

                alerts.append(alert_data)

            return alerts

        except GithubException as e:
            print(f"❌ Error fetching secret scanning alerts for {repo_name}: {e}")
            return []

    def get_dependabot_alerts(self, repo_name: str) -> list[dict[str, Any]]:
        """
        Get Dependabot vulnerability alerts for a repository.

        Args:
            repo_name: Repository name in format "owner/repo"

        Returns:
            List of Dependabot alert dictionaries
        """
        try:
            repo = self.github.get_repo(repo_name)
            alerts = []

            # Get Dependabot alerts
            for alert in repo.get_dependabot_alerts():
                alert_data = {
                    "number": alert.number,
                    "state": alert.state,
                    "dependency": {
                        "package": alert.dependency.package.name,
                        "ecosystem": alert.dependency.package.ecosystem,
                        "manifest_path": alert.dependency.manifest_path,
                        "scope": alert.dependency.scope,
                    },
                    "security_advisory": {
                        "ghsa_id": alert.security_advisory.ghsa_id,
                        "cve_id": alert.security_advisory.cve_id,
                        "summary": alert.security_advisory.summary,
                        "description": alert.security_advisory.description,
                        "severity": alert.security_advisory.severity,
                        "cvss_score": (
                            alert.security_advisory.cvss.score
                            if alert.security_advisory.cvss
                            else None
                        ),
                        "published_at": (
                            alert.security_advisory.published_at.isoformat()
                            if alert.security_advisory.published_at
                            else None
                        ),
                    },
                    "security_vulnerability": {
                        "package": alert.security_vulnerability.package.name,
                        "ecosystem": alert.security_vulnerability.package.ecosystem,
                        "vulnerable_version_range": alert.security_vulnerability.vulnerable_version_range,
                        "first_patched_version": (
                            alert.security_vulnerability.first_patched_version.identifier
                            if alert.security_vulnerability.first_patched_version
                            else None
                        ),
                    },
                    "url": alert.html_url,
                    "created_at": alert.created_at.isoformat() if alert.created_at else None,
                    "updated_at": alert.updated_at.isoformat() if alert.updated_at else None,
                }
                alerts.append(alert_data)

            return alerts

        except GithubException as e:
            print(f"❌ Error fetching Dependabot alerts for {repo_name}: {e}")
            return []

    def get_all_security_issues(self, repo_name: str) -> dict[str, list[dict[str, Any]]]:
        """
        Get all types of security issues for a repository.

        Args:
            repo_name: Repository name in format "owner/repo"

        Returns:
            Dictionary containing all security issue types
        """
        print(f"🔍 Fetching security issues for {repo_name}...")

        security_data = {
            "repository": repo_name,
            "timestamp": datetime.now().isoformat(),
            "security_advisories": self.get_repository_security_advisories(repo_name),
            "code_scanning_alerts": self.get_code_scanning_alerts(repo_name),
            "secret_scanning_alerts": self.get_secret_scanning_alerts(repo_name),
            "dependabot_alerts": self.get_dependabot_alerts(repo_name),
        }

        # Print summary
        print(f"📊 Security Issues Summary for {repo_name}:")
        print(f"   - Security Advisories: {len(security_data['security_advisories'])}")
        print(f"   - Code Scanning Alerts: {len(security_data['code_scanning_alerts'])}")
        print(f"   - Secret Scanning Alerts: {len(security_data['secret_scanning_alerts'])}")
        print(f"   - Dependabot Alerts: {len(security_data['dependabot_alerts'])}")

        return security_data

    def save_to_file(self, data: dict[str, Any], filename: str = "security_issues.json"):
        """Save security data to a JSON file."""
        allowed_filenames = {"security_issues.json"}
        if filename not in allowed_filenames:
            raise ValueError(f"Invalid filename: {filename}")
        safe_path = os.path.join(os.getcwd(), filename)
        with open(safe_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"💾 Security data saved to {safe_path}")


def main():
    """Main function to demonstrate usage."""
    try:
        # Initialize the loader (token will be read from environment)
        loader = GitHubSecurityLoader()

        # Get security issues for DinoAir repository
        repo_name = "dinoopitstudios/DinoAir"
        security_data = loader.get_all_security_issues(repo_name)

        # Save to file
        loader.save_to_file(security_data, "dinoair_security_issues.json")

        return security_data

    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
