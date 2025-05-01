from pydantic import BaseModel
from typing import Optional

class Personnel(BaseModel):
    name: str
    role: str
    contact: Optional[str]
    assigned_project: Optional[str]
