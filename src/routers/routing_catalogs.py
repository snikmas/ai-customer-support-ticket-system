from fastapi import APIRouter, Depends, Query

from src import models
from src.dependencies.auth import get_current_user
from src.services import routing_catalogs as service


departments_router = APIRouter(prefix="/departments", tags=["departments"])
skills_router = APIRouter(prefix="/skills", tags=["skills"])


@departments_router.get("/", status_code=200)
def list_departments(
    include_archived: bool = Query(False),
    requester=Depends(get_current_user),
):
    records = service.list_departments(requester, include_archived=include_archived)
    return {"data": [models.DepartmentResponse.model_validate(item, from_attributes=True) for item in records]}


@departments_router.post("/", status_code=201)
def create_department(data: models.DepartmentCreate, requester=Depends(get_current_user)):
    record = service.create_department(data, requester)
    return {"data": models.DepartmentResponse.model_validate(record, from_attributes=True)}


@departments_router.patch("/{department_id}", status_code=200)
def update_department(
    department_id: str,
    data: models.DepartmentUpdate,
    requester=Depends(get_current_user),
):
    record = service.update_department(department_id, data, requester)
    return {"data": models.DepartmentResponse.model_validate(record, from_attributes=True)}


@departments_router.delete("/{department_id}", status_code=200)
def archive_department(department_id: str, requester=Depends(get_current_user)):
    record = service.archive_department(department_id, requester)
    return {"data": models.DepartmentResponse.model_validate(record, from_attributes=True)}


@skills_router.get("/", status_code=200)
def list_skills(
    include_archived: bool = Query(False),
    requester=Depends(get_current_user),
):
    records = service.list_skills(requester, include_archived=include_archived)
    return {"data": [models.SkillResponse.model_validate(item, from_attributes=True) for item in records]}


@skills_router.post("/", status_code=201)
def create_skill(data: models.SkillCreate, requester=Depends(get_current_user)):
    record = service.create_skill(data, requester)
    return {"data": models.SkillResponse.model_validate(record, from_attributes=True)}


@skills_router.patch("/{skill_id}", status_code=200)
def update_skill(skill_id: str, data: models.SkillUpdate, requester=Depends(get_current_user)):
    record = service.update_skill(skill_id, data, requester)
    return {"data": models.SkillResponse.model_validate(record, from_attributes=True)}


@skills_router.delete("/{skill_id}", status_code=200)
def archive_skill(skill_id: str, requester=Depends(get_current_user)):
    record = service.archive_skill(skill_id, requester)
    return {"data": models.SkillResponse.model_validate(record, from_attributes=True)}
