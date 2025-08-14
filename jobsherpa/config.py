from pydantic import BaseModel
from typing import Optional

class UserConfigDefaults(BaseModel):
    """Defines the schema for the 'defaults' section of the user config."""
    workspace: str
    system: str
    partition: Optional[str] = None
    allocation: Optional[str] = None

class UserConfig(BaseModel):
    """Defines the top-level schema for a user's configuration file."""
    defaults: UserConfigDefaults
