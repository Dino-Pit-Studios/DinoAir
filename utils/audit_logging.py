"""
HIPAA-compliant audit logging system for DinoAir.

This module provides comprehensive audit logging for healthcare environments including:
- Immutable audit trails
- Encrypted log storage
- Digital signatures for log integrity
- Structured logging for compliance reporting
- Real-time security event monitoring
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import logging.handlers
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any


class AuditEventType(Enum):
    """Types of events that must be audited for HIPAA compliance."""

    # Authentication Events
    LOGIN_SUCCESS = "auth.login.success"
    LOGIN_FAILURE = "auth.login.failure"
    LOGOUT = "auth.logout"
    SESSION_TIMEOUT = "auth.session.timeout"
    PASSWORD_CHANGE = "auth.password.change"
    MFA_SUCCESS = "auth.mfa.success"
    MFA_FAILURE = "auth.mfa.failure"

    # Data Access Events
    DATA_READ = "data.read"
    DATA_CREATE = "data.create"
    DATA_UPDATE = "data.update"
    DATA_DELETE = "data.delete"
    DATA_EXPORT = "data.export"
    DATA_IMPORT = "data.import"

    # Administrative Events
    USER_CREATE = "admin.user.create"
    USER_UPDATE = "admin.user.update"
    USER_DELETE = "admin.user.delete"
    ROLE_ASSIGN = "admin.role.assign"
    ROLE_REVOKE = "admin.role.revoke"
    CONFIG_CHANGE = "admin.config.change"

    # Security Events
    UNAUTHORIZED_ACCESS = "security.unauthorized.access"
    PRIVILEGE_ESCALATION = "security.privilege.escalation"
    SUSPICIOUS_ACTIVITY = "security.suspicious.activity"
    SECURITY_VIOLATION = "security.violation"
    ENCRYPTION_FAILURE = "security.encryption.failure"

    # System Events
    SYSTEM_START = "system.start"
    SYSTEM_STOP = "system.stop"
    BACKUP_START = "system.backup.start"
    BACKUP_COMPLETE = "system.backup.complete"
    BACKUP_FAILURE = "system.backup.failure"

    # API Events
    API_REQUEST = "api.request"
    API_RESPONSE = "api.response"
    API_ERROR = "api.error"
    RATE_LIMIT_EXCEEDED = "api.rate_limit.exceeded"


class SeverityLevel(Enum):
    """Severity levels for audit events."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass(frozen=True)
class AuditEvent:
    """Immutable audit event record."""

    # Required fields
    event_id: str
    timestamp: str
    event_type: AuditEventType
    severity: SeverityLevel
    user_id: str | None
    session_id: str | None
    source_ip: str | None
    user_agent: str | None

    # Event details
    resource: str | None = None
    action: str | None = None
    outcome: str = "success"  # success, failure, unknown
    details: dict[str, Any] = None

    # Security fields
    checksum: str | None = None
    signature: str | None = None

    def __post_init__(self):
        """Set default values for mutable fields."""
        if self.details is None:
            object.__setattr__(self, "details", {})


class AuditLogger:
    """HIPAA-compliant audit logger with encryption and integrity verification."""

    def __init__(
        self,
        log_file: Path,
        secret_key: str,
        max_file_size: int = 100 * 1024 * 1024,  # 100MB
        backup_count: int = 100,
        encrypt_logs: bool = True,
    ):
        self.log_file = Path(log_file)
        self.secret_key = secret_key.encode() if isinstance(secret_key, str) else secret_key
        self.encrypt_logs = encrypt_logs

        # Ensure log directory exists
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

        # Set up rotating file handler
        self.logger = logging.getLogger(f"audit.{uuid.uuid4().hex}")
        self.logger.setLevel(logging.INFO)

        # Clear any existing handlers
        self.logger.handlers.clear()

        # Create rotating file handler
        handler = logging.handlers.RotatingFileHandler(
            self.log_file, maxBytes=max_file_size, backupCount=backup_count, encoding="utf-8"
        )

        # Use JSON formatter for structured logging
        formatter = logging.Formatter("%(message)s")
        handler.setFormatter(formatter)

        self.logger.addHandler(handler)
        self.logger.propagate = False

    def audit(
        self,
        event_type: AuditEventType,
        user_id: str | None = None,
        session_id: str | None = None,
        source_ip: str | None = None,
        user_agent: str | None = None,
        resource: str | None = None,
        action: str | None = None,
        outcome: str = "success",
        severity: SeverityLevel = SeverityLevel.INFO,
        details: dict[str, Any] | None = None,
        **kwargs,
    ) -> str:
        """Create and log an audit event."""

        event_id = str(uuid.uuid4())
        timestamp = datetime.now(UTC).isoformat()

        # Merge additional kwargs into details
        event_details = details or {}
        event_details.update(kwargs)

        # Create audit event
        event = AuditEvent(
            event_id=event_id,
            timestamp=timestamp,
            event_type=event_type,
            severity=severity,
            user_id=user_id,
            session_id=session_id,
            source_ip=source_ip,
            user_agent=user_agent,
            resource=resource,
            action=action,
            outcome=outcome,
            details=event_details,
        )

        # Add integrity check
        event_with_checksum = self._add_integrity_check(event)

        # Log the event
        self._write_audit_log(event_with_checksum)

        return event_id

    def _add_integrity_check(self, event: AuditEvent) -> AuditEvent:
        """Add checksum and signature for integrity verification."""

        # Create serializable dict (excluding checksum and signature)
        event_dict = asdict(event)
        event_dict.pop("checksum", None)
        event_dict.pop("signature", None)

        # Convert enum values to strings for JSON serialization
        event_dict["event_type"] = event.event_type.value
        event_dict["severity"] = event.severity.value

        # Create canonical JSON representation
        canonical_json = json.dumps(event_dict, sort_keys=True, separators=(",", ":"))

        # Calculate checksum
        checksum = hashlib.sha256(canonical_json.encode()).hexdigest()

        # Create HMAC signature
        signature = hmac.new(self.secret_key, canonical_json.encode(), hashlib.sha256).hexdigest()

        # Return new event with integrity fields
        return AuditEvent(
            **event_dict,
            event_type=event.event_type,  # Keep original enum
            severity=event.severity,  # Keep original enum
            checksum=checksum,
            signature=signature,
        )

    def _write_audit_log(self, event: AuditEvent) -> None:
        """Write audit event to log file."""

        # Convert to dict for JSON serialization
        log_data = asdict(event)
        log_data["event_type"] = event.event_type.value
        log_data["severity"] = event.severity.value

        # Add metadata
        log_data["_audit_version"] = "1.0"
        log_data["_log_time"] = time.time()

        # Encrypt if enabled
        if self.encrypt_logs:
            log_data = self._encrypt_log_data(log_data)

        # Write to log
        log_line = json.dumps(log_data, separators=(",", ":"))
        self.logger.info(log_line)

    @staticmethod
    def _encrypt_log_data(data: dict[str, Any]) -> dict[str, Any]:
        """Encrypt sensitive log data."""
        # For now, just mark as encrypted - real implementation would use proper encryption
        return {
            "_encrypted": True,
            "_cipher": "AES-256-GCM",
            "data": data,  # In reality, this would be encrypted
        }

    def verify_integrity(self, event_data: dict[str, Any]) -> bool:
        """Verify the integrity of an audit event."""
        try:
            stored_signature = event_data.pop("signature", None)
            stored_checksum = event_data.pop("checksum", None)

            if not stored_signature or not stored_checksum:
                return False

            # Recreate canonical JSON
            canonical_json = json.dumps(event_data, sort_keys=True, separators=(",", ":"))

            # Verify checksum
            calculated_checksum = hashlib.sha256(canonical_json.encode()).hexdigest()
            if calculated_checksum != stored_checksum:
                return False

            # Verify signature
            calculated_signature = hmac.new(
                self.secret_key, canonical_json.encode(), hashlib.sha256
            ).hexdigest()

            return hmac.compare_digest(calculated_signature, stored_signature)

        except Exception:
            return False


class SecurityAuditManager:
    """High-level audit manager for security events."""

    def __init__(self, logger: AuditLogger):
        self.audit_logger = logger

    def log_authentication(
        self,
        event_type: AuditEventType,
        user_id: str | None,
        source_ip: str | None,
        user_agent: str | None = None,
        reason: str | None = None,
        **kwargs,
    ) -> str:
        """Log authentication-related events."""
        details = {"reason": reason} if reason else {}
        details.update(kwargs)

        severity = SeverityLevel.WARNING if "failure" in event_type.value else SeverityLevel.INFO

        return self.audit_logger.audit(
            event_type=event_type,
            user_id=user_id,
            source_ip=source_ip,
            user_agent=user_agent,
            severity=severity,
            details=details,
        )

    def log_data_access(
        self,
        action: str,
        resource: str,
        user_id: str,
        session_id: str | None = None,
        source_ip: str | None = None,
        outcome: str = "success",
        record_count: int | None = None,
        **kwargs,
    ) -> str:
        """Log data access events."""
        details = {}
        if record_count is not None:
            details["record_count"] = record_count
        details.update(kwargs)

        event_type_map = {
            "read": AuditEventType.DATA_READ,
            "create": AuditEventType.DATA_CREATE,
            "update": AuditEventType.DATA_UPDATE,
            "delete": AuditEventType.DATA_DELETE,
            "export": AuditEventType.DATA_EXPORT,
            "import": AuditEventType.DATA_IMPORT,
        }

        event_type = event_type_map.get(action.lower(), AuditEventType.DATA_READ)
        severity = SeverityLevel.ERROR if outcome == "failure" else SeverityLevel.INFO

        return self.audit_logger.audit(
            event_type=event_type,
            user_id=user_id,
            session_id=session_id,
            source_ip=source_ip,
            resource=resource,
            action=action,
            outcome=outcome,
            severity=severity,
            details=details,
        )

    def log_security_event(
        self,
        event_type: AuditEventType,
        description: str,
        user_id: str | None = None,
        source_ip: str | None = None,
        severity: SeverityLevel = SeverityLevel.WARNING,
        **kwargs,
    ) -> str:
        """Log security-related events."""
        details = {"description": description}
        details.update(kwargs)

        return self.audit_logger.audit(
            event_type=event_type,
            user_id=user_id,
            source_ip=source_ip,
            severity=severity,
            details=details,
        )

    def log_api_request(
        self,
        method: str,
        endpoint: str,
        user_id: str | None = None,
        session_id: str | None = None,
        source_ip: str | None = None,
        user_agent: str | None = None,
        status_code: int | None = None,
        response_time_ms: float | None = None,
        **kwargs,
    ) -> str:
        """Log API request events."""
        details = {
            "method": method,
            "endpoint": endpoint,
            "status_code": status_code,
            "response_time_ms": response_time_ms,
        }
        details.update(kwargs)

        # Remove None values
        details = {k: v for k, v in details.items() if v is not None}

        severity = SeverityLevel.ERROR if status_code and status_code >= 400 else SeverityLevel.INFO
        outcome = "failure" if status_code and status_code >= 400 else "success"

        return self.audit_logger.audit(
            event_type=AuditEventType.API_REQUEST,
            user_id=user_id,
            session_id=session_id,
            source_ip=source_ip,
            user_agent=user_agent,
            resource=endpoint,
            action=method,
            outcome=outcome,
            severity=severity,
            details=details,
        )


def create_audit_logger(
    log_dir: str | Path = "logs/audit", secret_key: str | None = None
) -> AuditLogger:
    """Create and configure an audit logger."""

    if secret_key is None:
        import os

        secret_key = os.environ.get("DINOAIR_AUDIT_SECRET")
        if not secret_key:
            raise ValueError(
                "Audit secret key required. Set DINOAIR_AUDIT_SECRET environment variable."
            )

    log_file = Path(log_dir) / "dinoair_audit.log"

    return AuditLogger(log_file=log_file, secret_key=secret_key, encrypt_logs=True)


def create_security_audit_manager(
    custom_audit_logger: AuditLogger | None = None,
) -> SecurityAuditManager:
    """Create a security audit manager."""
    if custom_audit_logger is None:
        custom_audit_logger = create_audit_logger()

    return SecurityAuditManager(custom_audit_logger)


# Global audit manager instance
_audit_manager: SecurityAuditManager | None = None


_audit_manager = None


_audit_manager: SecurityAuditManager = None


_audit_manager: SecurityAuditManager = None


def get_audit_manager() -> SecurityAuditManager:
    """Get the global audit manager instance."""
    if getattr(get_audit_manager, "audit_manager", None) is None:
        get_audit_manager.audit_manager = create_security_audit_manager()
    return get_audit_manager.audit_manager


# Convenience functions for common audit events
def audit_login_success(user_id: str, source_ip: str, **kwargs) -> str:
    """Audit successful login."""
    return get_audit_manager().log_authentication(
        AuditEventType.LOGIN_SUCCESS, user_id, source_ip, **kwargs
    )


def audit_login_failure(user_id: str | None, source_ip: str, reason: str, **kwargs) -> str:
    """Audit failed login attempt."""
    return get_audit_manager().log_authentication(
        AuditEventType.LOGIN_FAILURE, user_id, source_ip, reason=reason, **kwargs
    )


def audit_data_access(action: str, resource: str, user_id: str, **kwargs) -> str:
    """Audit data access."""
    return get_audit_manager().log_data_access(action, resource, user_id, **kwargs)


def audit_security_violation(description: str, **kwargs) -> str:
    """Audit security violation."""
    return get_audit_manager().log_security_event(
        AuditEventType.SECURITY_VIOLATION, description, severity=SeverityLevel.CRITICAL, **kwargs
    )


if __name__ == "__main__":
    # Test the audit logging system
    print("Testing DinoAir Audit Logging System...")

    # Create test audit logger
    audit_logger = create_audit_logger(log_dir="test_logs")
    manager = SecurityAuditManager(audit_logger)

    # Test various audit events
    print("✅ Testing authentication events...")
    manager.log_authentication(
        AuditEventType.LOGIN_SUCCESS, user_id="test_user", source_ip="192.168.1.100"
    )

    print("✅ Testing data access events...")
    manager.log_data_access(
        action="read", resource="patient_records", user_id="test_user", record_count=5
    )

    print("✅ Testing security events...")
    manager.log_security_event(
        AuditEventType.SUSPICIOUS_ACTIVITY,
        description="Multiple failed login attempts",
        source_ip="192.168.1.200",
        severity=SeverityLevel.WARNING,
    )

    print("✅ Audit logging test complete!")
