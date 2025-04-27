import streamlit as st
import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Literal, Union
import streamlit.components.v1 as components
import logging
from streamlit_mermaid import st_mermaid

# Configure logging
from config.logging_config import setup_logging, logger
setup_logging()

# Import necessary backend functions
from config import settings
from utils.repository_fetcher import fetch_repository, validate_ruby_project
from utils.file_analyzer import analyze_file_structure
from utils.structure_mapper import create_file_mapping
from utils.code_generator import generate_java_project
from utils.validator import validate_java_project
from utils.output_packager import create_zip_archive
from agents.structure_analyzer_agent import analyze_and_propose_structure, list_files_recursive

# --- Constants ---
APP_TITLE = "Ruby to Java Transpiler (New)"
TEMP_DIR_PREFIX = "rjt_new_app_"
STATE_INPUT = "INPUT"
STATE_VALIDATING_SOURCE = "VALIDATING_SOURCE"
STATE_ANALYZING = "ANALYZING"
STATE_REVIEWING = "REVIEWING"
STATE_TRANSLATING = "TRANSLATING"
STATE_VALIDATING_OUTPUT = "VALIDATING_OUTPUT"
STATE_DOWNLOADING = "DOWNLOADING"
STATE_ERROR = "ERROR"

# --- Helper Functions ---

def is_tool_available(name: str) -> bool:
    """Check if a command-line tool is available in PATH."""
    return shutil.which(name) is not None

def cleanup_temp_dir(dir_path_key: str) -> None:
    """Safely cleans up a temporary directory stored in session state."""
    dir_path = st.session_state.get(dir_path_key)
    if dir_path and os.path.exists(dir_path) and dir_path.startswith(tempfile.gettempdir()):
        try:
            shutil.rmtree(dir_path)
            logger.info(f"Cleaned up temporary directory: {dir_path}")
            st.session_state[dir_path_key] = None
        except Exception as e:
            logger.error(f"Error cleaning up temporary directory {dir_path}: {e}")

def reset_app_state(target_state: str = STATE_INPUT) -> None:
    """Resets the application state, cleaning up temporary files."""
    logger.info(f"Resetting application state to {target_state}.")
    cleanup_temp_dir('source_dir')
    cleanup_temp_dir('generated_dir')

    # Reset session state variables (keep essential settings like base package)
    keys_to_reset = [
        'source_dir', 'generated_dir', 'project_name', 'source_description',
        'ruby_structure', 'source_files_list', 'proposed_java_structure',
        'mermaid_diagram', 'validation_results', 'zip_data', 'error_message',
        '_last_exception'
    ]
    for key in keys_to_reset:
        if key in st.session_state:
            st.session_state[key] = None

    st.session_state.current_state = target_state
    st.rerun()

def initialize_state() -> None:
    """Initializes Streamlit session state if not already done."""
    if 'current_state' not in st.session_state:
        st.session_state.current_state = STATE_INPUT
        st.session_state.source_dir = None
        st.session_state.generated_dir = None
        st.session_state.project_name = "transpiled-project"
        st.session_state.base_package = settings.DEFAULT_BASE_PACKAGE
        st.session_state.source_description = None
        st.session_state.ruby_structure = None
        st.session_state.source_files_list = None
        st.session_state.proposed_java_structure = None
        st.session_state.mermaid_diagram = None
        st.session_state.validation_results = None
        st.session_state.zip_data = None
        st.session_state.error_message = None
        st.session_state._last_exception = None
        st.session_state.maven_present = is_tool_available("mvn")
        logger.info("Session state initialized.")

# --- Tree Formatting Helper Functions ---

def build_file_tree_data(structure: Dict[str, List[Union[str, Dict[str, str]]]], root_name: str = ".") -> Dict[str, Any]:
    """
    Builds a nested dictionary representing the file tree structure.
    Handles both simple file lists (like potential ruby_structure) and dict lists (proposed_java_structure).
    Ensures consistent handling of paths.
    """
    tree = {}
    if not isinstance(structure, dict):
        logger.warning(f"Invalid structure passed to build_file_tree_data: {type(structure)}")
        return {root_name: {}} # Return empty root

    # Normalize structure keys to use forward slashes and handle root ('.')
    normalized_structure = {}
    for path_str, files_data in structure.items():
        norm_path = path_str.replace("\\", "/").strip("/")
        if norm_path == "" or norm_path == ".":
            norm_path = "."
        if norm_path not in normalized_structure:
             normalized_structure[norm_path] = []
        # Ensure files_data is a list before extending
        if isinstance(files_data, list):
            normalized_structure[norm_path].extend(files_data)
        else:
            logger.warning(f"Ignoring non-list data for path '{path_str}': {type(files_data)}")

    # Build the tree
    root_node = tree.setdefault(root_name, {}) # Root node dictionary

    # Sort paths for consistent processing
    sorted_paths = sorted(normalized_structure.keys())

    for norm_path in sorted_paths:
        files_data = normalized_structure[norm_path]
        if norm_path == ".":
            # Add root files directly to the root node
            current_level = root_node
        else:
            # Navigate or create directories
            parts = norm_path.split('/')
            current_level = root_node
            for part in parts:
                current_level = current_level.setdefault(part, {})

        # Add files/items at the current level
        if isinstance(files_data, list):
            for item in files_data:
                item_name = None
                if isinstance(item, dict) and 'name' in item:
                    item_name = item['name']
                elif isinstance(item, str):
                    item_name = item

                if item_name:
                    # Ensure we don't overwrite a directory with a file
                    if item_name not in current_level or current_level[item_name] is None:
                        current_level[item_name] = None # Mark as file

    return tree

def format_tree_recursive(node: Dict[str, Any], prefix: str = "") -> List[str]:
    """Recursively formats a directory node into ASCII tree lines."""
    lines = []
    # Sort items: directories first, then files
    items = sorted(node.keys(), key=lambda x: (isinstance(node[x], dict), x))
    count = len(items)

    for i, name in enumerate(items):
        is_last = (i == count - 1)
        connector = "└── " if is_last else "├── "
        entry = node[name]

        if isinstance(entry, dict): # It's a directory
            lines.append(f"{prefix}{connector}{name}/")
            # Calculate new prefix for children
            new_prefix = prefix + ("    " if is_last else "│   ")
            lines.extend(format_tree_recursive(entry, new_prefix))
        else: # It's a file (or marked as None)
            lines.append(f"{prefix}{connector}{name}")

    return lines

def format_file_tree(tree_data: Dict[str, Any]) -> List[str]:
    """
    Formats the nested dictionary from build_file_tree_data into an ASCII tree string list.
    Uses a recursive helper function.
    """
    if not tree_data or len(tree_data) != 1:
        logger.warning(f"Invalid tree_data structure: {tree_data}")
        return ["Error: Invalid tree structure"] # Or []

    root_name = list(tree_data.keys())[0]
    root_node = tree_data[root_name]

    if not isinstance(root_node, dict):
        # Handle case where root itself is not a directory (e.g., only contains files)
        return [f"{root_name}/"] # Just show the root

    # Start with the root name
    lines = [f"{root_name}/"]
    # Recursively format the contents of the root node
    lines.extend(format_tree_recursive(root_node, prefix=""))

    return lines

# --- NEW Directory Scanning Tree Function --- 
def build_dir_tree_recursive(dir_path: str) -> Dict[str, Any]:
    """Recursively scans a directory path and builds a nested dictionary tree."""
    tree: Dict[str, Any] = {}
    try:
        # List items, handling potential permission errors
        items = os.listdir(dir_path)
        for item in items:
            item_path = os.path.join(dir_path, item)
            if os.path.isdir(item_path):
                tree[item] = build_dir_tree_recursive(item_path)
            else:
                tree[item] = None # Mark as file
    except OSError as e:
        logger.warning(f"Could not list directory {dir_path}: {e}")
        tree["_error_"] = f"Could not read: {e.strerror}" # Add error marker
    return tree

def build_directory_tree_data(dir_path: str, root_name: Optional[str] = None) -> Dict[str, Any]:
    """Builds the complete tree data structure for a directory, including the root."""
    if not os.path.isdir(dir_path):
        return {}
    effective_root_name = root_name if root_name else os.path.basename(dir_path)
    if not effective_root_name: # Handle edge case if dir_path ends in /
         effective_root_name = "generated-project"
    return {effective_root_name: build_dir_tree_recursive(dir_path)}

# --- State Handling Functions ---

def handle_input_state():
    """Manages the UI and logic for the input state."""
    st.header("1. Provide Ruby Project Source")

    if st.session_state.get("error_message"):
        st.error(st.session_state.error_message)
        st.session_state.error_message = None

    input_method = st.radio(
        "Choose input method:",
        ("GitHub URL", "Upload ZIP"),
        key="input_method_radio", horizontal=True
    )

    if input_method == "GitHub URL":
        github_url = st.text_input("Enter public GitHub repository URL:", key="github_input", value=st.session_state.get("github_url_input_value", ""))
        if st.button("Fetch Repository", key="fetch_github_btn"):
            if github_url:
                st.session_state.github_url_input_value = github_url
                if 'error_message' in st.session_state: st.session_state.error_message = None
                if 'source_dir' in st.session_state: cleanup_temp_dir('source_dir')
                st.session_state.project_name = github_url.split('/')[-1].replace('.git', '') or "github-project"
                st.session_state.source_description = f"GitHub: {github_url}"
                with st.spinner(f"Cloning {github_url}..."):
                    repo_dir, error_msg = fetch_repository(github_url)
                    if error_msg:
                        st.error(f"Error cloning repository: {error_msg}")
                    elif repo_dir:
                        st.session_state.source_dir = repo_dir
                        st.session_state.current_state = STATE_VALIDATING_SOURCE
                        logger.info(f"Repository cloned to {repo_dir}")
                        st.rerun()
                    else:
                        st.error("Cloning failed for an unknown reason.")
            else:
                st.warning("Please enter a GitHub URL.")

    elif input_method == "Upload ZIP":
        uploaded_zip = st.file_uploader("Upload your project as a ZIP file:", type=['zip'], key="zip_input")
        if uploaded_zip is not None:
             st.session_state.zip_uploaded_state = uploaded_zip
             if st.button("Process Uploaded ZIP", key="process_zip_btn"):
                if 'error_message' in st.session_state: st.session_state.error_message = None
                if 'source_dir' in st.session_state: cleanup_temp_dir('source_dir')
                st.session_state.project_name = uploaded_zip.name.replace('.zip', '') or "uploaded-project"
                st.session_state.source_description = f"ZIP: {uploaded_zip.name}"
                with st.spinner(f"Extracting {uploaded_zip.name}..."):
                    temp_extract_base = tempfile.mkdtemp(prefix=TEMP_DIR_PREFIX + "extract_")
                    repo_dir_temp = None
                    error_msg = None
                    try:
                        with zipfile.ZipFile(uploaded_zip, 'r') as zip_ref:
                            zip_ref.extractall(temp_extract_base)
                        logger.info(f"Successfully extracted ZIP to {temp_extract_base}")
                        items = os.listdir(temp_extract_base)
                        if len(items) == 1 and os.path.isdir(os.path.join(temp_extract_base, items[0])):
                            single_root_path = os.path.join(temp_extract_base, items[0])
                            primary_temp_dir = tempfile.mkdtemp(prefix=TEMP_DIR_PREFIX)
                            for item_name in os.listdir(single_root_path):
                                shutil.move(os.path.join(single_root_path, item_name), primary_temp_dir)
                            repo_dir_temp = primary_temp_dir
                            shutil.rmtree(temp_extract_base)
                            logger.info(f"Moved single root folder contents to primary temp dir: {repo_dir_temp}")
                        else:
                            repo_dir_temp = temp_extract_base
                            logger.info(f"Using extraction root as primary temp dir: {repo_dir_temp}")

                    except zipfile.BadZipFile:
                        error_msg = "Invalid ZIP file."
                        if os.path.exists(temp_extract_base): shutil.rmtree(temp_extract_base)
                    except Exception as e:
                        error_msg = f"Error extracting ZIP: {e}"
                        if os.path.exists(temp_extract_base): shutil.rmtree(temp_extract_base)

                    if error_msg:
                        st.error(f"Error processing ZIP: {error_msg}")
                    elif repo_dir_temp:
                        st.session_state.source_dir = repo_dir_temp
                        st.session_state.current_state = STATE_VALIDATING_SOURCE
                        logger.info(f"ZIP processed, source dir set to: {repo_dir_temp}")
                        st.rerun()
                    else:
                        st.error("ZIP extraction failed unexpectedly.")
        elif 'zip_uploaded_state' in st.session_state:
             st.session_state.zip_uploaded_state = None


def handle_validating_source_state():
    """Validates the fetched/extracted source directory."""
    st.header("Validating Project Source...")
    st.write(f"Checking source: {st.session_state.source_description}")

    if not st.session_state.source_dir or not os.path.isdir(st.session_state.source_dir):
        st.error("Source directory not found. Please return to input.")
        st.session_state.current_state = STATE_ERROR
        st.session_state.error_message = "Source directory missing during validation."
        st.rerun()
        st.stop()

    with st.spinner("Validating Ruby project structure..."):
        try:
            is_ruby, is_rails = validate_ruby_project(st.session_state.source_dir)
        except Exception as e:
             logger.error(f"Error during project validation: {e}", exc_info=True)
             st.error(f"Error during project validation: {e}")
             st.session_state.current_state = STATE_ERROR
             st.session_state.error_message = f"Validation check failed: {e}"
             st.session_state._last_exception = e
             st.rerun()
             st.stop()


    if not is_ruby:
        st.error("The source does not appear to be a valid Ruby project (Gemfile or .rb files missing).")
        st.session_state.current_state = STATE_ERROR
        st.session_state.error_message = "Source validation failed: Not a Ruby project."
        cleanup_temp_dir('source_dir')
        st.rerun()
        st.stop()
    else:
        st.success(f"Project validated: {st.session_state.source_description} ({'Rails App' if is_rails else 'Ruby Project'})")
        st.session_state.current_state = STATE_ANALYZING
        logger.info("Source validation successful.")
        import time
        time.sleep(1)
        st.rerun()

def handle_analyzing_state():
    """Analyzes the Ruby project and proposes a Java structure."""
    st.header("2. Analyzing Project Structure")
    st.write(f"Analyzing: {st.session_state.source_description}")

    if not st.session_state.source_dir:
        st.error("Source directory missing. Please restart.")
        st.session_state.current_state = STATE_ERROR
        st.session_state.error_message = "Source directory missing during analysis."
        st.rerun()
        st.stop()

    if st.session_state.get('proposed_java_structure') is not None and st.session_state.get('ruby_structure') is not None:
         logger.info("Analysis data already exists, proceeding to review.")
         st.session_state.current_state = STATE_REVIEWING
         st.rerun()
         st.stop()

    col1, col2 = st.columns([1, 3])
    with col1:
        st.write("Analysis Steps:")
        step1_status = st.empty()
        step2_status = st.empty()
        step3_status = st.empty()
    with col2:
        progress_bar = st.progress(0)
        status_text = st.empty()

    analysis_successful = False
    try:
        step1_status.markdown("➡️ Initial Scan")
        status_text.info("Scanning source files...")
        logger.info("Analyzing Ruby file structure...")
        if st.session_state.get('ruby_structure') is None:
            st.session_state.source_files_list = list_files_recursive(st.session_state.source_dir)
            st.session_state.ruby_structure = analyze_file_structure(st.session_state.source_dir)
            if not isinstance(st.session_state.ruby_structure, dict):
                 logger.error(f"Ruby analysis returned unexpected type: {type(st.session_state.ruby_structure)}")
                 raise ValueError("Ruby project analysis failed to return a valid structure.")
            logger.info(f"Ruby structure analysis complete. Found {len(st.session_state.source_files_list or [])} files.")
        else:
             logger.info("Skipping Ruby structure analysis, already present.")
        progress_bar.progress(30)
        step1_status.markdown("✅ Initial Scan")

        step2_status.markdown("➡️ LLM Analysis")
        status_text.info("Requesting structure proposal from LLM...")
        logger.info("Calling LLM for Java structure proposal...")
        progress_bar.progress(60)

        if st.session_state.get('proposed_java_structure') is None:
            proposed_structure, mermaid_code = analyze_and_propose_structure(
                st.session_state.source_dir,
                st.session_state.base_package
            )
            st.session_state.proposed_java_structure = proposed_structure
            st.session_state.mermaid_diagram = mermaid_code
            logger.info("LLM analysis complete.")
        else:
            logger.info("Skipping LLM proposal, already present.")
            proposed_structure = st.session_state.proposed_java_structure

        step2_status.markdown("✅ LLM Analysis")

        if proposed_structure and isinstance(proposed_structure, dict):
            step3_status.markdown("➡️ Processing Results")
            status_text.success("Analysis complete!")
            progress_bar.progress(100)
            step3_status.markdown("✅ Processing Results")
            analysis_successful = True
        else:
            status_text.error("LLM analysis failed to return a valid structure.")
            logger.error(f"LLM returned invalid structure: {type(proposed_structure)}")
            st.session_state.error_message = "LLM analysis did not provide a valid structure."
            progress_bar.progress(100)

    except Exception as e:
        logger.error(f"Error during analysis phase: {e}", exc_info=True)
        status_text.error(f"An error occurred during analysis: {e}")
        st.session_state.error_message = f"Analysis Error: {e}"
        st.session_state._last_exception = e
        progress_bar.progress(100)

    if analysis_successful:
        st.session_state.current_state = STATE_REVIEWING
        import time; time.sleep(1)
        st.rerun()
    else:
        st.session_state.current_state = STATE_ERROR
        st.rerun()
        st.stop()


def handle_reviewing_state():
    """Displays analysis results and allows user review/confirmation."""
    st.header("3. Review Proposed Java Structure")

    # Check necessary data exists
    if not st.session_state.get('proposed_java_structure') or not st.session_state.get('ruby_structure'):
        missing_data = []
        if not st.session_state.get('proposed_java_structure'): missing_data.append("Proposed Java Structure")
        if not st.session_state.get('ruby_structure'): missing_data.append("Original Ruby Structure")
        st.error(f"Analysis results are missing: {', '.join(missing_data)}. Please re-analyze.")
        st.session_state.current_state = STATE_ERROR
        st.session_state.error_message = f"Missing data in review state: {', '.join(missing_data)}."
        st.rerun()
        st.stop()

    # Tab setup - Added Summary Tab
    tab_summary, tab_compare, tab_viz, tab_source_list = st.tabs([
        "📝 Project Summary", # New Tab
        "📊 Structure Comparison",
        "📈 Visualization",
        "📄 Source Files List"
    ])

    # --- New Summary Tab --- 
    with tab_summary:
        st.subheader("Original Ruby Project Analysis")
        ruby_struct = st.session_state.get('ruby_structure', {})
        if isinstance(ruby_struct, dict) and ruby_struct:
            # Basic summary based on directories found
            top_level_ruby_dirs = [k for k in ruby_struct.keys() if k not in ('.', '')]
            project_type_guess = "Ruby project"
            # Simple heuristic for Rails detection
            if 'app' in top_level_ruby_dirs and 'config' in top_level_ruby_dirs and 'db' in top_level_ruby_dirs:
                 project_type_guess = "Ruby on Rails application"

            st.markdown(f"The analysis identified the source as likely a **{project_type_guess}**.")
            if top_level_ruby_dirs:
                 st.markdown("Key top-level directories detected:")
                 st.markdown(f"```\n{', '.join(sorted(top_level_ruby_dirs))}\n```")
            else:
                 st.info("No distinct top-level directories were identified in the provided structure analysis data.")
        else:
            st.warning("Could not generate Ruby project summary due to missing or invalid structure data.")

        st.markdown("---")
        st.subheader("Proposed Java Project Overview")
        java_struct = st.session_state.get('proposed_java_structure', {})
        base_pkg = st.session_state.get('base_package', 'com.example.transpiled')
        if isinstance(java_struct, dict) and java_struct:
            # Extract top-level packages/directories proposed under the main Java source path
            java_src_prefix = f"src/main/java/{base_pkg.replace('.', '/')}"
            top_level_java_pkgs = set()
            for path_str in java_struct.keys():
                norm_path = path_str.replace("\\", "/").strip("/")
                if norm_path.startswith(java_src_prefix):
                    sub_path = norm_path[len(java_src_prefix):].strip("/")
                    if sub_path:
                        first_part = sub_path.split('/')[0]
                        top_level_java_pkgs.add(first_part)

            st.markdown("The proposed Java structure appears to follow a standard layered architecture (common in Spring Boot applications). A detailed structure is shown in the 'Structure Comparison' tab.")
            if top_level_java_pkgs:
                 st.markdown(f"Key packages planned under `src/main/java/{base_pkg}` include:")
                 st.markdown(f"```\n{', '.join(sorted(list(top_level_java_pkgs)))}\n```")
            else:
                 st.info("No specific Java packages were identified under the main source path in the proposal.")

            st.markdown("**Note:** For specific file purposes generated by the AI, please see the **'Show File Summaries'** expander under the 'Proposed Java Structure' section in the '📊 Structure Comparison' tab.")
        else:
            st.warning("Could not generate Java project overview due to missing or invalid proposed structure data.")

    # --- Structure Comparison Tab --- (No changes needed here)
    with tab_compare:
        st.subheader("Original Ruby vs. Proposed Java Structure")
        col_ruby, col_java = st.columns(2)

        with col_ruby:
            st.markdown("**Original Ruby Structure:**")
            try:
                ruby_struct = st.session_state.ruby_structure
                if not isinstance(ruby_struct, dict):
                     raise TypeError(f"Expected dict for ruby_structure, got {type(ruby_struct)}")
                ruby_tree_data = build_file_tree_data(ruby_struct, "ruby-project-root")
                ruby_tree_lines = format_file_tree(ruby_tree_data)
                st.code("\n".join(ruby_tree_lines), language=None)
            except Exception as e:
                st.error(f"Could not display Ruby structure tree: {e}")
                logger.error(f"Error formatting ruby tree: {e}", exc_info=True)
                st.json(st.session_state.ruby_structure, expanded=False) # Fallback

        with col_java:
            st.markdown("**Proposed Java Structure:**")
            try:
                 java_struct = st.session_state.proposed_java_structure
                 if not isinstance(java_struct, dict):
                     raise TypeError(f"Expected dict for proposed_java_structure, got {type(java_struct)}")
                 java_tree_data = build_file_tree_data(java_struct, "java-project-root")
                 java_tree_lines = format_file_tree(java_tree_data)
                 st.code("\n".join(java_tree_lines), language=None)

                 # File summaries expander
                 with st.expander("Show File Summaries (from LLM)", expanded=False):
                     summaries = []
                     for path, files in java_struct.items():
                         if isinstance(files, list):
                             for file_info in files:
                                 if isinstance(file_info, dict) and 'name' in file_info and 'summary' in file_info:
                                     display_path = Path(path) / file_info['name']
                                     summaries.append(f"**{display_path.as_posix()}**: {file_info['summary']}")
                     if summaries:
                         st.markdown("\n\n".join(summaries))
                     else:
                         st.info("No file summaries were provided by the analysis.")

            except Exception as e:
                st.error(f"Could not display Java structure tree: {e}")
                logger.error(f"Error formatting java tree: {e}", exc_info=True)
                st.json(st.session_state.proposed_java_structure, expanded=False) # Fallback

    # --- Visualization Tab --- (No changes needed here)
    with tab_viz:
        st.subheader("Structure Visualization (Mermaid)")
        mermaid_code = st.session_state.get('mermaid_diagram')
        if mermaid_code:
            with st.expander("Show Mermaid Code"):
                st.code(mermaid_code, language="mermaid")
            try:
                st_mermaid(mermaid_code, height=600)
            except ModuleNotFoundError:
                 st.error("Component Error: `streamlit-mermaid` library not installed. Please run `pip install streamlit-mermaid`.")
                 logger.error("streamlit-mermaid not found.")
            except Exception as e:
                 st.error(f"Failed to render Mermaid diagram: {e}")
                 st.warning("The diagram might be invalid or the `streamlit-mermaid` component failed.")
                 logger.error(f"Streamlit-mermaid rendering failed: {e}", exc_info=True)
        else:
            st.info("No visualization diagram was generated or found in session state.")

    # --- Source Files List Tab --- (No changes needed here)
    with tab_source_list:
        st.subheader("Original Source Files List")
        source_list = st.session_state.get('source_files_list')
        if isinstance(source_list, list):
            stringified_list = [str(item) for item in source_list]
            st.text_area("Files Found", "\n".join(stringified_list), height=400)
        elif source_list is not None:
            st.warning(f"Source file list is not in the expected list format (type: {type(source_list)}).")
            try:
                st.json(source_list)
            except:
                st.write(source_list)
        else:
            st.warning("Source file list not available (may need re-analysis).")

    # --- Configuration and Actions --- (No changes needed here)
    st.markdown("---")
    st.subheader("Configuration")
    new_base_package = st.text_input(
        "Java Base Package:",
        value=st.session_state.base_package,
        key="base_pkg_review"
    )

    needs_reanalysis = False
    if new_base_package != st.session_state.base_package:
        st.warning("Base package changed. Re-analysis is required to apply the change to the proposed structure.")
        needs_reanalysis = True

    col_action1, col_action2 = st.columns(2)
    with col_action1:
        if needs_reanalysis:
             if st.button("🔄 Re-analyze with New Package", key="reanalyze_btn"):
                st.session_state.base_package = new_base_package
                st.session_state.proposed_java_structure = None
                st.session_state.mermaid_diagram = None
                st.session_state.current_state = STATE_ANALYZING
                logger.info("Triggering re-analysis due to base package change.")
                st.rerun()

    with col_action2:
         st.write("") # Spacer
         st.write("") # Spacer for alignment
         proceed_disabled = needs_reanalysis
         button_label = "✅ Confirm and Proceed to Translation"
         if proceed_disabled:
             button_label = "Re-analysis Required Before Proceeding"

         if st.button(button_label, key="confirm_review_btn", type="primary", disabled=proceed_disabled):
             st.session_state.base_package = new_base_package
             st.session_state.current_state = STATE_TRANSLATING
             logger.info("Structure review confirmed. Proceeding to translation.")
             st.rerun()


def handle_translating_state():
    """Performs the code translation based on the reviewed structure."""
    st.header("4. Translating Code")
    st.write("Generating Java project based on the approved structure...")

    required_keys = ['source_dir', 'ruby_structure', 'proposed_java_structure', 'base_package', 'project_name']
    missing_keys = [k for k in required_keys if not st.session_state.get(k)]
    if missing_keys:
        st.error(f"Missing required data for translation: {', '.join(missing_keys)}. Please restart.")
        st.session_state.current_state = STATE_ERROR
        st.session_state.error_message = f"Missing data in translation state: {missing_keys}"
        st.rerun()
        st.stop()

    if st.session_state.get('generated_dir') and os.path.isdir(st.session_state.generated_dir):
        logger.info("Generated directory already exists, proceeding to validation.")
        st.session_state.current_state = STATE_VALIDATING_OUTPUT
        st.rerun()
        st.stop()


    col1, col2 = st.columns([1, 3])
    with col1:
        st.write("Translation Steps:")
        map_status = st.empty()
        gen_status = st.empty()
    with col2:
        progress_bar = st.progress(0)
        status_text = st.empty()

    translation_successful = False
    try:
        map_status.markdown("➡️ Creating File Map")
        status_text.info("Mapping Ruby files to proposed Java structure...")
        logger.info("Creating file mapping...")
        ruby_struct = st.session_state.ruby_structure
        java_struct = st.session_state.proposed_java_structure
        if not isinstance(ruby_struct, dict) or not isinstance(java_struct, dict):
             raise ValueError("Invalid structure types for file mapping.")

        file_mapping = create_file_mapping(
            ruby_struct,
            java_struct,
            st.session_state.base_package
        )
        progress_bar.progress(30)
        map_status.markdown("✅ Creating File Map")

        gen_status.markdown("➡️ Generating Code")
        status_text.info("Generating Java files (this may take time)...")
        logger.info("Starting Java project generation...")
        progress_bar.progress(50)

        generated_project_dir = generate_java_project(
            st.session_state.source_dir,
            file_mapping,
            java_struct,
            ruby_struct,
            st.session_state.base_package,
            st.session_state.project_name
        )
        gen_status.markdown("✅ Generating Code")

        if generated_project_dir and os.path.isdir(generated_project_dir):
            st.session_state.generated_dir = generated_project_dir
            status_text.success("Code translation complete!")
            progress_bar.progress(100)
            translation_successful = True
            logger.info(f"Java project generated at: {generated_project_dir}")
        else:
            status_text.error("Project generation failed to produce a valid directory.")
            logger.error("generate_java_project did not return a valid path.")
            st.session_state.error_message = "Code generation process failed."
            progress_bar.progress(100)

    except Exception as e:
        logger.error(f"Error during translation phase: {e}", exc_info=True)
        status_text.error(f"An error occurred during translation: {e}")
        st.session_state.error_message = f"Translation Error: {e}"
        st.session_state._last_exception = e
        progress_bar.progress(100)

    if translation_successful:
        st.session_state.current_state = STATE_VALIDATING_OUTPUT
        import time; time.sleep(1)
        st.rerun()
    else:
        st.session_state.current_state = STATE_ERROR
        st.rerun()
        st.stop()


def handle_validating_output_state():
    """Handles the validation step - Now modified to always skip Maven validation."""
    st.header("5. Validating Generated Project")
    st.info("Skipping Maven build validation as requested.")

    # Log that we are skipping
    logger.info("Skipping Maven validation step based on configuration/user request.")

    # Set validation_results to indicate skipped state
    if st.session_state.get('validation_results') is None:
        st.session_state.validation_results = {
            "success": True, # Treat as success for workflow progression
            "skipped": True,
            "output": "Maven validation was skipped."
        }

    # Add a button to proceed, even though we skipped
    if st.button("Proceed to Download", type="primary"):
        st.session_state.current_state = STATE_DOWNLOADING
        st.rerun()
    else:
         # Keep showing the skip message until button is pressed
         st.stop()


def handle_downloading_state():
    """Packages the generated project, shows code preview, and provides download link."""
    st.header("6. Download Generated Project")

    generated_dir = st.session_state.get('generated_dir')
    if not generated_dir or not os.path.isdir(generated_dir):
        st.error("Generated project directory not found. Cannot prepare download.")
        st.session_state.current_state = STATE_ERROR
        st.session_state.error_message = "Missing generated directory for download."
        st.rerun()
        st.stop()

    # --- Display Generated Project Tree --- 
    st.subheader("Generated Project Structure")
    try:
        project_name = st.session_state.get("project_name", "generated-project")
        dir_tree_data = build_directory_tree_data(generated_dir, root_name=f"{project_name}-java")
        dir_tree_lines = format_file_tree(dir_tree_data)
        st.code("\n".join(dir_tree_lines), language=None)
    except Exception as e:
        st.error(f"Could not display generated directory tree: {e}")
        logger.error(f"Error formatting directory tree for {generated_dir}: {e}", exc_info=True)

    # --- NEW: Display Generated Java Code Content --- 
    st.markdown("---")
    st.subheader("Generated Code Preview (.java files)")
    java_files_found = []
    generated_path = Path(generated_dir)
    src_main_java = generated_path / "src" / "main" / "java"

    if src_main_java.is_dir():
        try:
            # Use rglob to find all .java files recursively
            for java_file_path in sorted(src_main_java.rglob('*.java')):
                relative_path = java_file_path.relative_to(generated_path).as_posix()
                with st.expander(f"📄 {relative_path}"):
                    try:
                        with open(java_file_path, 'r', encoding='utf-8') as f:
                            file_content = f.read()
                        st.code(file_content, language='java')
                        java_files_found.append(relative_path)
                    except Exception as e:
                        st.error(f"Error reading content of {relative_path}: {e}")
                        logger.warning(f"Could not read content for preview: {java_file_path}, Error: {e}")
        except Exception as e:
            st.error(f"Error scanning for .java files: {e}")
            logger.error(f"Error scanning generated directory {src_main_java} for .java files: {e}", exc_info=True)

    if not java_files_found:
        st.info("No .java files were found in the expected location (src/main/java) to preview.")

    # --- Download Archive Section --- 
    st.markdown("---")
    st.subheader("Download Archive")

    # ZIP Creation and Download Button logic (remains the same)
    zip_data = st.session_state.get('zip_data')
    if isinstance(zip_data, bytes):
        st.download_button(
            label=f"⬇️ Download {st.session_state.project_name}-java.zip",
            data=zip_data,
            file_name=f"{st.session_state.project_name}-java.zip",
            mime="application/zip",
            key="download_btn"
        )
    elif zip_data is False:
         st.error("Failed to create the project ZIP archive.")
         if st.button("Retry Packaging"):
             st.session_state.zip_data = None 
             st.rerun()
    elif zip_data is None:
        with st.spinner("Packaging project into ZIP archive..."):
            logger.info(f"Creating ZIP for {generated_dir}")
            try:
                zip_bytes = create_zip_archive(
                    generated_dir,
                    f"{st.session_state.project_name}-java.zip"
                )
                if zip_bytes:
                    st.session_state.zip_data = zip_bytes
                    logger.info("ZIP archive created successfully.")
                else:
                    st.session_state.zip_data = False
                    logger.error("create_zip_archive returned None.")
            except Exception as e:
                st.session_state.zip_data = False
                logger.error(f"Error creating ZIP archive: {e}", exc_info=True)
                st.error(f"Error creating ZIP: {e}")
                st.session_state._last_exception = e
        st.rerun()

    st.markdown("---")
    if st.button("✨ Start New Transpilation", key="start_over_download_btn"):
        reset_app_state()

def handle_error_state():
    """Displays error messages and provides options to recover."""
    st.header("❌ Application Error")
    error_msg = st.session_state.get("error_message", "An unspecified error occurred.")
    st.error(error_msg)
    last_exception = st.session_state.get("_last_exception")
    if last_exception:
         logger.error(f"Application entered ERROR state: {error_msg}", exc_info=last_exception)
         with st.expander("Show Error Details"):
              st.exception(last_exception)
         st.session_state._last_exception = None
    else:
         logger.error(f"Application entered ERROR state: {error_msg}")


    st.warning("An error interrupted the process. You can try starting over.")
    if st.button("Start Over From Input", key="error_reset_btn"):
        reset_app_state()


# --- Main Application ---

def main():
    """Main function to run the Streamlit app."""
    st.set_page_config(layout="wide", page_title=APP_TITLE)
    st.title(APP_TITLE)
    st.caption("A revamped AI-assisted tool to migrate Rails projects to Spring Boot.")

    initialize_state()

    with st.expander("System Status", expanded=False):
        if st.session_state.maven_present:
             st.info("Maven ('mvn') found. Build validation enabled.", icon="✅")
        else:
             st.warning("Maven ('mvn') not found in PATH. Build validation will be skipped.", icon="⚠️")

    try:
        current_state = st.session_state.current_state

        if current_state == STATE_INPUT:
            handle_input_state()
        elif current_state == STATE_VALIDATING_SOURCE:
            handle_validating_source_state()
        elif current_state == STATE_ANALYZING:
            handle_analyzing_state()
        elif current_state == STATE_REVIEWING:
            handle_reviewing_state()
        elif current_state == STATE_TRANSLATING:
            handle_translating_state()
        elif current_state == STATE_VALIDATING_OUTPUT:
            handle_validating_output_state()
        elif current_state == STATE_DOWNLOADING:
            handle_downloading_state()
        elif current_state == STATE_ERROR:
            handle_error_state()
        else:
            st.error(f"Invalid application state: {current_state}. Resetting.")
            logger.error(f"Reached invalid state {current_state}")
            reset_app_state()

    except Exception as e:
         logger.error(f"Unhandled exception in state {st.session_state.current_state}: {e}", exc_info=True)
         st.session_state.current_state = STATE_ERROR
         st.session_state.error_message = f"Unexpected error occurred: {e}"
         st.session_state._last_exception = e
         st.rerun()


if __name__ == "__main__":
    setup_logging()
    main() 