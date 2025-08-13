import typer
from jobsherpa.agent.agent import JobSherpaAgent

def main(prompt: str):
    """
    Run the JobSherpa agent with a specific prompt.
    """
    print("CLI is running...")
    agent = JobSherpaAgent()
    response = agent.run(prompt)
    print("CLI received response:")
    print(f"--> {response}")

def run_app():
    typer.run(main)

if __name__ == "__main__":
    run_app()
