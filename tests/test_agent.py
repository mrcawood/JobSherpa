import pytest
from jobsherpa.agent.agent import JobSherpaAgent
from freezegun import freeze_time
from unittest.mock import MagicMock, patch, mock_open
import yaml


def test_agent_initialization_fails_without_system_in_profile():
    """
    Tests that the agent raises a ValueError if the user profile
    lacks a required 'system' key.
    """
    # 1. Setup: Create a user profile *without* a system key
    user_profile = {
        "defaults": {
            "workspace": "/tmp/workspace",
            # "system" is deliberately missing
        }
    }
    
    # 2. Assert that initializing the agent raises a ValueError
    with pytest.raises(ValueError) as excinfo:
        JobSherpaAgent(user_config=user_profile)

    # 3. Check that the error message is helpful
    assert "User profile must contain a 'system' key" in str(excinfo.value)
    assert "jobsherpa config set system <system_name>" in str(excinfo.value)


def test_run_hello_world_dry_run():
    """
    Tests the agent's ability to find the 'hello world' recipe
    and execute the correct tool in dry-run mode.
    """
    # Provide a minimal valid user config to satisfy the new requirement
    user_config = {"defaults": {"system": "mock_system"}}
    agent = JobSherpaAgent(dry_run=True, user_config=user_config)
    
    # Mock the RAG pipeline to avoid dependency on real files
    with patch.object(agent.rag_pipeline, "run", autospec=True) as mock_pipeline_run:
        mock_document = MagicMock()
        mock_document.meta = {
            "name": "hello_world",
            "tool": "submit_job.sh",
            "args": ["--job-name=hello_world", "--nodes=1", "--wrap='echo Hello World'"]
        }
        mock_pipeline_run.return_value = {"documents": [mock_document]}

        prompt = "Doesn't matter what the prompt is now, mock will return correct recipe"
        response, _ = agent.run(prompt)
    
        assert "Found recipe 'hello_world'" in response
        assert "DRY-RUN: Would execute: tools/submit_job.sh" in response

def test_run_hello_world_real_execution():
    """
    Tests the agent's ability to execute the 'hello world' tool
    and parse the mock job ID from the result.
    """
    # Provide a minimal valid user config to satisfy the new requirement
    user_config = {"defaults": {"system": "mock_system"}}
    agent = JobSherpaAgent(dry_run=False, user_config=user_config)

    # Mock the RAG pipeline
    with patch.object(agent.rag_pipeline, "run", autospec=True) as mock_pipeline_run:
        mock_document = MagicMock()
        mock_document.meta = {
            "name": "hello_world",
            "tool": "submit_job.sh",
            "args": ["--job-name=hello_world", "--nodes=1", "--wrap='echo Hello World'"]
        }
        mock_pipeline_run.return_value = {"documents": [mock_document]}
        
        # Mock the tool executor to simulate a real execution
        with patch("jobsherpa.agent.tool_executor.ToolExecutor.execute", return_value="Submitted batch job mock_12345") as mock_execute:
            prompt = "Doesn't matter, mock will return correct recipe"
            response, job_id = agent.run(prompt)

            assert "Found recipe 'hello_world'" in response
            assert "Job submitted successfully with ID: mock_12345" in response
            assert job_id == "mock_12345"

def test_agent_tracks_job_lifecycle():
    """
    Tests that the agent uses the system profile and JobStateTracker
    to monitor a job's full lifecycle after submission.
    """
    agent = JobSherpaAgent(dry_run=False, system_profile="mock_slurm")
    job_id_to_test = "mock_12345"

    mock_sbatch_output = MagicMock(stdout=f"Submitted batch job {job_id_to_test}")
    mock_squeue_running = MagicMock(stdout=(
        "JOBID PARTITION NAME USER ST TIME NODES NODELIST(REASON)\n"
        f"{job_id_to_test} debug generic_hello user R 0:01 1 n01"
    ))
    mock_squeue_empty = MagicMock(stdout="")
    mock_sacct_completed = MagicMock(stdout=f"{job_id_to_test}|COMPLETED|0:0")

    with patch("subprocess.run", side_effect=[
        mock_sbatch_output, 
        mock_squeue_running, 
        mock_squeue_empty, 
        mock_sacct_completed
    ]) as mock_subprocess:
        response, job_id = agent.run("Run the generic hello")
        assert job_id == job_id_to_test

        # Verify the agent used the system profile to call 'sbatch'
        submit_call = mock_subprocess.call_args_list[0]
        assert "sbatch" in submit_call.args[0]

        assert agent.get_job_status(job_id) == "PENDING"

        agent.check_jobs()
        assert agent.get_job_status(job_id) == "RUNNING"
        
        agent.check_jobs()
        assert agent.get_job_status(job_id) == "COMPLETED"

def test_agent_uses_system_config_for_commands():
    """
    Tests that the agent can load a system configuration and use it
    to resolve a generic command like 'submit' to a specific executable
    like 'sbatch'.
    """
    agent = JobSherpaAgent(dry_run=True, system_profile="mock_slurm")
    
    with patch("jobsherpa.agent.tool_executor.ToolExecutor.execute", return_value="Submitted batch job mock_123") as mock_execute:
        agent.run("Run the generic hello")
        
        # Verify that the executor was called with 'sbatch', not 'submit'
        called_tool = mock_execute.call_args.args[0]
        assert called_tool == "sbatch"

def test_agent_uses_haystack_rag_pipeline():
    """
    Tests that the agent uses a Haystack RAG pipeline to find an
    application recipe, replacing the old manual search method.
    """
    agent = JobSherpaAgent(dry_run=True, system_profile="mock_slurm")
    
    # Mock the entire pipeline's run method
    with patch.object(agent.rag_pipeline, "run", autospec=True) as mock_pipeline_run:
        # Configure the mock to return a document that looks like our recipe
        mock_document = MagicMock()
        mock_document.meta = {
            "name": "generic_hello",
            "description": "A generic application...",
            "tool": "submit",
            "args": ["--wrap='echo Generic Hello'"]
        }
        mock_pipeline_run.return_value = {"documents": [mock_document]}
        
        agent.run("Run the generic hello")
        
        # Verify that the pipeline was called
        mock_pipeline_run.assert_called_once()

def test_agent_renders_and_executes_template(tmp_path):
    """
    Tests that the agent can find a recipe with a template,
    render it with the provided arguments, and execute the result.
    """
    agent = JobSherpaAgent(
        dry_run=False, 
        system_profile="mock_slurm",
        user_config={"defaults": {"workspace": str(tmp_path)}}
    )
    
    # Mock the RAG pipeline to return our new templated recipe
    with patch.object(agent.rag_pipeline, "run", autospec=True) as mock_pipeline_run:
        mock_document = MagicMock()
        mock_document.meta = {
            "name": "random_number_generator",
            "template": "random_number.sh.j2",
            "template_args": {
                "job_name": "test-rng-job",
                "output_file": "test_output.txt"
            },
            "tool": "submit"
        }
        mock_pipeline_run.return_value = {"documents": [mock_document]}
        
        # We need to mock subprocess.run here to inspect the stdin
        with patch("subprocess.run") as mock_subprocess:
            mock_subprocess.return_value = MagicMock(stdout="Submitted batch job mock_rng_123")
            agent.run("Generate a random number")
            
            # Verify the call to subprocess.run
            executed_call = mock_subprocess.call_args
            assert "sbatch" in executed_call.args[0]
            
            # Check the stdin passed to the command - now we check cwd
            assert mock_subprocess.call_args.kwargs["cwd"] == str(tmp_path)


def test_agent_parses_job_output(tmp_path):
    """
    Tests the full end-to-end flow of finding a templated recipe,
    rendering it, executing the job, and finally parsing the output
    file upon completion to retrieve a result.
    """
    agent = JobSherpaAgent(
        dry_run=False, 
        system_profile="mock_slurm",
        user_config={"defaults": {"workspace": str(tmp_path)}}
    )
    job_id = "mock_rng_123"
    random_number = "42"
    output_filename = "test_rng_output.txt"
    
    # 1. Mock the RAG pipeline to return the random_number recipe
    with patch.object(agent.rag_pipeline, "run", autospec=True) as mock_pipeline_run:
        mock_document = MagicMock()
        mock_document.meta = {
            "name": "random_number_generator",
            "template": "random_number.sh.j2",
            "template_args": {"job_name": "test-rng-job", "output_file": output_filename},
            "tool": "submit",
            "output_parser": {"file": output_filename, "parser_regex": r'(\d+)'}
        }
        mock_pipeline_run.return_value = {"documents": [mock_document]}
        
        # 2. Mock the sequence of system interactions
        mock_sbatch = MagicMock(stdout=f"Submitted batch job {job_id}")
        mock_squeue_empty = MagicMock(stdout="") # Job finishes instantly
        mock_sacct_completed = MagicMock(stdout=f"{job_id}|COMPLETED|0:0")
        
        # 3. Mock the output file that the agent will read
        mock_output_content = f"Some header\n{random_number}\nSome footer"
        
        with patch("subprocess.run", side_effect=[mock_sbatch, mock_squeue_empty, mock_sacct_completed]), \
             patch("builtins.open", mock_open(read_data=mock_output_content)) as mock_file:
            
            # Run the agent
            response, returned_job_id = agent.run("Generate a random number")
            assert returned_job_id == job_id
            
            # Manually trigger status check to simulate monitoring
            agent.check_jobs() 
            
            # 4. Verify the result
            assert agent.get_job_status(job_id) == "COMPLETED"
            assert agent.get_job_result(job_id) == random_number
            mock_file.assert_called_with(output_filename, 'r')

def test_agent_merges_user_and_system_profiles(tmp_path):
    """
    Tests that the agent correctly merges defaults from system and user
    profiles, with user values taking precedence.
    """
    # 1. Set up the environment
    system_profile_data = {"defaults": {"partition": "default-partition", "qos": "normal"}}
    user_profile_data = {
        "defaults": {
            "partition": "user-partition", # Overwrites system
            "allocation": "USER-123",
            "system": "mock_system" # Required
        }
    }
    
    # 2. Initialize Agent with mocked configs
    with patch.object(JobSherpaAgent, "_load_system_config", return_value=system_profile_data):
        agent = JobSherpaAgent(user_config=user_profile_data)

    # To make this test independent, we create a temporary knowledge base
    kb_path = tmp_path / "knowledge_base"
    user_dir = kb_path / "user"
    user_dir.mkdir(parents=True)
    
    # Create the user profile file that the agent will load
    user_profile_file = user_dir / "mcawood.yaml"
    user_profile = {
        "defaults": {
            "workspace": str(tmp_path / "workspace"),
            "partition": "user-partition", # Overwrites system
            "allocation": "USER-123",
            "system": "mock_system" # Required
        }
    }
    with open(user_profile_file, 'w') as f:
        yaml.dump(user_profile, f)
        
    # Point the agent to our temporary knowledge base
    agent.knowledge_base_dir = str(kb_path)
    # Reload the user config based on the new path
    agent.user_config = agent._load_user_config("mcawood")
    agent.workspace = agent.user_config.get("defaults", {}).get("workspace")
    
    # Mock the RAG pipeline
    with patch.object(agent.rag_pipeline, "run", autospec=True) as mock_pipeline_run:
        mock_document = MagicMock()
        mock_document.meta = {
            "name": "random_number_generator",
            "template": "random_number.sh.j2",
            "template_args": {
                "job_name": "test-rng-job",
                "output_file": "test_output.txt"
            },
            "tool": "submit"
        }
        mock_pipeline_run.return_value = {"documents": [mock_document]}
        
        # Mock subprocess.run to inspect the final script
        with patch("subprocess.run") as mock_subprocess:
            mock_subprocess.return_value = MagicMock(stdout="Submitted batch job mock_123")
            agent.run("Generate a random number")
            
            # Check that the command was run from the correct workspace
            assert mock_subprocess.call_args.kwargs["cwd"] == str(tmp_path / "workspace")
            
            # Check the content of the script file, not stdin
            script_path = mock_subprocess.call_args.args[0][1]
            with open(script_path, 'r') as f:
                rendered_script = f.read()
            
            # Assert that values from the user profile were merged and rendered
            assert "#SBATCH --partition=user-partition" in rendered_script
            assert "#SBATCH --account=USER-123" in rendered_script
            
            # Assert that values from the recipe were also rendered
            assert "#SBATCH --job-name=test-rng-job" in rendered_script

def test_agent_fails_gracefully_with_missing_requirements():
    """
    Tests that the agent returns a helpful error if the final context
    is missing a parameter required by the system profile.
    """
    system_config = {
        "name": "TestSystem",
        "job_requirements": ["partition", "allocation"]
    }
    user_config = {
        "defaults": {
            "partition": "development",
            # allocation is missing
            "system": "TestSystem" # Required
        }
    }
    # Pass system_config via the constructor's expected mechanism (mocking)
    with patch.object(JobSherpaAgent, "_load_system_config", return_value=system_config):
        agent = JobSherpaAgent(user_config=user_config)

    # Mock the RAG pipeline
    with patch.object(agent.rag_pipeline, "run", autospec=True) as mock_pipeline_run:
        mock_document = MagicMock()
        mock_document.meta = {
            "name": "random_number_generator",
            "template": "random_number.sh.j2",
            "template_args": {"job_name": "test-rng-job"}, # Missing partition/allocation
            "tool": "submit"
        }
        mock_pipeline_run.return_value = {"documents": [mock_document]}
        
        # The agent should not even attempt to run a subprocess
        with patch("subprocess.run") as mock_subprocess:
            response, job_id = agent.run("Generate a random number")
            
            assert job_id is None
            assert "Missing required job parameters" in response
            assert "allocation" in response
            mock_subprocess.assert_not_called()

def test_agent_operates_within_scoped_workspace(tmp_path):
    """
    Tests that the agent correctly uses the workspace defined in the
    user profile to write its script and execute from that directory.
    """
    # 1. Set up the environment
    workspace_path = tmp_path / "my_test_workspace"
    workspace_path.mkdir()
    
    user_profile = {
        "defaults": {
            "workspace": str(workspace_path),
            "partition": "development", 
            "allocation": "TACC-12345",
            "system": "vista" # Required
        }
    }

    # Create dummy vista.yaml so system config loading works
    system_dir = tmp_path / "knowledge_base" / "system"
    system_dir.mkdir(parents=True)
    vista_config = {
        "name": "vista",
        "commands": {"submit": "sbatch"}
    }
    with open(system_dir / "vista.yaml", 'w') as f:
        yaml.dump(vista_config, f)


    # 2. Initialize the agent, pointing to our temp KB
    agent = JobSherpaAgent(
        user_config=user_profile,
        knowledge_base_dir=str(tmp_path / "knowledge_base")
    )
    
    # 3. Mock the RAG pipeline and subprocess
    with patch.object(agent.rag_pipeline, "run", autospec=True) as mock_pipeline_run:
        mock_document = MagicMock()
        mock_document.meta = {
            "name": "random_number_generator",
            "template": "random_number.sh.j2",
            "template_args": {"job_name": "test-rng-job", "output_file": "rng.txt"},
            "tool": "submit"
        }
        mock_pipeline_run.return_value = {"documents": [mock_document]}
        
        with patch("subprocess.run") as mock_subprocess:
            mock_subprocess.return_value = MagicMock(stdout="Submitted batch job mock_123")
            agent.run("Generate a random number")

            # 4. Assert the workspace behavior
            
            # Assert that a script was written inside the workspace
            scripts_dir = workspace_path / ".jobsherpa" / "scripts"
            assert scripts_dir.is_dir()
            written_scripts = list(scripts_dir.glob("*.sh"))
            assert len(written_scripts) == 1
            
            # Assert that the executor was called with the path to that script
            executed_command = mock_subprocess.call_args.args[0]
            assert executed_command[0] == "sbatch"
            assert executed_command[1] == str(written_scripts[0])
            
            # Assert that the command was executed from within the workspace
            assert mock_subprocess.call_args.kwargs["cwd"] == str(workspace_path)

def test_agent_provides_helpful_error_for_missing_workspace(tmp_path):
    """
    Tests that the agent returns an actionable error message when a templated
    job is run without a workspace defined in the user profile.
    """
    # 1. Setup: Create a user profile *without* a workspace key
    user_profile = {
        "defaults": {
            "partition": "development",
            "allocation": "TACC-12345",
            "system": "vista" # Required
        }
    }
    
    # 2. Initialize agent with this incomplete profile
    agent = JobSherpaAgent(
        system_profile="vista",
        user_config=user_profile 
    )

    # 3. Mock the RAG pipeline to return a templated recipe
    with patch.object(agent.rag_pipeline, "run", autospec=True) as mock_pipeline_run:
        mock_document = MagicMock()
        mock_document.meta = {"name": "any_templated_job", "template": "any.j2"}
        mock_pipeline_run.return_value = {"documents": [mock_document]}

        # 4. Run and assert the error message
        response, job_id = agent.run("Run a templated job")

        assert job_id is None
        assert "Workspace must be defined" in response
        assert "jobsherpa config set workspace /path/to/your/workspace" in response

