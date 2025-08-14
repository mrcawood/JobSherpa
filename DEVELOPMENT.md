# JobSherpa Development Plan

This document outlines the current development goal, the roadmap to achieve it, and a transparent log of known technical debt and placeholder implementations.

## Previous Goal: Implement Persistent User Configuration and Scoped Workspace (COMPLETED)

The agent now has a robust system for managing user-specific settings and operating within a defined workspace. This was achieved by creating a `jobsherpa config` command for persistent user profiles (`knowledge_base/user/<username>.yaml`) and refactoring the agent to use the `workspace` setting from that profile for all file operations. This makes the agent's behavior explicit and provides a scalable foundation for future multi-user support.

---

## Current Goal: Implement Asynchronous Job Handling

The agent's current `run` command is synchronous; it blocks the user's terminal from the moment a prompt is entered until the job is submitted. For a real HPC job that might queue for hours, this is not a viable user experience. This goal is to refactor the agent's core logic to handle job submission and monitoring in the background, immediately returning control to the user.

**The Vision:** The user should be able to submit a job and immediately get their prompt back, along with a job ID. They can then use other commands (e.g., `jobsherpa status <job_id>`, `jobsherpa results <job_id>`) to check on the job's progress or retrieve its results later. This transforms the agent from a simple one-shot tool into an interactive job manager.

**Definition of Done:**

1.  **Immediate User Feedback:**
    -   The `jobsherpa run` command returns a job ID and exits immediately after successful submission.
    -   The `JobStateTracker` continues to run in a separate, persistent background process or thread.
2.  **New CLI Commands:**
    -   A new `jobsherpa status <job_id>` command is implemented to query the `JobStateTracker` for the current status of a specific job.
    -   A new `jobsherpa results <job_id>` command is implemented to retrieve the final, parsed output of a completed job.
3.  **Robust Background Process:**
    -   The background monitoring process is robust and can be started/stopped reliably.
    -   The mechanism for communication between the CLI and the background process (e.g., via file-based state, sockets) is clearly defined and tested.

---

## Future Vision & Long-Term Goals

-   **Learn from Existing Scripts:** A powerful future feature will be the ability for the agent to read and learn from a user's existing job scripts. This could dramatically speed up onboarding, allowing the agent to quickly understand a user's established workflows, preferred applications, and common parameters. This could be triggered by pointing the agent to a directory or by uploading a script file.
-   **Conversational Configuration:** Build a natural language layer on top of the `jobsherpa config` mechanism, allowing users to manage their settings with prompts like "Update my workspace to /path/to/new/project" or "What is my default allocation?".
-   **Multi-User Web Portal:** Evolve the agent into a centralized, long-running daemon that can serve requests from a web-based UI, authenticating users and loading their specific profiles to provide a personalized, multi-user experience.

---

## Technical Debt & Placeholder Implementations

This section serves as a transparent record of design decisions made for short-term velocity. These items must be addressed before the project is considered mature.

1.  **Synchronous Agent Flow:**
    -   **Current State:** The agent's `run` method blocks until execution is complete.
    -   **Long-Term Plan:** This will be addressed by the "Implement Asynchronous Job Handling" goal.
2.  **No Real LLM Integration:**
    -   **Current State:** The "planning" logic is a simple mapping from a retrieved recipe to a tool.
    -   **Long-Term Plan:** Integrate a real Large Language Model (LLM) to enable more complex reasoning, planning, and conversational capabilities.
3.  **Simplistic Error Handling:**
    -   **Current State:** The agent has basic error handling but lacks sophisticated retry mechanisms or the ability to intelligently interpret and recover from failures.
    -   **Long-Term Plan:** Implement a robust error handling system with custom exception classes and recovery strategies.
4.  **Hardcoded Knowledge Base Path:**
    -   **Current State:** The path to the `knowledge_base` directory is hardcoded.
    -   **Long-Term Plan:** Make this path configurable via a central application configuration file to improve portability.
