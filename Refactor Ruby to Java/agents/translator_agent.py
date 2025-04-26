from agents.llm_client import get_llm_translation, extract_code_from_response
from config.logging_config import logger
import os
from pathlib import Path # Import Path

# Define path to prompts directory
_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

def _load_prompt_file(filename: str) -> str | None:
    """Loads a prompt file from the prompts directory."""
    file_path = _PROMPTS_DIR / filename
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        logger.error(f"Prompt file not found: {file_path}")
        return None
    except Exception as e:
        logger.error(f"Error loading prompt file {filename}: {e}")
        return None

def generate_system_prompt(file_type: str, java_class_name: str, base_package: str) -> str | None:
    """Generates a tailored system prompt for the LLM by loading templates."""
    base_prompt = _load_prompt_file("translation_base_system_prompt.txt")
    if not base_prompt:
        return None # Error already logged by _load_prompt_file

    instruction_filename_map = {
        "model": "translation_model_instructions.txt",
        "controller": "translation_controller_instructions.txt",
        "service": "translation_service_instructions.txt",
        "util": "translation_util_instructions.txt",
        "helper": "translation_util_instructions.txt", # Map helper to util instructions
    }
    instruction_filename = instruction_filename_map.get(file_type, "translation_generic_instructions.txt")
    
    instructions = _load_prompt_file(instruction_filename)
    if not instructions:
        # Fallback if specific instruction file missing but base exists?
        # For now, fail if instructions are missing.
        logger.error(f"Instruction snippet file '{instruction_filename}' missing, cannot generate full prompt.")
        return None

    # Combine base and instructions
    full_prompt_template = base_prompt + " " + instructions
    
    # Format the combined prompt with dynamic values
    try:
        # Prepare context for formatting - add more if needed by templates
        format_context = {
            'java_class_name': java_class_name,
            'base_package': base_package,
            # Add other potential placeholders if needed, e.g., base_package_path
            'base_package_path': base_package.replace('.', '/') 
        }
        formatted_prompt = full_prompt_template.format(**format_context)
        return formatted_prompt
    except KeyError as e:
        logger.error(f"Missing key {e} in prompt template '{instruction_filename}' or base prompt.")
        return None
    except Exception as e:
        logger.error(f"Failed to format system prompt: {e}")
        return None

def generate_user_prompt(ruby_code: str, file_type: str, java_class_name: str, context: dict = None) -> str:
    """Generates the user prompt containing the Ruby code and context."""
    # Context could include related model definitions, etc. for better translation (optional)
    prompt = f"Translate the following Ruby code (type: {file_type}) into the Java class '{java_class_name}'."
    if context:
        prompt += "\n\nRelevant Context:\n" + str(context) # Simple context passing
    prompt += f"\n\nRuby Code:\n```ruby\n{ruby_code}\n```\n\nJava Code:"
    return prompt

def translate_code_with_llm(ruby_code: str, file_info: dict, base_package: str) -> str | None:
    """Translates a single piece of Ruby code using the LLM.

    Args:
        ruby_code: The Ruby code content.
        file_info: Dictionary containing 'type', 'class_name', 'java_path'.
        base_package: The base Java package name.

    Returns:
        The translated Java code string, or None if translation fails.
    """
    file_type = file_info.get('type', 'unknown')
    java_class_name = file_info.get('class_name')
    java_path = file_info.get('java_path')

    if not java_class_name:
        logger.warning(f"Skipping translation for file type {file_type} mapped to {java_path} - missing Java class name.")
        return None # Cannot translate without a target class name

    logger.info(f"Starting LLM translation for {file_type} -> {java_path} (Class: {java_class_name})")

    system_prompt = generate_system_prompt(file_type, java_class_name, base_package)
    if not system_prompt:
        logger.error(f"Failed to generate system prompt for {java_class_name}. Aborting translation.")
        return None # Cannot proceed without a system prompt
    user_prompt = generate_user_prompt(ruby_code, file_type, java_class_name)

    # Get translation from LLM client
    raw_translation = get_llm_translation(system_prompt, user_prompt)

    if not raw_translation:
        logger.error(f"LLM translation failed for {java_class_name}.")
        return None

    # Extract the actual code from the potentially verbose LLM response
    # Since we asked the LLM to *only* output code, extraction might not be strictly needed,
    # but it's safer to include it.
    java_code = extract_code_from_response(raw_translation, language="java")

    # Basic sanity check - does it look like Java?
    if not java_code or not (f"class {java_class_name}" in java_code or f"interface {java_class_name}" in java_code or f"enum {java_class_name}" in java_code):
        logger.warning(f"Post-processed LLM output for {java_class_name} doesn't seem to contain the expected class definition. Response was:\n{java_code[:500]}...")
        # Return the raw extracted code anyway, maybe validator catches it
        # return None 

    logger.info(f"Successfully translated {file_type} to {java_class_name}.java")
    return java_code

# --- Rule-based translation (Optional - Placeholder) ---
# You could add simple rule-based translations here for very basic files
# to potentially save on LLM calls or handle simple cases more reliably.

def translate_with_rules(ruby_code: str, file_info: dict, base_package: str) -> str | None:
    """(Placeholder) Attempts translation using predefined rules."""
    # Example: Very simple model mapping
    # if file_info['type'] == 'model' and is_very_simple_model(ruby_code):
    #    return generate_simple_jpa_entity(ruby_code, file_info['class_name'], base_package)
    return None # Indicate rule-based translation did not apply/succeed

# --- Main Translation Orchestrator --- 

def translate_ruby_to_java(ruby_code: str, file_info: dict, base_package: str) -> str | None:
    """Orchestrates the translation of Ruby code to Java.
    
    Tries rule-based translation first (if implemented), then falls back to LLM.
    """
    
    # 1. Attempt rule-based translation (if rules exist)
    # rule_based_translation = translate_with_rules(ruby_code, file_info, base_package)
    # if rule_based_translation:
    #     logger.info(f"Successfully translated {file_info.get('class_name', 'file')} using rules.")
    #     return rule_based_translation
        
    # 2. Fallback to LLM translation
    llm_translation = translate_code_with_llm(ruby_code, file_info, base_package)
    if llm_translation:
        return llm_translation
    else:
        logger.error(f"Failed to translate file associated with Java class: {file_info.get('class_name', 'N/A')}")
        return None

