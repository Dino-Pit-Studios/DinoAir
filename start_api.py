#!/usr/bin/env python3
"""
DinoAir API Launcher with Datadog Tracing
Starts the DinoAir API with full Datadog monitoring and security tracing.
"""

import logging
import os
import sys
from pathlib import Path

# Initialize Datadog tracing as early as possible
try:
    import ddtrace

    # Configure Datadog environment variables
    os.environ["DD_SERVICE"] = "security_auth"
    os.environ["DD_ENV"] = "prod"
    os.environ["DD_LOGS_INJECTION"] = "true"
    os.environ["DD_PROFILING_ENABLED"] = "true"
    os.environ["DD_DATA_STREAMS_ENABLED"] = "true"
    os.environ["DD_TRACE_REMOVE_INTEGRATION_SERVICE_NAMES_ENABLED"] = "true"
    os.environ["DD_APPSEC_ENABLED"] = "true"
    os.environ["DD_IAST_ENABLED"] = "true"
    os.environ["DD_APPSEC_SCA_ENABLED"] = "true"
    os.environ["DD_GIT_REPOSITORY_URL"] = "github.com/dinopitstudiosllc/dinoair"

    # Configure the tracer
    ddtrace.config.service = "security_auth"
    ddtrace.config.env = "prod"
    ddtrace.config.tags = {"version": "1.0.0"}

    logging.info("Datadog tracing initialized successfully")
except ImportError:
    logging.warning("Datadog tracing not available - ddtrace not installed")
except Exception as e:
    logging.warning("Could not initialize Datadog tracing: %s", e)

# Add API_files to the Python path
api_dir = Path(__file__).parent / "API_files"
sys.path.insert(0, str(api_dir))


def main():
    """Start the DinoAir API server with Datadog tracing."""
    try:
        import uvicorn

        print("🚀 Starting DinoAir API with Datadog Security Monitoring")
        print("📍 Server URL: http://127.0.0.1:24801")
        print("🔐 Security tracing: ACTIVE")
        print(f"📁 Working directory: {api_dir}")

        # Run uvicorn with the API_files directory in path
        uvicorn.run(
            "app:create_app",
            factory=True,
            host="127.0.0.1",
            port=24801,
            log_level="info",
            access_log=True,
            reload=False,
        )

    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("Please ensure all dependencies are installed:")
        print("pip install fastapi uvicorn ddtrace")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error starting server: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
