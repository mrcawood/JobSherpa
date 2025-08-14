import typer
import logging
import yaml
import os
import getpass
from typing import Optional
# from jobsherpa.agent.agent import JobSherpaAgent # <-- This will be moved

app = typer.Typer()
config_app = typer.Typer()
app.add_typer(config_app, name="config", help="Manage user configuration.")

def get_user_profile_path(profile_name: Optional[str], profile_path: Optional[str]) -> str:
    """Determines the path to the user profile file."""
    if profile_path:
        return profile_path
    
    # Default to the current user's system username
    if not profile_name:
        profile_name = getpass.getuser()
        
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

@config_app.command("show")
def config_show(
    user_profile: Optional[str] = typer.Option(
        None, "--user-profile", help="The name of the user profile to show."
    ),
    user_profile_path: Optional[str] = typer.Option(
        None, "--user-profile-path", help="Direct path to the user profile file (for testing)."
    ),
):
    """
    Shows the entire contents of the user's configuration file.
    """
    profile_path = get_user_profile_path(user_profile, user_profile_path)
    
    if not os.path.exists(profile_path):
        print(f"Error: User profile not found at {profile_path}")
        raise typer.Exit(code=1)
        
    with open(profile_path, 'r') as f:
        print(f.read())


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
    system_profile: Optional[str] = typer.Option(
        None, "--system-profile", help="The name of the system profile to use from the knowledge base."
    ),
    user_profile: Optional[str] = typer.Option(
        None, "--user-profile", help="The name of the user profile to use for default values."
    ),
):
    """
    Run the JobSherpa agent with a specific prompt.
    """
    # Defer the import of the agent to this command
    from jobsherpa.agent.agent import JobSherpaAgent

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

    # If no user profile is specified, default to the current user
    effective_user_profile = user_profile or getpass.getuser()

    logging.info("CLI is running...")
    agent = JobSherpaAgent(
        dry_run=dry_run,
        knowledge_base_dir="knowledge_base",
        system_profile=system_profile,
        user_profile=effective_user_profile
    )
    response = agent.run(prompt)
    if isinstance(response, tuple):
        print(response[0])
    else:
        print(response)

def run_app():
    app()

if __name__ == "__main__":
    run_app()
