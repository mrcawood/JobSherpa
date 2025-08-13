import typer
import logging
from jobsherpa.agent.agent import JobSherpaAgent

def main(
    prompt: str,
    verbose: bool = typer.Option(
        False, "-v", "--verbose", help="Enable INFO level logging."
    ),
    debug: bool = typer.Option(
        False, "--debug", help="Enable DEBUG level logging."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Run in dry-run mode without executing real commands."
    ),
    system_profile: str = typer.Option(
        None, "--system-profile", help="The name of the system profile to use from the knowledge base."
    ),
    user_profile: str = typer.Option(
        None, "--user-profile", help="The name of the user profile to use for default values."
    ),
):
    """
    Run the JobSherpa agent with a specific prompt.
    """
    # Configure logging
    log_level = logging.WARNING
    if debug:
        log_level = logging.DEBUG
    elif verbose:
        log_level = logging.INFO
    
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    logging.info("CLI is running...")
    agent = JobSherpaAgent(
        dry_run=dry_run,
        system_profile=system_profile,
        user_profile=user_profile
    )
    agent.start()
    response, job_id = agent.run(prompt)
    
    # Use logger for agent output, but print final response to stdout
    logging.info("CLI received response: %s", response)
    print(f"--> {response}")
    
    agent.stop()

def run_app():
    typer.run(main)

if __name__ == "__main__":
    run_app()
