import typer
import logging
import yaml
import os
import getpass
from jobsherpa.util.errors import ExceptionManager
from typing import Optional
# from jobsherpa.agent.agent import JobSherpaAgent # <-- This will be moved
from jobsherpa.agent.config_manager import ConfigManager

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
    key: str = typer.Argument(..., help="The configuration key to set (e.g., 'workspace')."),
    value: str = typer.Argument(..., help="The value to set."),
    user_profile: Optional[str] = typer.Option(None, "--user-profile", help="The user profile to modify."),
    user_profile_path: Optional[str] = typer.Option(None, "--user-profile-path", help="Direct path to the user profile YAML file.", hidden=True),
):
    """Set a default configuration value in your user profile."""
    profile_path = get_user_profile_path(user_profile, user_profile_path)
    manager = ConfigManager(config_path=profile_path)
    
    config = None
    if os.path.exists(profile_path):
        try:
            config = manager.load()
        except Exception:
            pass # Will create a new one below
            
    if config is None:
        from jobsherpa.config import UserConfig, UserConfigDefaults
        # Create a new config object with empty strings for required fields
        config = UserConfig(defaults=UserConfigDefaults(workspace="", system=""))

    if not hasattr(config.defaults, key):
        print(f"Error: Unknown configuration key '{key}'. Valid keys are: workspace, system, partition, allocation.")
        raise typer.Exit(code=1)

    setattr(config.defaults, key, value)
    manager.save(config)
    print(f"Updated '{key}' in profile: {profile_path}")

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
        
    try:
        with open(path, 'r') as f:
            config = yaml.safe_load(f)
    except Exception as e:
        from jobsherpa.util.errors import ExceptionManager
        typer.secho(ExceptionManager.handle(e), fg=typer.colors.RED)
        raise typer.Exit(1)
        
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
        
    try:
        with open(profile_path, 'r') as f:
            print(f.read())
    except Exception as e:
        from jobsherpa.util.errors import ExceptionManager
        typer.secho(ExceptionManager.handle(e), fg=typer.colors.RED)
        raise typer.Exit(code=1)


def setup_logging(level: int):
    """
    Configure application logging at process start.
    Uses basicConfig with force=True to reset pre-existing handlers safely.
    Also reduces noise from very chatty third-party libraries when not debugging.
    """
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        force=True,
    )
    if level > logging.DEBUG:
        logging.getLogger("haystack").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)

@app.command()
def run(
    prompt: str = typer.Argument(..., help="The user's prompt to the agent."),
    verbose: bool = typer.Option(
        False, "-v", "--verbose", help="Enable INFO level logging."
    ),
    debug: bool = typer.Option(
        False, "-d", "--debug", help="Enable DEBUG level logging."
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
    Runs the JobSherpa agent with the given prompt.
    """
    # --- 1. Set up logging FIRST ---
    log_level = logging.WARNING
    if debug:
        log_level = logging.DEBUG
    elif verbose:
        log_level = logging.INFO
    setup_logging(log_level)

    # --- 2. Defer agent import until after logging is configured ---
    from jobsherpa.agent.agent import JobSherpaAgent
    
    effective_user_profile = user_profile if user_profile else getpass.getuser()

    logging.info("CLI is running...")
    
    try:
        agent = JobSherpaAgent(
            dry_run=dry_run,
            knowledge_base_dir="knowledge_base",
            system_profile=system_profile,
            user_profile=effective_user_profile
        )
        
        is_waiting = True
        current_prompt = prompt
        
        while is_waiting:
            response, job_id, is_waiting = agent.run(current_prompt)
            
            # Print the agent's response
            if isinstance(response, tuple):
                 # This can happen if an action returns a tuple by mistake
                print(response[0])
            else:
                print(response)

            if is_waiting:
                current_prompt = input("> ")
            
    except Exception as e:
        if debug:
            import traceback
            traceback.print_exc()
        else:
            user_msg = ExceptionManager.handle(e)
            typer.secho(user_msg, fg=typer.colors.RED)
        raise typer.Exit(code=1)

def run_app():
    app()

if __name__ == "__main__":
    run_app()
