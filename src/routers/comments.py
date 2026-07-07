from fastapi import APIRouter, HTTPException, Depends
from src import models
from src.services import comments as s_comments
from src.dependencies import *

router = APIRouter(
    prefix="/comments",
    tags=["comments"]
)

@router.get("/{comment_id}", status_code=200)
async def get_comment(comment_id: str, requester: models.User = Depends(get_current_user)):
    try:
        data = s_comments.get_comment(comment_id, requester)
    except PermissionError:
        raise HTTPException(403, detail="Permission Error")
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc))

    if data is None:
        raise HTTPException(404, detail="comment_not_found")
    return {"data": data}

@router.patch("/{comment_id}", status_code=200)
async def update_comment(comment_id: str, new_info: models.CommentUpdate, requester: models.User = Depends(get_current_user)):
    try:
        data = s_comments.update_comment(comment_id, new_info, requester)
    except PermissionError:
        raise HTTPException(403, detail="Permission Error")
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc))

    if data is None:
        raise HTTPException(404, detail="comment_not_found")
    return {"data": data}

@router.delete("/{comment_id}", status_code=200)
async def delete_comment(comment_id: str, requester: models.User = Depends(get_current_user)):
    try:
        data = s_comments.delete_comment(comment_id, requester)
    except PermissionError:
        raise HTTPException(403, detail="Permission Error")
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc))

    return {"data": data}
