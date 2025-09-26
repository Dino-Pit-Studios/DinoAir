#!/usr/bin/env python3
"""Simple script to run the DinoAir API server"""

import os
import sys
from pathlib import Path

# Initialize Datadog tracing as early as possible
try:
    import logging

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

# Add the API_files directory to Python path
api_dir = Path(__file__).parent / "API_files"
sys.path.insert(0, str(api_dir))

try:
    # Change to the API directory and run from there
    original_cwd = os.getcwd()
    os.chdir(str(api_dir))

    import uvicorn

    print("Starting DinoAir API server on http://127.0.0.1:24801")
    print(f"Working directory: {os.getcwd()}")
    print("Datadog tracing is active for security monitoring")

    config = uvicorn.Config(
        app="app:create_app",
        factory=True,
        host="127.0.0.1",
        port=24801,
        log_level="info",
        access_log=True,
        reload=False,
    )

    server = uvicorn.Server(config)
    server.run()

except ImportError as e:
    print(f"Import error: {e}")
    sys.exit(1)
except Exception as e:
    print(f"Error starting server: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)
