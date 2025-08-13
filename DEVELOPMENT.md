# JobSherpa Development Plan

This document outlines the current development goal, the roadmap to achieve it, and a transparent log of known technical debt and placeholder implementations.

## Previous Goal: Real SLURM Job Execution (COMPLETED)

The previous objective was to enable the agent to submit a simple, real job to a SLURM scheduler and report its status. This has been completed, with the core logic for command execution and status checking now in place and validated by mock-based tests.

---

## Current Goal: End-to-End "Random Number" Generation

The primary objective of the current development cycle is to implement a full, end-to-end workflow for a dynamic job. The agent must handle a request like "Generate a random number for me," which requires it to use a real RAG pipeline, generate a script dynamically, submit it, monitor it, and parse the final output to retrieve the result.

**Definition of Done:**
-   The manual, keyword-based RAG is replaced with a real RAG framework (e.g., Haystack or LlamaIndex) that performs semantic searches over the knowledge base.
-   The agent can use a template from the knowledge base (e.g., a Jinja2 template) to dynamically generate a job submission script.
-   The agent submits this generated script to the scheduler.
-   The `JobStateTracker`, upon detecting a `COMPLETED` job, triggers a post-processing step.
-   This post-processing step uses information from the application recipe to parse the job's output file and extract the final result (the random number).
-   The agent can report this final result back to the user.
-   A new end-to-end test verifies this entire workflow using mocks for the RAG pipeline and `subprocess` calls.

---

## Development Roadmap

1.  **Integrate a Real RAG Framework:**
    -   Select and add a RAG library (e.g., Haystack) to the project dependencies.
    -   Refactor the `JobSherpaAgent` to initialize and use a real RAG pipeline (e.g., create a DocumentStore, index the YAML recipes).
    -   Replace the `_find_matching_recipe` method with a query to the new RAG pipeline.
    -   Update existing tests to mock the RAG pipeline's output.

2.  **Implement Dynamic Script Generation:**
    -   Introduce a templating library (e.g., Jinja2).
    -   Create a new `random_number.yaml` recipe in the knowledge base that points to a script template file.
    -   Create the corresponding script template file (e.g., `random_number.sh.j2`).
    -   Add logic to the `JobSherpaAgent` to render this template into a runnable script before execution.

3.  **Implement Job Output Parsing:**
    -   Enhance the application recipe format to include output parsing information (e.g., `output_file`, `parser_regex`).
    -   Refactor the `JobStateTracker` to include a post-processing step. When a job's final status is determined, if parsing info is available, it should read the output file and extract the result.
    -   The extracted result should be stored with the job's state.

4.  **Create New End-to-End Test:**
    -   Write a comprehensive test case for the "random number" workflow. This test will mock the RAG pipeline and `subprocess` calls, and will verify script generation, job submission, and the final parsed result.

---

## Technical Debt & Placeholder Implementations

This section serves as a transparent record of design decisions made for short-term velocity. These items must be addressed before the project is considered mature.

1.  **Manual RAG Implementation:**
    -   **Current State:** The "Retrieval" logic is a simple keyword-matching loop over YAML files in `agent.py`.
    -   **Long-Term Plan:** Replace this with a dedicated RAG framework (e.g., Haystack, LlamaIndex) to enable true semantic search, support for unstructured documents, and scalability.

2.  **Synchronous Agent Flow:**
    -   **Current State:** The agent's `run` method blocks until execution is complete.
    -   **Long-Term Plan:** This is being addressed in the current development roadmap. The agent flow will become fully asynchronous.

3.  **No Real LLM Integration:**
    -   **Current State:** The "planning" logic is currently a simple mapping from a retrieved recipe to a tool.
    -   **Long-Term Plan:** Integrate a real Large Language Model (LLM) to enable more complex reasoning, planning, and conversational capabilities.

4.  **Simplistic Error Handling:**
    -   **Current State:** The `ToolExecutor` has a basic `try...except` block that returns a simple error string.
    -   **Long-Term Plan:** Implement a robust error handling system with custom exception classes, retry mechanisms, and the ability for the agent to intelligently interpret and report errors.

5.  **Hardcoded Knowledge Base Path:**
    -   **Current State:** The path to the `knowledge_base` directory is hardcoded in the `JobSherpaAgent` constructor.
    -   **Long-Term Plan:** Make this path configurable via a central application configuration file to improve portability.
