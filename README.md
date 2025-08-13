# JobSherpa: An AI Agent for HPC

JobSherpa is an experimental AI-powered agent designed to simplify interactions with High-Performance Computing (HPC) systems. The goal is to provide a natural language interface that allows users to manage complex scientific workflows without needing to be experts in command-line tools and job schedulers.

## Core Features (Under Development)

-   **Natural Language Prompts:** Interact with HPC systems using plain English commands.
-   **Automated Workflow Construction:** The agent can construct job scripts and directory structures based on high-level application recipes.
-   **Intelligent Job Monitoring:** A stateful tracker monitors jobs and can report on their status throughout their lifecycle.
-   **Portable Design:** Built with a modular architecture to support different HPC systems, schedulers, and scientific applications in the future.

## Getting Started

These instructions will get you a copy of the project up and running on your local machine for development and testing purposes.

### Prerequisites

-   Python 3.10+
-   `pip` and `venv`

### Installation

1.  **Clone the repository:**
    ```bash
    git clone <your-repo-url>
    cd JobSherpa
    ```

2.  **Create and activate a virtual environment:**
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    ```

3.  **Install the project in editable mode with test dependencies:**
    ```bash
    pip install -e ".[test]"
    ```

### Usage

Once installed, you can interact with the agent via the `jobsherpa` command-line tool.

**Run a job:**
```bash
jobsherpa run "Your prompt here"
```

**Example:**
```bash
jobsherpa run "Run the hello world test"
```

To run the agent in dry-run mode (which prevents real commands from being executed), use the `--dry-run` flag:
```bash
jobsherpa run "Run the hello world test" --dry-run
```

## Development

This project follows a Test-Driven Development (TDD) approach. To run the test suite, use `pytest`:
```bash
pytest
```
For more details on the development roadmap and current technical debt, see `DEVELOPMENT.md`.
