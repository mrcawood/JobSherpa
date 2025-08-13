# JobSherpa: An AI Agent for HPC

JobSherpa is an experimental AI-powered agent designed to simplify interactions with High-Performance Computing (HPC) systems. The goal is to provide a natural language interface that allows users to manage complex scientific workflows without needing to be experts in command-line tools and job schedulers.

## Core Features

-   **Natural Language Interface:** Interact with HPC systems using plain English commands.
-   **RAG-Powered:** Uses a Retrieval-Augmented Generation pipeline to find the correct workflow for a given prompt.
-   **Dynamic Script Generation:** Constructs job scripts on-the-fly using Jinja2 templates.
-   **Stateful Job Monitoring:** A background tracker monitors jobs and can report on their status throughout their lifecycle.
-   **Output Parsing:** Can parse job output files to extract and report specific results.

## Getting Started

These instructions will get you a copy of the project up and running on your local machine or an HPC login node for development and testing.

### Prerequisites

-   Python 3.10+
-   `pip` and `venv`
-   Git

### Installation

1.  **Clone the repository:**
    ```bash
    git clone git@github.com:mrcawood/JobSherpa.git
    cd JobSherpa
    ```

2.  **Create and activate a virtual environment:**
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    ```

3.  **Install the project in editable mode with all dependencies:**
    ```bash
    pip install -e ".[test,inference]"
    ```

## Usage

Once installed, you can interact with the agent via the `jobsherpa` command-line tool.

### Example 1: Generate a Random Number

This is the primary end-to-end example. It uses a template to generate a script, submits it, waits for it to complete, and parses the output file.

```bash
jobsherpa "Generate a random number for me"
```

### Example 2: Run a simple test job

This example uses a pre-defined, non-templated job script.

```bash
jobsherpa "Run the legacy hello world test"
```

To run the agent in dry-run mode (which prevents real commands from being executed), use the `--dry-run` flag:
```bash
jobsherpa "Generate a random number for me" --dry-run
```

## Configuration for a Real HPC System

To use JobSherpa on a real HPC system, you need to tell it how to interact with the local scheduler (e.g., Slurm, PBS).

1.  Create a new YAML file in `knowledge_base/system/`, for example `frontera.yaml`.
2.  Define the system's commands in this file. The agent uses generic keys like `submit` and `status`, which you map to the system-specific executables.

**Example `knowledge_base/system/frontera.yaml`:**
```yaml
name: Frontera
scheduler: slurm
description: TACC's Frontera system.
commands:
  submit: sbatch
  status: squeue
  history: sacct
```

3.  Run the agent with the `--system-profile` flag, specifying the name of your new file (without the `.yaml` extension).

```bash
jobsherpa --system-profile frontera "Generate a random number for me"
```

## Development

This project follows a Test-Driven Development (TDD) approach. To run the test suite, use `pytest`:
```bash
pytest
```
For more details on the development roadmap and current technical debt, see `DEVELOPMENT.md`.
