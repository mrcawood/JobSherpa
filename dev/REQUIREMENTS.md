# JobSherpa Project Requirements

This document outlines the functional and non-functional requirements for the JobSherpa AI agent.

## MVP Requirements (Initial Focus)

-   **Platform:** A Command-Line Interface (CLI) tool designed to run directly on an HPC system's login node.
-   **Scope:** Support a single, pre-configured HPC system to execute a minimal "hello world" type of job.
-   **Core Functionality:**
    -   Accept a basic, natural-language prompt from the user.
    -   Perform pre-submission validation:
        -   Check that specified job parameters (e.g., partition, account) are valid for the system.
        -   Verify that necessary environment modules are available and can be loaded.
    -   Require explicit user confirmation before submitting the job script.
-   **Job Status:**
    -   Submit the job to the local scheduler.
    -   Report the final status (e.g., completed, failed), and basic metrics like total runtime, once the job is finished.

## Long-Term Vision & Core Principles

-   **Portability & Configuration:** The agent must be adaptable to different HPC sites, schedulers (Slurm, PBS, etc.), hardware, and filesystems, managed by a robust configuration system.
-   **Interactive Agent:** Develop a sophisticated conversational agent that can proactively gather information by interacting with the user and the system (e.g., listing files, checking job history).
-   **Application Expertise:** The agent must understand how to construct and execute complex, multi-step application workflows (like WRF). It also needs to parse application-specific output files to answer questions about the results.
-   **Expanded Interface:** Evolve beyond the CLI to include a web-based portal for remote access.
-   **Security:** Implement secure authentication for remote users.
-   **Development Methodology:** Follow a Test-Driven Development (TDD) approach for adding new features.
-   **User-Specific Memory:** The agent will maintain a persistent knowledge base for each user to remember project structures, file locations, and workflow preferences.
-   **Modular Knowledge (RAG):** The agent's intelligence will be powered by a Retrieval-Augmented Generation (RAG) architecture with distinct, swappable knowledge bases for:
    -   General HPC concepts.
    -   System-specific details (schedulers, partitions, etc.).
    -   Application-specific workflows and file formats.
-   **Scoped Autonomy:** The agent will operate within a user-defined context (e.g., a project directory) to ensure safety and control.
-   **Job Monitoring & Analysis:** The agent will report job status and be capable of parsing output files to answer user questions about the results.
-   **User Confirmation:** The agent will always seek explicit, but configurable, user confirmation before taking a final action like submitting a job.
