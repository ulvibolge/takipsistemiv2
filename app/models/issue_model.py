from pydantic import BaseModel
from typing import Optional

class Issue(BaseModel):
    title: str
    description: Optional[str]
    reported_by: Optional[str]
    status: Optional[str]
    date_reported: Optional[str]
