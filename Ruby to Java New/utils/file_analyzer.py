import os
from config.logging_config import logger

def analyze_file_structure(repo_dir: str) -> dict:
    """Analyzes and categorizes files in the Ruby project directory.

    Args:
        repo_dir: The path to the root of the cloned/copied repository.

    Returns:
        A dictionary representing the categorized file structure.
    """
    structure = {
        "models": [],
        "controllers": [],
        "views": [],
        "helpers": [],
        "mailers": [], # Added mailers as they are common
        "jobs": [],    # Added jobs
        "channels": [], # Added channels for Action Cable
        "services": [], # Added services (common pattern)
        "lib": [],
        "config": [],
        "initializers": [],
        "db_migrate": [],
        "assets_js": [],
        "assets_css": [],
        "assets_images": [],
        "public": [],
        "test": [],
        "spec": [],
        "other_rb": [], # Catch-all for other Ruby files
        "other_files": [] # Non-Ruby files not covered elsewhere
    }
    logger.info(f"Analyzing file structure in: {repo_dir}")
    
    repo_dir_abs = os.path.abspath(repo_dir)

    for root, dirs, files in os.walk(repo_dir_abs):
        # Skip common ignored directories
        if '.git' in dirs:
            dirs.remove('.git')
        if 'node_modules' in dirs:
            dirs.remove('node_modules')
        if 'tmp' in dirs:
            dirs.remove('tmp')
        if 'log' in dirs:
            dirs.remove('log')
        if 'vendor' in dirs:
            dirs.remove('vendor') # Often contains bundled gems/assets

        for file in files:
            full_path = os.path.join(root, file)
            try:
                # Use relative path from the repo root for easier categorization
                relative_path = os.path.relpath(full_path, repo_dir_abs)
                # Normalize path separators for consistency
                relative_path = relative_path.replace(os.sep, '/')
            except ValueError as e:
                logger.warning(f"Could not get relative path for {full_path} relative to {repo_dir_abs}: {e}")
                continue # Skip if path calculation fails

            # --- Categorization Logic (prioritize specific paths) ---
            if relative_path.startswith('app/models/'):
                structure["models"].append(relative_path)
            elif relative_path.startswith('app/controllers/'):
                structure["controllers"].append(relative_path)
            elif relative_path.startswith('app/views/'):
                structure["views"].append(relative_path)
            elif relative_path.startswith('app/helpers/'):
                structure["helpers"].append(relative_path)
            elif relative_path.startswith('app/mailers/'):
                structure["mailers"].append(relative_path)
            elif relative_path.startswith('app/jobs/'):
                structure["jobs"].append(relative_path)
            elif relative_path.startswith('app/channels/'):
                structure["channels"].append(relative_path)
            elif relative_path.startswith('app/services/'): # Common convention
                structure["services"].append(relative_path)
            elif relative_path.startswith('lib/'):
                structure["lib"].append(relative_path)
            elif relative_path.startswith('config/initializers/'):
                structure["initializers"].append(relative_path)
            elif relative_path.startswith('config/'):
                structure["config"].append(relative_path)
            elif relative_path.startswith('db/migrate/'):
                structure["db_migrate"].append(relative_path)
            elif relative_path.startswith('app/assets/javascripts/') or relative_path.startswith('app/javascript/'):
                structure["assets_js"].append(relative_path)
            elif relative_path.startswith('app/assets/stylesheets/'):
                structure["assets_css"].append(relative_path)
            elif relative_path.startswith('app/assets/images/'):
                structure["assets_images"].append(relative_path)
            elif relative_path.startswith('public/'):
                structure["public"].append(relative_path)
            elif relative_path.startswith('test/'):
                structure["test"].append(relative_path)
            elif relative_path.startswith('spec/'):
                structure["spec"].append(relative_path)
            elif file.endswith('.rb'): # Catch-all for Ruby files
                structure["other_rb"].append(relative_path)
            else:
                structure["other_files"].append(relative_path)

    # Clean up empty categories
    final_structure = {k: sorted(v) for k, v in structure.items() if v}
    logger.info(f"Analysis complete. Found categories: {list(final_structure.keys())}")
    return final_structure

# Note: The display_file_tree function mentioned in the guide 
# is better suited for the Streamlit app (app.py) where UI elements are handled.
# This module focuses solely on the analysis logic.

