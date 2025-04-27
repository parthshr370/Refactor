import logging
import sys
import os

# Set the desired default level here
DEFAULT_LOG_LEVEL = logging.DEBUG 

def setup_logging():
    """Configure the logging for the application."""
    # Set up root logger
    root_logger = logging.getLogger()
    
    # Set default level to INFO instead of DEBUG to reduce logging verbosity
    default_level = logging.INFO
    
    # Check for env var to override default
    log_level_str = os.environ.get('RUBY_TO_JAVA_LOG_LEVEL', '').upper()
    if log_level_str:
        if log_level_str == 'DEBUG':
            default_level = logging.DEBUG
        elif log_level_str == 'INFO':
            default_level = logging.INFO
        elif log_level_str == 'WARNING':
            default_level = logging.WARNING
        elif log_level_str == 'ERROR':
            default_level = logging.ERROR
        elif log_level_str == 'CRITICAL':
            default_level = logging.CRITICAL
    
    # Set the level on the root logger
    root_logger.setLevel(default_level)
    
    # Log to console
    if not root_logger.handlers:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(default_level)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
    
    # Set higher levels for verbose third-party libraries to reduce noise
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("git").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("watchdog").setLevel(logging.WARNING)
    
    logger.info(f"Root logger level set to: {logging.getLevelName(default_level)}")


logger = logging.getLogger(__name__)

# Add a test message to confirm logger is working on import
logger.info("Logging module imported. Initial level (might be reset by setup_logging): %s", logging.getLevelName(logger.getEffectiveLevel()))

# Example usage:
# from config.logging_config import logger
# logger.info("This is an info message")
# logger.error("This is an error message")
