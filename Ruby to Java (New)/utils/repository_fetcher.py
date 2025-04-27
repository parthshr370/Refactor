import git
import tempfile
import os
import shutil
from config.logging_config import logger
from config.settings import TEMP_DIR_PREFIX

def fetch_repository(github_url: str) -> tuple[str | None, str | None]:
    """Clones a GitHub repository to a temporary directory.

    Args:
        github_url: The URL of the GitHub repository.

    Returns:
        A tuple containing the path to the temporary directory and an error message (if any).
    """
    print(f"[REPO FETCHER] Creating temporary directory...")
    temp_dir = tempfile.mkdtemp(prefix=TEMP_DIR_PREFIX)
    logger.info(f"Created temporary directory: {temp_dir}")
    print(f"[REPO FETCHER] Temporary directory created at: {temp_dir}")
    try:
        print(f"[REPO FETCHER] Attempting to clone {github_url} ...")
        logger.info(f"Cloning repository from {github_url} into {temp_dir}")
        git.Repo.clone_from(github_url, temp_dir)
        logger.info("Repository cloned successfully.")
        print(f"[REPO FETCHER] Repository cloned successfully into {temp_dir}")
        # Optional: Print top-level contents
        try:
            contents = os.listdir(temp_dir)
            print(f"[REPO FETCHER] Top-level contents of {temp_dir}: {contents}")
        except Exception as list_err:
            print(f"[REPO FETCHER] Warning: Could not list contents of {temp_dir}: {list_err}")
            
        return temp_dir, None
    except git.GitCommandError as e:
        logger.error(f"Error cloning repository: {e}")
        print(f"[REPO FETCHER] ERROR cloning repository: {e}")
        shutil.rmtree(temp_dir)
        return None, str(e)
    except Exception as e:
        logger.error(f"An unexpected error occurred during cloning: {e}")
        print(f"[REPO FETCHER] UNEXPECTED ERROR during cloning: {e}")
        shutil.rmtree(temp_dir)
        return None, f"An unexpected error occurred: {str(e)}"

def copy_local_directory(local_path: str) -> tuple[str | None, str | None]:
    """Copies a local directory to a temporary directory.

    Args:
        local_path: The path to the local directory.

    Returns:
        A tuple containing the path to the temporary directory and an error message (if any).
    """
    if not os.path.isdir(local_path):
        logger.error(f"Local path is not a valid directory: {local_path}")
        return None, f"Invalid directory path: {local_path}"

    temp_dir = tempfile.mkdtemp(prefix=TEMP_DIR_PREFIX)
    # Use directory name from source path for the destination inside temp_dir
    repo_name = os.path.basename(os.path.normpath(local_path))
    dest_path = os.path.join(temp_dir, repo_name)

    logger.info(f"Created temporary directory structure: {dest_path}")
    try:
        logger.info(f"Copying local directory from {local_path} to {dest_path}")
        shutil.copytree(local_path, dest_path)
        logger.info("Local directory copied successfully.")
        # Return the path containing the copied project, not the base temp dir
        return dest_path, None
    except shutil.Error as e:
        logger.error(f"Error copying directory: {e}")
        shutil.rmtree(temp_dir) # Clean up base temp dir
        return None, str(e)
    except Exception as e:
        logger.error(f"An unexpected error occurred during copying: {e}")
        shutil.rmtree(temp_dir) # Clean up base temp dir
        return None, f"An unexpected error occurred: {str(e)}"

def validate_ruby_project(repo_dir: str) -> tuple[bool, bool]:
    """Check if the directory likely contains a Ruby or Rails project.

    Args:
        repo_dir: The path to the directory.

    Returns:
        A tuple: (is_ruby_project, is_rails_project)
    """
    ruby_files_found = False
    gemfile_found = os.path.exists(os.path.join(repo_dir, 'Gemfile'))

    for root, dirs, files in os.walk(repo_dir):
        # Skip .git directory
        if '.git' in dirs:
            dirs.remove('.git')
            
        for file in files:
            if file.endswith('.rb'):
                ruby_files_found = True
                break # Found one, no need to check further in this dir
        if ruby_files_found:
            break # Found one, no need to check further

    # Basic check for Rails structure
    is_rails = (
        os.path.exists(os.path.join(repo_dir, 'app')) and
        os.path.exists(os.path.join(repo_dir, 'config')) and
        os.path.exists(os.path.join(repo_dir, 'config/routes.rb'))
    )

    # Consider it a Ruby project if Gemfile exists or Ruby files are found
    is_ruby = gemfile_found or ruby_files_found

    logger.info(f"Validation results for {repo_dir}: Ruby={is_ruby}, Rails={is_rails}")
    return is_ruby, is_rails

