import os
import shutil
import tempfile
from pathlib import Path
from string import Template
from typing import Dict

from config.logging_config import logger
from config.settings import TEMP_DIR_PREFIX, DEFAULT_BASE_PACKAGE
from agents.translator_agent import translate_ruby_to_java # We need the translator here

# --- Template Loading --- 

_TEMPLATE_DIR = Path(__file__).parent.parent / "templates"

def _load_template(template_name: str) -> Template | None:
    """Loads a template file from the templates directory."""
    template_path = _TEMPLATE_DIR / template_name
    try:
        with open(template_path, 'r', encoding='utf-8') as f:
            return Template(f.read())
    except FileNotFoundError:
        logger.error(f"Template file not found: {template_path}")
        return None
    except Exception as e:
        logger.error(f"Error loading template {template_name}: {e}")
        return None

# Pre-load common templates
_POM_TEMPLATE = _load_template("pom_template.xml")
_APP_TEMPLATE = _load_template("application_template.java")
# We no longer use these template files as we now use LLM for code generation
# _MODEL_TEMPLATE = _load_template("model_template.java")
# _REPO_TEMPLATE = _load_template("repository_template.java") 
# _CONTROLLER_TEMPLATE = _load_template("controller_template.java")

# --- Directory and File Creation --- 

def create_project_structure(output_dir: str, java_structure: dict):
    """Creates the directory structure for the Java project."""
    logger.info(f"Creating Java project structure in: {output_dir}")
    for path_key in java_structure.keys():
        dir_path = Path(output_dir) / path_key
        try:
            dir_path.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Created directory: {dir_path}")
        except OSError as e:
            logger.error(f"Failed to create directory {dir_path}: {e}")
            raise # Re-raise to signal failure

def _write_file(file_path: Path, content: str):
    """Writes content to a file, creating parent directories if needed."""
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        logger.debug(f"Successfully wrote file: {file_path}")
    except IOError as e:
        logger.error(f"Failed to write file {file_path}: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred writing file {file_path}: {e}")

def _generate_pom_xml(output_dir: str, base_package: str, artifact_id: str):
    """Generates the pom.xml file from the template."""
    if not _POM_TEMPLATE:
        logger.error("POM template not loaded. Cannot generate pom.xml.")
        return
    logger.info("Generating pom.xml")
    pom_content = _POM_TEMPLATE.safe_substitute(
        base_package=base_package,
        artifact_id=artifact_id
    )
    _write_file(Path(output_dir) / "pom.xml", pom_content)

def _generate_main_application(output_dir: str, base_package: str):
    """Generates the main Spring Boot Application.java file."""
    if not _APP_TEMPLATE:
        logger.error("Application template not loaded. Cannot generate Application.java.")
        return
    logger.info("Generating Application.java")
    app_content = _APP_TEMPLATE.safe_substitute(base_package=base_package)
    base_path = base_package.replace('.', '/')
    app_path = Path(output_dir) / "src/main/java" / base_path / "Application.java"
    _write_file(app_path, app_content)

def _generate_application_properties(output_dir: str):
     """Generates a basic application.properties file."""
     logger.info("Generating application.properties")
     props_content = (
         "# Basic Spring Boot Properties\n"
         "server.port=8080\n\n"
         "# H2 Database Configuration (for development/testing)\n"
         "spring.datasource.url=jdbc:h2:mem:testdb\n"
         "spring.datasource.driverClassName=org.h2.Driver\n"
         "spring.datasource.username=sa\n"
         "spring.datasource.password=\n"
         "spring.jpa.database-platform=org.hibernate.dialect.H2Dialect\n"
         "# Create/update tables on startup (use 'validate' or 'none' in production)\n"
         "spring.jpa.hibernate.ddl-auto=update\n"
         "spring.h2.console.enabled=true\n" # Enable H2 console at /h2-console
     )
     props_path = Path(output_dir) / "src/main/resources" / "application.properties"
     _write_file(props_path, props_content)

# --- Main Generation Function --- 

def generate_java_project(
    ruby_repo_dir: str, 
    file_mapping: dict, 
    java_structure: dict, 
    ruby_structure: dict,
    base_package: str,
    project_name: str = "transpiled-project"
) -> str | None:
    """Generates the complete Java project directory with translated files.

    Args:
        ruby_repo_dir: Path to the original Ruby project source.
        file_mapping: Dictionary mapping Ruby file paths to Java file info.
        java_structure: Dictionary representing the target Java structure.
        ruby_structure: Dictionary representing the analyzed Ruby structure (for asset paths).
        base_package: The base package for the Java code.
        project_name: The base name for the output directory and artifact ID.

    Returns:
        The path to the generated Java project directory, or None on failure.
    """
    output_parent_dir = tempfile.mkdtemp(prefix=TEMP_DIR_PREFIX)
    output_dir = Path(output_parent_dir) / project_name
    logger.info(f"Starting Java project generation in {output_dir}")

    try:
        # 1. Create basic directory structure
        create_project_structure(str(output_dir), java_structure)

        # 2. Generate standard Maven/Spring Boot files
        _generate_pom_xml(str(output_dir), base_package, project_name)
        _generate_main_application(str(output_dir), base_package)
        _generate_application_properties(str(output_dir))

        # 3. Translate and write Java files based on mapping
        total_files = len(file_mapping)
        translated_count = 0
        failed_count = 0
        for i, (ruby_path, java_info) in enumerate(file_mapping.items()):
            logger.info(f"Processing file {i+1}/{total_files}: {ruby_path} -> {java_info.get('java_path', 'N/A')}")
            
            # Skip files without a target Java path (e.g., views mapped to templates)
            if not java_info.get('java_path') or not java_info.get('class_name'):
                logger.debug(f"Skipping translation for {ruby_path} (no direct Java class target).")
                continue
                
            full_ruby_path = Path(ruby_repo_dir) / ruby_path
            java_target_path = Path(output_dir) / java_info['java_path']

            try:
                # Read Ruby file content
                with open(full_ruby_path, 'r', encoding='utf-8', errors='ignore') as f:
                    ruby_code = f.read()
            except Exception as e:
                logger.error(f"Error reading Ruby file {full_ruby_path}: {e}")
                failed_count += 1
                continue
                
            # Translate using the translator agent
            java_code = translate_ruby_to_java(ruby_code, java_info, base_package)

            if java_code:
                _write_file(java_target_path, java_code)
                translated_count += 1
            else:
                logger.warning(f"Translation failed for {ruby_path}, skipping file generation for {java_info['java_path']}.")
                failed_count += 1
        
        logger.info(f"Translation and generation summary: {translated_count} successful, {failed_count} failed.")

        # 4. Copy static assets (CSS, JS, Images) and templates (HTML)
        logger.info("Copying static assets and templates...")

        # Define mapping from ruby_structure keys to Java static directories
        asset_category_mapping: Dict[str, str] = {}
        asset_category_mapping["assets_js"] = "src/main/resources/static/js"
        asset_category_mapping["assets_css"] = "src/main/resources/static/css"
        asset_category_mapping["assets_images"] = "src/main/resources/static/images"
        asset_category_mapping["assets_fonts"] = "src/main/resources/static/fonts"
        asset_category_mapping["assets_others"] = "src/main/resources/static/vendor"

        for ruby_category, java_target_dir_rel_str in asset_category_mapping.items():
            if ruby_category in ruby_structure:
                # Convert relative path string to Path object
                java_target_dir_rel = Path(java_target_dir_rel_str)
                java_target_dir_abs = output_dir / java_target_dir_rel
                # Ensure target directory exists
                java_target_dir_abs.mkdir(parents=True, exist_ok=True)
                
                for ruby_asset_rel_path in ruby_structure[ruby_category]:
                    ruby_asset_abs_path = Path(ruby_repo_dir) / ruby_asset_rel_path
                    asset_filename = os.path.basename(ruby_asset_rel_path)
                    java_asset_abs_path = java_target_dir_abs / asset_filename
                    
                    if ruby_asset_abs_path.exists() and ruby_asset_abs_path.is_file():
                        try:
                            shutil.copy2(ruby_asset_abs_path, java_asset_abs_path)
                            logger.debug(f"Copied asset: {ruby_asset_rel_path} -> {java_target_dir_rel / asset_filename}")
                        except Exception as e:
                            logger.warning(f"Failed to copy asset {ruby_asset_rel_path}: {e}")
                    else:
                        logger.warning(f"Source asset file not found or is not a file: {ruby_asset_abs_path}")

        # Copying templates (HTML files derived from views)
        if "src/main/resources/templates" in java_structure:
            template_dir = Path(output_dir) / "src/main/resources/templates"
            # Ensure base template dir exists (subdirectory creation is handled by _write_file)
            # template_dir.mkdir(parents=True, exist_ok=True)
            for ruby_path, java_info in file_mapping.items():
                 if java_info.get('type') == 'view' and java_info.get('java_path'):
                     # This is rudimentary - assumes simple HTML content for now
                     # A real solution would involve ERB/HAML -> HTML conversion
                     # or using a templating engine that understands the original format
                     # For now, create a placeholder HTML file.
                     html_content = f"<!-- Placeholder for {ruby_path} -->\n<p>Content for {java_info['java_path']}</p>"
                     html_path = Path(output_dir) / java_info['java_path']
                     _write_file(html_path, html_content)
                     logger.debug(f"Created placeholder template: {html_path}")
        
        logger.info(f"Java project generation complete in: {output_dir}")
        return str(output_dir)

    except Exception as e:
        logger.error(f"Project generation failed: {e}", exc_info=True)
        # Clean up the partially created output directory
        shutil.rmtree(output_parent_dir)
        return None

