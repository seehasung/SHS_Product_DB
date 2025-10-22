# routers/marketing.py

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(prefix="/marketing") # 모든 경로 앞에 /marketing 추가
templates = Jinja2Templates(directory="templates")

@router.get("/cafe", response_class=HTMLResponse)
async def marketing_cafe(request: Request):
    # TODO: 카페 관련 데이터 로드 및 로직 추가
    return templates.TemplateResponse("marketing_cafe.html", {"request": request})

@router.get("/blog", response_class=HTMLResponse)
async def marketing_blog(request: Request):
    # TODO: 블로그 관련 데이터 로드 및 로직 추가
    return templates.TemplateResponse("marketing_blog.html", {"request": request})

@router.get("/homepage", response_class=HTMLResponse)
async def marketing_homepage(request: Request):
    # TODO: 홈페이지 관련 데이터 로드 및 로직 추가
    return templates.TemplateResponse("marketing_homepage.html", {"request": request})

@router.get("/kin", response_class=HTMLResponse)
async def marketing_kin(request: Request):
    # TODO: 지식인 관련 데이터 로드 및 로직 추가
    return templates.TemplateResponse("marketing_kin.html", {"request": request})