# JobSherpa Development Plan

This document outlines the current development goal, the roadmap to achieve it, and a transparent log of known technical debt and placeholder implementations.

## Previous Goal: Implement Agentic Architecture for Conversation and Memory (COMPLETED)

The agent has been successfully refactored into a modular, intent-driven system. It now features a `ConversationManager` that delegates tasks to specific `ActionHandlers` (`RunJobAction`, `QueryHistoryAction`) based on user intent. This is supported by a persistent `JobHistory` component, which gives the agent long-term memory and the ability to answer questions about past jobs. This new architecture provides a robust and extensible foundation for all future conversational features.

---

## Current Goal: Enhance Conversational Capabilities and Error Handling

Now that the core agentic architecture is in place, the next step is to make the agent's interactions more intelligent, resilient, and user-friendly. This involves moving beyond simple, rigid command execution and handling the inevitable errors and missing information that occur in real-world use cases.

**The Vision:** The agent should be able to handle ambiguity and missing information gracefully. If a required parameter is not found in a user's profile, the agent shouldn't just fail; it should engage the user in a dialogue to resolve the issue. This moves us closer to a truly helpful assistant that can guide users through the process of setting up and running their jobs.

**Definition of Done:**

1.  **Conversational Parameter Onboarding:**
    -   If the `RunJobAction` handler determines that a required parameter (e.g., `allocation`) is missing, it will not fail immediately.
    -   Instead, it will return a specific message to the user, asking for the missing information (e.g., "I see you're missing a default allocation. What allocation should I use for this job?").
    -   The agent will then be able to receive the user's response in a subsequent prompt and re-attempt the job submission with the new information.
    -   (Stretch Goal): The agent will offer to save the newly provided information to the user's configuration file for future use.
2.  **Richer `QueryHistoryAction`:**
    -   The action will be able to answer more flexible questions, such as "What was the status of my last 3 jobs?" or "Show me all my failed jobs."
3.  **Refined Error Handling:**
    -   The agent will provide more user-friendly error messages for common issues (e.g., template not found, tool execution failure).
    -   Custom exception classes will be introduced to better manage internal error states.

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
