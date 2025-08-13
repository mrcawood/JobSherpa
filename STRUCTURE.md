# JobSherpa Project Directory Structure

This document describes the directory structure for the JobSherpa project, outlining the purpose of each component.

```
jobsherpa/
├── agent/
├── cli/
├── docs/
├── knowledge_base/
│   ├── applications/
│   ├── system/
│   └── user/
├── tests/
└── tools/
```

### `/jobsherpa`
The root directory for the main Python package. All core application code resides here.

### `/jobsherpa/agent`
Contains the core backend logic of the AI agent. This package is designed to be self-contained and UI-agnostic. It will house the `Agent Core`, `RAG Engine`, `Task Planner`, `Job State Tracker`, etc. It knows nothing about being in a CLI or a web server; it just exposes a clean API.

### `/jobsherpa/cli`
The client interface for the Command-Line tool. This package is responsible for parsing command-line arguments, calling the public API of the `agent` package, and printing the results to the console. It is a thin wrapper around the agent.

### `/docs`
Project documentation, including `REQUIREMENTS.md`, `DESIGN.md`, and this `STRUCTURE.md` file.

### `/knowledge_base`
This directory holds the content for the RAG engine's knowledge bases. It is separated from the core application code.
-   **/applications**: Contains "recipes" for specific scientific applications (e.g., `wrf.yaml`).
-   **/system**: Contains configuration files for specific HPC systems (e.g., `frontera.yaml`).
-   **/user**: Will contain the persistent user memory databases (e.g., `user_mcawood.db`).

### `/tests`
Contains all the tests for the project, following a structure that mirrors the `jobsherpa` package.

### `/tools`
A library of pre-written, static scripts (e.g., `.sh`, `.py`) that the `Tool Executor` will run. These are the agent's "hands," providing a secure and reliable way to interact with the HPC system.
