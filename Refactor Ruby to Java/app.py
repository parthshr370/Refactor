import streamlit as st
import os
import shutil
import tempfile
import zipfile # Need zipfile for extraction logic
from pathlib import Path
from typing import Dict, List # For type hinting
import streamlit.components.v1 as components # Import components
from streamlit_mermaid import st_mermaid # Import the new component
import logging

# Configure logging first
from config.logging_config import setup_logging, logger
setup_logging() # Setup logging defaults

from config import settings
# Make sure necessary utils are imported
from utils.repository_fetcher import fetch_repository, validate_ruby_project # Removed copy_local_directory temporarily
from utils.file_analyzer import analyze_file_structure # Keep for mapping
from utils.structure_mapper import create_file_mapping # Keep for mapping
from utils.code_generator import generate_java_project # Keep for phase 2
from utils.validator import validate_java_project # Keep for phase 2
from utils.output_packager import create_zip_archive # Keep for phase 2
# Import the new agent
from agents.structure_analyzer_agent import analyze_and_propose_structure, list_files_recursive # Import list_files_recursive

# Define TEMP_DIR_PREFIX if not defined elsewhere (e.g., in settings)
# This was assumed in the original ZIP extraction logic
TEMP_DIR_PREFIX = "rjt_app_"

# --- Helper Functions ---

def _is_tool(name):
    """Check whether `name` is on PATH and marked as executable."""
    return shutil.which(name) is not None

def _build_tree_string_recursive(data: Dict, prefix: str = "", is_last: bool = True) -> List[str]:
    """Recursively builds the file tree string list from a nested dict."""
    lines = []
    items = sorted(data.keys())
    # connector = "└── " if is_last else "├── " # Connector logic simplified below
    
    for i, name in enumerate(items):
        is_current_last = (i == len(items) - 1)
        current_connector = "└── " if is_current_last else "├── "
        new_prefix = prefix + ("    " if is_current_last else "│   ")
        
        if isinstance(data[name], dict): # It's a directory
            lines.append(f"{prefix}{current_connector}{name}/")
            # Ensure the child dict is not empty before recursing
            if data[name]:
                lines.extend(_build_tree_string_recursive(data[name], new_prefix, True))
        else: # It's a file (value is None in our reconstructed dict)
            lines.append(f"{prefix}{current_connector}{name}")
            
    return lines

def display_file_tree(structure: Dict[str, List[Dict[str,str]]], streamlit_obj, title: str):
    """Displays a file structure dictionary as a text tree in Streamlit.
    
    Args:
        structure: Dictionary with paths as keys and lists of file data dicts as values
        streamlit_obj: The Streamlit instance to render to (st or a container)
        title: Title to display above the tree
    """
    streamlit_obj.subheader(title)
    if not structure or not isinstance(structure, dict):
        streamlit_obj.write("No files found or structure is empty/invalid.")
        return

    # Build the hierarchical dictionary representation for the tree
    tree_data = {}
    total_files = 0
    for path_str, files_data in structure.items():
        parts = path_str.split('/')
        current_level = tree_data
        for part in parts:
            if part != parts[-1]:
                current_level = current_level.setdefault(part, {})
            else: 
                dir_node = current_level.setdefault(part, {})
                # Add file names to the node, marking them as files (value=None)
                for file_info in files_data:
                    if isinstance(file_info, dict) and 'name' in file_info:
                        dir_node[file_info['name']] = None 
                        total_files += 1
                    else:
                         logger.warning(f"Skipping invalid file data in {path_str}: {file_info}")

    # Generate tree string using the recursive helper
    tree_lines = _build_tree_string_recursive(tree_data) 
    tree_string = "\n".join(tree_lines)

    # Calculate total file count (already done above)
    streamlit_obj.caption(f"Total files: {total_files}")

    # Display using markdown code block
    streamlit_obj.markdown(f"```\n{tree_string}\n```")

def cleanup_temp_dir(dir_path):
    """Safely removes a temporary directory."""
    if dir_path and os.path.exists(dir_path) and dir_path.startswith(tempfile.gettempdir()):
        try:
            shutil.rmtree(dir_path)
            logger.info(f"Cleaned up temporary directory: {dir_path}")
        except Exception as e:
            logger.error(f"Error cleaning up temporary directory {dir_path}: {e}")

def render_mermaid(mermaid_code: str, height: int = 500) -> None:
    """
    Renders a Mermaid diagram directly using Streamlit components.
    This is an alternative to the streamlit-mermaid package.
    
    Args:
        mermaid_code: The Mermaid diagram code
        height: Height of the rendering in pixels
    """
    components.html(
        f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <script src="https://cdn.jsdelivr.net/npm/mermaid@9.3.0/dist/mermaid.min.js"></script>
            <style>
                .mermaid {{
                    font-family: 'Trebuchet MS', 'Lucida Sans Unicode', 'Lucida Grande', 'Lucida Sans', Arial, sans-serif;
                    fill: #333;
                    width: 100%;
                }}
            </style>
        </head>
        <body>
            <pre class="mermaid">
{mermaid_code}
            </pre>
            <script>
                mermaid.initialize({{
                    startOnLoad: true,
                    theme: 'default',
                    securityLevel: 'loose'
                }});
            </script>
        </body>
        </html>
        """,
        height=height,
        scrolling=True
    )

# --- Streamlit App Main Logic ---

def main():
    st.set_page_config(layout="wide", page_title="Ruby to Java Transpiler")
    st.title("💎 Ruby on Rails to Java Spring Boot Transpiler ☕")
    st.caption("An AI-assisted tool to help migrate Rails projects to Spring Boot.")

    # Initialize session state variables
    if 'repo_dir' not in st.session_state:
        st.session_state.repo_dir = None
    if 'ruby_structure' not in st.session_state:
        st.session_state.ruby_structure = None
    if 'parsed_source_files' not in st.session_state:
        st.session_state.parsed_source_files = None # To store the list of source files
    if 'proposed_java_structure_llm' not in st.session_state:
        st.session_state.proposed_java_structure_llm = None
    if 'mermaid_diagram' not in st.session_state:
        st.session_state.mermaid_diagram = None
    if 'base_package' not in st.session_state:
        st.session_state.base_package = settings.DEFAULT_BASE_PACKAGE
    if 'project_name' not in st.session_state:
         st.session_state.project_name = "transpiled-project"
    if 'generated_project_dir' not in st.session_state:
        st.session_state.generated_project_dir = None
    if 'validation_results' not in st.session_state:
        st.session_state.validation_results = None
    if 'zip_path' not in st.session_state: # Store zip path instead of data
        st.session_state.zip_path = None
    if 'current_step' not in st.session_state:
         st.session_state.current_step = "input" # Initial step

    # Check for Maven dependency early on
    if 'maven_checked' not in st.session_state:
        st.session_state.maven_present = _is_tool("mvn")
        st.session_state.maven_checked = True
        if not st.session_state.maven_present:
             st.warning("Maven ('mvn') command not found in PATH. Project validation will be skipped.")

    # --- Input Section ---
    if st.session_state.current_step == "input":
        st.subheader("1. Select Project Source")
        input_method = st.radio(
            "Choose input method:",
            ("GitHub Repository URL", "Upload Local Directory (ZIP)"), # Simplified ZIP option
            horizontal=True,
            key="input_method"
        )

        github_url = ""
        uploaded_zip = None
        analyze_button_pressed = False
        source_description_for_state = None # Store source description

        if input_method == "GitHub Repository URL":
            github_url = st.text_input("Enter public GitHub Repository URL:", key="github_url_input", value=st.session_state.get("github_url_input", ""))
            if github_url:
                analyze_button_pressed = st.button("Analyze Repository", key="analyze_github")
                if analyze_button_pressed:
                    st.session_state.project_name = github_url.split('/')[-1].replace('.git', '') if '/' in github_url else "github-project"
                    source_description_for_state = f"GitHub repo: {github_url}"
                    # --- Trigger Analysis Start ---
                    # Clear previous state
                    logger.info(f"Analyze button pressed for GitHub URL: {github_url}")
                    # ... (clear state variables) ...
                    cleanup_temp_dir(st.session_state.get('repo_dir'))
                    cleanup_temp_dir(st.session_state.get('generated_project_dir'))
                    st.session_state.repo_dir = None
                    st.session_state.ruby_structure = None
                    st.session_state.parsed_source_files = None
                    st.session_state.proposed_java_structure_llm = None
                    st.session_state.mermaid_diagram = None
                    st.session_state.generated_project_dir = None
                    st.session_state.validation_results = None
                    st.session_state.zip_path = None
                    
                    # Fetch immediately
                    with st.spinner(f"Cloning {github_url}..."): 
                        repo_dir_temp, error_msg = fetch_repository(github_url)
                        if error_msg:
                             st.error(f"Error cloning repository: {error_msg}")
                             st.session_state.current_step = "input" # Stay on input
                        elif repo_dir_temp:
                             st.session_state.repo_dir = repo_dir_temp
                             st.session_state.source_description = source_description_for_state # Store description
                             st.session_state.current_step = "validating_source" # Move to new validation step
                             st.rerun()
                        else:
                             st.error("Cloning failed for an unknown reason.")
                             st.session_state.current_step = "input"
                             
        else: # Upload Local Directory (ZIP)
            uploaded_zip = st.file_uploader("Upload your Ruby project as a ZIP file:", type=['zip'], key="zip_uploader")
            if uploaded_zip:
                analyze_button_pressed = st.button("Analyze Uploaded ZIP", key="analyze_zip")
                if analyze_button_pressed:
                    st.session_state.project_name = uploaded_zip.name.replace('.zip', '') or "uploaded-project"
                    source_description_for_state = f"Uploaded ZIP: {uploaded_zip.name}"
                    # --- Trigger Analysis Start ---
                    logger.info(f"Analyze button pressed for Uploaded ZIP: {uploaded_zip.name}")
                    # ... (clear state variables - same as above) ...
                    cleanup_temp_dir(st.session_state.get('repo_dir'))
                    cleanup_temp_dir(st.session_state.get('generated_project_dir'))
                    st.session_state.repo_dir = None
                    st.session_state.ruby_structure = None
                    st.session_state.parsed_source_files = None
                    st.session_state.proposed_java_structure_llm = None
                    st.session_state.mermaid_diagram = None
                    st.session_state.generated_project_dir = None
                    st.session_state.validation_results = None
                    st.session_state.zip_path = None
                    
                    # Extract immediately
                    with st.spinner(f"Extracting {uploaded_zip.name}..."): 
                        temp_extract_base = tempfile.mkdtemp(prefix=TEMP_DIR_PREFIX)
                        repo_dir_temp = None
                        error_msg = None
                        try:
                            with zipfile.ZipFile(uploaded_zip, 'r') as zip_ref:
                                zip_ref.extractall(temp_extract_base)
                            logger.info(f"Successfully extracted ZIP to {temp_extract_base}")
                            extracted_items = os.listdir(temp_extract_base)
                            if len(extracted_items) == 1 and os.path.isdir(os.path.join(temp_extract_base, extracted_items[0])):
                                repo_dir_temp = os.path.join(temp_extract_base, extracted_items[0])
                                logger.info(f"Using single root folder from ZIP: {repo_dir_temp}")
                            else:
                                repo_dir_temp = temp_extract_base
                                logger.info(f"Using extraction root: {temp_extract_base}")
                        except zipfile.BadZipFile:
                            error_msg = "Uploaded file is not a valid ZIP archive."
                            cleanup_temp_dir(temp_extract_base)
                        except Exception as e:
                            error_msg = f"Error extracting ZIP file: {e}"
                            cleanup_temp_dir(temp_extract_base) # Clean up on any extraction error
                            
                        if error_msg:
                             st.error(f"Error extracting ZIP: {error_msg}")
                             st.session_state.current_step = "input"
                        elif repo_dir_temp:
                             st.session_state.repo_dir = repo_dir_temp
                             st.session_state.source_description = source_description_for_state
                             st.session_state.current_step = "validating_source" # Move to validation step
                             st.rerun()
                        else:
                             st.error("Extraction failed for an unknown reason.")
                             st.session_state.current_step = "input"
                             
    # --- Source Validation Step ---
    if st.session_state.current_step == "validating_source":
        st.subheader("Validating Project Source...")
        if not st.session_state.repo_dir:
             st.error("Project source directory not found. Please go back to input.")
             st.session_state.current_step = "input"
             if st.button("Back to Input"): st.rerun()
             st.stop()
             
        with st.spinner("Validating Ruby project structure..."):
             is_ruby, is_rails = validate_ruby_project(st.session_state.repo_dir)
        
        if not is_ruby:
             st.error("The provided source does not appear to be a Ruby project (missing Gemfile or critical .rb files). Please provide a different source.")
             cleanup_temp_dir(st.session_state.repo_dir)
             st.session_state.repo_dir = None
             st.session_state.current_step = "input"
             if st.button("Back to Input"): st.rerun()
             st.stop()
        else:
             st.success(f"Project source validated: {st.session_state.source_description} ({'Rails Application' if is_rails else 'Ruby Project'})")
             st.info("Proceeding to analysis...")
             st.session_state.current_step = "analyzing" # Now move to analysis
             st.rerun()
             
    # --- Analysis Running Section ---
    # This now runs *after* successful validation
    if st.session_state.current_step == "analyzing":
        st.subheader("Analyzing Project...")
        st.markdown("---")
        
        repo_dir_temp = st.session_state.get('repo_dir')
        if not repo_dir_temp:
             # This case should ideally not be reached if validation passed
             st.error("Internal Error: Project directory reference lost after validation.")
             st.session_state.current_step = "input"
             if st.button("Back to Input"): st.rerun()
             st.stop()

        # Display progress during analysis
        analysis_success = False
        progress_bar = st.progress(0)
        status_text = st.empty()

        try:
            status_text.text("Step 1/3: Analyzing Ruby project structure...")
            progress_bar.progress(20)
            logger.info("Running initial Ruby file analysis...")
            
            all_files = list_files_recursive(repo_dir_temp)
            st.session_state.parsed_source_files = all_files # Store for later display
            
            st.session_state.ruby_structure = analyze_file_structure(repo_dir_temp)
            logger.info(f"Ruby analysis complete. Found {len(all_files)} files.")
            
            if not st.session_state.ruby_structure:
                st.warning("Could not identify significant Ruby files/structure for mapping.")

            status_text.text("Step 2/3: Preparing LLM prompt with project analysis...")
            progress_bar.progress(40)
            logger.info("Calling LLM for Java structure proposal...")
            
            status_text.text("Step 3/3: Generating Java structure with LLM (this may take a minute)...")
            progress_bar.progress(60)
            proposed_structure, mermaid_code = analyze_and_propose_structure(
                repo_dir_temp,
                st.session_state.base_package
            )

            if proposed_structure:
                progress_bar.progress(100)
                status_text.text("Analysis complete! Preparing results...")
                st.session_state.proposed_java_structure_llm = proposed_structure
                st.session_state.mermaid_diagram = mermaid_code
                analysis_success = True
                logger.info("LLM analysis successful.")
            else:
                progress_bar.progress(100)
                status_text.text("Analysis failed. See error message below.")
                logger.error("LLM failed to return a valid Java structure.")

        except Exception as e:
            progress_bar.progress(100)
            status_text.text("Error occurred during analysis.")
            logger.error(f"An unexpected error occurred during analysis: {e}", exc_info=True)
            error_msg = f"Analysis Error: {e}"

        # --- Update State Based on Analysis Outcome ---
        if analysis_success:
            st.success("LLM analysis complete. Proceeding to review.")
            st.session_state.current_step = "review_tabs" # Move to the new tabbed review step
            st.rerun()
        else:
            st.error(f"LLM analysis failed. {error_msg or 'Could not generate proposed Java structure. Please check logs.'}")
            st.session_state.current_step = "input" # Go back to input on failure
            if st.button("Back to Input"): st.rerun()
            st.stop() # Stop processing for this run

    # --- Review Section (Tabs) ---
    if st.session_state.current_step == "review_tabs":
        st.subheader("2. Analysis Results & Review")
        st.markdown("---")

        # Ensure necessary data is present
        if not st.session_state.proposed_java_structure_llm or st.session_state.parsed_source_files is None:
            st.error("Missing analysis results. Please re-analyze the project.")
            st.session_state.current_step = "input"
            if st.button("Back to Input"): st.rerun()
            st.stop()
            
        tab_source, tab_tree, tab_viz, tab_summary = st.tabs([
            "Source Files Parsed", 
            "Proposed Tree", 
            "Visualization", 
            "File Summaries"
        ])

        with tab_source:
            st.caption(f"Found {len(st.session_state.parsed_source_files)} files in the source repository.")
            st.text_area("Source Files List", "\n".join(st.session_state.parsed_source_files), height=400)

        with tab_tree:
            # Use st.markdown or similar if needed, but display_file_tree handles subheader
            display_file_tree(st.session_state.proposed_java_structure_llm, st, "Proposed Java File Structure")

        with tab_viz:
            st.caption("Mermaid diagram showing proposed structure relationships.")
            if st.session_state.mermaid_diagram:
                try:
                    # Debug log to see what's in the mermaid diagram
                    logger.debug(f"Mermaid diagram content:\n{st.session_state.mermaid_diagram}")
                    
                    # Add a direct code visualization for confirmation
                    st.code(st.session_state.mermaid_diagram, language="none")
                    
                    # Use st_mermaid component
                    st.subheader("Mermaid Diagram (Component Rendering)")
                    st_mermaid(st.session_state.mermaid_diagram, height="800px") # Pass code and optional height
                    
                    # Keep the raw code text area as fallback/copy source
                    st.text_area(
                        "Mermaid Code (for copying or if rendering fails)", 
                        st.session_state.mermaid_diagram, 
                        height=200, 
                        key="mermaid_raw_code_viz_tab"
                    )
                except Exception as e:
                    st.error(f"Failed to render Mermaid diagram using st_mermaid: {e}")
                    
                    # Try alternative rendering using HTML component
                    st.subheader("Alternative Mermaid Rendering")
                    try:
                        render_mermaid(st.session_state.mermaid_diagram, height=600)
                    except Exception as e_alt:
                        st.error(f"Alternative rendering also failed: {e_alt}")
                    
                    st.text_area("Mermaid Code (Raw - Error)", st.session_state.mermaid_diagram, height=300)
                    
                    # Try rendering a simple test diagram to see if component works at all
                    st.subheader("Testing Mermaid Component with Simple Diagram")
                    try:
                        test_diagram = """graph TD
                            A[Client] --> B[Load Balancer]
                            B --> C[Server1]
                            B --> D[Server2]"""
                        
                        # Try both rendering methods
                        st.write("Using st_mermaid:")
                        st_mermaid(test_diagram, height="300px")
                        
                        st.write("Using custom renderer:")
                        render_mermaid(test_diagram, height=300)
                    except Exception as e_test:
                        st.error(f"Test diagram also failed: {e_test}. This suggests the Mermaid component itself is not working.")
            else:
                st.warning("Mermaid diagram was not generated or provided by the LLM.")

        with tab_summary:
            st.caption("Click on a file path to see its proposed purpose (generated by LLM).")
            sorted_dirs = sorted(st.session_state.proposed_java_structure_llm.keys())
            for dir_path in sorted_dirs:
                files_data = st.session_state.proposed_java_structure_llm[dir_path]
                if files_data:
                    for file_info in files_data:
                        if isinstance(file_info, dict) and 'name' in file_info and 'summary' in file_info:
                            full_path = f"{dir_path}/{file_info['name']}"
                            with st.expander(full_path):
                                 st.markdown(f"**Purpose:** {file_info['summary']}")
                        else:
                            logger.warning(f"Skipping summary display for malformed file info in {dir_path}: {file_info}")

        # --- Options and Actions (Below Tabs) ---
        st.markdown("---")
        st.markdown("#### Options")
        new_base_package = st.text_input(
            "Adjust Base Package Name:",
            value=st.session_state.base_package,
            key="base_package_input",
            help="Changing this requires re-running the analysis."
        )
        if new_base_package != st.session_state.base_package:
            st.session_state.base_package = new_base_package
            st.warning("Base package changed. Click 'Re-analyze' to apply.")
            if st.button("Re-analyze with New Base Package", key="reanalyze"):
                  logger.info("Re-analyze button pressed.")
                  # Need repo_dir to persist
                  if not st.session_state.repo_dir:
                      st.error("Cannot re-analyze: Project directory reference lost. Please start over.")
                      st.session_state.current_step = "input"
                      st.rerun()
                  else:
                      # Clear results and go back to analysis step
                      st.session_state.proposed_java_structure_llm = None
                      st.session_state.mermaid_diagram = None
                      st.session_state.parsed_source_files = None # Also clear parsed files
                      st.session_state.current_step = "analyzing" 
                      logger.info("Triggering re-analysis with new base package...")
                      st.rerun() 

        st.markdown("---")
        st.markdown("#### Actions")
        if st.button("Proceed to Translation", key="proceed_translate"):
            if not st.session_state.repo_dir or not st.session_state.proposed_java_structure_llm or not st.session_state.ruby_structure:
                 st.error("Missing necessary data for translation. Please re-analyze.")
            else:
                  logger.info("Proceeding to translation phase.")
                  st.session_state.current_step = "translating"
                  st.rerun() 

    # --- Translation Section ---
    if st.session_state.current_step == "translating":
        st.subheader("3. Translating Code...")
        st.markdown("---")
        # ... (Keep translation logic, progress bar, etc.) ...
        # Ensure it uses st.session_state.proposed_java_structure_llm and st.session_state.ruby_structure
        if not st.session_state.generated_project_dir: # Only run if not already generated
             # Create a progress bar and status message
             progress_bar = st.progress(0)
             status_text = st.empty()
             
             # Step 1: Create file mappings
             status_text.text("Step 1/4: Creating file mappings...")
             progress_bar.progress(10)
             
             # Explicitly check logger level before mapping
             mapper_logger = logging.getLogger("utils.structure_mapper")
             effective_level_name = logging.getLevelName(mapper_logger.getEffectiveLevel())
             logger.info(f"Effective logging level for 'utils.structure_mapper' before mapping: {effective_level_name}")
             
             # Ensure we have all needed components from previous steps
             if not st.session_state.repo_dir or not st.session_state.proposed_java_structure_llm or not st.session_state.ruby_structure:
                  st.error("Cannot proceed: Missing data from analysis phase. Please go back and re-analyze.")
                  st.session_state.current_step = "review_tabs" # Send back to review
                  st.stop() # Stop execution for this run

             file_mapping = None # Initialize file_mapping
             try:
                 logger.info("Creating file mapping between original Ruby structure and LLM-proposed Java structure.")
                 file_mapping = create_file_mapping(
                     st.session_state.ruby_structure,
                     st.session_state.proposed_java_structure_llm,
                     st.session_state.base_package
                 )
                 if not file_mapping:
                      logger.warning("File mapping is empty. Translation might not produce many files.")
                 
                 # Step 2: Create project structure
                 status_text.text("Step 2/4: Creating Java project directories...")
                 progress_bar.progress(25)

             except Exception as e:
                 progress_bar.progress(100)
                 status_text.text("Error creating file mappings.")
                 logger.error(f"Failed to create file mapping: {e}", exc_info=True)
                 st.error(f"Error creating file mapping: {e}")
                 st.stop()

             # Proceed only if mapping was successful (or empty but no error)
             if file_mapping is not None:
                 try:
                     # Step 3: Translate code
                     status_text.text("Step 3/4: Translating Ruby code to Java (this may take several minutes)...")
                     progress_bar.progress(40)
                     
                     st.session_state.generated_project_dir = generate_java_project(
                         st.session_state.repo_dir,
                         file_mapping,
                         st.session_state.proposed_java_structure_llm,
                         st.session_state.ruby_structure, 
                         st.session_state.base_package,
                         st.session_state.project_name
                     )
                     
                     # Step 4: Complete
                     status_text.text("Step 4/4: Translation complete! Moving to validation...")
                     progress_bar.progress(100)
                     
                     # Ensure project dir is set on success
                     if st.session_state.generated_project_dir:
                          logger.info(f"Project generation successful: {st.session_state.generated_project_dir}")
                          st.session_state.current_step = "validation" # Move to validation
                          st.rerun() # Rerun immediately to trigger validation
                     else: 
                          progress_bar.progress(100)
                          status_text.text("Project generation function failed to return a path.")
                          logger.error("generate_java_project returned None")
                          st.error("Project generation process failed.")
                          # Consider where to go - back to review? Stay here?
                          st.session_state.current_step = "review_tabs"
                          if st.button("Back to Review"): st.rerun()
                          st.stop()
                          
                 except Exception as e:
                     progress_bar.progress(100)
                     status_text.text("Error during project generation.")
                     logger.error(f"Error during project generation: {e}", exc_info=True)
                     st.error(f"Project generation failed: {e}")
                     st.session_state.generated_project_dir = None # Ensure it's None on failure
                     st.session_state.current_step = "review_tabs"
                     if st.button("Back to Review"): st.rerun()
                     st.stop()
             
        else: # Project already generated, proceed to validation
             logger.info("Project already generated, moving to validation step.")
             st.session_state.current_step = "validation"
             st.rerun()

    # --- Validation Section ---
    if st.session_state.current_step == "validation":
        st.subheader("4. Validation")
        if not st.session_state.generated_project_dir:
             st.warning("Cannot validate: Generated project directory not found.")
             st.session_state.current_step = "translating" # Go back if dir missing
             st.rerun()
        else:
             # Run validation only once
             if st.session_state.validation_results is None:
                  if st.session_state.maven_present:
                      with st.spinner("Attempting to compile the generated Java project using Maven... (This might take a while)"):
                          success, output = validate_java_project(st.session_state.generated_project_dir)
                          st.session_state.validation_results = {"success": success, "output": output}
                  else:
                      logger.warning("Skipping Maven validation because 'mvn' was not found.")
                      st.warning("Skipping Maven compilation check because 'mvn' command was not found.")
                      # Set results to indicate skipped validation but allow proceeding
                      st.session_state.validation_results = {"success": True, "output": "Maven validation skipped (mvn not found).", "skipped": True}
                  st.rerun() # Rerun to display results
             else:
                  # Display validation results
                  val_results = st.session_state.validation_results
                  if val_results.get("skipped"):
                       st.info(val_results["output"])
                  elif val_results["success"]:
                       st.success("Maven compilation successful!")
                  else:
                       st.error("Maven compilation failed.")
                       st.text_area("Maven Output:", val_results["output"], height=300)

                  # Move to download step regardless of validation outcome
                  st.session_state.current_step = "download"
                  st.rerun()

    # --- Download Section --- 
    if st.session_state.current_step == "download":
        st.subheader("5. Download")
        if not st.session_state.generated_project_dir:
             st.warning("Cannot prepare download: Generated project directory not found.")
             st.session_state.current_step = "validation" # Go back if dir missing
             st.rerun()
        else:
            # Prepare ZIP only once
            # Revert to storing zip data in memory for reliability across reruns
            if 'zip_data' not in st.session_state:
                 st.session_state.zip_data = None # Initialize
                 with st.spinner("Packaging generated project into a ZIP file..."):
                     zip_path = None
                     temp_zip_dir = None # Initialize temp_zip_dir
                     try:
                         # Create zip in a temporary path first
                         temp_zip_dir = tempfile.mkdtemp()
                         zip_basename = f"{st.session_state.project_name}-java.zip"
                         zip_path = os.path.join(temp_zip_dir, zip_basename)
                         
                         logger.info(f"Attempting to create ZIP at: {zip_path}") # Add log
                         # This function returns BYTES, not the path
                         zip_data_bytes = create_zip_archive(
                            st.session_state.generated_project_dir, 
                            # output_filename argument is just for metadata in the function
                            f"{st.session_state.project_name}-java.zip" 
                         )
                         # Check if bytes were returned
                         if zip_data_bytes:
                              st.session_state.zip_data = zip_data_bytes # Store the bytes
                              logger.info(f"ZIP data ({len(st.session_state.zip_data)} bytes) read into session state.")
                         else:
                             logger.error("create_zip_archive function returned None, indicating failure.")
                             st.error("Failed to create ZIP archive.")
                             st.session_state.zip_data = False # Indicate creation failure
                     except Exception as e:
                         logger.error(f"Error creating or reading ZIP archive: {e}", exc_info=True)
                         st.error(f"Failed to create or read ZIP archive: {e}")
                         st.session_state.zip_data = False # Indicate exception failure
                     finally:
                         # Clean up the temporary zip file and dir immediately after reading/failing
                         if zip_path and os.path.exists(zip_path):
                             try:
                                 os.remove(zip_path)
                                 logger.debug(f"Removed temporary ZIP file: {zip_path}")
                             except OSError as clean_e:
                                 logger.warning(f"Could not remove temporary ZIP {zip_path}: {clean_e}")
                         if temp_zip_dir and os.path.exists(temp_zip_dir):
                             try:
                                 os.rmdir(temp_zip_dir) # Remove temp dir if empty
                                 logger.debug(f"Removed temporary ZIP directory: {temp_zip_dir}")
                             except OSError as clean_e:
                                 logger.warning(f"Could not remove temporary ZIP directory {temp_zip_dir}: {clean_e}")
                                 
                 # Only rerun if zip_data is still None (meaning spinner is still active)
                 # If it's True (bytes) or False (error), we let the next part render
                 if st.session_state.zip_data is None:
                     st.rerun() 

            # Display download button or error message
            if isinstance(st.session_state.zip_data, bytes) and st.session_state.zip_data:
                 st.download_button(
                     label="Download Generated Java Project (.zip)",
                     data=st.session_state.zip_data,
                     file_name=f"{st.session_state.project_name}-java.zip",
                     mime="application/zip",
                     key="download_zip"
                 )
            elif st.session_state.zip_data is False:
                 st.error("Could not prepare the project for download (ZIP creation failed previously).")
            elif st.session_state.zip_data is None:
                 # This happens if the rerun occurred before data was set, should resolve on next rerun
                 st.info("Preparing download...") 
            else:
                 # Should not happen
                 st.error("Unexpected state while preparing download.")

if __name__ == "__main__":
    # Ensure logger is set up before running main
    if not logger.handlers:
         setup_logging()
    main()
