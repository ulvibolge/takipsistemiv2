from pydantic import BaseModel
from typing import Optional, List

class Project(BaseModel):
    name: str
    description: Optional[str]
    start_date: Optional[str]
    end_date: Optional[str]
    status: Optional[str]
    assigned_personnel: Optional[List[str]] = []
