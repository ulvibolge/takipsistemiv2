from pydantic import BaseModel
from typing import Optional

class Subcontractor(BaseModel):
    company_name: str
    contact_person: Optional[str]
    phone: Optional[str]
    assigned_project: Optional[str]
