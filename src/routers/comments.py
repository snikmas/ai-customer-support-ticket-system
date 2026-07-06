from fastapi import APIRouter, HTTPException, Depends
from src import models, db, constants
from src.services import users as s_users, tickets as s_tickets, comments as s_comments
from src.dependencies import *

router = APIRouter(
    prefix="/comments",
    tags=["comments"]
)

@router.get("/{comment_id}", status_code=200)
async def get_comment(comment_id: str, requester: models.User = Depends(get_current_user)):
    pass

@router.patch("/{comment_id}", status_code=200)
async def update_comment(comment_id: str, new_info: models.CommentUpdate, requester: models.User = Depends(get_current_user)):
    pass

@router.delete("/{comment_id}", status_code=200)
async def delete_comment(comment_id: str, requester: models.User = Depends(get_current_user)):
    pass