# Application Settings
import os
from config.logging_config import logger

# Base package for generated Java code
DEFAULT_BASE_PACKAGE = "com.example.transpiled"

# Temporary directory prefix
TEMP_DIR_PREFIX = "ruby_java_transpiler_"

# LLM Settings (customize as needed)
# API Provider: "openai" or "openrouter" (or others if added)
API_PROVIDER = "openrouter"
# Base URL for the API
API_BASE_URL = "https://openrouter.ai/api/v1"

# The primary model to use for translations and analysis
LLM_MODEL = "anthropic/claude-3.7-sonnet" # Default model from user config
# LLM_MODEL = "openai/gpt-4o" # Original default
# LLM_MODEL = "google/gemini-1.5-pro-latest"
# LLM_MODEL = "anthropic/claude-3-opus-20240229"

# Controls randomness: Lower values make the output more focused and deterministic.
LLM_TEMPERATURE = 0.1 # Slightly creative but mostly predictable
LLM_MAX_TOKENS = 4000

# Add other settings here
