import pytest
from jobsherpa.agent.agent import JobSherpaAgent
from freezegun import freeze_time
from unittest.mock import MagicMock, patch, mock_open

def test_run_hello_world_dry_run():
    """
    Tests the agent's ability to find the 'hello world' recipe
    and execute the correct tool in dry-run mode.
    """
    agent = JobSherpaAgent(dry_run=True)
    
    # Mock the RAG pipeline to ensure the correct recipe is "found"
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
    agent = JobSherpaAgent(dry_run=False)

    # Mock the RAG pipeline to ensure the correct recipe is "found"
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

def test_agent_renders_and_executes_template():
    """
    Tests that the agent can find a recipe with a template,
    render it with the provided arguments, and execute the result.
    """
    agent = JobSherpaAgent(dry_run=False, system_profile="mock_slurm")
    
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
            
            # Check the stdin passed to the command
            rendered_script = executed_call.kwargs["input"]
            assert "test-rng-job" in rendered_script
            assert "test_output.txt" in rendered_script
            assert "{{ job_name }}" not in rendered_script # Ensure template was rendered

def test_agent_parses_job_output():
    """
    Tests the full end-to-end flow of finding a templated recipe,
    rendering it, executing the job, and finally parsing the output
    file upon completion to retrieve a result.
    """
    agent = JobSherpaAgent(dry_run=False, system_profile="mock_slurm")
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
