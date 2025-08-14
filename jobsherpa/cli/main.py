import typer
import logging
import yaml
import os
from typing import Optional
from jobsherpa.agent.agent import JobSherpaAgent

app = typer.Typer()
config_app = typer.Typer()
app.add_typer(config_app, name="config", help="Manage user configuration.")

def get_user_profile_path(profile_name: Optional[str], profile_path: Optional[str]) -> str:
    """Determines the path to the user profile file."""
    if profile_path:
        return profile_path
    
    # Default to a standard location if no path is given
    if not profile_name:
        # In a real app, we might get the username from the environment
        profile_name = "default_user"
        
    return os.path.join("knowledge_base", "user", f"{profile_name}.yaml")

@config_app.command("set")
def config_set(
    key: str,
    value: str,
    user_profile: Optional[str] = typer.Option(None, "--user-profile", help="The name of the user profile to use."),
    user_profile_path: Optional[str] = typer.Option(None, "--user-profile-path", help="Direct path to user profile file (for testing).")
):
    """Set a configuration key-value pair in the user profile."""
    path = get_user_profile_path(user_profile, user_profile_path)
    
    # Ensure the directory exists
    os.makedirs(os.path.dirname(path), exist_ok=True)
    
    config = {}
    if os.path.exists(path):
        with open(path, 'r') as f:
            config = yaml.safe_load(f) or {}
            
    if "defaults" not in config:
        config["defaults"] = {}
        
    config["defaults"][key] = value
    
    with open(path, 'w') as f:
        yaml.dump(config, f)
        
    print(f"Updated configuration in {path}: set {key} = {value}")

@config_app.command("get")
def config_get(
    key: str,
    user_profile: Optional[str] = typer.Option(None, "--user-profile", help="The name of the user profile to use."),
    user_profile_path: Optional[str] = typer.Option(None, "--user-profile-path", help="Direct path to user profile file (for testing).")
):
    """Get a configuration value from the user profile."""
    path = get_user_profile_path(user_profile, user_profile_path)
    
    if not os.path.exists(path):
        print(f"Error: User profile not found at {path}")
        raise typer.Exit(1)
        
    with open(path, 'r') as f:
        config = yaml.safe_load(f)
        
    value = config.get("defaults", {}).get(key)
    
    if value:
        print(value)
    else:
        print(f"Error: Key '{key}' not found in user profile.")
        raise typer.Exit(1)

@app.command()
def run(
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
    app()

if __name__ == "__main__":
    run_app()
