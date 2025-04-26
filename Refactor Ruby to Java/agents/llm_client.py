import os
import re
import time
import openai
from openai import OpenAI
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from config.settings import API_PROVIDER, API_BASE_URL, LLM_MODEL, LLM_TEMPERATURE, LLM_MAX_TOKENS
from config.api_keys import OPENAI_API_KEY, OPENROUTER_API_KEY
from config.logging_config import logger

class LLMClient:
    def __init__(self):
        """Initialize LLM client based on the selected API provider."""
        self.client = None
        self.api_key = None
        self.base_url = None
        
        # Setup based on provider
        if API_PROVIDER.lower() == "openrouter":
            self.api_key = OPENROUTER_API_KEY
            self.base_url = API_BASE_URL or "https://openrouter.ai/api/v1"
            
            # Setup LangChain client for OpenRouter
            self.client = ChatOpenAI(
                model=LLM_MODEL,
                openai_api_key=self.api_key,
                openai_api_base=self.base_url,
                temperature=LLM_TEMPERATURE,
                max_tokens=LLM_MAX_TOKENS
            )
        else:  # Default to OpenAI
            self.api_key = OPENAI_API_KEY
            self.base_url = API_BASE_URL or "https://api.openai.com/v1"
            
            # Setup native OpenAI client
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url
            )
    
    def is_configured(self):
        """Check if the LLM client is properly configured."""
        return self.client is not None and self.api_key is not None
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((openai.RateLimitError, openai.APIConnectionError, requests.exceptions.RequestException))
    )
    def get_translation(self, system_prompt, user_prompt, temperature=None, max_tokens=None):
        """
        Get a translation from the LLM.
        
        Args:
            system_prompt (str): The system prompt/instructions
            user_prompt (str): The user prompt/content to translate
            temperature (float, optional): Override default temperature
            max_tokens (int, optional): Override default max_tokens
            
        Returns:
            str: The LLM's response
        """
        if not self.is_configured():
            logger.error("LLM client not properly configured. Check API keys and settings.")
            return "ERROR: LLM client not configured properly."
        
        temp = temperature if temperature is not None else LLM_TEMPERATURE
        tokens = max_tokens if max_tokens is not None else LLM_MAX_TOKENS
        
        try:
            if API_PROVIDER.lower() == "openrouter":
                # Use LangChain for OpenRouter
                messages = [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_prompt)
                ]
                response = self.client.invoke(messages)
                return response.content
            else:
                # Use native OpenAI client
                response = self.client.chat.completions.create(
                    model=LLM_MODEL,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=temp,
                    max_tokens=tokens
                )
                return response.choices[0].message.content
                
        except Exception as e:
            logger.error(f"Error getting LLM response: {str(e)}")
            raise
    
    def extract_code_from_response(self, response, language=None):
        """
        Extract code blocks from LLM response.
        
        Args:
            response (str): The LLM response text
            language (str, optional): The programming language to extract (e.g., 'java')
            
        Returns:
            str: Extracted code or the full response if no code blocks found
        """
        # Pattern to match code blocks with or without language specification
        if language:
            pattern = rf"```(?:{language})?\s*([\s\S]*?)```"
        else:
            pattern = r"```(?:\w*)?\s*([\s\S]*?)```"
            
        matches = re.findall(pattern, response)
        
        if matches:
            # Join all code blocks with newlines
            return "\n\n".join(matches)
        else:
            # If no code blocks found, return the original response
            return response

# Re-import re here because it's used in extract_code_from_response
import re

# Initialize a global client instance for backward compatibility
_llm_client = LLMClient()

# Create backward compatibility functions to maintain the old interface
def get_llm_translation(system_prompt: str, user_prompt: str) -> str | None:
    """Backward compatibility function for the old interface."""
    try:
        return _llm_client.get_translation(system_prompt, user_prompt)
    except Exception as e:
        logger.error(f"Translation error in backward compatibility layer: {e}")
        return None

def extract_code_from_response(llm_response: str, language: str = "java") -> str:
    """Backward compatibility function for the old interface."""
    return _llm_client.extract_code_from_response(llm_response, language)

# Create an alias to maintain backwards compatibility with other modules
call_llm = get_llm_translation

