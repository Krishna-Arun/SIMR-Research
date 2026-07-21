import os
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi import APIRouter, Request, Response, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

router = APIRouter()
BASE_DIR = os.environ.get('BASE_DIR_WEBAPP','')
STATIC_DIR = os.path.join(BASE_DIR, "static")
@router.get("/node-evaluation", response_class=HTMLResponse)
async def serve_node_evaluation():
    file_path = os.path.join(STATIC_DIR, "node-evaluation.html")
    with open(file_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


