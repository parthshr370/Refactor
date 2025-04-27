import streamlit as st
import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import streamlit.components.v1 as components
import logging
from streamlit_mermaid import st_mermaid  # Import the streamlit-mermaid component

# Configure logging
from config.logging_config import setup_logging, logger
setup_logging()

# Import necessary utilities
from config import settings
from utils.repository_fetcher import fetch_repository, validate_ruby_project
from utils.file_analyzer import analyze_file_structure
from utils.structure_mapper import create_file_mapping
from utils.code_generator import generate_java_project
from utils.validator import validate_java_project
from utils.output_packager import create_zip_archive
from agents.structure_analyzer_agent import analyze_and_propose_structure, list_files_recursive

# Constants
TEMP_DIR_PREFIX = "rjt_app_"

# Helper Functions
def is_tool_available(name: str) -> bool:
    """Check if a command-line tool is available in PATH."""
    return shutil.which(name) is not None

def build_tree_structure(structure: Dict[str, List[Dict[str, str]]]) -> Dict:
    """Builds a hierarchical tree structure for display."""
    tree_data = {}
    for path_str, files_data in structure.items():
        parts = path_str.split('/')
        current_level = tree_data
        for part in parts[:-1]:  # Process all but the last part (directory)
            current_level = current_level.setdefault(part, {})
        
        # Process the last part (directory) and its files
        dir_name = parts[-1]
        dir_node = current_level.setdefault(dir_name, {})
        
        # Add files to the directory
        for file_info in files_data:
            if isinstance(file_info, dict) and 'name' in file_info:
                dir_node[file_info['name']] = None  # Files are marked with None value
    
    return tree_data

def format_tree_display(tree_data: Dict, prefix: str = "") -> List[str]:
    """Formats a tree structure for pretty-printing."""
    lines = []
    items = sorted(tree_data.keys())
    
    for i, name in enumerate(items):
        is_last = (i == len(items) - 1)
        connector = "└── " if is_last else "├── "
        new_prefix = prefix + ("    " if is_last else "│   ")
        
        if isinstance(tree_data[name], dict) and tree_data[name]:  # Directory with contents
            lines.append(f"{prefix}{connector}{name}/")
            lines.extend(format_tree_display(tree_data[name], new_prefix))
        else:  # File
            lines.append(f"{prefix}{connector}{name}")
    
    return lines

def display_file_tree(structure: Dict[str, List[Dict[str, str]]], container, title: str = "File Structure"):
    """Displays a file tree structure in a Streamlit container."""
    container.subheader(title)
    
    if not structure or not isinstance(structure, dict):
        container.write("No files found or structure is empty.")
        return
    
    tree_data = build_tree_structure(structure)
    tree_lines = format_tree_display(tree_data)
    tree_string = "\n".join(tree_lines)
    
    # Count total files
    total_files = sum(len(files) for files in structure.values())
    container.caption(f"Total files: {total_files}")
    
    # Display tree in a code block
    container.code(tree_string, language=None)

def render_mermaid_diagram(diagram_code: str, height: int = 600, use_st_mermaid: bool = True) -> None:
    """
    Renders a Mermaid diagram with streamlit-mermaid or using HTML embedding as fallback.
    
    Args:
        diagram_code: The Mermaid diagram code to render
        height: Height of the diagram in pixels
        use_st_mermaid: Whether to try using streamlit-mermaid first
    """
    # Clean up the diagram code
    diagram_code = diagram_code.strip()
    
    if use_st_mermaid:
        try:
            # First attempt with streamlit-mermaid
            st_mermaid(diagram_code, height=f"{height}px")
            return
        except Exception as e:
            st.warning(f"streamlit-mermaid failed to render: {e}. Using HTML fallback.")
            logger.warning(f"streamlit-mermaid rendering failed: {e}")
    
    # Fallback to HTML rendering
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <script src="https://cdn.jsdelivr.net/npm/mermaid@9.3.0/dist/mermaid.min.js"></script>
        <style>
            .mermaid {{
                font-family: sans-serif;
                margin: 0 auto;
                width: 100%;
            }}
        </style>
    </head>
    <body>
        <pre class="mermaid">
{diagram_code}
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
    """
    
    # Use direct HTML component rendering
    components.html(html, height=height, scrolling=True)

def cleanup_temp_dir(dir_path: str) -> None:
    """Safely cleans up a temporary directory."""
    if dir_path and os.path.exists(dir_path) and dir_path.startswith(tempfile.gettempdir()):
        try:
            shutil.rmtree(dir_path)
            logger.info(f"Cleaned up temporary directory: {dir_path}")
        except Exception as e:
            logger.error(f"Error cleaning up temporary directory {dir_path}: {e}")

def initialize_session_state():
    """Initialize Streamlit session state variables if they don't exist."""
    # Project state
    if 'repo_dir' not in st.session_state:
        st.session_state.repo_dir = None
    if 'ruby_structure' not in st.session_state:
        st.session_state.ruby_structure = None
    if 'parsed_source_files' not in st.session_state:
        st.session_state.parsed_source_files = None
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
    if 'zip_data' not in st.session_state:
        st.session_state.zip_data = None
    
    # Workflow state
    if 'current_step' not in st.session_state:
        st.session_state.current_step = "input"
    
    # Tool availability
    if 'maven_checked' not in st.session_state:
        st.session_state.maven_present = is_tool_available("mvn")
        st.session_state.maven_checked = True

def clear_project_state():
    """Clear project-related session state for a fresh start."""
    cleanup_temp_dir(st.session_state.get('repo_dir'))
    cleanup_temp_dir(st.session_state.get('generated_project_dir'))
    
    st.session_state.repo_dir = None
    st.session_state.ruby_structure = None
    st.session_state.parsed_source_files = None
    st.session_state.proposed_java_structure_llm = None
    st.session_state.mermaid_diagram = None
    st.session_state.generated_project_dir = None
    st.session_state.validation_results = None
    st.session_state.zip_data = None

def process_github_input(github_url: str):
    """Process GitHub repository URL input."""
    st.session_state.project_name = github_url.split('/')[-1].replace('.git', '') if '/' in github_url else "github-project"
    source_description = f"GitHub repo: {github_url}"
    
    # Clear previous state
    clear_project_state()
    logger.info(f"Analyze button pressed for GitHub URL: {github_url}")
    
    # Fetch repository
    with st.spinner(f"Cloning {github_url}..."):
        repo_dir_temp, error_msg = fetch_repository(github_url)
        
        if error_msg:
            st.error(f"Error cloning repository: {error_msg}")
            st.session_state.current_step = "input"
        elif repo_dir_temp:
            st.session_state.repo_dir = repo_dir_temp
            st.session_state.source_description = source_description
            st.session_state.current_step = "validating_source"
            st.rerun()
        else:
            st.error("Cloning failed for an unknown reason.")
            st.session_state.current_step = "input"

def process_zip_input(uploaded_zip):
    """Process uploaded ZIP file input."""
    st.session_state.project_name = uploaded_zip.name.replace('.zip', '') or "uploaded-project"
    source_description = f"Uploaded ZIP: {uploaded_zip.name}"
    
    # Clear previous state
    clear_project_state()
    logger.info(f"Analyze button pressed for Uploaded ZIP: {uploaded_zip.name}")
    
    # Extract ZIP
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
            cleanup_temp_dir(temp_extract_base)
            
        if error_msg:
            st.error(f"Error extracting ZIP: {error_msg}")
            st.session_state.current_step = "input"
        elif repo_dir_temp:
            st.session_state.repo_dir = repo_dir_temp
            st.session_state.source_description = source_description
            st.session_state.current_step = "validating_source"
            st.rerun()
        else:
            st.error("Extraction failed for an unknown reason.")
            st.session_state.current_step = "input"

def validate_source():
    """Validate that the source is a Ruby/Rails project."""
    if not st.session_state.repo_dir:
        st.error("Project source directory not found. Please go back to input.")
        st.session_state.current_step = "input"
        if st.button("Back to Input"):
            st.rerun()
        st.stop()
    
    with st.spinner("Validating Ruby project structure..."):
        is_ruby, is_rails = validate_ruby_project(st.session_state.repo_dir)
    
    if not is_ruby:
        st.error("The provided source does not appear to be a Ruby project (missing Gemfile or critical .rb files). Please provide a different source.")
        cleanup_temp_dir(st.session_state.repo_dir)
        st.session_state.repo_dir = None
        st.session_state.current_step = "input"
        if st.button("Back to Input"):
            st.rerun()
        st.stop()
    else:
        st.success(f"Project source validated: {st.session_state.source_description} ({'Rails Application' if is_rails else 'Ruby Project'})")
        st.info("Proceeding to analysis...")
        st.session_state.current_step = "analyzing"
        st.rerun()

def analyze_project():
    """Analyze the Ruby project structure and generate a proposed Java structure."""
    repo_dir_temp = st.session_state.get('repo_dir')
    if not repo_dir_temp:
        st.error("Internal Error: Project directory reference lost after validation.")
        st.session_state.current_step = "input"
        if st.button("Back to Input"):
            st.rerun()
        st.stop()
    
    # Display progress
    analysis_success = False
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    try:
        # Step 1: Analyze Ruby structure
        status_text.text("Step 1/3: Analyzing Ruby project structure...")
        progress_bar.progress(20)
        logger.info("Running initial Ruby file analysis...")
        
        all_files = list_files_recursive(repo_dir_temp)
        st.session_state.parsed_source_files = all_files
        
        st.session_state.ruby_structure = analyze_file_structure(repo_dir_temp)
        logger.info(f"Ruby analysis complete. Found {len(all_files)} files.")
        
        # Step 2: Prepare for LLM analysis
        status_text.text("Step 2/3: Preparing LLM prompt with project analysis...")
        progress_bar.progress(40)
        logger.info("Calling LLM for Java structure proposal...")
        
        # Step 3: LLM-based structure proposal
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
        st.error(f"LLM analysis failed. {error_msg}")
    
    # Update state based on analysis outcome
    if analysis_success:
        st.success("LLM analysis complete. Proceeding to review.")
        st.session_state.current_step = "review"
        st.rerun()
    else:
        st.error("Could not generate proposed Java structure. Please check logs.")
        st.session_state.current_step = "input"
        if st.button("Back to Input"):
            st.rerun()
        st.stop()

def display_analysis_results():
    """Display the results of the analysis with tabs."""
    if not st.session_state.proposed_java_structure_llm or st.session_state.parsed_source_files is None:
        st.error("Missing analysis results. Please re-analyze the project.")
        st.session_state.current_step = "input"
        if st.button("Back to Input"):
            st.rerun()
        st.stop()
    
    # Create tabs for different views
    tab_source, tab_tree, tab_viz, tab_summary = st.tabs([
        "Source Files", 
        "Proposed Structure", 
        "Visualization", 
        "File Summaries"
    ])
    
    # Tab 1: Source Files
    with tab_source:
        st.caption(f"Found {len(st.session_state.parsed_source_files)} files in the source repository.")
        st.text_area("Source Files List", "\n".join(st.session_state.parsed_source_files), height=400)
    
    # Tab 2: Proposed Structure Tree
    with tab_tree:
        display_file_tree(st.session_state.proposed_java_structure_llm, st, "Proposed Java File Structure")
    
    # Tab 3: Mermaid Visualization
    with tab_viz:
        st.subheader("Structure Visualization")
        
        if st.session_state.mermaid_diagram:
            # Display the raw code for verification
            with st.expander("Mermaid Code"):
                st.code(st.session_state.mermaid_diagram, language=None)
            
            # Render the diagram with streamlit-mermaid first, fallback to HTML if needed
            try:
                logger.debug(f"Rendering Mermaid diagram:\n{st.session_state.mermaid_diagram}")
                render_mermaid_diagram(st.session_state.mermaid_diagram, height=600, use_st_mermaid=True)
            except Exception as e:
                st.error(f"Failed to render Mermaid diagram: {e}")
                
                # Try with a simple test diagram to debug
                st.subheader("Test Diagram")
                test_diagram = """graph TD
                    A[Client] --> B[Load Balancer]
                    B --> C[Server1]
                    B --> D[Server2]"""
                
                try:
                    st.write("Using streamlit-mermaid:")
                    st_mermaid(test_diagram, height="300px")
                    st.write("Using HTML fallback:")
                    render_mermaid_diagram(test_diagram, height=300, use_st_mermaid=False)
                except Exception as e_test:
                    st.error(f"Test diagram also failed: {e_test}")
        else:
            st.warning("No Mermaid diagram was generated or provided by the LLM.")
    
    # Tab 4: File Summaries
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
                        logger.warning(f"Skipping summary display for malformed file info in {dir_path}")
    
    # Options and Actions
    st.markdown("---")
    
    # Base package adjustment
    st.subheader("Options")
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
            
            if not st.session_state.repo_dir:
                st.error("Cannot re-analyze: Project directory reference lost. Please start over.")
                st.session_state.current_step = "input"
                st.rerun()
            else:
                # Clear results and go back to analysis step
                st.session_state.proposed_java_structure_llm = None
                st.session_state.mermaid_diagram = None
                st.session_state.parsed_source_files = None
                st.session_state.current_step = "analyzing"
                logger.info("Triggering re-analysis with new base package...")
                st.rerun()
    
    # Proceed to translation
    st.markdown("---")
    st.subheader("Actions")
    
    if st.button("Proceed to Translation", key="proceed_translate"):
        if not st.session_state.repo_dir or not st.session_state.proposed_java_structure_llm or not st.session_state.ruby_structure:
            st.error("Missing necessary data for translation. Please re-analyze.")
        else:
            logger.info("Proceeding to translation phase.")
            st.session_state.current_step = "translating"
            st.rerun()

def translate_code():
    """Handle the code translation process."""
    if not st.session_state.generated_project_dir:  # Only run if not already generated
        # Create progress tracking
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # Step 1: Create file mappings
        status_text.text("Step 1/4: Creating file mappings...")
        progress_bar.progress(10)
        
        mapper_logger = logging.getLogger("utils.structure_mapper")
        effective_level_name = logging.getLevelName(mapper_logger.getEffectiveLevel())
        logger.info(f"Effective logging level for 'utils.structure_mapper': {effective_level_name}")
        
        # Ensure we have all needed components
        if not st.session_state.repo_dir or not st.session_state.proposed_java_structure_llm or not st.session_state.ruby_structure:
            st.error("Cannot proceed: Missing data from analysis phase. Please go back and re-analyze.")
            st.session_state.current_step = "review"
            st.stop()
        
        file_mapping = None
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
        
        # Proceed only if mapping was successful
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
                    st.session_state.current_step = "validation"
                    st.rerun()
                else:
                    progress_bar.progress(100)
                    status_text.text("Project generation function failed to return a path.")
                    logger.error("generate_java_project returned None")
                    st.error("Project generation process failed.")
                    st.session_state.current_step = "review"
                    if st.button("Back to Review"):
                        st.rerun()
                    st.stop()
                    
            except Exception as e:
                progress_bar.progress(100)
                status_text.text("Error during project generation.")
                logger.error(f"Error during project generation: {e}", exc_info=True)
                st.error(f"Project generation failed: {e}")
                st.session_state.generated_project_dir = None
                st.session_state.current_step = "review"
                if st.button("Back to Review"):
                    st.rerun()
                st.stop()
    
    else:  # Project already generated
        logger.info("Project already generated, moving to validation step.")
        st.session_state.current_step = "validation"
        st.rerun()

def validate_project():
    """Validate the generated Java project."""
    if not st.session_state.generated_project_dir:
        st.warning("Cannot validate: Generated project directory not found.")
        st.session_state.current_step = "translating"
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
                st.session_state.validation_results = {
                    "success": True,
                    "output": "Maven validation skipped (mvn not found).",
                    "skipped": True
                }
            st.rerun()
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
            
            # Move to download step
            st.session_state.current_step = "download"
            st.rerun()

def prepare_download():
    """Prepare the project for download."""
    if not st.session_state.generated_project_dir:
        st.warning("Cannot prepare download: Generated project directory not found.")
        st.session_state.current_step = "validation"
        st.rerun()
    else:
        # Prepare ZIP only once
        if st.session_state.zip_data is None:
            with st.spinner("Packaging generated project into a ZIP file..."):
                try:
                    logger.info(f"Creating ZIP archive for {st.session_state.generated_project_dir}")
                    zip_data_bytes = create_zip_archive(
                        st.session_state.generated_project_dir,
                        f"{st.session_state.project_name}-java.zip"
                    )
                    
                    if zip_data_bytes:
                        st.session_state.zip_data = zip_data_bytes
                        logger.info(f"ZIP data ({len(st.session_state.zip_data)} bytes) read into session state.")
                    else:
                        logger.error("create_zip_archive function returned None, indicating failure.")
                        st.error("Failed to create ZIP archive.")
                        st.session_state.zip_data = False  # Indicate creation failure
                        
                except Exception as e:
                    logger.error(f"Error creating or reading ZIP archive: {e}", exc_info=True)
                    st.error(f"Failed to create or read ZIP archive: {e}")
                    st.session_state.zip_data = False  # Indicate exception failure
            
            # Only rerun if zip_data is still None (spinner still active)
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
            
            # Add option to start over
            if st.button("Start New Project", key="start_new"):
                clear_project_state()
                st.session_state.current_step = "input"
                st.rerun()
                
        elif st.session_state.zip_data is False:
            st.error("Could not prepare the project for download (ZIP creation failed).")
            
            if st.button("Try Again", key="retry_zip"):
                st.session_state.zip_data = None  # Reset to try again
                st.rerun()
                
            if st.button("Back to Validation", key="back_to_validation"):
                st.session_state.current_step = "validation"
                st.rerun()
                
        else:
            # This happens if the rerun occurred before data was set
            st.info("Preparing download...")

def configure_app_logging():
    """Configure application-specific logging settings."""
    # Configure less verbose logging for specific modules
    logging.getLogger("streamlit").setLevel(logging.WARNING)
    
    # Only set debug for critical app components if needed
    # For example, if troubleshooting structure analysis:
    # logging.getLogger("agents.structure_analyzer_agent").setLevel(logging.DEBUG)

def main():
    """Main function that runs the Streamlit app."""
    # Set up page
    st.set_page_config(layout="wide", page_title="Ruby to Java Transpiler")
    st.title("💎 Ruby on Rails to Java Spring Boot Transpiler ☕")
    st.caption("An AI-assisted tool to help migrate Rails projects to Spring Boot.")
    
    # Initialize logging and session state
    configure_app_logging()
    initialize_session_state()
    
    # Show Maven warning if needed
    if not st.session_state.maven_present:
        st.warning("Maven ('mvn') command not found in PATH. Project validation will be skipped.")
    
    # Main workflow based on current step
    if st.session_state.current_step == "input":
        st.subheader("1. Select Project Source")
        
        input_method = st.radio(
            "Choose input method:",
            ("GitHub Repository URL", "Upload Local Directory (ZIP)"),
            horizontal=True,
            key="input_method"
        )
        
        if input_method == "GitHub Repository URL":
            github_url = st.text_input(
                "Enter public GitHub Repository URL:",
                key="github_url_input",
                value=st.session_state.get("github_url_input", "")
            )
            
            if github_url and st.button("Analyze Repository", key="analyze_github"):
                process_github_input(github_url)
                
        else:  # Upload ZIP
            uploaded_zip = st.file_uploader(
                "Upload your Ruby project as a ZIP file:",
                type=['zip'],
                key="zip_uploader"
            )
            
            if uploaded_zip and st.button("Analyze Uploaded ZIP", key="analyze_zip"):
                process_zip_input(uploaded_zip)
    
    elif st.session_state.current_step == "validating_source":
        st.subheader("Validating Project Source...")
        validate_source()
    
    elif st.session_state.current_step == "analyzing":
        st.subheader("Analyzing Project...")
        st.markdown("---")
        analyze_project()
    
    elif st.session_state.current_step == "review":
        st.subheader("2. Analysis Results & Review")
        st.markdown("---")
        display_analysis_results()
    
    elif st.session_state.current_step == "translating":
        st.subheader("3. Translating Code...")
        st.markdown("---")
        translate_code()
    
    elif st.session_state.current_step == "validation":
        st.subheader("4. Validation")
        validate_project()
    
    elif st.session_state.current_step == "download":
        st.subheader("5. Download")
        prepare_download()
    
    else:
        st.error(f"Unknown step: {st.session_state.current_step}")
        st.session_state.current_step = "input"
        st.rerun()

if __name__ == "__main__":
    # Ensure logger is set up before running
    setup_logging()
    main()
