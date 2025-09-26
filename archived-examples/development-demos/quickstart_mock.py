#!/usr/bin/env python3
import os
import sys
from pathlib import Path


def _ensure_repo_on_path() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))


def main() -> int:
    try:
        # Safe defaults: disable plugins for deterministic, network-free behavior
        os.environ["PSEUDOCODE_ENABLE_PLUGINS"] = "0"

        # Ensure imports work when running from the examples/ directory
        _ensure_repo_on_path()

        from pseudocode_translator.integration.api import TranslatorAPI

        # Initialize API
        api = TranslatorAPI()

        # Force mock model for deterministic output
        try:
            api.switch_model("mock")
        except Exception:
            return 1

        # Minimal instruction
        instruction = "Define add(a, b) that returns sum"
        result = api.translate(instruction, language="python")

        if not result.get("success"):
            return 2

        result.get("code") or ""

        # Optionally print telemetry summary if enabled
        info = api.get_info()
        telemetry = info.get("telemetry") or {}
        if telemetry:
            telemetry.get("enabled", False)
            telemetry.get("events", {})

        api.shutdown()
        return 0
    except Exception:
        return 3


if __name__ == "__main__":
    sys.exit(main())
