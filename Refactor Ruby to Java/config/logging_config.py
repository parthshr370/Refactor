import logging
import sys

# Set the desired default level here
DEFAULT_LOG_LEVEL = logging.DEBUG 

def setup_logging(level=DEFAULT_LOG_LEVEL):
    """Configure basic logging."""
    # Ensure level is explicitly set
    logging.basicConfig(
        level=level, 
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        stream=sys.stdout,  # Log to standard output
        force=True # Force reconfiguration in case Streamlit messes with root logger
    )
    # Suppress verbose logs from libraries if needed
    # logging.getLogger("git").setLevel(logging.WARNING)
    # logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    
    # Explicitly set root logger level AFTER basicConfig just in case
    logging.getLogger().setLevel(level)
    logger.info(f"Root logger level set to: {logging.getLevelName(logging.getLogger().getEffectiveLevel())}")


logger = logging.getLogger(__name__)

# Add a test message to confirm logger is working on import
logger.info("Logging module imported. Initial level (might be reset by setup_logging): %s", logging.getLevelName(logger.getEffectiveLevel()))

# Example usage:
# from config.logging_config import logger
# logger.info("This is an info message")
# logger.error("This is an error message")
