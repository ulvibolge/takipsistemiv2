from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from bson import ObjectId
from fastapi import APIRouter, status, Depends, HTTPException, Query
from fastapi.security import OAuth2PasswordBearer
from pydantic import TypeAdapter
from app.schemas.tenant_schema import TenantCreate, TenantOut, TenantList, TenantUpdate
from app.services.tenant_service import TenantService
from app.core.security import validate_admin_access, get_current_user
from app.utils.pagination import PaginationParams, validate_pagination_params
from app.utils.logger import logger

router = APIRouter(
    prefix="/tenants",
    tags=["Tenant Yönetimi"],
    responses={
        status.HTTP_400_BAD_REQUEST: {"description": "Geçersiz istek"},
        status.HTTP_401_UNAUTHORIZED: {"description": "Yetkilendirme hatası"},
        status.HTTP_403_FORBIDDEN: {"description": "Yetkisiz erişim"},
        status.HTTP_404_NOT_FOUND: {"description": "Firma bulunamadı"},
        status.HTTP_409_CONFLICT: {"description": "Çakışan veri"},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"description": "Sunucu hatası"}
    }
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")

tenant_out_adapter = TypeAdapter(TenantOut)
tenant_list_adapter = TypeAdapter(List[TenantOut])

def validate_object_id(tenant_id: str) -> None:
    """Helper function to validate MongoDB ObjectId."""
    if not ObjectId.is_valid(tenant_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Geçersiz firma ID formatı"
        )

@router.post(
    "",
    response_model=TenantOut,
    status_code=status.HTTP_201_CREATED,
    summary="Yeni firma oluştur",
    description="""
    ### Yeni bir firma ve ona özel veritabanı oluşturur:
    - Firma adı ve email benzersiz olmalıdır
    - Otomatik veritabanı ismi oluşturulur (örn: firma_adı → firma_adi)
    - Varsayılan admin kullanıcısı eklenir
    - Gerekli tüm koleksiyonlar ve indexler oluşturulur
    - Sadece sistem adminleri bu işlemi yapabilir
    """,
    response_description="Oluşturulan firma bilgisi",
    dependencies=[Depends(validate_admin_access)]
)
async def create_tenant(
    data: TenantCreate,
    current_user: dict = Depends(get_current_user)
) -> TenantOut:
    """Yeni bir firma kaydı oluşturur ve gerekli veritabanı altyapısını hazırlar."""
    try:
        logger.info("Yeni firma oluşturma isteği - Kullanıcı: %s", current_user['email'])
        tenant = await TenantService.create_tenant(data)
        return tenant_out_adapter.validate_python(tenant)
    except HTTPException as he:
        logger.warning("Firma oluşturma hatası: %s", he.detail)
        raise
    except Exception as e:
        logger.error("Beklenmeyen hata: %s", str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Firma oluşturulamadı"
        )

@router.get(
    "",
    response_model=TenantList,
    summary="Firmaları listele",
    description="""
    Sistemde kayıtlı firmaları filtreleyerek ve sayfalandırarak listeler.
    Sadece admin kullanıcılar tüm firmaları görebilir.
    """,
    response_description="Firma listesi ve sayfalama bilgisi",
    dependencies=[Depends(validate_admin_access)]
)
async def list_tenants(
    pagination: PaginationParams = Depends(validate_pagination_params),
    active_only: bool = Query(default=True, description="Sadece aktif firmaları getir"),
    search: Optional[str] = Query(default=None, min_length=2, max_length=50,
                                  description="Firma adında arama"),
    license_type: Optional[str] = Query(default=None, description="Lisans tipine göre filtrele")
) -> TenantList:
    """Firmaları filtreli ve sayfalandırılmış şekilde listeler."""
    try:
        query = {
            "is_active": active_only if active_only else None,
            "company_name": {"$regex": search, "$options": "i"} if search else None,
            "license_type": license_type if license_type else None
        }
        query = {k: v for k, v in query.items() if v is not None}  # Remove None values

        tenants = await TenantService.list_tenants(
            query=query,
            page=pagination.page,
            size=pagination.size
        )
        total = await TenantService.count_tenants(query)

        return TenantList(
            items=tenant_list_adapter.validate_python(tenants),
            total=total,
            page=pagination.page,
            size=pagination.size
        )
    except Exception as e:
        logger.error("Firma listeleme hatası: %s", str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Firma listesi alınamadı"
        ) from e

@router.get(
    "/{tenant_id}",
    response_model=TenantOut,
    summary="Firma detaylarını getir",
    description="Belirtilen ID'ye ait firmanın detay bilgilerini getirir",
    response_description="Firma detay bilgisi",
    dependencies=[Depends(validate_admin_access)]
)
async def get_tenant(
    tenant_id: str,
    current_user: dict = Depends(get_current_user)
) -> TenantOut:
    """Firma detay bilgilerini getirir."""
    try:
        validate_object_id(tenant_id)

        tenant = await TenantService.get_tenant_by_id(tenant_id)
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Firma bulunamadı"
            )

        return tenant_out_adapter.validate_python(tenant)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Firma detay hatası: %s", str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Firma bilgisi alınamadı"
        ) from e

@router.patch(
    "/{tenant_id}/status",
    response_model=TenantOut,
    summary="Firma durumunu güncelle",
    description="Firmanın aktif/pasif durumunu değiştirir",
    response_description="Güncellenen firma bilgisi",
    dependencies=[Depends(validate_admin_access)]
)
async def update_tenant_status(
    tenant_id: str,
    is_active: bool,
    current_user: dict = Depends(get_current_user)
) -> TenantOut:
    """Firmanın aktiflik durumunu günceller."""
    try:
        validate_object_id(tenant_id)

        logger.info(
            "Firma durum güncelleme - Kullanıcı: %s, Firma: %s, Durum: %s",
            current_user['email'], tenant_id, is_active
        )

        updated_tenant = await TenantService.update_tenant_status(
            tenant_id=tenant_id,
            is_active=is_active
        )
        return tenant_out_adapter.validate_python(updated_tenant)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Durum güncelleme hatası: %s", str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Firma durumu güncellenemedi"
        ) from e

@router.put(
    "/{tenant_id}",
    response_model=TenantOut,
    summary="Firma bilgilerini güncelle",
    description="Firmanın temel bilgilerini günceller",
    dependencies=[Depends(validate_admin_access)]
)
async def update_tenant(
    tenant_id: str,
    data: TenantUpdate,
    current_user: dict = Depends(get_current_user)
) -> TenantOut:
    """Firmanın bilgilerini günceller."""
    try:
        validate_object_id(tenant_id)

        updated_tenant = await TenantService.update_tenant(
            tenant_id=tenant_id,
            update_data=data.dict(exclude_unset=True)
        )
        return tenant_out_adapter.validate_python(updated_tenant)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Firma güncelleme hatası: %s", str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Firma bilgileri güncellenemedi"
        ) from e