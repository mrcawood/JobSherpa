import yaml
import os
import re
import jinja2
from typing import Optional
from jobsherpa.agent.tool_executor import ToolExecutor
from jobsherpa.agent.job_state_tracker import JobStateTracker
from haystack.document_stores import InMemoryDocumentStore
from haystack.nodes import BM25Retriever
from haystack import Pipeline
from haystack import Document

class JobSherpaAgent:
    """
    The core logic of the JobSherpa AI agent.
    This class is UI-agnostic and exposes a clean API.
    """
    def __init__(
        self, 
        dry_run: bool = False, 
        knowledge_base_dir: str = "knowledge_base",
        system_profile: Optional[str] = None
    ):
        """
        Initializes the agent.
        """
        self.dry_run = dry_run
        self.tool_executor = ToolExecutor(dry_run=self.dry_run)
        self.knowledge_base_dir = knowledge_base_dir
        self.system_config = self._load_system_config(system_profile)
        self.tracker = JobStateTracker()
        self.rag_pipeline = self._initialize_rag_pipeline()

    def start(self):
        """Starts the agent's background threads."""
        self.tracker.start_monitoring()

    def check_jobs(self):
        """Triggers the job state tracker to check for updates."""
        self.tracker.check_and_update_statuses()

    def stop(self):
        """Stops the agent's background threads."""
        self.tracker.stop_monitoring()

    def get_job_status(self, job_id: str) -> Optional[str]:
        """Gets the status of a job from the tracker."""
        return self.tracker.get_status(job_id)

    def _load_app_recipes(self):
        """Loads all application recipes from the knowledge base."""
        recipes = {}
        app_dir = os.path.join(self.knowledge_base_dir, "applications")
        for filename in os.listdir(app_dir):
            if filename.endswith(".yaml"):
                with open(os.path.join(app_dir, filename), 'r') as f:
                    recipe = yaml.safe_load(f)
                    recipes[recipe['name']] = recipe
        return recipes

    def _load_system_config(self, profile_name: Optional[str]):
        """Loads a specific system configuration from the knowledge base."""
        if not profile_name:
            return None
        
        system_file = os.path.join(self.knowledge_base_dir, "system", f"{profile_name}.yaml")
        if os.path.exists(system_file):
            with open(system_file, 'r') as f:
                return yaml.safe_load(f)
        return None

    def _initialize_rag_pipeline(self) -> Pipeline:
        """Initializes the Haystack RAG pipeline and indexes documents."""
        document_store = InMemoryDocumentStore(use_bm25=True)
        
        # Index all application recipes
        app_dir = os.path.join(self.knowledge_base_dir, "applications")
        docs = []
        for filename in os.listdir(app_dir):
            if filename.endswith(".yaml"):
                with open(os.path.join(app_dir, filename), 'r') as f:
                    recipe = yaml.safe_load(f)
                    # Use keywords as the content for BM25 search
                    content = " ".join(recipe.get("keywords", []))
                    doc = Document(content=content, meta=recipe)
                    docs.append(doc)
        
        document_store.write_documents(docs)
        
        retriever = BM25Retriever(document_store=document_store)
        pipeline = Pipeline()
        pipeline.add_node(component=retriever, name="Retriever", inputs=["Query"])
        return pipeline

    def _find_matching_recipe(self, prompt: str):
        """Finds a recipe using the Haystack RAG pipeline."""
        results = self.rag_pipeline.run(query=prompt)
        if results["documents"]:
            # The meta field of the document contains our original recipe dict
            return results["documents"][0].meta
        return None

    def _parse_job_id(self, output: str) -> Optional[str]:
        """Parses a job ID from a string using regex."""
        match = re.search(r"Submitted batch job (\S+)", output)
        if match:
            return match.group(1)
        return None

    def run(self, prompt: str) -> tuple[str, Optional[str]]:
        """
        The main entry point for the agent to process a user prompt.
        Returns a user-facing response string and an optional job ID.
        """
        print(f"Agent received prompt: {prompt}")

        recipe = self._find_matching_recipe(prompt)

        if not recipe:
            return "Sorry, I don't know how to handle that.", None

        # Check if the recipe uses a template
        if "template" in recipe:
            template_name = recipe["template"]
            template_args = recipe.get("template_args", {})
            
            # Create a Jinja2 environment
            template_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'tools')
            env = jinja2.Environment(loader=jinja2.FileSystemLoader(template_dir))
            
            try:
                template = env.get_template(template_name)
                rendered_script = template.render(template_args)
                
                # The "tool" in a templated recipe is the command to pipe the script to
                submit_command = recipe["tool"]
                if self.system_config and submit_command in self.system_config.get("commands", {}):
                    submit_command = self.system_config["commands"][submit_command]

                # The ToolExecutor will receive the submit command and the script content
                execution_result = self.tool_executor.execute(submit_command, [], script_content=rendered_script)

            except jinja2.TemplateNotFound:
                return f"Error: Template '{template_name}' not found.", None
            except Exception as e:
                return f"Error rendering template: {e}", None
        else:
            # Fallback to existing logic for non-templated recipes
            tool_name = recipe['tool']
            if self.system_config and tool_name in self.system_config.get("commands", {}):
                tool_name = self.system_config["commands"][tool_name]
            
            args = recipe.get('args', [])
            execution_result = self.tool_executor.execute(tool_name, args)

        job_id = self._parse_job_id(execution_result)
        if job_id:
            # Pass the parser info to the tracker when registering the job
            output_parser = recipe.get("output_parser")
            self.tracker.register_job(job_id, output_parser_info=output_parser)
            response = f"Found recipe '{recipe['name']}'.\nJob submitted successfully with ID: {job_id}"
            return response, job_id

        response = f"Found recipe '{recipe['name']}'.\nExecution result: {execution_result}"
        return response, None

    def get_job_result(self, job_id: str) -> Optional[str]:
        """Gets the parsed result of a completed job."""
        return self.tracker.get_result(job_id)
