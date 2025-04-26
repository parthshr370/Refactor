# 💎 Ruby to Java Transpiler ☕

An AI-assisted tool designed to help migrate Ruby/Rails projects to Java Spring Boot. It analyzes the structure of a Ruby project, proposes an equivalent Spring Boot structure using an LLM, allows review and modification, and then uses an LLM again to translate the Ruby code into Java within the generated structure.

## How it Works

The transpiler follows these main steps:

1.  **Input**: Accepts a Ruby project source via a public GitHub URL or by uploading a local project as a ZIP file.
2.  **Fetch & Validate**: Clones the repository or extracts the ZIP into a temporary directory. Validates if it's a recognizable Ruby/Rails project.
3.  **Analyze Ruby Structure**: Performs a basic analysis of the source directory to categorize files (models, controllers, views, libs, etc.).
4.  **LLM Structure Proposal**: Sends the file list and project type information to an LLM (configurable, e.g., Claude, GPT) with a detailed prompt asking it to propose an idiomatic Java Spring Boot structure (directories and files) based on the input. It also requests file summaries and a Mermaid diagram visualization.
5.  **Review & Refine**: The Streamlit UI displays:
    *   The list of source files parsed.
    *   A hierarchical view of the LLM-proposed Java file tree.
    *   A visualization of the proposed structure using MermaidJS (rendered in a scrollable HTML component).
    *   Expandable summaries for each proposed file's purpose.
    *   Options to adjust the base Java package name (triggering re-analysis if changed).
6.  **File Mapping**: Once the structure is approved, it maps the original Ruby files to their corresponding proposed Java files. The process iterates through the *LLM-proposed Java structure* and attempts to identify the most likely original Ruby source file based on naming conventions (converting Java CamelCase to Ruby snake_case), expected directory locations (e.g., Java models map to Ruby models, Java services map to Ruby services or lib), and fallback logic.
7.  **Code Generation & Translation**:
    *   Generates boilerplate files (pom.xml, Application.java, application.properties) using templates.
    *   Iterates through the mapped files:
        *   Reads the Ruby code.
        *   Sends the Ruby code and contextual information (target class name, file type, base package) to the LLM with specific translation prompts.
        *   Writes the LLM's translated Java code to the corresponding file in the generated structure.
    *   Copies static assets (CSS, JS, images) from the Ruby project to the Java structure.
8.  **Validation (Optional)**: If Apache Maven (`mvn`) is found in the system's PATH, it attempts to compile the generated Java project using `mvn compile` to check for basic errors.
9.  **Download**: Packages the generated Java Spring Boot project into a ZIP file for download.

```mermaid
graph TD
    A[Input: GitHub URL / ZIP] --> B{Fetch/Extract Source};
    B --> C{Validate Ruby/Rails Project};
    C -- Valid --> D[Analyze Ruby File Structure];
    D --> E[LLM Propose Java Structure + Summaries + Mermaid];
    E --> F[Review & Refine (UI)];
    F -- Approve --> G[Map Ruby Files to Java Files];
    G --> H{Generate Java Project};
    H -- Generate Boilerplate --> I[pom.xml, App.java, etc.];
    H -- Translate Code (LLM) --> J[Generate Java Files];
    H -- Copy Assets --> K[Static Files];
    J --> L{Generated Project};
    I --> L;
    K --> L;
    L --> M{Validate (Optional: mvn compile)};
    M --> N[Package Project (ZIP)];
    N --> O[Download];

    C -- Invalid --> P[Show Error];
    F -- Re-analyze --> E;

    classDef llmNode fill:#f9d,stroke:#333,stroke-width:2px;
    class E,J llmNode;
```

## Features

*   Supports input from public GitHub repositories or local ZIP archives.
*   Uses Large Language Models (LLMs) like Claude 3.5 Sonnet (via OpenRouter) or OpenAI models for:
    *   Intelligent Java Spring Boot structure proposal based on Ruby project analysis.
    *   Generating file summaries.
    *   Visualizing the proposed structure with Mermaid diagrams.
    *   Translating Ruby code (`.rb` files) to Java.
*   Provides a Streamlit web UI for input, review, and download.
*   Generates standard Maven `pom.xml` and Spring Boot `Application.java` boilerplate.
*   Attempts to map Ruby `lib` files to appropriate Java packages (`core`, `util`, `service`, etc.).
*   Copies static assets.
*   Optional validation using `mvn compile` if Maven is installed.
*   Packages the final Java project into a downloadable ZIP file.
*   Configurable API provider (OpenRouter, OpenAI) and model selection.
*   Terminal output for background processes like repository cloning.

## Technology Stack

*   **Python 3.10+**
*   **Streamlit**: Web UI framework.
*   **Langchain / OpenAI Python Library**: Interacting with LLMs.
*   **GitPython**: Cloning GitHub repositories.
*   **Tenacity**: Retry logic for LLM calls.
*   **python-dotenv**: Managing environment variables for API keys.
*   **MermaidJS**: Used via CDN for structure visualization.
*   **Apache Maven** (Optional): For Java project validation.

## Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/your-username/ruby-to-java-transpiler.git # Replace with your repo URL if different
    cd ruby-to-java-transpiler
    ```

2.  **Create a Python Environment:** (Recommended, e.g., using Conda or venv)
    ```bash
    # Using Conda
    conda create -n rjt_env python=3.10
    conda activate rjt_env

    # Or using venv
    # python -m venv venv
    # source venv/bin/activate # On Linux/macOS
    # venv\Scripts\activate # On Windows
    ```

3.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure API Keys:**
    *   Create a file named `.env` in the project root directory.
    *   Add your API keys to the `.env` file. The specific key needed depends on the `API_PROVIDER` set in `config/settings.py`.
        *   For OpenRouter (default):
            ```dotenv
            OPENROUTER_API_KEY="your_openrouter_api_key"
            # OPENAI_API_KEY="your_openai_api_key" # Optional, if you switch provider
            ```
        *   For OpenAI:
            ```dotenv
            OPENAI_API_KEY="your_openai_api_key"
            ```
    *   *Note:* The application currently prioritizes OpenRouter if `API_PROVIDER` is set to `"openrouter"` in `config/settings.py`.

5.  **Install Maven (Optional):**
    *   If you want the automated Java code compilation check to run, install Apache Maven and ensure the `mvn` command is in your system's PATH. If Maven is not found, this validation step will be skipped.

## Usage

1.  Ensure your Python environment is activated (e.g., `conda activate rjt_env`).
2.  Make sure your `.env` file with the API key is present in the project root.
3.  Run the Streamlit application:
    ```bash
    streamlit run app.py
    ```
4.  Open the provided URL (usually `http://localhost:8501`) in your web browser.
5.  Follow the steps in the UI:
    *   Provide a GitHub URL or upload a ZIP file.
    *   Click "Analyze".
    *   Review the results in the tabs (Source Files, Proposed Structure, File Summaries).
    *   Optionally adjust the base package and re-analyze.
    *   Click "Proceed to Translation".
    *   Wait for the translation and generation process.
    *   Download the resulting ZIP file.

## Project Structure

```
ruby-to-java-transpiler/
│
├── app.py                      # Main Streamlit application UI and workflow logic
├── requirements.txt            # Python dependencies
├── README.md                   # This file
├── LLM.md                      # Details about LLM integration (NEW)
├── .env.example                # Example environment file structure
│
├── utils/                      # Utility functions (non-LLM specific)
│   ├── __init__.py
│   ├── repository_fetcher.py   # GitHub/ZIP fetching and validation
│   ├── file_analyzer.py        # Basic Ruby file structure analysis
│   ├── structure_mapper.py     # Mapping LLM-proposed Java files back to Ruby sources
│   ├── code_generator.py       # Java project dir creation, template filling, translation orchestration
│   ├── validator.py            # Optional Java code validation (using Maven)
│   └── output_packager.py      # ZIP file creation for download
│
├── agents/                     # LLM-dependent components
│   ├── __init__.py
│   ├── translator_agent.py     # Handles LLM calls for Ruby->Java code translation
│   ├── structure_analyzer_agent.py # Handles LLM calls for Java structure proposal
│   └── llm_client.py           # LLM API client (OpenAI/OpenRouter, retry logic)
│
├── templates/                  # Minimal Java code templates
│   ├── pom_template.xml        # Template for Maven pom.xml
│   └── application_template.java # Template for Spring Boot Application class
│
├── prompts/                    # LLM Prompt templates
│   ├── structure_analysis_prompt_template.txt # Prompt for proposing structure
│   ├── translation_base_system_prompt.txt     # Base system prompt for translation
│   ├── translation_controller_instructions.txt # Specific instructions for controllers
│   ├── translation_model_instructions.txt      # Specific instructions for models
│   ├── translation_service_instructions.txt    # Specific instructions for services
│   └── translation_util_instructions.txt       # Specific instructions for utils/helpers
│   └── translation_generic_instructions.txt    # Fallback instructions
│
└── config/                     # Configuration files
    ├── __init__.py
    ├── settings.py             # Core application settings (API provider, model, etc.)
    ├── api_keys.py             # Loads API keys from environment/.env
    └── logging_config.py       # Logging setup
```

## Limitations & Future Work

*   **Translation Quality**: The accuracy of the Java code depends heavily on the LLM used and the complexity of the Ruby code. Generated code will likely require manual review and debugging.
*   **Complex Mappings**: Mapping certain Rails concepts (e.g., complex routing, mailers, jobs, intricate ActiveRecord associations, meta-programming) to Spring Boot equivalents is challenging for the LLM and may require significant manual intervention. View translation (`.erb`/`.haml` -> HTML) is currently placeholder only.
*   **Testing**: The project currently lacks automated tests.
*   **Error Handling**: Error handling can be improved, especially during the LLM interaction and file generation stages.
*   **Dependency Mapping**: Does not attempt to map Gemfile dependencies to Maven dependencies in `pom.xml` beyond the standard Spring Boot starters.
*   **UI Refinement**: The Streamlit UI could be further enhanced for better user experience.

Contributions are welcome! Please refer to the contributing guidelines (if available).
