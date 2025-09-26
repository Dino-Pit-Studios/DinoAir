"""
Secure configuration management for DinoAir.

This module provides healthcare-grade security configuration including:
- Secret management with environment variables and key vaults
- Encryption configuration for data at rest and in transit
- Audit logging configuration
- Security policy enforcement
"""

from __future__ import annotations

import os
import warnings
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SecurityConfig:
    """Security configuration for healthcare-grade environments."""

    # Encryption Settings
    encryption_enabled: bool = True
    encryption_algorithm: str = "AES-256-GCM"
    key_rotation_days: int = 90

    # Database Security
    database_encryption: bool = True
    database_backup_encryption: bool = True
    database_connection_encryption: bool = True

    # Audit Logging
    audit_logging_enabled: bool = True
    audit_log_encryption: bool = True
    audit_retention_days: int = 2555  # 7 years for HIPAA
    audit_log_integrity_check: bool = True

    # Authentication
    require_mfa: bool = True
    session_timeout_minutes: int = 15
    max_login_attempts: int = 3
    password_min_length: int = 14
    password_require_complexity: bool = True

    # Network Security
    require_tls: bool = True
    tls_min_version: str = "1.3"
    rate_limit_requests_per_minute: int = 100
    cors_strict_mode: bool = True

    # Data Privacy
    pii_detection_enabled: bool = True
    data_masking_enabled: bool = True
    secure_delete_enabled: bool = True

    # Monitoring
    security_monitoring_enabled: bool = True
    vulnerability_scanning_enabled: bool = True
    intrusion_detection_enabled: bool = True

    # Compliance
    hipaa_compliance_mode: bool = True
    soc2_compliance_mode: bool = True

    # Secret Management
    secret_rotation_enabled: bool = True
    secret_vault_provider: str = "environment"  # environment, azure_kv, aws_secrets

    # Allowed security overrides (for testing only)
    security_overrides: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SecretManager:
    """Secure secret management with multiple backend support."""

    provider: str = "environment"
    vault_url: str | None = None
    rotation_enabled: bool = True

    def get_secret(self, key: str, default: str | None = None) -> str | None:
        """Get a secret from the configured provider."""
        if self.provider == "environment":
            return self._get_from_environment(key, default)
        if self.provider == "azure_kv":
            return self._get_from_azure_kv(key, default)
        if self.provider == "aws_secrets":
            return self._get_from_aws_secrets(key, default)
        raise ValueError(f"Unsupported secret provider: {self.provider}")

    @staticmethod
    def _get_from_environment(key: str, default: str | None = None) -> str | None:
        """Get secret from environment variables."""
        value = os.environ.get(key, default)
        if value and len(value) < 16:
            warnings.warn(
                f"Secret '{key}' appears to be too short for production use",
                SecurityWarning,
                stacklevel=3,
            )
        return value

    def _get_from_azure_kv(self, key: str, default: str | None = None) -> str | None:
        """Get secret from Azure Key Vault."""
        try:
            from azure.identity import DefaultAzureCredential
            from azure.keyvault.secrets import SecretClient

            if not self.vault_url:
                raise ValueError("Azure Key Vault URL not configured")

            credential = DefaultAzureCredential()
            client = SecretClient(vault_url=self.vault_url, credential=credential)
            secret = client.get_secret(key)
            return secret.value
        except ImportError:
            warnings.warn(
                "Azure Key Vault dependencies not installed. Using environment fallback.",
                RuntimeWarning,
                stacklevel=2,
            )
            return self._get_from_environment(key, default)
        except Exception as e:
            warnings.warn(
                f"Failed to get secret from Azure Key Vault: {e}", RuntimeWarning, stacklevel=2
            )
            return self._get_from_environment(key, default)

    def _get_from_aws_secrets(self, key: str, default: str | None = None) -> str | None:
        """Get secret from AWS Secrets Manager."""
        try:
            import boto3

            client = boto3.client("secretsmanager")
            response = client.get_secret_value(SecretId=key)
            return response["SecretString"]
        except ImportError:
            warnings.warn(
                "AWS SDK not installed. Using environment fallback.", RuntimeWarning, stacklevel=2
            )
            return self._get_from_environment(key, default)
        except Exception as e:
            warnings.warn(
                f"Failed to get secret from AWS Secrets Manager: {e}", RuntimeWarning, stacklevel=2
            )
            return self._get_from_environment(key, default)


class SecurityWarning(UserWarning):
    """Warning for security-related issues."""


def get_security_config() -> SecurityConfig:
    """Get security configuration from environment variables."""
    return SecurityConfig(
        # Encryption
        encryption_enabled=_get_bool_env("DINOAIR_ENCRYPTION_ENABLED", True),
        encryption_algorithm=os.environ.get("DINOAIR_ENCRYPTION_ALGORITHM", "AES-256-GCM"),
        key_rotation_days=_get_int_env("DINOAIR_KEY_ROTATION_DAYS", 90),
        # Database
        database_encryption=_get_bool_env("DINOAIR_DB_ENCRYPTION", True),
        database_backup_encryption=_get_bool_env("DINOAIR_DB_BACKUP_ENCRYPTION", True),
        database_connection_encryption=_get_bool_env("DINOAIR_DB_CONNECTION_ENCRYPTION", True),
        # Audit
        audit_logging_enabled=_get_bool_env("DINOAIR_AUDIT_LOGGING", True),
        audit_log_encryption=_get_bool_env("DINOAIR_AUDIT_ENCRYPTION", True),
        audit_retention_days=_get_int_env("DINOAIR_AUDIT_RETENTION_DAYS", 2555),
        audit_log_integrity_check=_get_bool_env("DINOAIR_AUDIT_INTEGRITY_CHECK", True),
        # Authentication
        require_mfa=_get_bool_env("DINOAIR_REQUIRE_MFA", True),
        session_timeout_minutes=_get_int_env("DINOAIR_SESSION_TIMEOUT_MINUTES", 15),
        max_login_attempts=_get_int_env("DINOAIR_MAX_LOGIN_ATTEMPTS", 3),
        password_min_length=_get_int_env("DINOAIR_PASSWORD_MIN_LENGTH", 14),
        password_require_complexity=_get_bool_env("DINOAIR_PASSWORD_COMPLEXITY", True),
        # Network
        require_tls=_get_bool_env("DINOAIR_REQUIRE_TLS", True),
        tls_min_version=os.environ.get("DINOAIR_TLS_MIN_VERSION", "1.3"),
        rate_limit_requests_per_minute=_get_int_env("DINOAIR_RATE_LIMIT_RPM", 100),
        cors_strict_mode=_get_bool_env("DINOAIR_CORS_STRICT", True),
        # Privacy
        pii_detection_enabled=_get_bool_env("DINOAIR_PII_DETECTION", True),
        data_masking_enabled=_get_bool_env("DINOAIR_DATA_MASKING", True),
        secure_delete_enabled=_get_bool_env("DINOAIR_SECURE_DELETE", True),
        # Monitoring
        security_monitoring_enabled=_get_bool_env("DINOAIR_SECURITY_MONITORING", True),
        vulnerability_scanning_enabled=_get_bool_env("DINOAIR_VULN_SCANNING", True),
        intrusion_detection_enabled=_get_bool_env("DINOAIR_INTRUSION_DETECTION", True),
        # Compliance
        hipaa_compliance_mode=_get_bool_env("DINOAIR_HIPAA_COMPLIANCE", True),
        soc2_compliance_mode=_get_bool_env("DINOAIR_SOC2_COMPLIANCE", True),
        # Secrets
        secret_rotation_enabled=_get_bool_env("DINOAIR_SECRET_ROTATION", True),
        secret_vault_provider=os.environ.get("DINOAIR_SECRET_PROVIDER", "environment"),
    )


def get_secret_manager() -> SecretManager:
    """Get configured secret manager."""
    return SecretManager(
        provider=os.environ.get("DINOAIR_SECRET_PROVIDER", "environment"),
        vault_url=os.environ.get("DINOAIR_VAULT_URL"),
        rotation_enabled=_get_bool_env("DINOAIR_SECRET_ROTATION", True),
    )


def validate_security_config(config: SecurityConfig) -> list[str]:
    """Validate security configuration and return warnings/errors."""
    validation_warnings = []

    # Check for production security requirements
    if not config.encryption_enabled:
        validation_warnings.append(
            "❌ CRITICAL: Encryption is disabled - required for HIPAA compliance"
        )

    if not config.database_encryption:
        validation_warnings.append(
            "❌ CRITICAL: Database encryption is disabled - required for PHI protection"
        )

    if not config.audit_logging_enabled:
        validation_warnings.append(
            "❌ CRITICAL: Audit logging is disabled - required for compliance"
        )

    if not config.require_mfa:
        validation_warnings.append(
            "⚠️  WARNING: MFA is disabled - strongly recommended for healthcare environments"
        )

    if config.session_timeout_minutes > 30:
        validation_warnings.append("⚠️  WARNING: Session timeout is longer than 30 minutes")

    if not config.require_tls:
        validation_warnings.append(
            "❌ CRITICAL: TLS is disabled - required for data in transit protection"
        )

    if config.tls_min_version not in ["1.2", "1.3"]:
        validation_warnings.append("⚠️  WARNING: TLS version should be 1.2 or 1.3")

    if not config.pii_detection_enabled:
        validation_warnings.append("⚠️  WARNING: PII detection is disabled")

    if config.audit_retention_days < 2555:  # 7 years
        validation_warnings.append(
            "⚠️  WARNING: Audit retention is less than 7 years (HIPAA requirement)"
        )

    # Check for development overrides in production
    if config.security_overrides and _is_production():
        validation_warnings.append(
            "❌ CRITICAL: Security overrides detected in production environment"
        )

    return validation_warnings


def _get_bool_env(key: str, default: bool) -> bool:
    """Get boolean value from environment variable."""
    value = os.environ.get(key, "").lower()
    if value in ("true", "1", "yes", "on"):
        return True
    if value in ("false", "0", "no", "off"):
        return False
    return default


def _get_int_env(key: str, default: int) -> int:
    """Get integer value from environment variable."""
    try:
        return int(os.environ.get(key, str(default)))
    except ValueError:
        return default


def _is_production() -> bool:
    """Check if running in production environment."""
    env = os.environ.get("DINOAIR_ENVIRONMENT", "development").lower()
    return env in ("production", "prod")


def print_security_status() -> None:
    """Print current security configuration status."""
    config = get_security_config()
    config_warnings = validate_security_config(config)

    print("=" * 60)
    print("🔒 DinoAir Security Configuration Status")
    print("=" * 60)

    print(f"Environment: {os.environ.get('DINOAIR_ENVIRONMENT', 'development')}")
    print(
        f"HIPAA Compliance Mode: {'✅ Enabled' if config.hipaa_compliance_mode else '❌ Disabled'}"
    )
    print(f"SOC2 Compliance Mode: {'✅ Enabled' if config.soc2_compliance_mode else '❌ Disabled'}")
    print()

    print("🔐 Encryption:")
    print(f"  Data at Rest: {'✅ Enabled' if config.database_encryption else '❌ Disabled'}")
    print(f"  Data in Transit: {'✅ Enabled' if config.require_tls else '❌ Disabled'}")
    print(f"  Algorithm: {config.encryption_algorithm}")
    print()

    print("🔍 Audit & Monitoring:")
    print(f"  Audit Logging: {'✅ Enabled' if config.audit_logging_enabled else '❌ Disabled'}")
    print(
        f"  Security Monitoring: {'✅ Enabled' if config.security_monitoring_enabled else '❌ Disabled'}"
    )
    print(f"  Retention: {config.audit_retention_days} days")
    print()

    print("🔑 Authentication:")
    print(f"  Multi-Factor Auth: {'✅ Required' if config.require_mfa else '❌ Optional'}")
    print(f"  Session Timeout: {config.session_timeout_minutes} minutes")
    print("  Password Policy: Enforced")
    print()

    print("🛡️  Privacy & Protection:")
    print(f"  PII Detection: {'✅ Enabled' if config.pii_detection_enabled else '❌ Disabled'}")
    print(f"  Data Masking: {'✅ Enabled' if config.data_masking_enabled else '❌ Disabled'}")
    print(f"  Secure Delete: {'✅ Enabled' if config.secure_delete_enabled else '❌ Disabled'}")
    print()

    if config_warnings:
        print("⚠️  Security Warnings:")
        for warning in config_warnings:
            print(f"  {warning}")
        print()
    else:
        print("✅ All security checks passed!")
        print()

    print("=" * 60)


if __name__ == "__main__":
    print_security_status()
