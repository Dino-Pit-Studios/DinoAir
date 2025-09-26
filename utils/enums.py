"""
Enums and constants for DinoAir
Centralized location for application constants
"""

from enum import Enum, auto
from typing import Any


class AppState(Enum):
    """Application state enumeration"""

    STARTING = auto()
    RUNNING = auto()
    PAUSED = auto()
    SHUTTING_DOWN = auto()
    ERROR = auto()


class DatabaseState(Enum):
    """Database state enumeration"""

    CONNECTED = auto()
    DISCONNECTED = auto()
    INITIALIZING = auto()
    ERROR = auto()
    BACKUP_IN_PROGRESS = auto()


class NoteStatus(Enum):
    """Note status enumeration"""

    DRAFT = auto()
    ACTIVE = auto()
    ARCHIVED = auto()
    DELETED = auto()


class InputType(Enum):
    """Input type enumeration for input processing"""

    TEXT = auto()
    VOICE = auto()
    FILE = auto()
    CLIPBOARD = auto()


class ProcessingStage(Enum):
    """Input processing stage enumeration"""

    VALIDATION = auto()
    ESCAPING = auto()
    PATTERN_NOTIFY = auto()
    PROFANITY_FILTER = auto()
    INTENT_CLASSIFIER = auto()
    TRANSLATION = auto()
    COMPLETE = auto()


class AgentType(Enum):
    """AI Agent type enumeration"""

    LLM_WRAPPER = auto()
    ORCHESTRATOR = auto()
    TRANSLATOR = auto()
    CLASSIFIER = auto()


class ToolType(Enum):
    """Tool type enumeration"""

    MEMORY_TOOL = auto()
    TIMER_TOOL = auto()
    CODE_AGENT = auto()
    FILE_TOOL = auto()


class UITheme(Enum):
    """UI Theme enumeration"""

    LIGHT = "light"
    DARK = "dark"
    AUTO = "auto"


class LogLevel(Enum):
    """Logging level enumeration"""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class Enums:
    """Container class for all application enums with utility methods for validation and listing."""

    AppState = AppState
    DatabaseState = DatabaseState
    NoteStatus = NoteStatus
    InputType = InputType
    ProcessingStage = ProcessingStage
    AgentType = AgentType
    ToolType = ToolType
    UITheme = UITheme
    LogLevel = LogLevel

    @classmethod
    def list_enum_names(cls) -> list[str]:
        """Return a list of all enum class names in this container."""
        return [
            name
            for name in dir(cls)
            if isinstance(getattr(cls, name), type) and issubclass(getattr(cls, name), Enum)
        ]

    @staticmethod
    def is_valid_value(enum_name: str, value: Any) -> bool:
        """Validate if a value is valid for the specified enum.

        Args:
            enum_name (str): The name of the enum class (e.g., 'AppState').
            value: The value to validate.

        Returns:
            bool: True if the value is valid for the enum, False otherwise.
        """
        if not isinstance(enum_name, str) or enum_name is None:
            return False

        enum_class = getattr(Enums, enum_name, None)
        if enum_class and issubclass(enum_class, Enum):
            return isinstance(value, enum_class)
        return False
