from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

# database.py에서 TargetCafe 모델과 SessionLocal을 import 합니다.
from database import SessionLocal, TargetCafe

router = APIRouter(prefix="/marketing")
templates = Jinja2Templates(directory="templates")

# 데이터베이스 세션을 가져오는 함수
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/cafe", response_class=HTMLResponse)
async def marketing_cafe(request: Request, db: Session = Depends(get_db)):
    # DB에서 모든 타겟 카페 목록을 가져옵니다.
    cafes = db.query(TargetCafe).all()
    return templates.TemplateResponse("marketing_cafe.html", {
        "request": request,
        "cafes": cafes # 카페 목록을 템플릿으로 전달
    })

@router.post("/cafe/add", response_class=RedirectResponse)
async def add_target_cafe(
    name: str = Form(...),
    url: str = Form(...),
    db: Session = Depends(get_db)
):
    # 새로운 카페 객체를 만들어 DB에 저장합니다.
    new_cafe = TargetCafe(name=name, url=url)
    db.add(new_cafe)
    db.commit()
    # 저장 후, 다시 카페 관리 페이지로 돌아갑니다.
    return RedirectResponse(url="/marketing/cafe", status_code=303)

@router.post("/cafe/delete/{cafe_id}", response_class=RedirectResponse)
async def delete_target_cafe(cafe_id: int, db: Session = Depends(get_db)):
    # 해당 ID의 카페를 찾아 삭제합니다.
    cafe_to_delete = db.query(TargetCafe).filter(TargetCafe.id == cafe_id).first()
    if cafe_to_delete:
        db.delete(cafe_to_delete)
        db.commit()
    # 삭제 후, 다시 카페 관리 페이지로 돌아갑니다.
    return RedirectResponse(url="/marketing/cafe", status_code=303)

# ... (blog, homepage, kin 라우트는 그대로) ...
@router.get("/blog", response_class=HTMLResponse)
async def marketing_blog(request: Request):
    return templates.TemplateResponse("marketing_blog.html", {"request": request})

@router.get("/homepage", response_class=HTMLResponse)
async def marketing_homepage(request: Request):
    return templates.TemplateResponse("marketing_homepage.html", {"request": request})

@router.get("/kin", response_class=HTMLResponse)
async def marketing_kin(request: Request):
    return templates.TemplateResponse("marketing_kin.html", {"request": request})
