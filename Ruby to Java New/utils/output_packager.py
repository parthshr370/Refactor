import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from config.logging_config import logger

def create_zip_archive(source_dir: str, output_filename: str = "java_project.zip") -> bytes | None:
    """Creates a ZIP archive of the specified directory.

    Args:
        source_dir: The directory to archive.
        output_filename: The desired name for the output zip file (used for metadata).

    Returns:
        The byte content of the created ZIP file, or None on failure.
    """
    source_path = Path(source_dir)
    if not source_path.is_dir():
        logger.error(f"Source directory does not exist or is not a directory: {source_dir}")
        return None

    # Create a temporary file to write the zip archive to
    # Using a temporary file avoids issues with large archives in memory
    # and ensures cleanup.
    try:
        temp_zip_file = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
        zip_file_path = Path(temp_zip_file.name)
        temp_zip_file.close() # Close it so zipfile can open it

        logger.info(f"Creating ZIP archive for {source_dir} at {zip_file_path}")
        
        with zipfile.ZipFile(zip_file_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_path in source_path.rglob('*'):
                if file_path.is_file():
                    # Calculate the path inside the zip file
                    arcname = file_path.relative_to(source_path)
                    zipf.write(file_path, arcname=arcname)
                    logger.debug(f"Added to zip: {arcname}")
        
        logger.info(f"ZIP archive created successfully at {zip_file_path}.")
        
        # Read the content of the temporary zip file into memory
        with open(zip_file_path, 'rb') as f:
            zip_content = f.read()
        
        return zip_content

    except Exception as e:
        logger.error(f"Failed to create ZIP archive: {e}", exc_info=True)
        return None
    finally:
        # Ensure the temporary file is deleted
        if 'zip_file_path' in locals() and zip_file_path.exists():
            try:
                os.remove(zip_file_path)
                logger.debug(f"Removed temporary zip file: {zip_file_path}")
            except OSError as e:
                logger.error(f"Error removing temporary zip file {zip_file_path}: {e}")

# Example usage (typically called from app.py):
# if java_project_dir:
#     zip_data = create_zip_archive(java_project_dir, "my_transpiled_app.zip")
#     if zip_data:
#         st.download_button(
#             label="Download Java Project",
#             data=zip_data,
#             file_name="my_transpiled_app.zip",
#             mime="application/zip"
#         )
