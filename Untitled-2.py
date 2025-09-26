import logging
import os

import ddtrace


def dd_setup() -> None:
    """Configure Datadog tracing for the DinoAir security service."""
    # Set Datadog environment variables
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

    # Configure the Datadog tracer programmatically (optional, as env vars take precedence)
    ddtrace.config.service = "security_auth"
    ddtrace.config.env = "prod"

    # Set global tags - these will be applied to all traces
    ddtrace.config.tags = {"version": "1.0.0"}

    # Initialize the tracer (this happens automatically when ddtrace is imported)
    # Note: To run your app with tracing, use: ddtrace-run python my_app.py
    logging.info("Datadog tracer configured successfully.")


if __name__ == "__main__":
    dd_setup()
    logging.info("Datadog tracing setup complete. Import this module in your application files.")
