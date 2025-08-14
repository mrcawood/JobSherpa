import pytest
from jobsherpa.agent.agent import JobSherpaAgent
from freezegun import freeze_time
from unittest.mock import MagicMock, patch, mock_open
import yaml
import uuid
from jobsherpa.agent.workspace_manager import JobWorkspace


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
            "args": ["--job-name=hello_world"]
        }
        mock_pipeline_run.return_value = {"documents": [mock_document]}
        
        response, job_id = agent.run("Run hello world")
        
        assert job_id is None
        assert "DRY-RUN" in response
        assert "submit_job.sh --job-name=hello_world" in response


def test_run_hello_world_real_execution():
    """
    Tests the agent's ability to execute the 'hello world' tool
    and parse the mock job ID from the result.
    """
    # Provide a minimal valid user config to satisfy the new requirement
    user_config = {"defaults": {"system": "mock_system", "workspace": "/tmp"}}
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

            assert "Job submitted successfully" in response
            assert job_id == "mock_12345"
            mock_execute.assert_called_with(
                "submit_job.sh",
                ["--job-name=hello_world", "--nodes=1", "--wrap='echo Hello World'"],
                workspace="/tmp"
            )


def test_agent_tracks_job_lifecycle():
    """
    Tests that the agent uses the system profile and JobStateTracker
    to monitor a job's full lifecycle after submission.
    """
    user_config = {"defaults": {"system": "mock_slurm", "workspace": "/tmp"}}
    agent = JobSherpaAgent(dry_run=False, system_profile="mock_slurm", user_config=user_config)
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
        assert agent.get_job_status(job_id) == "PENDING"
        
        # Manually trigger checks to simulate monitoring loop
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
    user_config = {"defaults": {"system": "mock_slurm", "workspace": "/tmp"}}
    agent = JobSherpaAgent(dry_run=True, system_profile="mock_slurm", user_config=user_config)

    with patch("jobsherpa.agent.tool_executor.ToolExecutor.execute", return_value="Submitted batch job mock_123") as mock_execute:
        agent.run("Run the generic hello")
        # Check that the generic 'submit' from the recipe was translated to 'sbatch'
        mock_execute.assert_called_with("sbatch", ["--wrap='echo Generic Hello'"], workspace='/tmp')


def test_agent_renders_and_executes_template(tmp_path):
    """
    Tests that the agent can find a recipe with a template,
    render it with the provided arguments, and execute the result.
    """
    user_config={"defaults": {"workspace": str(tmp_path), "system": "mock_slurm", "partition": "a", "allocation": "b"}}
    agent = JobSherpaAgent(dry_run=False, system_profile="mock_slurm", user_config=user_config)
    
    mock_template = MagicMock()
    mock_template.render.return_value = "script content"

    with patch("uuid.uuid4") as mock_uuid, \
         patch.object(agent.rag_pipeline, "run", autospec=True) as mock_pipeline_run, \
         patch("jinja2.Environment.get_template", return_value=mock_template), \
         patch("subprocess.run") as mock_subprocess:
        
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
        mock_subprocess.return_value = MagicMock(stdout="Submitted batch job mock_rng_123")
        
        agent.run("Generate a random number")
        
        executed_call = mock_subprocess.call_args
        assert "sbatch" in executed_call.args[0]
        
        expected_job_dir = tmp_path / str(mock_uuid.return_value)
        assert mock_subprocess.call_args.kwargs["cwd"] == str(expected_job_dir)


def test_agent_parses_job_output(tmp_path):
    """
    Tests the full end-to-end flow of finding a templated recipe,
    rendering it, executing the job, and finally parsing the output
    file upon completion to retrieve a result.
    """
    user_config={"defaults": {"workspace": str(tmp_path), "system": "mock_slurm", "partition": "a", "allocation": "b"}}
    agent = JobSherpaAgent(dry_run=False, system_profile="mock_slurm", user_config=user_config)
    
    job_id = "mock_rng_123"
    random_number = "42"
    output_filename = "test_rng_output.txt"

    job_uuid = uuid.uuid4()
    job_dir = tmp_path / str(job_uuid)
    mock_job_workspace = JobWorkspace(
        job_dir=job_dir,
        output_dir=job_dir / "output",
        slurm_dir=job_dir / "slurm",
        script_path=job_dir / "job_script.sh"
    )
    with patch("jobsherpa.agent.workspace_manager.WorkspaceManager.create_job_workspace", return_value=mock_job_workspace), \
         patch.object(agent.rag_pipeline, "run", autospec=True) as mock_pipeline_run:
        
        mock_document = MagicMock()
        mock_document.meta = {
            "name": "random_number_generator",
            "template": "random_number.sh.j2",
            "template_args": {"job_name": "test-rng-job", "output_file": output_filename},
            "tool": "submit",
            "output_parser": {"file": output_filename, "parser_regex": r'(\d+)'}
        }
        mock_pipeline_run.return_value = {"documents": [mock_document]}

        mock_sbatch = MagicMock(stdout=f"Submitted batch job {job_id}")
        mock_squeue_empty = MagicMock(stdout="")
        mock_sacct_completed = MagicMock(stdout=f"{job_id}|COMPLETED|0:0")
        mock_output_content = f"Some header\n{random_number}\nSome footer"

        with patch("subprocess.run", side_effect=[mock_sbatch, mock_squeue_empty, mock_sacct_completed]), \
             patch("builtins.open", mock_open(read_data=mock_output_content)) as mock_file:

            response, returned_job_id = agent.run("Generate a random number")
            assert returned_job_id == job_id

            agent.check_jobs()

            assert agent.get_job_status(job_id) == "COMPLETED"
            assert agent.get_job_result(job_id) == random_number
            
            expected_output_path = mock_job_workspace.output_dir / output_filename
            mock_file.assert_called_with(str(expected_output_path), 'r')


def test_agent_merges_user_and_system_profiles(tmp_path):
    """
    Tests that the agent correctly merges defaults from system and user
    profiles, with user values taking precedence.
    """
    system_profile_data = {"defaults": {"partition": "default-partition", "qos": "normal"}}
    user_profile_data = {
        "defaults": {
            "workspace": str(tmp_path / "workspace"),
            "partition": "user-partition", 
            "allocation": "USER-123",
            "system": "mock_system"
        }
    }
    
    job_uuid = uuid.uuid4()
    mock_template = MagicMock()
    mock_template.render.return_value = "script content"

    with patch("uuid.uuid4", return_value=job_uuid), \
         patch.object(JobSherpaAgent, "_load_system_config", return_value=system_profile_data), \
         patch("jinja2.Environment.get_template", return_value=mock_template), \
         patch("subprocess.run") as mock_subprocess:

        agent = JobSherpaAgent(user_config=user_profile_data)
        
        with patch.object(agent.rag_pipeline, "run", autospec=True) as mock_pipeline_run:
            mock_document = MagicMock()
            mock_document.meta = {
                "name": "random_number_generator",
                "template": "random_number.sh.j2",
                "tool": "submit"
            }
            mock_pipeline_run.return_value = {"documents": [mock_document]}
            mock_subprocess.return_value = MagicMock(stdout="Submitted batch job mock_123")
            
            agent.run("Generate a random number")

            mock_job_workspace = JobWorkspace(
                job_dir=(tmp_path / "workspace") / str(job_uuid),
                output_dir=(tmp_path / "workspace") / str(job_uuid) / "output",
                slurm_dir=(tmp_path / "workspace") / str(job_uuid) / "slurm",
                script_path=(tmp_path / "workspace") / str(job_uuid) / "job_script.sh"
            )
            assert mock_subprocess.call_args.kwargs["cwd"] == str(mock_job_workspace.job_dir)


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
            "system": "TestSystem"
        }
    }
    
    with patch.object(JobSherpaAgent, "_load_system_config", return_value=system_config):
        agent = JobSherpaAgent(user_config=user_config)

    with patch.object(agent.rag_pipeline, "run", autospec=True) as mock_pipeline_run:
        mock_document = MagicMock()
        mock_document.meta = {"name": "any_templated_job", "template": "any.j2"}
        mock_pipeline_run.return_value = {"documents": [mock_document]}

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
    workspace_path = tmp_path / "my_test_workspace"
    workspace_path.mkdir()
    
    user_profile = {
        "defaults": {
            "workspace": str(workspace_path),
            "partition": "development",
            "allocation": "TACC-12345",
            "system": "vista"
        }
    }

    system_dir = tmp_path / "knowledge_base" / "system"
    system_dir.mkdir(parents=True)
    vista_config = {
        "name": "vista",
        "commands": {"submit": "sbatch"}
    }
    with open(system_dir / "vista.yaml", 'w') as f:
        yaml.dump(vista_config, f)

    job_uuid = uuid.uuid4()
    mock_template = MagicMock()
    mock_template.render.return_value = "script content"

    with patch("uuid.uuid4", return_value=job_uuid), \
         patch("jinja2.Environment.get_template", return_value=mock_template), \
         patch("subprocess.run") as mock_subprocess:

        agent = JobSherpaAgent(
            user_config=user_profile,
            knowledge_base_dir=str(tmp_path / "knowledge_base")
        )
        
        with patch.object(agent.rag_pipeline, "run", autospec=True) as mock_rag_run:
            mock_document = MagicMock()
            mock_document.meta = {"name": "mock_job", "tool": "submit", "template": "any.j2"}
            mock_rag_run.return_value = {"documents": [mock_document]}
            mock_subprocess.return_value = MagicMock(stdout="Submitted batch job mock_123")
            
            agent.run("Generate a random number")

            mock_job_workspace = JobWorkspace(
                job_dir=workspace_path / str(job_uuid),
                output_dir=workspace_path / str(job_uuid) / "output",
                slurm_dir=workspace_path / str(job_uuid) / "slurm",
                script_path=workspace_path / str(job_uuid) / "job_script.sh"
            )
            assert mock_job_workspace.job_dir.is_dir()
            assert mock_subprocess.call_args.kwargs["cwd"] == str(mock_job_workspace.job_dir)


def test_agent_provides_helpful_error_for_missing_workspace(tmp_path):
    """
    Tests that the agent returns an actionable error message when a templated
    job is run without a workspace defined in the user profile.
    """
    user_profile = {
        "defaults": {
            "partition": "development",
            "allocation": "TACC-12345",
            "system": "vista"
        }
    }
    
    agent = JobSherpaAgent(system_profile="vista", user_config=user_profile)

    with patch.object(agent.rag_pipeline, "run", autospec=True) as mock_pipeline_run:
        mock_document = MagicMock()
        mock_document.meta = {"name": "any_templated_job", "template": "any.j2"}
        mock_pipeline_run.return_value = {"documents": [mock_document]}

        response, job_id = agent.run("Run a templated job")

        assert job_id is None
        assert "Workspace must be defined" in response
        assert "jobsherpa config set workspace /path/to/your/workspace" in response

