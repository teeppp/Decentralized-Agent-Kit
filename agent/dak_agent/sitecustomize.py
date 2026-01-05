import logging
import os
import sys

# Configure basic logging to ensure we see output
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("langfuse_init")

# Langfuse OpenTelemetry Instrumentation
try:
    # Avoid re-instrumentation if this script runs multiple times or in subprocesses
    if "LANGFUSE_INSTRUMENTED" not in os.environ:
        logger.warning("[Langfuse] Initializing instrumentation from PYTHONSTARTUP...")
        
        # Check if dependencies are available
        try:
            from openinference.instrumentation.google_adk import GoogleADKInstrumentor
            from langfuse import get_client
        except ImportError:
            logger.warning("[Langfuse] Dependencies not found. Skipping.")
            # Don't raise, just exit script cleanly so main app runs
        else:
            # Instrument Google ADK for OpenTelemetry tracing
            GoogleADKInstrumentor().instrument()
            os.environ["LANGFUSE_INSTRUMENTED"] = "true"
            logger.warning("[Langfuse] Instrumentation initialized.")
            
            # Optional: Verify Langfuse authentication if environment variables are set
            if os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"):
                try:
                    langfuse = get_client()
                    if langfuse.auth_check():
                        logger.warning("[Langfuse] Authentication successful - monitoring enabled")
                    else:
                        logger.warning("[Langfuse] Authentication failed - check your credentials")
                except Exception as e:
                    logger.warning(f"[Langfuse] Connection error: {e}")
except Exception as e:
    logger.warning(f"[Langfuse] Error in startup script: {e}")
    # Don't crash the app
    pass
