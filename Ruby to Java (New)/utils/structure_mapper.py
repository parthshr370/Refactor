import os
import re
from config.logging_config import logger

def snake_to_camel_case(snake_str: str, capitalize_first: bool = True) -> str:
    """Converts snake_case_string to CamelCaseString or camelCaseString."""
    if not snake_str:
        return ""
    components = snake_str.split('_')
    # Capitalize the first letter only if capitalize_first is True
    first = components[0].capitalize() if capitalize_first else components[0]
    rest = ''.join(x.capitalize() for x in components[1:])
    return first + rest

def camel_to_snake_case(camel_str: str) -> str:
    """Converts CamelCaseString to snake_case_string."""
    if not camel_str:
        return ""
    # Add underscore before uppercase letters (except the first one)
    step1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', camel_str)
    # Add underscore between lowercase/digit and uppercase
    step2 = re.sub('([a-z0-9])([A-Z])', r'\1_\2', step1).lower()
    return step2

def clean_java_class_name(name: str) -> str:
    """Removes invalid characters and ensures the name is a valid Java class name."""
    # Remove file extension if present
    name = os.path.splitext(name)[0]
    # Remove invalid characters (keep alphanumeric and underscore)
    name = re.sub(r'[^a-zA-Z0-9_]', '', name)
    # Ensure it doesn't start with a number
    if name and name[0].isdigit():
        name = '_' + name
    # Handle empty or invalid names
    if not name:
        name = 'UnnamedClass'
    return name

def propose_java_structure(ruby_structure: dict, base_package: str = "com.example.transpiled") -> dict:
    """Generates a proposed Java Spring Boot project structure based on the Ruby structure.

    Args:
        ruby_structure: Dictionary representing the analyzed Ruby project structure.
        base_package: The root package name for the Java project.

    Returns:
        A dictionary representing the proposed Java project structure (paths as keys, list of files as values).
    """
    logger.info(f"Proposing Java structure for base package: {base_package}")
    base_path = base_package.replace('.', '/')
    java_structure = {
        f"src/main/java/{base_path}/model": [],
        f"src/main/java/{base_path}/repository": [],
        f"src/main/java/{base_path}/controller": [],
        f"src/main/java/{base_path}/service": [],
        f"src/main/java/{base_path}/config": [],
        f"src/main/java/{base_path}/dto": [], # Added Data Transfer Objects
        f"src/main/java/{base_path}/util": [],
        f"src/main/java/{base_path}/exception": [], # Added custom exceptions
        f"src/main/resources/templates": [],
        f"src/main/resources/static/css": [],
        f"src/main/resources/static/js": [],
        f"src/main/resources/static/images": [],
        f"src/main/resources": [] # For application.properties etc.
    }

    mapped_entities = set()

    # 1. Map Models -> Entities and Repositories
    for model_path in ruby_structure.get("models", []):
        file_name = os.path.basename(model_path)
        base_name = file_name.replace('.rb', '')
        class_name = snake_to_camel_case(clean_java_class_name(base_name))
        if not class_name:
            logger.warning(f"Could not generate valid class name for model: {model_path}")
            continue
        java_structure[f"src/main/java/{base_path}/model"].append(f"{class_name}.java")
        java_structure[f"src/main/java/{base_path}/repository"].append(f"{class_name}Repository.java")
        mapped_entities.add(class_name)

    # 2. Map Controllers -> Controllers and Services
    for controller_path in ruby_structure.get("controllers", []):
        file_name = os.path.basename(controller_path)
        base_name = file_name.replace('_controller.rb', '')
        class_name_base = snake_to_camel_case(clean_java_class_name(base_name))
        if not class_name_base:
            logger.warning(f"Could not generate valid class name base for controller: {controller_path}")
            continue
        controller_class = f"{class_name_base}Controller.java"
        service_class = f"{class_name_base}Service.java"
        java_structure[f"src/main/java/{base_path}/controller"].append(controller_class)
        java_structure[f"src/main/java/{base_path}/service"].append(service_class)
        # Consider adding DTOs based on controller actions later if needed

    # 3. Map Views (.erb, .haml, etc.) -> Templates (.html)
    for view_path in ruby_structure.get("views", []):
        # Basic mapping, assumes .erb -> .html in templates directory
        if view_path.endswith(('.erb', '.haml', '.slim')):
            # Try to maintain subdirectory structure from app/views
            relative_view_path = view_path.split('app/views/', 1)[-1]
            # Remove original extension and add .html
            base_view_name = os.path.splitext(relative_view_path)[0]
            template_name = f"{base_view_name}.html"
            java_structure["src/main/resources/templates"].append(template_name)
        else:
            logger.warning(f"Skipping non-template view file: {view_path}")

    # 4. Map Helpers, Lib -> Utils
    for helper_path in ruby_structure.get("helpers", []):
        file_name = os.path.basename(helper_path)
        base_name = file_name.replace('_helper.rb', '').replace('.rb', '')
        class_name = snake_to_camel_case(clean_java_class_name(base_name)) + "Util"
        if not class_name.replace("Util", ""): # Check if base name was valid
            logger.warning(f"Could not generate valid class name for helper: {helper_path}")
            continue
        java_structure[f"src/main/java/{base_path}/util"].append(f"{class_name}.java")

    for lib_path in ruby_structure.get("lib", []):
         if lib_path.endswith('.rb'):
            file_name = os.path.basename(lib_path)
            base_name = file_name.replace('.rb', '')
            class_name = snake_to_camel_case(clean_java_class_name(base_name))
            if not class_name:
                logger.warning(f"Could not generate valid class name for lib file: {lib_path}")
                continue
            # Decide if it's a Util or maybe a Service/Config based on name/path?
            # Defaulting to Util for now
            java_structure[f"src/main/java/{base_path}/util"].append(f"{class_name}.java")

    # 5. Map Config/Initializers -> Config
    # This is complex. Maybe just map *.rb to a generic Config class?
    # Or have specific logic for common initializers (devise -> SecurityConfig?)
    config_files = ruby_structure.get("config", []) + ruby_structure.get("initializers", [])
    if config_files:
        java_structure[f"src/main/java/{base_path}/config"].append("ApplicationConfig.java") # Placeholder
        java_structure["src/main/resources"].append("application.properties") # Standard Spring Boot

    # 6. Map Assets -> static resources
    for js_path in ruby_structure.get("assets_js", []):
        java_structure["src/main/resources/static/js"].append(os.path.basename(js_path))
    for css_path in ruby_structure.get("assets_css", []):
        java_structure["src/main/resources/static/css"].append(os.path.basename(css_path))
    for img_path in ruby_structure.get("assets_images", []):
        java_structure["src/main/resources/static/images"].append(os.path.basename(img_path))

    # 7. Other common Java structures (can be added based on analysis or user input)
    if any(cat in ruby_structure for cat in ["models", "controllers", "services"]):
        java_structure[f"src/main/java/{base_path}/exception"].append("ResourceNotFoundException.java")

    # Clean up empty categories and sort files within categories
    final_structure = {k: sorted(list(set(v))) for k, v in java_structure.items() if v}
    logger.info(f"Proposed Java structure generated with {len(final_structure)} categories.")

    return final_structure


# Mapping structure to relate Ruby files to their proposed Java counterparts
# This is needed for the translation step.
def create_file_mapping(ruby_structure: dict, java_structure: dict, base_package: str) -> dict:
    """Creates a mapping from original Ruby files to their proposed Java counterparts.

    Iterates through the LLM-proposed Java structure and maps back to likely Ruby sources.

    Args:
        ruby_structure: The analyzed Ruby structure (Dict[str, List[str]]).
        java_structure: The proposed Java structure (Dict[str, List[Dict[str, str]]]).
        base_package: The Java base package.

    Returns:
        A dictionary where keys are Ruby file relative paths and values are
        dicts containing {'java_path': str, 'type': str, 'class_name': str}.
    """
    mapping = {}
    base_path = base_package.replace('.', '/')
    
    # Flatten the ruby structure for easier searching
    all_ruby_files = set()
    for category, files in ruby_structure.items():
        if isinstance(files, list):
             all_ruby_files.update(files)
    logger.debug(f"Total potential Ruby source files for mapping: {len(all_ruby_files)}")

    # --- Mapping Logic: Iterate through Proposed Java Structure --- 
    
    # Invert map for faster lookup: Map base ruby filename -> full ruby path
    ruby_basename_map = {os.path.basename(f): f for f in all_ruby_files if f.endswith('.rb')}
    
    for java_dir, java_files_data in java_structure.items():
        if not java_dir.startswith("src/main/java/"): # Focus on source code
            continue
            
        java_package_type = java_dir.split('/')[-1] # e.g., model, controller, service, util, config, core

        for java_file_info in java_files_data:
            java_filename = java_file_info.get('name')
            if not java_filename or not java_filename.endswith('.java'):
                continue
                
            java_classname = java_filename.replace('.java', '')
            full_java_path = os.path.join(java_dir, java_filename).replace(os.sep, '/')
            
            # --- Try to find corresponding Ruby file --- 
            potential_ruby_path = None
            
            # 1. Exact Match Strategy (Convert Java name back to potential Ruby name)
            potential_ruby_basename_snake = camel_to_snake_case(java_classname)
            
            # Refine potential Ruby filename based on Java type
            potential_ruby_filename = potential_ruby_basename_snake + ".rb"
            if java_package_type == 'controller' and potential_ruby_basename_snake.endswith('_controller'):
                 potential_ruby_filename = potential_ruby_basename_snake + ".rb"
            elif java_package_type == 'util' and potential_ruby_basename_snake.endswith('_util'):
                 potential_ruby_filename = potential_ruby_basename_snake.replace('_util', '_helper.rb') # Map util back to helper?
                 # Or just map to lib/util_name.rb ?
                 potential_ruby_filename_lib = potential_ruby_basename_snake.replace('_util', '.rb')
            elif java_package_type == 'repository' and potential_ruby_basename_snake.endswith('_repository'):
                 # Repositories map back to models
                 potential_ruby_filename = potential_ruby_basename_snake.replace('_repository', '.rb')
            # Add more rules if needed (e.g., Service? Config?)
            
            # Search in likely Ruby locations based on Java type
            search_locations = []
            if java_package_type == 'model' or java_package_type == 'repository':
                 search_locations.append('app/models')
            elif java_package_type == 'controller':
                 search_locations.append('app/controllers')
            elif java_package_type == 'service':
                 search_locations.append('app/services')
                 search_locations.append('lib') # Also check lib for services
            elif java_package_type == 'util':
                 search_locations.append('app/helpers')
                 search_locations.append('lib') # Also check lib for utils
            elif java_package_type == 'config':
                 search_locations.append('config/initializers')
                 search_locations.append('config')
                 search_locations.append('lib') # Maybe lib
            else: # Default check lib for core, exception, etc.
                search_locations.append('lib')
                
            # Try finding the derived ruby filename in search locations
            found_exact = False
            for loc in search_locations:
                 # Check primary derived name
                 check_path = f"{loc}/{potential_ruby_filename}"
                 if check_path in all_ruby_files:
                     potential_ruby_path = check_path
                     found_exact = True
                     break
                 # Check alternative lib name for utils
                 if java_package_type == 'util' and 'potential_ruby_filename_lib' in locals():
                     check_path_lib = f"{loc}/{potential_ruby_filename_lib}"
                     if check_path_lib in all_ruby_files:
                          potential_ruby_path = check_path_lib
                          found_exact = True
                          break
                          
            # 2. Fallback: Base name match (less precise)
            # If exact path/convention didn't match, check if just the core name matches a lib file
            if not found_exact:
                # Extract core part of Java class, convert to snake
                core_java_name = java_classname.replace('Repository','').replace('Controller','').replace('Service','').replace('Util','').replace('Config','').replace('Exception','')
                core_ruby_name = camel_to_snake_case(core_java_name) + ".rb"
                # Look for this core name in the lib directory specifically
                lib_path_guess = f"lib/{core_ruby_name}"
                if lib_path_guess in all_ruby_files:
                     potential_ruby_path = lib_path_guess
                     logger.debug(f"Fallback mapping: Matched '{core_ruby_name}' for {java_classname} in lib.")
                else:
                    # Try multi-level lib path match
                    # e.g., RetryableConfig -> retryable_config.rb -> lib/retryable/config.rb?
                    # This is complex, skipping for now.
                    pass

            # If a potential Ruby source was found, add to mapping
            if potential_ruby_path and potential_ruby_path in all_ruby_files:
                if potential_ruby_path not in mapping:
                     mapping[potential_ruby_path] = {
                         'java_path': full_java_path, 
                         'type': java_package_type, # Use type from where Java file is placed
                         'class_name': java_classname
                     }
                     logger.info(f"Mapped '{potential_ruby_path}' (Ruby) -> '{full_java_path}' (Java) as type '{java_package_type}'")
                else:
                    # Handle cases where multiple Java files might map back to the same Ruby file?
                    logger.warning(f"Ruby file '{potential_ruby_path}' already mapped to {mapping[potential_ruby_path]['java_path']}. Skipping mapping for {full_java_path}.")
            # else:
                # logger.debug(f"Could not find suitable Ruby source for Java file: {full_java_path}")

    # --- Add mappings for non-code files (like views) --- 
    # Views (.erb -> .html) - Map Java template back to Ruby view
    java_template_dir = "src/main/resources/templates"
    if java_template_dir in java_structure:
        for java_file_info in java_structure[java_template_dir]:
             java_template_name = java_file_info.get('name')
             if java_template_name and java_template_name.endswith('.html'):
                 base_template_name = java_template_name.replace('.html', '')
                 # Guess original Ruby view paths
                 potential_ruby_views = [
                     f"app/views/{base_template_name}.erb",
                     f"app/views/{base_template_name}.haml",
                     f"app/views/{base_template_name}.slim"
                 ]
                 for ruby_view_path in potential_ruby_views:
                     if ruby_view_path in all_ruby_files:
                         if ruby_view_path not in mapping:
                             mapping[ruby_view_path] = {
                                 'java_path': os.path.join(java_template_dir, java_template_name).replace(os.sep, '/'), 
                                 'type': 'view', 
                                 'class_name': None
                             }
                             logger.info(f"Mapped view '{ruby_view_path}' -> '{mapping[ruby_view_path]['java_path']}'")
                             break # Found one match

    logger.info(f"Created file mapping for {len(mapping)} Ruby files.")
    return mapping

