# LLM Integration Details

This document outlines how Large Language Models (LLMs) are integrated and utilized within the Ruby to Java Transpiler project.

## Overview

The project leverages LLMs for two primary tasks:

1.  **Java Structure Proposal**: Analyzing the file structure of an input Ruby/Rails project and proposing an idiomatic Java Spring Boot project layout (directories, files, summaries, and a Mermaid visualization).
2.  **Code Translation**: Translating individual Ruby code files (`.rb`) into corresponding Java code based on the proposed structure and file type.

## Core Components

1.  **`agents/llm_client.py`**: This module acts as the central client for interacting with different LLM APIs.
    *   **Provider Agnostic**: It supports configurable API providers, currently `openai` and `openrouter`, defined in `config/settings.py`.
    *   **API Key Management**: Retrieves the necessary API keys (e.g., `OPENROUTER_API_KEY`, `OPENAI_API_KEY`) from environment variables via `config/api_keys.py`.
    *   **Client Initialization**: Creates either a native `openai.OpenAI` client or a `langchain_openai.ChatOpenAI` client based on the selected provider and configuration.
    *   **Retry Logic**: Uses the `tenacity` library to automatically retry API calls in case of transient errors like rate limits or connection issues.
    *   **Core Function**: The `get_translation` method provides a unified interface for sending prompts (system + user) to the configured LLM and retrieving the response.
    *   **Backward Compatibility**: Includes wrapper functions (`get_llm_translation`, `extract_code_from_response`, `call_llm` alias) to maintain compatibility with older parts of the codebase that used a functional approach.

2.  **`agents/structure_analyzer_agent.py`**: This agent is responsible for the first LLM task – proposing the Java structure.
    *   **File Analysis**: It first lists all files in the input Ruby project.
    *   **Prompt Generation**: It reads the template from `prompts/structure_analysis_prompt_template.txt`, formats it with the file list and target base package, and creates the final prompt.
    *   **LLM Call**: It calls the `llm_client.get_translation` (via the `generic_llm_call` import) method with a specific system prompt instructing the LLM on the desired output format (JSON structure with file summaries + Mermaid diagram).
    *   **Response Parsing**: It parses the LLM's response, attempting to extract the JSON block and the Mermaid diagram block using regex, with fallbacks for variations in formatting.
    *   **Output**: Returns the parsed JSON structure (as a Python dictionary) and the Mermaid diagram string.

3.  **`agents/translator_agent.py`**: This agent handles the second LLM task – translating Ruby code to Java.
    *   **Contextual Prompts**: It generates specific prompts for each file being translated:
        *   **System Prompt**: Loads a base template (`prompts/translation_base_system_prompt.txt`) and combines it with type-specific instructions (e.g., `prompts/translation_model_instructions.txt`, `prompts/translation_controller_instructions.txt`). This provides role definition and specific guidance based on whether a model, controller, util, etc., is being translated.
        *   **User Prompt**: Includes the actual Ruby code snippet, the target Java class name, and the file type.
    *   **LLM Call**: Calls `llm_client.get_translation` (via the imported backward compatibility function) with the generated system and user prompts.
    *   **Code Extraction**: Uses `llm_client.extract_code_from_response` (via import) to attempt to extract only the Java code block from the LLM's potentially verbose response.
    *   **Output**: Returns the extracted Java code string.

4.  **`prompts/` Directory**: Contains various `.txt` files used as templates for generating the final prompts sent to the LLM. This allows for easier modification of instructions without changing Python code.

## Configuration (`config/settings.py`)

Several settings control the LLM interaction:

*   `API_PROVIDER`: Specifies which service to use (`"openrouter"` or `"openai"`).
*   `API_BASE_URL`: The base URL for the API endpoint (defaults correctly for OpenRouter/OpenAI if not set).
*   `LLM_MODEL`: The specific model identifier (e.g., `"anthropic/claude-3.5-sonnet"`, `"openai/gpt-4o"`).
*   `LLM_TEMPERATURE`: Controls the creativity/randomness of the LLM response (lower values are more deterministic).
*   `LLM_MAX_TOKENS`: Sets the maximum number of tokens the LLM should generate in its response.

## Dependencies

The LLM integration relies on these key libraries (specified in `requirements.txt`):

*   `openai>=1.0.0`: The official OpenAI Python client library.
*   `langchain-openai`: LangChain integration specifically for OpenAI-compatible APIs (used for OpenRouter).
*   `langchain-core`: Core LangChain abstractions (like SystemMessage, HumanMessage).
*   `tenacity`: For robust retry mechanisms during API calls.

This setup provides a flexible way to interact with different LLMs for the distinct tasks of structure analysis and code translation within the application. 