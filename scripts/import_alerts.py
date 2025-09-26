#!/usr/bin/env python3
"""
Import Organization Alert System for DinoAir
==========================================

This system provides alerting capabilities for import organization issues,
circular dependencies, and performance regressions.

Features:
- Email notifications for critical issues
- Webhook integrations (Slack, Teams, Discord)
- GitHub issue creation for persistent problems
- Alert severity management
- Rate limiting and deduplication

Usage:
    python scripts/import_alerts.py [command] [options]

Commands:
    check       - Check current conditions and send alerts
    test        - Test alert configurations
    history     - Show alert history
    configure   - Configure alert settings
"""

import argparse
import json
import logging
import os
import smtplib
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import requests

from utils.config_loader import save_json_config

# Import the centralized config utility
sys.path.append(str(Path(__file__).parent.parent))


@dataclass
class Alert:
    """Represents an alert condition."""

    id: str
    severity: str  # critical, warning, info
    title: str
    message: str
    module: str | None
    metric_value: float | None
    threshold: float | None
    timestamp: datetime
    acknowledged: bool = False
    resolved: bool = False


@dataclass
class AlertConfig:
    """Alert system configuration."""

    email_enabled: bool = False
    email_smtp_host: str = ""
    email_smtp_port: int = 587
    email_username: str = ""
    # SECURITY: email_password must only come from environment variable SMTP_PASSWORD
    email_recipients: list[str] = None

    webhook_enabled: bool = False
    webhook_url: str = ""
    webhook_format: str = "slack"  # slack, teams, discord, generic

    github_enabled: bool = False
    # SECURITY: github_token must only come from environment variable GITHUB_TOKEN
    github_repo: str = ""

    rate_limit_minutes: int = 60
    deduplication_enabled: bool = True

    @property
    def email_password(self) -> str:
        """Get email password from environment variable only."""
        return os.getenv("SMTP_PASSWORD", "")

    @property
    def github_token(self) -> str:
        """Get GitHub token from environment variable only."""
        return os.getenv("GITHUB_TOKEN", "")


class AlertManager:
    """Manages alerts for import organization issues."""

    def __init__(self, config_path: Path | None = None):
        self.config_path = config_path or Path(".import_alerts_config.json")
        self.config = self._load_config()
        self.alerts_history: list[Alert] = []
        self.sent_alerts_cache: dict[str, datetime] = {}
        self.logger = self._setup_logging()

    def _setup_logging(self) -> logging.Logger:
        """Set up logging for alert system."""
        logger = logging.getLogger("import_alerts")
        logger.setLevel(logging.INFO)

        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
            handler.setFormatter(formatter)
            logger.addHandler(handler)

        return logger

    def _load_config(self) -> AlertConfig:
        """Load alert configuration."""
        if self.config_path.exists():
            try:
                with open(self.config_path, encoding="utf-8") as f:
                    config_data = json.load(f)
                return AlertConfig(**config_data)
            except Exception as e:
                self.logger.warning("Failed to load config: %s", e)

        # Return default configuration
        config = AlertConfig()
        config.email_recipients = []
        return config

    def save_config(self) -> None:
        """Save alert configuration."""
        success = save_json_config(asdict(self.config), self.config_path, indent=2)
        if not success:
            self.logger.error("Failed to save alert config using centralized utility")

    def should_send_alert(self, alert: Alert) -> bool:
        """Check if alert should be sent based on rate limiting and deduplication."""
        if not self.config.deduplication_enabled:
            return True

        # Create deduplication key
        dedup_key = f"{alert.severity}:{alert.title}:{alert.module}"

        if dedup_key in self.sent_alerts_cache:
            last_sent = self.sent_alerts_cache[dedup_key]
            if (datetime.now() - last_sent).total_seconds() < (self.config.rate_limit_minutes * 60):
                return False

        return True

    def mark_alert_sent(self, alert: Alert) -> None:
        """Mark alert as sent for rate limiting."""
        dedup_key = f"{alert.severity}:{alert.title}:{alert.module}"
        self.sent_alerts_cache[dedup_key] = datetime.now()

    def send_email_alert(self, alert: Alert) -> bool:
        """Send email notification for alert."""
        if not self.config.email_enabled or not self.config.email_recipients:
            return False

        try:
            # Get credentials from environment
            username = self.config.email_username or os.getenv("SMTP_USERNAME")
            password = self.config.email_password

            if not username or not password:
                self.logger.error("Email credentials not configured")
                return False

            # Create message
            msg = MIMEMultipart()
            msg["From"] = username
            msg["To"] = ", ".join(self.config.email_recipients)
            msg["Subject"] = f"🚨 DinoAir Import Alert - {alert.severity.upper()}: {alert.title}"

            # Email body
            body = f"""
DinoAir Import Organization Alert

Severity: {alert.severity.upper()}
Title: {alert.title}
Module: {alert.module or "N/A"}
Time: {alert.timestamp.isoformat()}

Description:
{alert.message}

{f"Metric Value: {alert.metric_value}" if alert.metric_value is not None else ""}
{f"Threshold: {alert.threshold}" if alert.threshold is not None else ""}

Please check the import organization system and resolve any issues.

---
DinoAir Import Organization Monitoring
            """.strip()

            msg.attach(MIMEText(body, "plain"))

            # Send email
            with smtplib.SMTP(self.config.email_smtp_host, self.config.email_smtp_port) as server:
                server.starttls()
                server.login(username, password)
                server.send_message(msg)

            self.logger.info("Email alert sent for: %s", alert.title)
            return True

        except Exception as e:
            self.logger.error("Failed to send email alert: %s", e)
            return False

    def send_webhook_alert(self, alert: Alert) -> bool:
        """Send webhook notification for alert."""
        if not self.config.webhook_enabled or not self.config.webhook_url:
            return False

        try:
            # Format message based on webhook type
            if self.config.webhook_format == "slack":
                payload = {
                    "text": "🚨 DinoAir Import Alert",
                    "attachments": [
                        {
                            "color": "danger" if alert.severity == "critical" else "warning",
                            "title": f"{alert.severity.upper()}: {alert.title}",
                            "text": alert.message,
                            "fields": [
                                {
                                    "title": "Module",
                                    "value": alert.module or "N/A",
                                    "short": True,
                                },
                                {
                                    "title": "Time",
                                    "value": alert.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                                    "short": True,
                                },
                            ]
                            + (
                                [
                                    {
                                        "title": "Metric",
                                        "value": f"{alert.metric_value}",
                                        "short": True,
                                    },
                                    {
                                        "title": "Threshold",
                                        "value": f"{alert.threshold}",
                                        "short": True,
                                    },
                                ]
                                if alert.metric_value is not None
                                else []
                            ),
                        }
                    ],
                }
            elif self.config.webhook_format == "teams":
                color = "FF0000" if alert.severity == "critical" else "FFA500"
                payload = {
                    "@type": "MessageCard",
                    "@context": "http://schema.org/extensions",
                    "themeColor": color,
                    "summary": f"DinoAir Import Alert: {alert.title}",
                    "sections": [
                        {
                            "activityTitle": f"🚨 {alert.severity.upper()}: {alert.title}",
                            "activitySubtitle": f"Module: {alert.module or 'N/A'}",
                            "text": alert.message,
                            "facts": [
                                {
                                    "name": "Time",
                                    "value": alert.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                                }
                            ]
                            + (
                                [
                                    {
                                        "name": "Metric Value",
                                        "value": str(alert.metric_value),
                                    },
                                    {
                                        "name": "Threshold",
                                        "value": str(alert.threshold),
                                    },
                                ]
                                if alert.metric_value is not None
                                else []
                            ),
                        }
                    ],
                }
            else:
                # Generic webhook format
                payload = {
                    "alert": asdict(alert),
                    "timestamp": alert.timestamp.isoformat(),
                    "source": "DinoAir Import Organization",
                }

            # Send webhook
            response = requests.post(
                self.config.webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            response.raise_for_status()

            self.logger.info("Webhook alert sent for: %s", alert.title)
            return True

        except Exception as e:
            self.logger.error("Failed to send webhook alert: %s", e)
            return False

    def create_github_issue(self, alert: Alert) -> bool:
        """Create GitHub issue for critical alerts."""
        if not self.config.github_enabled or alert.severity != "critical":
            return False

        try:
            token = self.config.github_token
            if not token or not self.config.github_repo:
                self.logger.error("GitHub integration not properly configured")
                return False

            # Check if similar issue already exists
            search_url = "https://api.github.com/search/issues"
            search_params = {
                "q": f'repo:{self.config.github_repo} is:issue is:open "Import Alert" "{alert.title}"'
            }

            response = requests.get(
                search_url,
                params=search_params,
                headers={"Authorization": f"token {token}"},
                timeout=10,
            )

            if response.ok and response.json().get("total_count", 0) > 0:
                self.logger.info("Similar GitHub issue already exists")
                return True

            # Create new issue
            issue_url = f"https://api.github.com/repos/{self.config.github_repo}/issues"
            issue_data = {
                "title": f"🚨 Import Alert: {alert.title}",
                "body": f"""
**Alert Details**

- **Severity**: {alert.severity.upper()}
- **Module**: {alert.module or "N/A"}
- **Time**: {alert.timestamp.isoformat()}
- **Metric Value**: {alert.metric_value if alert.metric_value is not None else "N/A"}
- **Threshold**: {alert.threshold if alert.threshold is not None else "N/A"}

**Description**

{alert.message}

**Automated Actions**

This issue was created automatically by the DinoAir import organization monitoring system.

Please investigate and resolve the underlying import organization issues.

**Labels**: `automation`, `import-organization`, `{alert.severity}`
                """.strip(),
                "labels": ["automation", "import-organization", alert.severity],
            }

            response = requests.post(
                issue_url,
                json=issue_data,
                headers={"Authorization": f"token {token}"},
                timeout=10,
            )
            response.raise_for_status()

            issue_number = response.json().get("number")
            self.logger.info("GitHub issue #%s created for: %s", issue_number, alert.title)
            return True

        except Exception as e:
            self.logger.error("Failed to create GitHub issue: %s", e)
            return False

    def send_alert(self, alert: Alert) -> dict[str, bool]:
        """Send alert through all configured channels."""
        if not self.should_send_alert(alert):
            self.logger.info("Alert rate-limited: %s", alert.title)
            return {}

        results = {}

        # Send email notification
        if self.config.email_enabled:
            results["email"] = self.send_email_alert(alert)

        # Send webhook notification
        if self.config.webhook_enabled:
            results["webhook"] = self.send_webhook_alert(alert)

        # Create GitHub issue for critical alerts
        if self.config.github_enabled and alert.severity == "critical":
            results["github"] = self.create_github_issue(alert)

        # Mark alert as sent and store in history
        self.mark_alert_sent(alert)
        self.alerts_history.append(alert)

        return results

    def check_import_conditions(self) -> list[Alert]:
        """Check current import organization conditions and generate alerts."""
        alerts = []

        try:
            # Run circular dependency check
            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/check_circular_dependencies.py",
                    "--format",
                    "json",
                ],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )

            if result.returncode != 0:
                data = json.loads(result.stdout) if result.stdout else {}

                if data.get("circular_dependencies"):
                    for dep in data["circular_dependencies"]:
                        alert = Alert(
                            id=f"circular_dep_{hash(str(dep['cycle']))}",
                            severity="critical",
                            title="Circular Dependency Detected",
                            message=f"Circular dependency found: {' -> '.join(dep['cycle'])}",
                            module=dep["cycle"][0] if dep["cycle"] else None,
                            metric_value=len(dep["cycle"]),
                            threshold=0,
                            timestamp=datetime.now(),
                        )
                        alerts.append(alert)

            # Run dependency monitoring if available
            try:
                result = subprocess.run(
                    [
                        sys.executable,
                        "scripts/dependency_monitor.py",
                        "analyze",
                        "--format",
                        "json",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=False,
                )

                if result.returncode == 0:
                    data = json.loads(result.stdout)

                    # Check for low health scores
                    for module_name, module_data in data.get("modules", {}).items():
                        health_score = module_data.get("health_score", 1.0)

                        if health_score < 0.5:
                            alert = Alert(
                                id=f"health_score_{module_name}",
                                severity="critical",
                                title="Low Module Health Score",
                                message=f"Module {module_name} has critically low health score",
                                module=module_name,
                                metric_value=health_score,
                                threshold=0.8,
                                timestamp=datetime.now(),
                            )
                            alerts.append(alert)
                        elif health_score < 0.8:
                            alert = Alert(
                                id=f"health_score_{module_name}",
                                severity="warning",
                                title="Module Health Warning",
                                message=f"Module {module_name} health score below recommended threshold",
                                module=module_name,
                                metric_value=health_score,
                                threshold=0.8,
                                timestamp=datetime.now(),
                            )
                            alerts.append(alert)

            except Exception:
                pass  # Dependency monitor not available

        except Exception as e:
            self.logger.error("Failed to check import conditions: %s", e)

        return alerts


def main():
    """Main entry point for alert system."""
    parser = argparse.ArgumentParser(
        description="Import organization alert system",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "command",
        choices=["check", "test", "history", "configure"],
        help="Alert command to execute",
    )
    parser.add_argument("--config", type=Path, help="Path to alert configuration file")
    parser.add_argument(
        "--severity",
        choices=["critical", "warning", "info"],
        default="warning",
        help="Minimum severity level for alerts",
    )

    args = parser.parse_args()

    alert_manager = AlertManager(args.config)

    if args.command == "check":
        print("🔍 Checking import organization conditions...")
        alerts = alert_manager.check_import_conditions()

        # Filter by severity
        severity_order = {"info": 0, "warning": 1, "critical": 2}
        min_severity = severity_order.get(args.severity, 1)
        filtered_alerts = [a for a in alerts if severity_order.get(a.severity, 0) >= min_severity]

        if not filtered_alerts:
            print("✅ No alerts to send")
            return

        print(f"📢 Sending {len(filtered_alerts)} alert(s)...")
        for alert in filtered_alerts:
            results = alert_manager.send_alert(alert)
            print(f"  {alert.severity.upper()}: {alert.title}")
            for channel, success in results.items():
                status = "✅" if success else "❌"
                print(f"    {channel}: {status}")

    elif args.command == "test":
        print("🧪 Testing alert configuration...")

        test_alert = Alert(
            id="test_alert",
            severity="warning",
            title="Test Alert",
            message="This is a test alert to verify the alert system configuration",
            module="test_module",
            metric_value=0.5,
            threshold=0.8,
            timestamp=datetime.now(),
        )

        results = alert_manager.send_alert(test_alert)
        print("Test Results:")
        for channel, success in results.items():
            status = "✅ Success" if success else "❌ Failed"
            print(f"  {channel.capitalize()}: {status}")

    elif args.command == "history":
        print("📊 Alert History:")
        if not alert_manager.alerts_history:
            print("  No alerts in history")
        else:
            for alert in alert_manager.alerts_history[-10:]:  # Show last 10
                print(
                    f"  {alert.timestamp.strftime('%Y-%m-%d %H:%M:%S')} | "
                    f"{alert.severity.upper():<8} | {alert.title}"
                )

    elif args.command == "configure":
        print("⚙️ Alert Configuration:")
        print("Current settings:")
        print(f"  Email enabled: {alert_manager.config.email_enabled}")
        print(f"  Webhook enabled: {alert_manager.config.webhook_enabled}")
        print(f"  GitHub enabled: {alert_manager.config.github_enabled}")
        print(f"  Rate limit: {alert_manager.config.rate_limit_minutes} minutes")

        print("\nTo configure alerts, edit the configuration file:")
        print(f"  {alert_manager.config_path}")
        print("\nExample configuration:")
        example_config = {
            "email_enabled": True,
            "email_smtp_host": "smtp.gmail.com",
            "email_smtp_port": 587,
            "email_username": "alerts@yourcompany.com",
            "email_recipients": ["team@yourcompany.com"],
            "webhook_enabled": True,
            "webhook_url": "https://hooks.slack.com/services/...",
            "webhook_format": "slack",
            "github_enabled": True,
            "github_repo": "yourorg/dinoair",
            "rate_limit_minutes": 60,
        }
        print(json.dumps(example_config, indent=2))


if __name__ == "__main__":
    main()
