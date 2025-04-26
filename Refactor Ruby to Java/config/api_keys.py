import os
import streamlit as st
from dotenv import load_dotenv
from config.logging_config import logger

# It's recommended to use environment variables or Streamlit secrets for API keys
# Avoid hardcoding keys directly in the code.

# Option 1: Use Streamlit Secrets (Preferred for deployed apps)
# Example: Create secrets.toml in .streamlit folder
# [openai]
# api_key = "sk-..."
# OPENAI_API_KEY = st.secrets.get("openai", {}).get("api_key")

# Option 2: Use Environment Variables
# Example: export OPENAI_API_KEY='sk-...'
# OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# Option 3: Allow user input (Less secure for shared use)
# OPENAI_API_KEY = st.text_input("Enter OpenAI API Key", type="password") 

# Load environment variables from .env file
load_dotenv()

# --- API Keys --- 
# Fetch API keys from environment variables
# TODO: Add support for other providers if needed
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

if not OPENAI_API_KEY:
    logger.warning("OPENAI_API_KEY environment variable not set.")

if not OPENROUTER_API_KEY:
    logger.warning("OPENROUTER_API_KEY environment variable not set.")

# Add other API keys if needed (e.g., GitHub)
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN") # Optional, for higher rate limits

