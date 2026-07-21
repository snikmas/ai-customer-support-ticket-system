from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from .validation import RoutingCatalogDescription, RoutingCatalogName


class RoutingCatalogCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: RoutingCatalogName
    description: RoutingCatalogDescription | None = None


class RoutingCatalogUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: RoutingCatalogName | None = None
    description: RoutingCatalogDescription | None = None

    @field_validator("name")
    @classmethod
    def reject_explicit_null_name(cls, value: str | None):
        if value is None:
            raise ValueError("catalog_name_cannot_be_null")
        return value


class RoutingCatalogResponse(BaseModel):
    id: str
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


class DepartmentCreate(RoutingCatalogCreate):
    pass


class DepartmentUpdate(RoutingCatalogUpdate):
    pass


class DepartmentResponse(RoutingCatalogResponse):
    pass


class SkillCreate(RoutingCatalogCreate):
    pass


class SkillUpdate(RoutingCatalogUpdate):
    pass


class SkillResponse(RoutingCatalogResponse):
    pass
