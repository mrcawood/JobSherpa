# JobSherpa Development Plan

This document outlines the current development goal, the roadmap to achieve it, and a transparent log of known technical debt and placeholder implementations.

## Previous Goal: End-to-End "Random Number" Generation (COMPLETED)

The previous objective was to implement a full, end-to-end workflow for a dynamic job. This has been successfully completed and validated on a real HPC system. The agent can now use a RAG pipeline, generate a script from a template with user- and system-specific parameters, submit it, monitor it, and parse the final output.

---

## Current Goal: Implement a Scoped Workspace

The primary objective of the next development cycle is to make the agent's file operations explicit and safe. Currently, the agent reads and writes files in the current working directory, which is implicit and potentially dangerous. We will introduce the concept of a "workspace" to manage all file interactions.

**Definition of Done:**
-   The agent's constructor accepts a `workspace` path. All file operations (script generation, output file parsing) are constrained to this directory.
-   The `ToolExecutor` is updated to execute all commands *from within* the workspace directory.
-   The `random_number.sh.j2` template is updated to refer to the output file using a path relative to the workspace.
-   The agent, when rendering a template, will first write the rendered script to a file inside the workspace (e.g., `.jobsherpa/scripts/job_12345.sh`).
-   The `ToolExecutor` will now execute this script file directly, rather than piping content via stdin.
-   The CLI is updated with a `--workspace` option to allow users to specify the execution context.
-   All relevant tests are updated to use and verify the workspace logic, likely by creating a temporary directory for each test run.

---

## Future Vision & Long-Term Goals

-   **Learn from Existing Scripts:** A powerful future feature will be the ability for the agent to read and learn from a user's existing job scripts. This could dramatically speed up onboarding, allowing the agent to quickly understand a user's established workflows, preferred applications, and common parameters. This could be triggered by pointing the agent to a directory or by uploading a script file.

---

## Technical Debt & Placeholder Implementations

This section serves as a transparent record of design decisions made for short-term velocity. These items must be addressed before the project is considered mature.

1.  **Implicit Workspace & File Paths:**
    -   **Current State:** The agent generates and reads files (like `rng_output.txt`) in the current working directory. The location of the generated script is in memory and piped via stdin. This is not robust and makes tracking job artifacts difficult.
    -   **Long-Term Plan:** This will be addressed by the "Implement a Scoped Workspace" goal.

2.  **Synchronous Agent Flow:**
    -   **Current State:** The agent's `run` method blocks until execution is complete.
    -   **Long-Term Plan:** Refactor the agent's execution flow to be fully asynchronous, allowing it to manage multiple jobs and conversations concurrently.

3.  **No Real LLM Integration:**
    -   **Current State:** The "planning" logic is a simple mapping from a retrieved recipe to a tool.
    -   **Long-Term Plan:** Integrate a real Large Language Model (LLM) to enable more complex reasoning, planning, and conversational capabilities.

4.  **Simplistic Error Handling:**
    -   **Current State:** The agent has basic error handling but lacks sophisticated retry mechanisms or the ability to intelligently interpret and recover from failures.
    -   **Long-Term Plan:** Implement a robust error handling system with custom exception classes and recovery strategies.

5.  **Hardcoded Knowledge Base Path:**
    -   **Current State:** The path to the `knowledge_base` directory is hardcoded.
    -   **Long-Term Plan:** Make this path configurable via a central application configuration file to improve portability.
