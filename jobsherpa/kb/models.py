from typing import Dict, List, Optional, Any, Literal
from pydantic import BaseModel, Field, validator


class SystemCommands(BaseModel):
    submit: str
    status: str
    history: str
    cancel: Optional[str] = None
    launcher: Optional[str] = None  # e.g., srun, ibrun


class SystemProfile(BaseModel):
    name: str
    scheduler: Literal["slurm"]
    description: Optional[str] = None
    commands: SystemCommands
    job_requirements: List[str] = Field(default_factory=list)
    available_partitions: List[str] = Field(default_factory=list)
    module_init: List[str] = Field(default_factory=list)  # commands to prep module environment
    filesystem_roots: Dict[str, str] = Field(default_factory=dict)  # e.g., {scratch: "/scratch", work: "/work"}


class OutputParser(BaseModel):
    file: str
    parser_regex: str


class ApplicationRecipe(BaseModel):
    name: str
    description: Optional[str] = None
    keywords: List[str] = Field(default_factory=list)
    template: str
    template_args: Dict[str, Any] = Field(default_factory=dict)
    module_loads: List[str] = Field(default_factory=list)
    output_parser: Optional[OutputParser] = None


class StagingSpec(BaseModel):
    url: str
    steps: List[str] = Field(default_factory=list)


class DatasetProfile(BaseModel):
    name: str
    aliases: List[str] = Field(default_factory=list)
    locations: Dict[str, str] = Field(default_factory=dict)  # system_name -> path
    staging: Optional[StagingSpec] = None
    pre_run_edits: List[str] = Field(default_factory=list)  # e.g., sed commands
    resource_hints: Dict[str, Any] = Field(default_factory=dict)  # e.g., {nodes: 4, time: "02:00:00"}


