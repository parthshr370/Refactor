# agents/structure_analyzer_agent.py
import os
import json
import re # Added for fallback parsing
from typing import Tuple, Dict, List, Any
from pathlib import Path
import tempfile # Added for testing block
import shutil  # Added for testing block

from config.logging_config import logger
# Assuming llm_client has a function like call_llm(prompt) -> str
# We need to handle the case where llm_client might not be directly importable
# depending on project structure, adjust sys.path if needed for testing.
try:
    # Use a generic call function name for flexibility
    from agents.llm_client import call_llm as generic_llm_call
except ImportError:
    logger.error("Could not import call_llm from agents.llm_client. Ensure it exists and paths are correct.")
    # Define a dummy function so the file can be loaded, but it will fail at runtime
    def generic_llm_call(prompt=None, system_prompt=None, user_prompt=None, **kwargs) -> str:
        raise NotImplementedError("LLM Client not found")

# Define prompt template file path relative to this file
_PROMPT_TEMPLATE_PATH = Path(__file__).parent.parent / "prompts" / "structure_analysis_prompt_template.txt"

def list_files_recursive(directory: str) -> List[str]:
    root_path = Path(directory)
    file_list = []
    if not root_path.is_dir():
        logger.error(f"Provided path is not a directory or doesn't exist: {directory}")
        return []
    for path in root_path.rglob('*'):
        if path.is_file():
            try:
                # Get path relative to the root directory
                relative_path = str(path.relative_to(root_path))
                file_list.append(relative_path)
            except ValueError as e:
                logger.warning(f"Could not make path relative: {path} (Error: {e})")
                # Fallback to absolute path or skip? Skipping for now.
                pass
    return file_list

def analyze_and_propose_structure(repo_path: str, base_package: str) -> Tuple[Dict[str, List[Dict[str, str]]] | None, str | None]:
    """
    Analyzes a Ruby/Rails project using an LLM, proposes a Java Spring Boot
    structure, and generates a Mermaid visualization.

    Args:
        repo_path: The absolute path to the cloned/extracted Ruby project directory.
        base_package: The desired base package name for the Java project.

    Returns:
        A tuple containing:
        - A dictionary representing the proposed Java structure (keys are directories,
          values are lists of filenames), or None on failure.
        - A string containing the Mermaid diagram definition, or None on failure.
    """
    logger.info(f"Starting LLM-based structure analysis for {repo_path} with base package {base_package}")
    if not base_package:
        base_package = "com.example.transpiled" # Default if empty
        logger.warning(f"Base package was empty, defaulting to {base_package}")

    base_package_path = base_package.replace('.', '/')


    try:
        # 1. List files
        all_files = list_files_recursive(repo_path)
        if not all_files:
            logger.warning(f"No files found in directory: {repo_path}")
            return None, None

        # Limit file list size if necessary (e.g., > 500 files?)
        max_files_in_prompt = 1000 # Configurable?
        if len(all_files) > max_files_in_prompt:
            logger.warning(f"Project has {len(all_files)} files. Truncating list to {max_files_in_prompt} for LLM prompt.")
            # Maybe select important files? Gemfile, routes.rb, schema.rb, app/* ?
            # For now, just truncate
            all_files = all_files[:max_files_in_prompt]

        # Join files with literal newline characters for the prompt
        file_list_str = "\n".join(all_files)

        # 2. Load and format prompt from template
        try:
            with open(_PROMPT_TEMPLATE_PATH, 'r', encoding='utf-8') as f:
                prompt_template = f.read()
            prompt = prompt_template.format(
                file_list_str=file_list_str,
                base_package=base_package,
                base_package_path=base_package_path
            )
        except FileNotFoundError:
            logger.error(f"Prompt template file not found: {_PROMPT_TEMPLATE_PATH}")
            return None, None
        except Exception as e:
            logger.error(f"Error reading or formatting prompt template: {e}")
            return None, None

        # 3. Call LLM
        logger.info("Sending structure analysis request to LLM...")
        # Use the generic call function
        system_prompt = """You are a Ruby to Java Spring Boot architecture analyzer and translator.
Your response must contain a JSON structure defining the file mapping and optionally a Mermaid diagram.
IMPORTANT: Your response must be valid JSON in the format {"directory_path": ["File1.java", "File2.java"]} with all keys starting with "src/"."""
        response_text = generic_llm_call(system_prompt=system_prompt, user_prompt=prompt)
        if not response_text:
             logger.error("LLM response was empty.")
             return None, None
        logger.debug(f"LLM Raw Response:\\n{response_text[:500]}...") # Log beginning of response

        # 4. Parse Response - More flexible parsing approach
        json_part = None
        mermaid_part = None
        
        # First try to find direct JSON in the response (with or without markdown)
        json_matches = [
            # Standard markdown json block
            re.search(r'```json\s*(\{.*?\})\s*```', response_text, re.DOTALL | re.IGNORECASE),
            # Plain JSON object without markdown
            re.search(r'(\{\s*"src/.*?\})', response_text, re.DOTALL),
            # JSON with single quotes instead of double
            re.search(r'(\{\s*\'src/.*?\})', response_text, re.DOTALL),
        ]
        
        # Use the first successful match
        for match in json_matches:
            if match:
                try:
                    # Replace single quotes with double quotes if needed
                    potential_json = match.group(1).replace("'", '"')
                    # Test if it's valid JSON
                    json.loads(potential_json)
                    json_part = potential_json
                    logger.info("Found valid JSON structure in response")
                    break
                except json.JSONDecodeError:
                    continue
        
        # Try to find Mermaid diagram
        mermaid_match = re.search(r'```mermaid\s*(graph\s+TD.*?|flowchart\s+TD.*?)\s*```', response_text, re.DOTALL | re.IGNORECASE)
        
        # Alternative Mermaid extraction methods if the main one fails
        if not mermaid_match:
            # Try looking for the Mermaid section without explicit code block markers
            mermaid_section = re.search(r'---MERMAID---\s*(.*?)(?=---|$)', response_text, re.DOTALL)
            if mermaid_section:
                # Within that section, try to find the graph definition
                graph_definition = re.search(r'(graph\s+TD.*?|flowchart\s+TD.*?)(?=```|$)', mermaid_section.group(1), re.DOTALL)
                if graph_definition:
                    mermaid_part = graph_definition.group(1).strip()
                    logger.info("Found Mermaid diagram using alternative extraction method")
        
        if mermaid_match:
            mermaid_part = mermaid_match.group(1)
            logger.info("Found Mermaid diagram in response")
            
        # Special handling if we have neither part
        if not json_part and not mermaid_part:
            # Last resort: check if the entire response is valid JSON
            try:
                json.loads(response_text)
                json_part = response_text
                logger.info("Using entire response as JSON")
            except json.JSONDecodeError:
                logger.error("Could not find valid JSON or Mermaid content in the response")
                return None, None

        # Process JSON
        proposed_structure: Dict[str, List[Dict[str, str]]] | None = None # Structure now holds List[Dict]
        if json_part:
            try:
                proposed_structure_raw = json.loads(json_part)
                if not isinstance(proposed_structure_raw, dict):
                    logger.error(f"Parsed JSON is not a dictionary: {type(proposed_structure_raw)}")
                else:
                    proposed_structure = {}
                    # Clean and validate structure
                    for k, v in proposed_structure_raw.items():
                        if isinstance(k, str) and k.startswith("src/") and isinstance(v, list):
                             # Ensure all items in list are dicts with 'name' and 'summary'
                             cleaned_files_data = []
                             for item in v:
                                 if isinstance(item, dict) and isinstance(item.get('name'), str) and isinstance(item.get('summary'), str):
                                     cleaned_files_data.append({'name': item['name'], 'summary': item['summary']})
                                 else:
                                     logger.warning(f"Ignoring invalid file entry in directory '{k}': {item}")
                             
                             # Sort by name
                             if cleaned_files_data:
                                 cleaned_files_data.sort(key=lambda x: x['name'])
                                 proposed_structure[k] = cleaned_files_data
                        else:
                            logger.warning(f"Ignoring invalid entry in proposed structure JSON: Key='{k}' (Type: {type(k)}), Value='{v}' (Type: {type(v)})")
                    if not proposed_structure: # Check if cleaning resulted in empty dict
                        logger.error("Cleaned proposed structure is empty.")
                        proposed_structure = None

            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON structure from LLM response: {e}\\nPotential JSON Part:\\n{json_part}")
                # Invalidate structure if JSON is bad
                proposed_structure = None
        else:
            logger.error("No JSON part found in LLM response after parsing.")


        # Process Mermaid
        if mermaid_part:
            # Simple validation: check if it looks like a mermaid graph definition
            if not ("graph" in mermaid_part or "flowchart" in mermaid_part):
                 logger.warning(f"Parsed Mermaid diagram looks suspicious or empty, discarding: {mermaid_part[:100]}...")
                 mermaid_part = None
            else:
                 # Ensure proper formatting - trim extra whitespace and ensure it starts correctly
                 mermaid_part = mermaid_part.strip()
                 
                 # Make sure it starts with "graph TD" or "flowchart TD"
                 if not (mermaid_part.startswith("graph TD") or mermaid_part.startswith("flowchart TD")):
                     if "graph TD" in mermaid_part:
                         # Extract from where graph TD starts
                         mermaid_part = mermaid_part[mermaid_part.find("graph TD"):]
                     elif "flowchart TD" in mermaid_part:
                         # Extract from where flowchart TD starts
                         mermaid_part = mermaid_part[mermaid_part.find("flowchart TD"):]
                     else:
                         logger.warning("Mermaid diagram doesn't start with graph TD or flowchart TD")
                 
                 # Log the cleaned diagram for debugging
                 logger.debug(f"Cleaned Mermaid diagram:\n{mermaid_part}")
        else:
            logger.warning("No Mermaid part found or extracted.")

        if proposed_structure:
            logger.info(f"Successfully parsed LLM response. Proposed structure has {len(proposed_structure)} directories.")
        else:
            logger.error("Failed to obtain a valid proposed structure from LLM.")

        return proposed_structure, mermaid_part

    except Exception as e:
        logger.error(f"Error during structure analysis: {e}", exc_info=True)
        return None, None

# # --- Basic Testing Block (Example Usage) ---
# # To run this test: python -m agents.structure_analyzer_agent
# if __name__ == '__main__':
#     print("Running basic test for structure_analyzer_agent...")
#     # Need a dummy llm_client.call_llm for testing
#     class MockLLMClient:
#         def call_llm(self, prompt: str, **kwargs) -> str: # Match signature
#             print("\\n--- LLM PROMPT (Truncated) ---")
#             print(prompt[:1000] + "...")
#             print("-----------------------------\\n")
#             # Extract base_package_path from prompt for realistic response
#             match = re.search(r"base package '([^']*)'", prompt)
#             base_pkg = "com.example.mock"
#             if match:
#                 base_pkg = match.group(1)
#             base_pkg_path = base_pkg.replace('.', '/')

#             # Return a sample response matching the requested format
#             return f\"\"\"
# ```json
# {{
#   "src/main/java/{base_pkg_path}/model": ["Post.java", "User.java"],
#   "src/main/java/{base_pkg_path}/repository": ["PostRepository.java", "UserRepository.java"],
#   "src/main/java/{base_pkg_path}/controller": ["PostsController.java", "UsersController.java"],
#   "src/main/java/{base_pkg_path}/service": ["UserService.java"],
#   "src/main/java/{base_pkg_path}/util": ["ApplicationHelperUtil.java"],
#   "src/main/java/{base_pkg_path}/config": ["WebConfig.java"],
#   "src/main/resources": ["application.properties"],
#   "src/main/resources/templates/users": ["index.html", "show.html"],
#   "src/main/resources/templates/posts": ["index.html", "show.html"],
#   "src/main/resources/static/css": ["application.css"],
#   "src/main/resources/static/js": ["application.js"]
# }}
# ```
# ---MERMAID---
# ```mermaid
# graph TD
#     subgraph "Java Source (/{base_pkg_path})"
#         pkg_controller["controller"]
#         pkg_service["service"]
#         pkg_repository["repository"]
#         pkg_model["model"]
#         pkg_util["util"]
#         pkg_config["config"]

#         pkg_controller --> UsersController;
#         pkg_controller --> PostsController;
#         pkg_service --> UserService;
#         pkg_repository --> UserRepository;
#         pkg_repository --> PostRepository;
#         pkg_model --> User;
#         pkg_model --> Post;
#         pkg_util --> ApplicationHelperUtil;
#         pkg_config --> WebConfig;

#         UsersController --> UserService;
#         UserService --> UserRepository;
#         PostsController --> PostRepository;
#     end
#     subgraph "Resources"
#         pkg_templates["templates"]
#         pkg_static["static"]
#         pkg_root["."]

#         pkg_templates --> users_index["users/index.html"];
#         pkg_templates --> users_show["users/show.html"];
#         pkg_templates --> posts_index["posts/index.html"];
#         pkg_templates --> posts_show["posts/show.html"];
#         pkg_static --> css["css/application.css"];
#         pkg_static --> js["js/application.js"];
#         pkg_root --> props["application.properties"];
#     end
# ```
# \"\"\"
#     # Mock the LLM call for the test
#     original_llm_call = generic_llm_call
#     generic_llm_call = MockLLMClient().call_llm

#     # Create a dummy repo structure for testing
#     dummy_repo = tempfile.mkdtemp(prefix="rjt_test_repo_")
#     try:
#         Path(dummy_repo, "app", "models").mkdir(parents=True, exist_ok=True)
#         Path(dummy_repo, "app", "controllers").mkdir(parents=True, exist_ok=True)
#         Path(dummy_repo, "app", "helpers").mkdir(parents=True, exist_ok=True)
#         Path(dummy_repo, "app", "services").mkdir(parents=True, exist_ok=True)
#         Path(dummy_repo, "app", "views", "users").mkdir(parents=True, exist_ok=True)
#         Path(dummy_repo, "app", "views", "posts").mkdir(parents=True, exist_ok=True)
#         Path(dummy_repo, "app", "assets", "stylesheets").mkdir(parents=True, exist_ok=True)
#         Path(dummy_repo, "app", "assets", "javascripts").mkdir(parents=True, exist_ok=True)
#         Path(dummy_repo, "config", "initializers").mkdir(parents=True, exist_ok=True)
#         Path(dummy_repo, "lib").mkdir(parents=True, exist_ok=True)

#         Path(dummy_repo, "app", "models", "user.rb").touch()
#         Path(dummy_repo, "app", "models", "post.rb").touch()
#         Path(dummy_repo, "app", "controllers", "users_controller.rb").touch()
#         Path(dummy_repo, "app", "controllers", "posts_controller.rb").touch()
#         Path(dummy_repo, "app", "helpers", "application_helper.rb").touch()
#         Path(dummy_repo, "app", "services", "user_service.rb").touch()
#         Path(dummy_repo, "app", "views", "users", "index.html.erb").touch()
#         Path(dummy_repo, "app", "views", "users", "show.html.erb").touch()
#         Path(dummy_repo, "app", "views", "posts", "index.html.haml").touch()
#         Path(dummy_repo, "app", "views", "posts", "show.html.slim").touch()
#         Path(dummy_repo, "app", "assets", "stylesheets", "application.css").touch()
#         Path(dummy_repo, "app", "assets", "javascripts", "application.js").touch()
#         Path(dummy_repo, "config", "routes.rb").touch()
#         Path(dummy_repo, "config", "initializers", "devise.rb").touch()
#         Path(dummy_repo, "lib", "custom_task.rake").touch()
#         Path(dummy_repo, "Gemfile").touch()
#         Path(dummy_repo, "README.md").touch()

#         print(f"Testing with dummy repo: {dummy_repo}")
#         test_base_pkg = "com.example.testapp"
#         structure, mermaid = analyze_and_propose_structure(dummy_repo, test_base_pkg)

#         print("\\n--- Proposed Structure ---")
#         if structure:
#             print(json.dumps(structure, indent=2))
#         else:
#             print("Failed to get structure.")

#         print("\\n--- Mermaid Diagram ---")
#         if mermaid:
#             print(mermaid)
#         else:
#             print("Failed to get mermaid diagram.")

#         # Basic Assertions
#         assert structure is not None, "Structure should not be None"
#         assert mermaid is not None, "Mermaid should not be None"
#         assert f"src/main/java/{test_base_pkg.replace('.', '/')}/controller" in structure
#         assert "UsersController.java" in structure[f"src/main/java/{test_base_pkg.replace('.', '/')}/controller"]
#         assert "graph TD" in mermaid

#         print("\\nBasic assertions passed.")

#     finally:
#         # Clean up dummy repo and restore llm_client if it was mocked
#         print(f"Cleaning up dummy repo: {dummy_repo}")
#         shutil.rmtree(dummy_repo)
#         generic_llm_call = original_llm_call # Restore original
#         print("Restored original LLM call function.")
#         print("Test finished.") 