#!/usr/bin/env python3
"""
GitHub Security Issues Summary Generator

Parse the security data and create a readable summary of security issues.
"""

import json
import os
from collections import Counter


def load_security_data(filename="dinoair_security_data.json"):
    """Load the security data from JSON file."""
    allowed_filenames = {"dinoair_security_data.json"}
    if filename not in allowed_filenames:
        raise ValueError(f"Invalid filename: {filename}")
    safe_path = os.path.join(os.path.dirname(__file__), filename)
    with open(safe_path, encoding="utf-8") as f:
        return json.load(f)


def analyze_code_scanning_alerts(alerts):
    """Analyze CodeQL code scanning alerts."""
    print("🔍 CodeQL Code Scanning Analysis")
    print("=" * 40)

    if not alerts:
        print("✅ No code scanning alerts found")
        return None

    # Count by severity
    severity_counts = Counter(alert["rule"]["severity"] for alert in alerts)

    # Count by rule type
    rule_counts = Counter(alert["rule"]["name"] for alert in alerts)

    # Count by state
    state_counts = Counter(alert["state"] for alert in alerts)

    print(f"📊 Total Alerts: {len(alerts)}")
    print("\n🚨 By Severity:")
    for severity, count in severity_counts.most_common():
        severity_icon = {"error": "🔴", "warning": "🟡", "note": "ℹ️"}.get(severity, "❓")
        print(f"   {severity_icon} {severity.title()}: {count}")

    print("\n📋 By State:")
    for state, count in state_counts.most_common():
        state_icon = {"open": "🔓", "dismissed": "🔕", "fixed": "✅"}.get(state, "❓")
        print(f"   {state_icon} {state.title()}: {count}")

    print("\n🔧 Top Rule Types:")
    for rule, count in rule_counts.most_common(10):
        print(f"   • {rule}: {count}")

    # Show some specific high-priority alerts
    error_alerts = [a for a in alerts if a["rule"]["severity"] == "error"]
    if error_alerts:
        print(f"\n🔴 High Priority Errors ({len(error_alerts)}):")
        for alert in error_alerts[:5]:  # Show first 5
            print(f"   • {alert['rule']['name']}: {alert['rule']['description']}")
            print(
                f"     File: Line {alert.get('most_recent_instance', {}).get('location', {}).get('start_line', 'unknown')}"
            )

    return {
        "total": len(alerts),
        "by_severity": dict(severity_counts),
        "by_state": dict(state_counts),
        "by_rule": dict(rule_counts),
    }


def analyze_secret_scanning(alerts):
    """Analyze secret scanning alerts."""
    print("\n🔐 Secret Scanning Analysis")
    print("=" * 40)

    if not alerts:
        print("✅ No secrets detected - Great job!")
        return {"total": 0}

    secret_types = Counter(alert["secret_type"] for alert in alerts)
    state_counts = Counter(alert["state"] for alert in alerts)

    print(f"📊 Total Secret Alerts: {len(alerts)}")
    print("\n🔑 By Secret Type:")
    for secret_type, count in secret_types.most_common():
        print(f"   • {secret_type}: {count}")

    print("\n📋 By State:")
    for state, count in state_counts.most_common():
        print(f"   • {state}: {count}")

    return {"total": len(alerts), "by_type": dict(secret_types), "by_state": dict(state_counts)}


def analyze_dependabot(alerts):
    """Analyze Dependabot alerts."""
    print("\n📦 Dependabot Analysis")
    print("=" * 40)

    if not alerts:
        print("✅ No vulnerable dependencies found!")
        return {"total": 0}

    severity_counts = Counter(alert["security_advisory"]["severity"] for alert in alerts)
    state_counts = Counter(alert["state"] for alert in alerts)
    ecosystem_counts = Counter(alert["dependency"]["package"]["ecosystem"] for alert in alerts)

    print(f"📊 Total Dependency Alerts: {len(alerts)}")
    print("\n🚨 By Severity:")
    for severity, count in severity_counts.most_common():
        print(f"   • {severity}: {count}")

    print("\n🌐 By Ecosystem:")
    for ecosystem, count in ecosystem_counts.most_common():
        print(f"   • {ecosystem}: {count}")

    return {
        "total": len(alerts),
        "by_severity": dict(severity_counts),
        "by_ecosystem": dict(ecosystem_counts),
    }


def generate_security_summary():
    """Generate a comprehensive security summary."""
    print("🔒 GitHub Security Issues Summary")
    print("=" * 50)

    # Load data
    data = load_security_data()

    print(f"Repository: {data['repository']}")
    print(f"Scan Time: {data['timestamp']}")
    print(f"Repository Type: {'Private' if data['repository_info']['private'] else 'Public'}")

    # Analyze each type of security alert
    code_analysis = analyze_code_scanning_alerts(data["security_alerts"]["code_scanning"])
    secret_analysis = analyze_secret_scanning(data["security_alerts"]["secret_scanning"])
    dependabot_analysis = analyze_dependabot(data["security_alerts"]["dependabot"])

    # Overall summary
    print("\n🎯 Security Score Summary")
    print("=" * 30)

    total_issues = sum(
        [
            code_analysis.get("total", 0),
            secret_analysis.get("total", 0),
            dependabot_analysis.get("total", 0),
        ]
    )

    print(f"Total Security Issues: {total_issues}")

    # Security score (simple scoring)
    score = 100
    score -= code_analysis.get("by_severity", {}).get("error", 0) * 5
    score -= code_analysis.get("by_severity", {}).get("warning", 0) * 2
    score -= secret_analysis.get("total", 0) * 10
    score -= dependabot_analysis.get("total", 0) * 3
    score = max(0, score)

    score_color = "🟢" if score >= 80 else "🟡" if score >= 60 else "🔴"
    print(f"Security Score: {score_color} {score}/100")

    # Recommendations
    print("\n💡 Recommendations:")
    if code_analysis.get("by_severity", {}).get("error", 0) > 0:
        print(f"   1. Fix {code_analysis['by_severity']['error']} high-priority CodeQL errors")
    if secret_analysis.get("total", 0) > 0:
        print("   2. Address all exposed secrets immediately")
    if dependabot_analysis.get("total", 0) > 0:
        print(f"   3. Update {dependabot_analysis['total']} vulnerable dependencies")
    if total_issues == 0:
        print("   ✅ Security posture looks good! Keep monitoring.")

    print("\n🔗 View Details:")
    print(f"   GitHub Security Tab: https://github.com/{data['repository']}/security")
    print(f"   Code Scanning: https://github.com/{data['repository']}/security/code-scanning")


if __name__ == "__main__":
    generate_security_summary()
