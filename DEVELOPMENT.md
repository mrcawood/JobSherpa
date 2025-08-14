# JobSherpa Development Plan

This document outlines the current development goal, the roadmap to achieve it, and a transparent log of known technical debt and placeholder implementations.

## Previous Goal: End-to-End "Random Number" Generation (COMPLETED)

The previous objective was to implement a full, end-to-end workflow for a dynamic job. This has been successfully completed and validated on a real HPC system. The agent can now use a RAG pipeline, generate a script from a template with user- and system-specific parameters, submit it, monitor it, and parse the final output.

---

## Current Goal: Implement Persistent User Configuration and Scoped Workspace

Based on recent real-world testing, we've identified the need for a more robust way to manage user preferences and the agent's file-based operations. This goal evolves the previous "Scoped Workspace" idea into a more comprehensive solution that prepares the agent for a multi-user future.

**The Vision:** The agent's context (e.g., user identity, workspace location) should always be explicit. This is achieved by making the user's profile a persistent, "living" configuration file that the agent can read and, in the future, modify based on conversational commands. This architecture is designed to scale seamlessly from a single-user CLI tool to a multi-user web service, where a single agent daemon will serve requests from many users by loading their respective profiles.

**Definition of Done:**

1.  **Persistent User Configuration:**
    -   A new `jobsherpa config` command is added to the CLI.
    -   This command supports `get <key>` and `set <key> <value>` subcommands to read and write to the user's profile YAML file (e.g., `knowledge_base/user/mcawood.yaml`).
    -   This provides the foundational mechanism for a persistent, modifiable user memory.

2.  **Scoped Workspace Implementation:**
    -   The agent is refactored to always load the user profile specified by the `--user-profile` flag.
    -   The agent looks for a `workspace` key within the loaded user profile to determine the directory for all operations.
    -   All commands executed by the `ToolExecutor` are run from within the workspace directory.
    -   The agent writes all generated artifacts (rendered job scripts, output files) to predictable locations inside the workspace (e.g., `.jobsherpa/scripts/`, `outputs/`).
    -   The `--workspace` CLI flag is removed in favor of the persistent configuration managed by `jobsherpa config`.
    -   All relevant tests are updated to use and verify this new configuration-driven workspace logic.

---

## Future Vision & Long-Term Goals

-   **Learn from Existing Scripts:** A powerful future feature will be the ability for the agent to read and learn from a user's existing job scripts. This could dramatically speed up onboarding, allowing the agent to quickly understand a user's established workflows, preferred applications, and common parameters. This could be triggered by pointing the agent to a directory or by uploading a script file.
-   **Conversational Configuration:** Build a natural language layer on top of the `jobsherpa config` mechanism, allowing users to manage their settings with prompts like "Update my workspace to /path/to/new/project" or "What is my default allocation?".
-   **Multi-User Web Portal:** Evolve the agent into a centralized, long-running daemon that can serve requests from a web-based UI, authenticating users and loading their specific profiles to provide a personalized, multi-user experience.

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
