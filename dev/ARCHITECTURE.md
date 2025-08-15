# JobSherpa System Architecture

This document provides a high-level overview of the JobSherpa agent's architecture, its core components, and how they interact.

## 1. Architectural Diagram

```mermaid
graph TD
    subgraph User Interface
        CLI[CLI: main.py]
    end

    subgraph Agent Core [jobsherpa.agent]
        A[JobSherpaAgent] --> CM[ConversationManager];
        CM --> IC[IntentClassifier];
        CM --> AH[Action Handlers];

        subgraph Action Handlers [actions.py]
            Run[RunJobAction]
            Query[QueryHistoryAction]
        end
        
        AH --> Run;
        AH --> Query;

        Run --> RAG[RAG Engine];
        Run --> WM[WorkspaceManager];
        Run --> TE[ToolExecutor];
        Run --> JH[JobHistory];
        Query --> JH;
    end

    subgraph Knowledge & State
        KB[Knowledge Bases: YAML files]
        JH_DB[Job History: history.json]
    end

    subgraph System Tools
        Shell[Shell Commands: sbatch, echo]
    end

    CLI -- User Prompt --> A;
    A -- Agent Response --> CLI;
    
    RAG -- Reads --> KB;
    TE -- Executes --> Shell;
    JH -- Reads/Writes --> JH_DB;

    style Agent Core fill:#f9f,stroke:#333,stroke-width:2px
    style User Interface fill:#ccf,stroke:#333,stroke-width:2px
    style "Knowledge & State" fill:#cfc,stroke:#333,stroke-width:2px
    style "System Tools" fill:#fcc,stroke:#333,stroke-width:2px
```

## 2. Core Components

### 2.1. `JobSherpaAgent` (`agent.py`)
The main entry point and orchestrator for the agent. It is responsible for initializing all other components (e.g., `ConversationManager`, `JobHistory`) and exposing a single `run()` method to the user interface. It is UI-agnostic.

### 2.2. `ConversationManager` (`conversation_manager.py`)
The "brain" of the agent. It manages the flow of a conversation. It uses the `IntentClassifier` to determine what the user wants to do and then delegates the task to the appropriate `ActionHandler`. It also maintains the state for multi-turn conversations, such as when the agent needs to ask for more information.

### 2.3. `IntentClassifier` (`intent_classifier.py`)
A simple component that performs intent recognition on the user's prompt. It uses keyword matching to classify the prompt into a predefined category (e.g., `run_job`, `query_history`).

### 2.4. `Action Handlers` (`actions.py`)
A collection of classes, each responsible for executing a specific high-level action.
-   **`RunJobAction`**: Handles all logic related to running a job. This includes finding a matching application "recipe" using the RAG engine, validating required parameters, rendering job scripts, executing them via the `ToolExecutor`, and registering the job with `JobHistory`.
-   **`QueryHistoryAction`**: Handles queries about past jobs by retrieving information from the `JobHistory` component.

### 2.5. `JobHistory` (`job_history.py`)
Manages the state of all submitted jobs. It persists this information to a JSON file (`history.json`) within the user's workspace. It is responsible for registering new jobs, checking the status of pending jobs (by calling the system's scheduler, e.g., `squeue`), and parsing job output upon completion.

### 2.6. Other Components
-   **`WorkspaceManager`**: Manages the creation of clean, isolated, timestamped directories for each job run.
-   **`ToolExecutor`**: A simple wrapper around Python's `subprocess` module that executes shell commands (e.g., `sbatch`, `echo`).
-   **`ConfigManager`**: A robust, comment-preserving manager for loading and saving user and system configuration files using `pydantic` for validation and `ruamel.yaml` for file I/O.
-   **Knowledge Bases**: A set of YAML files that provide the agent with information about HPC systems, application recipes, and user default settings.

## 3. Component Interactions

This section describes the flow of control for key scenarios.

### 3.1. Standard Job Submission

1.  The **User** executes `jobsherpa run "..."`.
2.  The **CLI** instantiates the `JobSherpaAgent` and calls its `run()` method.
3.  The **Agent** passes the prompt to the `ConversationManager`.
4.  The **ConversationManager** calls the `IntentClassifier`, which returns the intent `run_job`.
5.  The **ConversationManager** delegates to the `RunJobAction`.
6.  The **RunJobAction** finds a matching recipe, confirms all required parameters are present, renders the job script, and uses the `ToolExecutor` to submit it.
7.  The `ToolExecutor` returns the stdout from the command (e.g., "Submitted batch job 12345").
8.  The **RunJobAction** parses the job ID and registers the new job with the `JobHistory`.
9.  The **RunJobAction** returns `(response, job_id, is_waiting=False, param_needed=None)`.
10. The **ConversationManager** and **Agent** pass this response back to the **CLI**, which prints it and exits.

### 3.2. Conversational Parameter Onboarding

This flow demonstrates how the agent handles missing information.

1.  Steps 1-5 are the same as above.
2.  The **RunJobAction** finds a matching recipe but discovers a required parameter (e.g., `allocation`) is missing from the user's configuration.
3.  Instead of failing, the **RunJobAction** constructs a question (e.g., "I need a value for 'allocation'. What should I use?").
4.  It then returns a 4-tuple to the `ConversationManager`: `("I need a value for 'allocation'...", None, True, "allocation")`.
5.  The **ConversationManager** sees that `is_waiting=True`. It saves the state of the conversation (the original prompt, the pending action, and the needed parameter "allocation") and passes the question back to the **CLI**.
6.  The **CLI** sees that `is_waiting=True`, prints the question, and displays a `>` prompt for user input.
7.  The **User** types their answer (e.g., "A-ccsc") and hits Enter.
8.  The **CLI** calls the `agent.run()` method again with the user's new input.
9.  The **ConversationManager** sees that it is in a `_is_waiting` state. It bypasses intent classification and assumes the user's input ("A-ccsc") is the answer for the `_param_needed` ("allocation"). It updates its internal context: `{'allocation': 'A-ccsc'}`.
10. It re-invokes the pending `RunJobAction` with the original prompt and the newly updated context.
11. The **RunJobAction** now has all the information it needs and proceeds with the standard job submission flow (Step 6 in the previous scenario).
12. The final response is passed back to the CLI, which sees that `is_waiting=False` and exits the interactive loop.
