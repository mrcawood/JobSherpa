from jobsherpa.agent.job_history import JobHistory
from jobsherpa.agent.workspace_manager import WorkspaceManager

class RunJobAction:
    def __init__(self, job_history: JobHistory, workspace_manager: WorkspaceManager):
        self.job_history = job_history
        self.workspace_manager = workspace_manager

    def run(self, prompt: str):
        # Placeholder for now
        pass

class QueryHistoryAction:
    def __init__(self, job_history: JobHistory):
        self.job_history = job_history

    def run(self, prompt: str):
        # Placeholder for now
        pass
