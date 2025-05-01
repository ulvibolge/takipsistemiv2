from datetime import datetime
from fastapi import APIRouter, status, Depends, HTTPException, Query, Path, Request, Body
from fastapi.responses import JSONResponse
from app.schemas.project_schema import (
    ProjectCreate, 
    ProjectUpdate, 
    ProjectOut, 
    ProjectList,
    ProjectStatsResponse
)
from app.services.project_service import ProjectService
from app.core.security import (
    get_current_user,
    get_current_active_user,
    validate_project_access,
    check_project_permission
)
from app.utils.pagination import PaginationParams, paginate, validate_pagination_params
from app.utils.logger import logger
from app.utils.rate_limiter import limiter
from app.core.config import settings
from typing import Optional, List, Any
from pydantic import TypeAdapter
from bson import ObjectId
from enum import Enum

router = APIRouter(
    prefix="/projects",
    tags=["Projeler"],
    responses={
        status.HTTP_400_BAD_REQUEST: {"description": "Geçersiz istek"},
        status.HTTP_401_UNAUTHORIZED: {"description": "Yetkilendirme hatası"},
        status.HTTP_403_FORBIDDEN: {"description": "Yetkisiz erişim"},
        status.HTTP_404_NOT_FOUND: {"description": "Proje bulunamadı"},
        status.HTTP_409_CONFLICT: {"description": "Veri çakışması"},
        status.HTTP_422_UNPROCESSABLE_ENTITY: {"description": "Doğrulama hatası"},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"description": "Sunucu hatası"}
    }
)

class ProjectStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    ON_HOLD = "on_hold"
    CANCELLED = "cancelled"

@router.post(
    "",
    response_model=ProjectOut,
    status_code=status.HTTP_201_CREATED,
    summary="Yeni proje oluştur",
    description="Verilen detaylarla yeni bir proje oluşturur",
    dependencies=[Depends(check_project_permission("create"))]
)
@limiter.limit(settings.RATE_LIMIT_PER_MINUTE)
async def create_project(
    request: Request,
    data: ProjectCreate,
    current_user: dict = Depends(get_current_active_user),
    project_service: ProjectService = Depends()
):
    """
    Yeni bir proje oluşturur.
    
    Gerekli izinler:
    - Proje oluşturma hakları
    
    Döndürür:
        ProjectOut: Oluşturulan proje detayları
    """
    try:
        logger.info(f"Proje oluşturma isteği: {current_user['email'][:3]}***")
        
        project = await project_service.create_project(
            tenant_id=current_user["tenant_id"],
            user_id=current_user["id"],
            data=data
        )
        
        # Denetim logu
        logger.info(f"Proje oluşturuldu: {project.id} - Kullanıcı: {current_user['email'][:3]}***")
        
        return project
        
    except HTTPException as e:
        raise
    except Exception as e:
        logger.error(f"Proje oluşturma hatası: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Proje oluşturulamadı"
        )

@router.get(
    "",
    response_model=ProjectList,
    summary="Projeleri listele",
    description="İsteğe bağlı filtreleme ile sayfalandırılmış proje listesi getirir",
    dependencies=[Depends(check_project_permission("read"))]
)
@limiter.limit(settings.RATE_LIMIT_PER_MINUTE)
async def list_projects(
    request: Request,
    pagination: PaginationParams = Depends(validate_pagination_params),
    search: Optional[str] = Query(None, min_length=2, max_length=50, description="Proje adı/açıklamasında arama"),
    status_filter: Optional[ProjectStatus] = Query(None, description="Proje durumuna göre filtrele"),
    start_date: Optional[datetime] = Query(None, description="Başlangıç tarihine göre filtrele (başlangıç)"),
    end_date: Optional[datetime] = Query(None, description="Başlangıç tarihine göre filtrele (bitiş)"),
    current_user: dict = Depends(get_current_user),
    project_service: ProjectService = Depends()
):
    """
    Filtrelenmiş ve sayfalandırılmış proje listesini getirir.
    
    İsteğe bağlı filtreler:
    - search: Proje adı/açıklamasında metin araması
    - status: Proje durumu filtresi
    - date_range: Proje başlangıç/bitiş tarihlerine göre filtrele
    
    Döndürür:
        ProjectList: Sayfalandırılmış proje listesi
    """
    try:
        filters = {"tenant_id": current_user["tenant_id"]}
        
        if search:
            filters["$or"] = [
                {"name": {"$regex": search, "$options": "i"}},
                {"description": {"$regex": search, "$options": "i"}}
            ]
            
        if status_filter:
            filters["status"] = status_filter.value
            
        if start_date and end_date:
            filters["start_date"] = {"$gte": start_date, "$lte": end_date}
        elif start_date:
            filters["start_date"] = {"$gte": start_date}
        elif end_date:
            filters["start_date"] = {"$lte": end_date}
            
        projects, total = await project_service.list_projects(
            filters=filters,
            skip=pagination.skip,
            limit=pagination.size,
            sort=[("created_at", -1)]
        )
        
        return paginate(projects, total, pagination)
        
    except Exception as e:
        logger.error(f"Proje listeleme hatası: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Projeler getirilemedi"
        )

@router.get(
    "/{project_id}",
    response_model=ProjectOut,
    summary="Proje detaylarını getir",
    description="Belirli bir proje hakkında detaylı bilgi getirir",
    dependencies=[Depends(check_project_permission("read"))]
)
@limiter.limit(settings.RATE_LIMIT_PER_MINUTE)
async def get_project(
    request: Request,
    project_id: str = Path(..., min_length=24, max_length=24, description="Proje ID"),
    current_user: dict = Depends(get_current_user),
    project_service: ProjectService = Depends()
):
    """
    ID'ye göre proje getirir.
    
    Parametreler:
    - project_id: Geçerli 24 karakterlik proje ID'si
    
    Döndürür:
        ProjectOut: Tam proje detayları
    """
    try:
        if not ObjectId.is_valid(project_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Geçersiz proje ID formatı"
            )
            
        project = await project_service.get_project_by_id(
            tenant_id=current_user["tenant_id"],
            project_id=project_id
        )
        
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Proje bulunamadı"
            )
            
        return project
        
    except HTTPException as e:
        raise
    except Exception as e:
        logger.error(f"Proje getirme hatası: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Proje getirilemedi"
        )

@router.put(
    "/{project_id}",
    response_model=ProjectOut,
    summary="Proje güncelle",
    description="Proje detaylarını günceller",
    dependencies=[Depends(check_project_permission("update"))]
)
@limiter.limit(settings.RATE_LIMIT_PER_MINUTE)
async def update_project(
    request: Request,
    project_id: str = Path(..., min_length=24, max_length=24, description="Proje ID"),
    data: ProjectUpdate = Body(...),
    current_user: dict = Depends(get_current_active_user),
    project_service: ProjectService = Depends()
):
    """
    Mevcut projeyi günceller.
    
    Parametreler:
    - project_id: Geçerli 24 karakterlik proje ID'si
    
    Döndürür:
        ProjectOut: Güncellenmiş proje detayları
    """
    try:
        if not ObjectId.is_valid(project_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Geçersiz proje ID formatı"
            )
            
        updated_project = await project_service.update_project(
            tenant_id=current_user["tenant_id"],
            project_id=project_id,
            user_id=current_user["id"],
            data=data
        )
        
        logger.info(f"Proje güncellendi: {project_id} - Kullanıcı: {current_user['email'][:3]}***")
        
        return updated_project
        
    except HTTPException as e:
        raise
    except Exception as e:
        logger.error(f"Proje güncelleme hatası: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Proje güncellenemedi"
        )

@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Proje sil",
    description="Bir projeyi kalıcı olarak siler",
    dependencies=[Depends(check_project_permission("delete"))]
)
@limiter.limit(settings.RATE_LIMIT_PER_MINUTE)
async def delete_project(
    request: Request,
    project_id: str = Path(..., min_length=24, max_length=24, description="Proje ID"),
    current_user: dict = Depends(get_current_active_user),
    project_service: ProjectService = Depends()
):
    """
    ID'ye göre proje siler.
    
    Parametreler:
    - project_id: Geçerli 24 karakterlik proje ID'si
    """
    try:
        if not ObjectId.is_valid(project_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Geçersiz proje ID formatı"
            )
            
        await project_service.delete_project(
            tenant_id=current_user["tenant_id"],
            project_id=project_id,
            user_id=current_user["id"]
        )
        
        logger.warning(f"Proje silindi: {project_id} - Kullanıcı: {current_user['email'][:3]}***")
        
        return JSONResponse(
            status_code=status.HTTP_204_NO_CONTENT,
            content=None
        )
        
    except HTTPException as e:
        raise
    except Exception as e:
        logger.error(f"Proje silme hatası: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Proje silinemedi"
        )

@router.get(
    "/{project_id}/stats",
    response_model=ProjectStatsResponse,
    summary="Proje istatistiklerini getir",
    description="Bir proje için istatistik ve analitik bilgileri getirir",
    dependencies=[Depends(check_project_permission("read"))]
)
@limiter.limit(settings.RATE_LIMIT_PER_MINUTE)
async def get_project_stats(
    request: Request,
    project_id: str = Path(..., min_length=24, max_length=24, description="Proje ID"),
    current_user: dict = Depends(get_current_user),
    project_service: ProjectService = Depends()
):
    """
    Proje istatistikleri ve analizlerini getirir.
    
    Parametreler:
    - project_id: Geçerli 24 karakterlik proje ID'si
    
    Döndürür:
        ProjectStatsResponse: Proje istatistikleri
    """
    try:
        if not ObjectId.is_valid(project_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Geçersiz proje ID formatı"
            )
            
        stats = await project_service.get_project_stats(
            tenant_id=current_user["tenant_id"],
            project_id=project_id
        )
        
        return stats
        
    except HTTPException as e:
        raise
    except Exception as e:
        logger.error(f"Proje istatistikleri hatası: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Proje istatistikleri getirilemedi"
        )