from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.orm import Session

from shoponline.web.app import get_db, redirect, render
from shoponline.web.auth import authenticate

router = APIRouter()


@router.get("/login")
def login_form(request: Request):
    return render(request, "login.html", None)


@router.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = authenticate(db, username.strip(), password)
    if user is None:
        return render(request, "login.html", None, error="Sai tên đăng nhập hoặc mật khẩu.")
    request.session.clear()
    request.session["user_id"] = user.id
    return redirect("/batches")


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return redirect("/login")
