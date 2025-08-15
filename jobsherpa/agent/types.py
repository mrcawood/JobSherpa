from dataclasses import dataclass
from typing import Optional


@dataclass
class ActionResult:
    message: str
    job_id: Optional[str] = None
    is_waiting: bool = False
    param_needed: Optional[str] = None
    status: Optional[str] = None
    error: Optional[str] = None


