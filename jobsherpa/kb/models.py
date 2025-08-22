from typing import Dict, List, Optional, Any, Literal
from pydantic import BaseModel, Field, validator


class SystemCommands(BaseModel):
    submit: str
    status: str
    history: str
    cancel: Optional[str] = None
    launcher: Optional[str] = None  # e.g., srun, ibrun
    # Forbid unknown keys across Pydantic v1/v2
    try:  # Pydantic v2
        model_config = {"extra": "forbid"}  # type: ignore[attr-defined]
    except Exception:
        class Config:  # Pydantic v1
            extra = "forbid"


class SystemProfile(BaseModel):
    name: str
    scheduler: Literal["slurm"]
    description: Optional[str] = None
    commands: Optional[SystemCommands] = None
    job_requirements: List[str] = Field(default_factory=list)
    available_partitions: List[str] = Field(default_factory=list)
    module_init: List[str] = Field(default_factory=list)  # commands to prep module environment
    filesystem_roots: Dict[str, str] = Field(default_factory=dict)  # e.g., {scratch: "/scratch", work: "/work"}
    apps: Dict[str, Dict[str, str]] = Field(default_factory=dict)  # optional per-app bindings (e.g., {wrf: {module: ..., exe_path: ...}})
    launcher: Optional[str] = None  # system-preferred launcher (e.g., ibrun)


class SchedulerProfile(BaseModel):
    name: str
    commands: SystemCommands
    try:
        model_config = {"extra": "forbid"}  # type: ignore[attr-defined]
    except Exception:
        class Config:
            extra = "forbid"


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
    binary: Optional[Dict[str, str]] = None  # e.g., {name: "wrf.exe"}
    dataset_required: bool = False


class StagingSpec(BaseModel):
    url: str
    steps: List[str] = Field(default_factory=list)
    # Optional helpers to normalize extracted archive layout
    strip_components: int = 0  # tar --strip-components value
    working_subdir: Optional[str] = None  # cd into this subdir (relative to job_dir) after staging


class DatasetProfile(BaseModel):
    name: str
    aliases: List[str] = Field(default_factory=list)
    locations: Dict[str, str] = Field(default_factory=dict)  # system_name -> path
    staging: Optional[StagingSpec] = None
    pre_run_edits: List[str] = Field(default_factory=list)  # e.g., sed commands
    resource_hints: Dict[str, Any] = Field(default_factory=dict)  # e.g., {nodes: 4, time: "02:00:00"}


class SiteProfile(BaseModel):
    name: str
    description: Optional[str] = None
    job_requirements: List[str] = Field(default_factory=list)
    module_init: List[str] = Field(default_factory=list)
    systems: List[str] = Field(default_factory=list)
    # Allow optional launcher if defined at site level in the future
    launcher: Optional[str] = None
    try:
        model_config = {"extra": "ignore"}  # tolerate site-specific keys
    except Exception:
        class Config:
            extra = "ignore"


