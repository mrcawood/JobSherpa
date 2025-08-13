import typer
from jobsherpa.agent.agent import JobSherpaAgent

def main(
    prompt: str,
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Run in dry-run mode without executing real commands."
    ),
):
    """
    Run the JobSherpa agent with a specific prompt.
    """
    print("CLI is running...")
    agent = JobSherpaAgent(dry_run=dry_run)
    agent.start()
    response, job_id = agent.run(prompt)
    print("CLI received response:")
    print(f"--> {response}")
    
    # In a real CLI, we might want to start polling here or just exit.
    # For now, we'll just stop the agent to clean up the thread.
    agent.stop()

def run_app():
    typer.run(main)

if __name__ == "__main__":
    run_app()
