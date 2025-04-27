import subprocess
import os
import re
from pathlib import Path
from config.logging_config import logger

def _run_maven_compile(java_project_dir: str) -> tuple[bool, str]:
    """Runs 'mvn compile' in the specified directory and captures output."""
    pom_path = Path(java_project_dir) / "pom.xml"
    if not pom_path.is_file():
        logger.error("pom.xml not found. Cannot run Maven validation.")
        return False, "Validation Error: pom.xml not found."

    logger.info(f"Running 'mvn compile' in {java_project_dir}...")
    # Ensure Maven executable is findable (common locations)
    # This might need adjustment based on user's system
    maven_command = "mvn"
    if os.name == 'nt': # Windows
        maven_command = "mvn.cmd"
        
    try:
        # Use subprocess.run for simpler execution and output capture
        process = subprocess.run(
            [maven_command, "clean", "compile"], # Added 'clean' for consistency
            cwd=java_project_dir,
            capture_output=True,
            text=True,
            check=False, # Don't raise exception on non-zero exit code
            timeout=300 # Add a timeout (e.g., 5 minutes)
        )

        if process.returncode == 0:
            logger.info("Maven compilation successful.")
            return True, "Maven compilation successful."
        else:
            logger.warning(f"Maven compilation failed (Return Code: {process.returncode}).")
            # Try to extract relevant error messages
            error_output = process.stdout + "\n" + process.stderr
            # Simple extraction of lines containing '[ERROR]' or 'Compilation failure'
            error_lines = [line for line in error_output.splitlines() 
                           if '[ERROR]' in line or 'Compilation failure' in line or 'cannot find symbol' in line]
            if not error_lines:
                 error_lines = error_output.splitlines()[-20:] # Get last 20 lines as fallback
                 
            return False, "Maven compilation failed:\n" + "\n".join(error_lines)

    except FileNotFoundError:
        logger.error("'mvn' command not found. Please ensure Maven is installed and in your system's PATH.")
        return False, "Validation Error: 'mvn' command not found. Is Maven installed and in PATH?"
    except subprocess.TimeoutExpired:
        logger.error("Maven compilation timed out.")
        return False, "Validation Error: Maven compilation timed out."
    except Exception as e:
        logger.error(f"An unexpected error occurred during Maven validation: {e}")
        return False, f"Validation Error: An unexpected error occurred: {e}"

def _basic_java_syntax_check(java_project_dir: str) -> list[str]:
    """Performs very basic checks on .java files (e.g., balanced braces)."""
    issues = []
    logger.info("Performing basic syntax checks on .java files...")
    for java_file in Path(java_project_dir).rglob('*.java'):
        try:
            with open(java_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Check for balanced curly braces
            if content.count('{') != content.count('}'):
                issues.append(f"{java_file.relative_to(java_project_dir)}: Unbalanced curly braces {{}}.")
            # Check for balanced parentheses
            if content.count('(') != content.count(')'):
                issues.append(f"{java_file.relative_to(java_project_dir)}: Unbalanced parentheses ().")
             # Check for package declaration (simple check)
            if not content.strip().startswith("package "):
                 issues.append(f"{java_file.relative_to(java_project_dir)}: Missing or incorrect package declaration.")
            # Check for missing semicolons at end of typical lines
            # This is very approximate!
            lines_ending_without_semicolon = 0
            for line in content.splitlines():
                stripped_line = line.strip()
                if stripped_line and not stripped_line.endswith((';', '{', '}', '(', ')', ',')) and not stripped_line.startswith(('/', '*','@')):
                    # crude check for lines that look like statements but don't end with ';'
                    if '=' in stripped_line or '(' in stripped_line or '.' in stripped_line: 
                         lines_ending_without_semicolon += 1
            # if lines_ending_without_semicolon > 0: # This might be too noisy
            #      issues.append(f"{java_file.relative_to(java_project_dir)}: Found {lines_ending_without_semicolon} potential missing semicolons.")
                 
        except Exception as e:
            issues.append(f"Error reading/checking {java_file.relative_to(java_project_dir)}: {e}")
            
    logger.info(f"Basic syntax check found {len(issues)} potential issues.")
    return issues

def validate_java_project(java_project_dir: str) -> tuple[bool, list[str]]:
    """Validates the generated Java project.

    Runs basic syntax checks and attempts Maven compilation.

    Args:
        java_project_dir: The path to the generated Java project root.

    Returns:
        A tuple: (is_valid, list_of_issues)
    """
    logger.info(f"Starting validation for project: {java_project_dir}")
    all_issues = [] 
    overall_success = True
    
    # 1. Basic Syntax Checks
    basic_issues = _basic_java_syntax_check(java_project_dir)
    if basic_issues:
        all_issues.extend(basic_issues)
        # Don't necessarily fail overall just for basic checks
        # overall_success = False 

    # 2. Maven Compilation Check
    maven_success, maven_output = _run_maven_compile(java_project_dir)
    if not maven_success:
        all_issues.append(maven_output) # Add Maven output as a single issue string
        overall_success = False
    else:
        # Optional: Add success message if needed, but usually not required if overall_success is true
        # all_issues.append("Maven compilation successful.")
        pass

    if not all_issues:
        all_issues.append("Project passed basic validation and Maven compilation.")
        
    logger.info(f"Validation completed. Success: {overall_success}. Issues found: {len(all_issues) if overall_success else len(all_issues)-1}")
    return overall_success, all_issues

