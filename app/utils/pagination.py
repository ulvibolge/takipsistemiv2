from typing import Optional, List, Dict, Any
from fastapi import Query
from pydantic import BaseModel, Field


class PaginationParams(BaseModel):
    """Pagination parameters model with validation."""
    page: int = Field(default=1, gt=0, description="Sayfa numarası")
    size: int = Field(default=20, gt=0, le=100, description="Sayfa başına kayıt sayısı")

    @property
    def skip(self) -> int:
        """Calculate the number of items to skip based on page and size."""
        return (self.page - 1) * self.size


def validate_pagination_params(
    page: int = Query(1, gt=0, description="Sayfa numarası"),
    size: int = Query(20, gt=0, le=100, description="Sayfa başına kayıt sayısı")
) -> PaginationParams:
    """Validate and return pagination parameters."""
    return PaginationParams(page=page, size=size)


def paginate(
    items: List[Dict[str, Any]], 
    total: int, 
    params: PaginationParams, 
    exclude_fields: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Paginate items with metadata and optional field exclusion.
    
    Args:
        items: List of items to paginate
        total: Total number of items available
        params: Pagination parameters
        exclude_fields: Optional list of fields to exclude from items
        
    Returns:
        Dictionary containing paginated response with metadata
    """
    if exclude_fields:
        items = [
            {k: v for k, v in item.items() if k not in exclude_fields}
            for item in items
        ]

    return {
        "items": items,
        "total": total,
        "page": params.page,
        "size": params.size,
        "pages": (total + params.size - 1) // params.size  # Calculate total pages
    }