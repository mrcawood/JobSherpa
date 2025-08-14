# JobSherpa Development Plan

This document outlines the current development goal, the roadmap to achieve it, and a transparent log of known technical debt and placeholder implementations.

## Previous Goal: Implement Persistent User Configuration and Scoped Workspace (COMPLETED)

The agent now has a robust system for managing user-specific settings and operating within a defined workspace. This was achieved by creating a `jobsherpa config` command for persistent user profiles (`knowledge_base/user/<username>.yaml`) and refactoring the agent to use the `workspace` setting from that profile for all file operations. This makes the agent's behavior explicit and provides a scalable foundation for future multi-user support.

---

## Current Goal: Implement Agentic Architecture for Conversation and Memory

To evolve from a command-executor into a true conversational agent, we must refactor the core architecture. The current monolithic `agent.run` method is insufficient for handling different types of user queries (e.g., running jobs vs. asking about past jobs). This goal is to implement a modular, intent-driven architecture that provides a robust foundation for all future conversational features.

**The Vision:** The agent's core will be a `ConversationManager` that inspects the user's prompt to determine their intent. Based on that intent, it will delegate the task to a specific `ActionHandler` (e.g., `RunJobAction`, `QueryHistoryAction`). This is a foundational shift from a "doer" to a "knower and doer," enabling the agent to understand, remember, and act with much greater flexibility. A key part of this is introducing a persistent `JobHistory` to give the agent a long-term memory.

**Definition of Done:**

1.  **New Core Components:**
    -   A `ConversationManager` is created and becomes the new entry point for the agent's logic.
    -   A simple, keyword-based `IntentClassifier` is implemented to distinguish between "run job" and "query history" intents.
    -   The `JobStateTracker` is refactored into a persistent `JobHistory` component that saves its state to a file (e.g., `~/.jobsherpa/history.json`).
2.  **Refactored Logic into Action Handlers:**
    -   All logic for running a job (RAG, workspace creation, execution) is moved from `agent.py` into a new `RunJobAction` handler.
    -   New logic for querying the `JobHistory` is implemented in a `QueryHistoryAction` handler.
3.  **Support for "What was the result of my last job?":**
    -   The `QueryHistoryAction` can successfully find the most recent job in the `JobHistory`.
    -   The agent can formulate a correct, human-readable response based on the parsed results of the last job.
    -   The `output_parser` format in recipes is enhanced to support parsing multiple named values (e.g., "completion_time", "timesteps").

---

## Future Vision & Long-Term Goals

-   **Conversational Onboarding & Initialization:** The ultimate goal is to create a truly intelligent agent that can guide a new user through the entire setup process. This involves moving beyond static `config` commands to a stateful, interactive dialogue where the agent can ask questions, understand user queries about available resources, and dynamically populate the user's configuration file based on the conversation. For example:
    -   *Agent:* "I see you don't have a default system set up. What HPC system will you be primarily using?"
    -   *User:* "I need to run on H100 GPUs, what are my options?"
    -   *Agent:* "I see that Vista and Stampede3 both have H100 GPUs available. Which would you like as your default?"
-   **Learn from Existing Scripts:** A powerful future feature will be the ability for the agent to read and learn from a user's existing job scripts. This could dramatically speed up onboarding, allowing the agent to quickly understand a user's established workflows, preferred applications, and common parameters. This could be triggered by pointing the agent to a directory or by uploading a script file.
-   **Conversational Configuration:** Build a natural language layer on top of the `jobsherpa config` mechanism, allowing users to manage their settings with prompts like "Update my workspace to /path/to/new/project" or "What is my default allocation?".
-   **Multi-User Web Portal:** Evolve the agent into a centralized, long-running daemon that can serve requests from a web-based UI, authenticating users and loading their specific profiles to provide a personalized, multi-user experience.

---

## Technical Debt & Placeholder Implementations

This section serves as a transparent record of design decisions made for short-term velocity. These items must be addressed before the project is considered mature.

1.  **No Real LLM Integration:**
    -   **Current State:** The "planning" logic is a simple mapping from a retrieved recipe to a tool. The new `IntentClassifier` will be keyword-based.
    -   **Long-Term Plan:** Integrate a real Large Language Model (LLM) to replace the simple `IntentClassifier` and enable more complex reasoning, planning, and conversational capabilities.
2.  **Simplistic Error Handling:**
    -   **Current State:** The agent has basic error handling but lacks sophisticated retry mechanisms or the ability to intelligently interpret and recover from failures.
    -   **Long-Term Plan:** Implement a robust error handling system with custom exception classes and recovery strategies.
3.  **Hardcoded Knowledge Base Path:**
    -   **Current State:** The path to the `knowledge_base` directory is hardcoded.
    -   **Long-Term Plan:** Make this path configurable via a central application configuration file to improve portability.
