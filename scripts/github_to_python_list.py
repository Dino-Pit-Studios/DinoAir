#!/usr/bin/env python3
"""
GitHub Security Issues to Python List

Convert GitHub security data into structured Python lists for easy processing.
"""

import json
import os
from datetime import datetime
from typing import Any


class GitHubSecurityIssuesList:
    """Convert GitHub security data into Python lists."""

    def __init__(self, data_file: str = "dinoair_security_data.json"):
        """Initialize with security data file."""
        self.data_file = data_file
        self.data = self.load_data()

    def load_data(self) -> dict[str, Any]:
        """Load security data from JSON file."""
        if not os.path.exists(self.data_file):
            raise FileNotFoundError(f"Security data file not found: {self.data_file}")

        with open(self.data_file, encoding="utf-8") as f:
            return json.load(f)

    def get_code_scanning_issues(self) -> list[dict[str, Any]]:
        """Get CodeQL code scanning issues as a Python list."""
        alerts = self.data.get("security_alerts", {}).get("code_scanning", [])

        issues = []
        for alert in alerts:
            # Extract most recent instance for location info
            instance = alert.get("most_recent_instance", {})
            location = instance.get("location", {})

            issue = {
                "id": alert.get("number"),
                "type": "code_scanning",
                "severity": alert.get("rule", {}).get("severity", "unknown"),
                "rule_id": alert.get("rule", {}).get("id", ""),
                "rule_name": alert.get("rule", {}).get("name", ""),
                "title": alert.get("rule", {}).get("description", ""),
                "state": alert.get("state", "unknown"),
                "file_path": location.get("path", ""),
                "line_start": location.get("start_line"),
                "line_end": location.get("end_line"),
                "column_start": location.get("start_column"),
                "column_end": location.get("end_column"),
                "url": alert.get("html_url", ""),
                "created_at": alert.get("created_at", ""),
                "updated_at": alert.get("updated_at", ""),
                "tags": alert.get("rule", {}).get("tags", []),
                "help_text": alert.get("rule", {}).get("help", ""),
            }
            issues.append(issue)

        return issues

    def get_secret_scanning_issues(self) -> list[dict[str, Any]]:
        """Get secret scanning issues as a Python list."""
        alerts = self.data.get("security_alerts", {}).get("secret_scanning", [])

        issues = []
        for alert in alerts:
            locations = alert.get("locations", [])
            location_info = locations[0] if locations else {}

            issue = {
                "id": alert.get("number"),
                "type": "secret_scanning",
                "severity": "high",  # Secrets are always high severity
                "secret_type": alert.get("secret_type", ""),
                "secret_type_display_name": alert.get("secret_type_display_name", ""),
                "state": alert.get("state", "unknown"),
                "file_path": location_info.get("path", ""),
                "line_start": location_info.get("start_line"),
                "line_end": location_info.get("end_line"),
                "url": alert.get("html_url", ""),
                "created_at": alert.get("created_at", ""),
                "updated_at": alert.get("updated_at", ""),
            }
            issues.append(issue)

        return issues

    def get_dependabot_issues(self) -> list[dict[str, Any]]:
        """Get Dependabot dependency issues as a Python list."""
        alerts = self.data.get("security_alerts", {}).get("dependabot", [])

        issues = []
        for alert in alerts:
            dependency = alert.get("dependency", {})
            package = dependency.get("package", {})
            advisory = alert.get("security_advisory", {})
            vulnerability = alert.get("security_vulnerability", {})

            issue = {
                "id": alert.get("number"),
                "type": "dependabot",
                "severity": advisory.get("severity", "unknown"),
                "package_name": package.get("name", ""),
                "package_ecosystem": package.get("ecosystem", ""),
                "manifest_path": dependency.get("manifest_path", ""),
                "vulnerable_version_range": vulnerability.get("vulnerable_version_range", ""),
                "first_patched_version": vulnerability.get("first_patched_version", ""),
                "cve_id": advisory.get("cve_id", ""),
                "ghsa_id": advisory.get("ghsa_id", ""),
                "title": advisory.get("summary", ""),
                "description": advisory.get("description", ""),
                "state": alert.get("state", "unknown"),
                "url": alert.get("html_url", ""),
                "created_at": alert.get("created_at", ""),
                "updated_at": alert.get("updated_at", ""),
            }
            issues.append(issue)

        return issues

    def get_all_security_issues(self) -> list[dict[str, Any]]:
        """Get all security issues combined into a single list."""
        all_issues = []

        # Add code scanning issues
        all_issues.extend(self.get_code_scanning_issues())

        # Add secret scanning issues
        all_issues.extend(self.get_secret_scanning_issues())

        # Add Dependabot issues
        all_issues.extend(self.get_dependabot_issues())

        # Sort by severity and creation date
        severity_order = {
            "error": 0,
            "high": 1,
            "warning": 2,
            "medium": 3,
            "note": 4,
            "low": 5,
            "unknown": 6,
        }
        all_issues.sort(
            key=lambda x: (
                severity_order.get(x.get("severity", "unknown"), 6),
                x.get("created_at", ""),
            )
        )

        return all_issues

    def get_issues_by_severity(self, severity: str) -> list[dict[str, Any]]:
        """Get issues filtered by severity level."""
        all_issues = self.get_all_security_issues()
        return [
            issue for issue in all_issues if issue.get("severity", "").lower() == severity.lower()
        ]

    def get_issues_by_type(self, issue_type: str) -> list[dict[str, Any]]:
        """Get issues filtered by type (code_scanning, secret_scanning, dependabot)."""
        all_issues = self.get_all_security_issues()
        return [issue for issue in all_issues if issue.get("type", "") == issue_type]

    def get_issues_by_file(self, file_path: str) -> list[dict[str, Any]]:
        """Get issues filtered by file path."""
        all_issues = self.get_all_security_issues()
        return [issue for issue in all_issues if file_path in issue.get("file_path", "")]

    def print_issues_summary(self):
        """Print a summary of all security issues."""
        all_issues = self.get_all_security_issues()

        print("🔒 Security Issues Summary")
        print("=" * 30)
        print(f"Total Issues: {len(all_issues)}")

        # Count by type
        type_counts = {}
        severity_counts = {}

        for issue in all_issues:
            issue_type = issue.get("type", "unknown")
            severity = issue.get("severity", "unknown")

            type_counts[issue_type] = type_counts.get(issue_type, 0) + 1
            severity_counts[severity] = severity_counts.get(severity, 0) + 1

        print("\nBy Type:")
        for type_name, count in type_counts.items():
            print(f"  {type_name}: {count}")

        print("\nBy Severity:")
        for severity, count in severity_counts.items():
            print(f"  {severity}: {count}")

        return all_issues


def demo_usage():
    """Demonstrate how to use the security issues list."""
    print("🚀 GitHub Security Issues - Python List Demo")
    print("=" * 50)

    # Initialize the security issues loader
    loader = GitHubSecurityIssuesList()

    # Get all security issues as a Python list
    all_issues = loader.get_all_security_issues()

    print(f"✅ Loaded {len(all_issues)} security issues into Python list")

    # Show examples of accessing the data
    if all_issues:
        print("\n📋 Example Issue (first item):")
        first_issue = all_issues[0]
        for key, value in first_issue.items():
            print(f"  {key}: {value}")

    # Get specific types of issues
    code_issues = loader.get_code_scanning_issues()
    secret_issues = loader.get_secret_scanning_issues()
    dependabot_issues = loader.get_dependabot_issues()

    print("\n🔍 Issue Breakdown:")
    print(f"  Code Scanning: {len(code_issues)}")
    print(f"  Secret Scanning: {len(secret_issues)}")
    print(f"  Dependabot: {len(dependabot_issues)}")

    # Get high-priority issues
    high_priority = loader.get_issues_by_severity("error")
    print(f"  High Priority (errors): {len(high_priority)}")

    # Show how to iterate through issues
    print("\n🔴 High Priority Issues:")
    for issue in high_priority:
        print(f"  • {issue['rule_name']}: {issue['title']}")
        print(f"    File: {issue['file_path']} (line {issue['line_start']})")

    return all_issues


if __name__ == "__main__":
    # Run the demo
    security_issues_list = demo_usage()

    # Save as Python file for easy import
    output_file = "security_issues_list.py"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("# GitHub Security Issues - Generated Python List\n")
        f.write(f"# Generated on: {datetime.now().isoformat()}\n")
        f.write(f"# Total issues: {len(security_issues_list)}\n\n")
        f.write("security_issues = ")
        f.write(repr(security_issues_list))

    print(f"\n💾 Security issues saved to: {output_file}")
    print("📝 You can now import with: from security_issues_list import security_issues")
