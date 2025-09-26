"""Input sanitization pipeline for processing user input before sending to LLM.

This module provides a pipeline that validates, escapes, normalizes, filters,
and classifies user input to ensure clean and safe interaction with the
LLM model.
"""

from datetime import datetime
from typing import Any, Protocol

# Import command handlers
from .command_handlers import WatchdogCommandHandler
from .exceptions import InputPipelineError

# Import all modular components from stages
from .stages import (  # Enhanced security; Validation; Intent classification; Pattern normalization; Profanity filtering; Rate limiting; Escaping
    EnhancedInputSanitizer,
    InputValidator,
    IntentClassifier,
    IntentType,
    PatternNormalizer,
    ProfanityFilter,
    RateLimitConfig,
    RateLimiter,
    RateLimitStrategy,
    Severity,
    TextEscaper,
    ThreatLevel,
)

# Constants for magic numbers
MAX_WATCHDOG_ALERTS_HISTORY = 100
HIGH_CONFIDENCE_THRESHOLD = 0.8


class GUIFeedback(Protocol):
    """Protocol for GUI feedback callback."""

    def __call__(self, message: str) -> None:
        """Display feedback message to the user."""
        ...


class ContextManager:
    """Manage conversation context history."""

    def __init__(self, history_limit: int = 5) -> None:
        """Initialize context manager with history limit."""
        self.history: list[str] = []  # list of past prompts or intents
        self.limit = history_limit

    def add_entry(self, entry: str) -> None:
        """Add entry to context history."""
        self.history.append(entry)
        if len(self.history) > self.limit:
            self.history.pop(0)

    def get_context(self) -> str:
        """Get context as concatenated string."""
        return " ".join(self.history)


class InputPipeline:
    """Pipeline for processing and sanitizing user input.

    This class orchestrates the input sanitization process through multiple
    stages: validation, escaping, pattern normalization, profanity filtering,
    and intent classification.

    Optimized for chat interface usage with graceful error handling.

    Attributes:
        gui_feedback: Callback function to send feedback to the GUI.
        skip_empty_feedback: Whether to skip feedback for empty inputs.
    """

    def __init__(
        self,
        gui_feedback_hook: GUIFeedback,
        skip_empty_feedback: bool = True,
        model_type: str = "default",
        watchdog_ref: Any | None = None,
        main_window_ref: Any | None = None,
        enable_enhanced_security: bool = True,
    ) -> None:
        """Initialize the input pipeline.

        Args:
            gui_feedback_hook: Callable that accepts a string message to
                display feedback in the GUI (e.g., status bar updates).
            skip_empty_feedback: If True, don't show feedback for empty inputs.
            model_type: Type of LLM model for specific escaping
                ("claude", "gpt", "default").
            watchdog_ref: Reference to the watchdog instance for command
                handling.
            main_window_ref: Reference to main window for accessing app
                components.
            enable_enhanced_security: Enable comprehensive XSS, SQL injection,
                and Unicode protection.
        """
        self.gui_feedback = gui_feedback_hook
        self.skip_empty_feedback = skip_empty_feedback
        self.enable_enhanced_security = enable_enhanced_security
        self.watchdog_ref = watchdog_ref
        self.main_window_ref = main_window_ref

        self._setup_components(model_type)
        self._setup_security(watchdog_ref)
        self._setup_rate_limiter()
        self._setup_context_and_handlers()

    def _setup_components(self, model_type: str) -> None:
        """Setup core processing components."""
        self.validator = InputValidator()
        self.escaper = TextEscaper(model_type)
        self.pattern_normalizer = PatternNormalizer()
        self.profanity_filter = ProfanityFilter()
        self.intent_classifier = IntentClassifier()

    def _setup_security(self, _watchdog_ref: Any | None) -> None:
        """Setup enhanced security components."""
        # Enhanced sanitizer doesn't require external logger - it has internal logging
        self.enhanced_sanitizer = (
            EnhancedInputSanitizer(None) if self.enable_enhanced_security else None
        )

    def _setup_rate_limiter(self) -> None:
        """Setup rate limiting configuration."""
        rate_config = RateLimitConfig(
            max_requests=60,
            window_seconds=60,
            strategy=RateLimitStrategy.SLIDING_WINDOW,
        )
        self.rate_limiter = RateLimiter(rate_config)
        self.user_id = "default_user"  # Could use actual user ID

    def _setup_context_and_handlers(self) -> None:
        """Setup context manager and command handlers."""
        # Initialize context manager
        self.context = ContextManager()

        # Initialize watchdog command handler
        self.watchdog_handler = WatchdogCommandHandler(
            watchdog=self.watchdog_ref, chat_callback=self.gui_feedback
        )

        # Store alerts history for legacy compatibility
        self.watchdog_alerts_history: list[tuple[str, str, datetime]] = []
        # Security outcome counters (basic metrics)
        self.security_counters: dict[str, int] = {
            "attacks_blocked": 0,
            "rejections": 0,
        }

    def _increment_counter(self, key: str, value: int = 1) -> None:
        """Increment the security counter for the given key by the specified value.

        Args:
            key: The name of the counter to increment.
            value: The amount to add to the counter. Default is 1.
        """
        try:
            self.security_counters[key] += value
        except KeyError:
            self.security_counters[key] = value

    def _process_enhanced_security(self, text: str) -> str:
        """Process security enhancements on the input text, performing sanitization and updating counters.

        Args:
            text: The input text to sanitize.

        Returns:
            The sanitized text string.

        Raises:
            InputPipelineError: If sanitization fails due to a strict mode violation.
        """
        if not self.enhanced_sanitizer:
            return text

        try:
            sanitized = self.enhanced_sanitizer.sanitize_input(
                text, context="general", allow_unicode=True, strict_mode=False
            )
            summary = self.enhanced_sanitizer.get_security_summary()
            attacks = summary.get("total_attacks", 0)
            if attacks > 0:
                self._increment_counter("attacks_blocked", int(attacks))
                self.gui_feedback(f"🛡️ Security: Blocked {attacks} attack(s)")
            return sanitized
        except ValueError as e:
            self._increment_counter("rejections", 1)
            self.gui_feedback(f"🚨 Security: {str(e)}")
            raise InputPipelineError(str(e)) from e

    def _check_rate_limit(self) -> None:
        """Check if the current request is within rate limits.

        Raises:
            InputPipelineError: If rate limit is exceeded.
        """
        status = self.rate_limiter.check_rate_limit(self.user_id, action="default")
        if not status.allowed:
            self.gui_feedback(f"⏱️ {status.message}")
            raise InputPipelineError(status.message)

    def _validate_input(self, raw: str) -> str:
        """Validate input text for security threats.

        Args:
            raw: The raw input text to validate.

        Returns:
            The cleaned text after validation.

        Raises:
            InputPipelineError: If validation fails with high threat level.
        """
        result = self.validator.validate(raw)
        message = "; ".join(result.issues) if result.issues else "Invalid input"
        icons = {
            ThreatLevel.HIGH: "🚨",
            ThreatLevel.MEDIUM: "⚠️",
        }
        icon = icons.get(result.threat_level, "ℹ️")
        self.gui_feedback(f"{icon} {message}")
        if result.threat_level == ThreatLevel.HIGH:
            raise InputPipelineError(message)
        return result.cleaned_text

    def _sanitize(self, raw: str) -> str:
        """Sanitize the input text using appropriate security measures.

        Args:
            raw: The raw input text to sanitize.

        Returns:
            The sanitized text.
        """
        if self.enable_enhanced_security and self.enhanced_sanitizer:
            return self._process_enhanced_security(raw)
        return self._validate_input(raw)

    def run(self, raw: str) -> tuple[str, IntentType]:
        """Process raw input through the sanitization pipeline.

        Args:
            raw: Raw user input string.

        Returns:
            A tuple containing:
                - Sanitized text string ready for LLM processing
                - Classified intent enum value

        Raises:
            InputPipelineError: If any stage of the pipeline fails.
        """
        try:
            self._check_rate_limit()
            text = self._sanitize(raw)

            if not text:
                if not self.skip_empty_feedback:
                    self.gui_feedback("Empty input - please enter a message")
                return "", IntentType.UNCLEAR

            # Stage 2: Pattern normalization
            text, pattern_metadata = self.pattern_normalizer.normalize(text)
            if pattern_metadata.get("changed"):
                self.gui_feedback("✨ Input normalized")

            # Stage 3: LLM-specific escaping
            text = self.escaper.escape(text)

            # Stage 4: Profanity filtering
            filter_result = self.profanity_filter.filter(text)
            if filter_result.has_profanity:
                severity_emoji = {
                    Severity.MILD: "😅",
                    Severity.MODERATE: "⚠️",
                    Severity.SEVERE: "🚨",
                    Severity.HATE: "🛑",
                }
                if filter_result.max_severity:
                    emoji = severity_emoji.get(filter_result.max_severity, "⚠️")
                    self.gui_feedback(
                        f"{emoji} Content filtered (severity: {filter_result.max_severity.name})"
                    )
                else:
                    self.gui_feedback("⚠️ Content filtered")
                text = filter_result.filtered_text

            # Stage 5: Intent classification
            intent_result = self.intent_classifier.classify(text)
            intent = intent_result.primary_intent

            # Stage 5b: Handle watchdog commands if detected
            if intent == IntentType.COMMAND and self.watchdog_handler.can_handle(text):
                command_result = self.watchdog_handler.handle_command(text)
                if command_result.should_display_in_chat:
                    # Return the command result as processed text
                    return command_result.message, IntentType.COMMAND

            # Stage 6: Add to context history
            self.context.add_entry(text)

            # Final feedback
            confidence_emoji = (
                "🎯" if intent_result.confidence > HIGH_CONFIDENCE_THRESHOLD else "🤔"
            )
            self.gui_feedback(
                f"{confidence_emoji} Intent: {intent.value} ({intent_result.confidence:.0%} confident)"
            )

            return text, intent

        except InputPipelineError as e:
            self.gui_feedback(f"Input error: {e}")
            raise
        except Exception as e:
            error_msg = f"Unexpected error in input pipeline: {e}"
            self.gui_feedback(error_msg)
            raise InputPipelineError(error_msg) from e

    def get_conversation_context(self) -> str:
        """Get the current conversation context."""
        return self.context.get_context()

    def clear_context(self) -> None:
        """Clear the conversation context history."""
        self.context.history.clear()
        self.gui_feedback("🧹 Conversation context cleared")

    def update_model_type(self, model_type: str) -> None:
        """Update the LLM model type for escaping."""
        self.escaper.set_model(model_type)
        self.gui_feedback(f"🔧 Model type updated to: {model_type}")

    def record_watchdog_alert(self, level: str, message: str) -> None:
        """Record a watchdog alert for history tracking.

        Args:
            level: Alert level (info/warning/critical)
            message: Alert message
        """
        self.watchdog_alerts_history.append((level, message, datetime.now()))
        # Keep only last MAX_WATCHDOG_ALERTS_HISTORY alerts
        if len(self.watchdog_alerts_history) > MAX_WATCHDOG_ALERTS_HISTORY:
            self.watchdog_alerts_history.pop(0)

    # Convenience methods for rate limiting control
    def reset_rate_limit(self) -> None:
        """Reset rate limit for current user."""
        self.rate_limiter.reset_user(self.user_id)
        self.gui_feedback("🔄 Rate limit reset")

    def get_rate_limit_stats(self) -> dict:
        """Get rate limiting statistics."""
        return self.rate_limiter.get_stats()

    # Methods for updating component configurations
    def update_profanity_settings(self, mask_style: str = "stars") -> None:
        """Update profanity filter settings."""
        self.profanity_filter.set_mask_style(mask_style)
        self.gui_feedback("🔧 Profanity settings updated")

    def add_custom_profanity_word(self, word: str, severity: Severity) -> None:
        """Add a custom word to the profanity filter."""
        self.profanity_filter.add_custom_word(word, severity)
        self.gui_feedback(f"➕ Added '{word}' to profanity filter")

    def get_profanity_report(self) -> dict:
        """Get profanity filtering statistics."""
        return self.profanity_filter.get_report()

    def get_security_report(self) -> dict:
        """Get comprehensive security report."""
        if self.enhanced_sanitizer:
            return self.enhanced_sanitizer.get_security_summary()
        return {"enabled": False, "message": "Enhanced security disabled"}

    def get_security_counters(self) -> dict:
        """Return basic counters for sanitizer outcomes (attacks blocked, rejections)."""
        # Return a shallow copy to avoid external mutation
        return dict(self.security_counters)

    def reset_security_monitoring(self) -> None:
        """Reset security monitoring counters."""
        if self.enhanced_sanitizer:
            self.enhanced_sanitizer.reset_security_monitoring()
            self.gui_feedback("🔒 Security monitoring reset")


# Maintain backward compatibility by re-exporting IntentType as Intent
Intent = IntentType

# Maintain backward compatibility for InputSanitizer
InputSanitizer = InputPipeline
