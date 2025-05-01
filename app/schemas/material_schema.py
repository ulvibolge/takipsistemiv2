from datetime import datetime, date, timezone
from decimal import Decimal
from typing import Optional, List, Annotated
from enum import Enum
from bson import ObjectId
from pydantic import BaseModel, Field, EmailStr, constr, field_validator

class PyObjectId(str):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate
    @classmethod
    def validate(cls, v):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return str(v)

DecimalField = Annotated[
    Decimal,
    Field(
        strict=True,
        allow_inf_nan=False,
        max_digits=10,
        decimal_places=2,
        gt=Decimal('0')
    )
]

class MaterialCategory(str, Enum):
    construction = "construction"
    electrical = "electrical"
    plumbing = "plumbing"
    finishing = "finishing"
    safety = "safety"
    other = "other"

class UnitType(str, Enum):
    piece = "piece"
    kg = "kg"
    meter = "meter"
    liter = "liter"
    box = "box"
    set = "set"

class MaterialCreate(BaseModel):
    name: constr(min_length=2, max_length=100)
    category: MaterialCategory
    quantity: DecimalField
    unit: UnitType
    min_stock_level: DecimalField = Decimal('0')
    supplier: Optional[constr(max_length=100)] = None
    unit_price: Optional[DecimalField] = None
    currency: constr(regex=r'^[A-Z]{3}$', max_length=3) = "TRY"
    project_id: PyObjectId
    notes: Optional[constr(max_length=500)] = None

class MaterialUpdate(BaseModel):
    name: Optional[constr(min_length=2, max_length=100)] = None
    category: Optional[MaterialCategory] = None
    quantity: Optional[DecimalField] = None
    min_stock_level: Optional[DecimalField] = None
    supplier: Optional[constr(max_length=100)] = None
    unit_price: Optional[DecimalField] = None
    currency: Optional[constr(regex=r'^[A-Z]{3}$', max_length=3)] = None
    notes: Optional[constr(max_length=500)] = None

class MaterialTransaction(BaseModel):
    transaction_type: constr(pattern=r'^(in|out)$')
    amount: DecimalField
    date: date = Field(default_factory=date.today)
    performed_by: PyObjectId
    notes: Optional[constr(max_length=300)] = None

class MaterialOut(MaterialCreate):
    id: PyObjectId
    current_value: Optional[DecimalField] = None
    is_low_stock: bool = False
    last_transaction: Optional[datetime] = None
    transactions: List[MaterialTransaction] = Field(default_factory=list, max_items=1000)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator('current_value', mode='before')
    @classmethod
    def calculate_value(cls, v, values):
        quantity = values.get('quantity')
        unit_price = values.get('unit_price')
        if quantity and unit_price:
            return quantity * unit_price
        return None

    @field_validator('is_low_stock', mode='before')
    @classmethod
    def check_stock_level(cls, v, values):
        quantity = values.get('quantity')
        min_stock = values.get('min_stock_level')
        if quantity is not None and min_stock is not None:
            return quantity < min_stock
        return False

    @field_validator('updated_at', mode='before')
    @classmethod
    def set_updated_at(cls, v):
        return v or datetime.now(timezone.utc)

    class Config:
        json_encoders = {
            date: lambda v: v.isoformat(),
            datetime: lambda v: v.isoformat(),
            ObjectId: lambda v: str(v),
            Decimal: lambda v: str(v)
        }
        json_schema_extra = {
            "example": {
                "id": "64e8f8c7a1ef2c001f12a888",
                "name": "Çimento",
                "category": "construction",
                "quantity": Decimal('100.0'),
                "unit": "kg",
                "min_stock_level": Decimal('20.0'),
                "supplier": "ABC İnşaat",
                "unit_price": Decimal('15.50'),
                "currency": "TRY",
                "project_id": "64d72c9a1ef2c001f73e999b",
                "notes": "50kg çuvallarda",
                "current_value": Decimal('1550.00'),
                "is_low_stock": False,
                "transactions": [{
                    "transaction_type": "in",
                    "amount": Decimal('100.0'),
                    "date": "2024-03-15",
                    "performed_by": "64a1b2c3d4e5f67890123456",
                    "notes": "Depo girişi"
                }],
                "created_at": "2024-03-15T10:00:00Z",
                "updated_at": "2024-03-15T10:00:00Z"
            }
        }
