import asyncio
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy import select, func
from database import init_db, AsyncSessionLocal
from models import URL, Click, User, LoginLog, SiteVisit
from utils import generate_short_code
from ai_service import analyze_url
from scraper import scrape_metadata
from auth import hash_password, verify_password, create_session_token, get_current_user
from datetime import datetime, timezone

app = FastAPI(title="Smart URL Shortener")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

BASE_URL = "http://localhost:8000"


@app.on_event("startup")
async def startup():
    await init_db()


# ─── BACKGROUND HELPERS ──────────────────────────────────────

async def log_visit(path: str, ip: str, ua: str):
    try:
        await asyncio.sleep(0)
        async with AsyncSessionLocal() as db:
            visit = SiteVisit(ip_address=ip, user_agent=ua, path=path)
            db.add(visit)
            await db.commit()
    except Exception:
        pass


async def log_login(user_id: int, ip: str, ua: str):
    try:
        await asyncio.sleep(0)
        async with AsyncSessionLocal() as db:
            log = LoginLog(user_id=user_id, ip_address=ip, user_agent=ua)
            db.add(log)
            await db.commit()
    except Exception:
        pass


# ─── VISIT TRACKER MIDDLEWARE ────────────────────────────────

@app.middleware("http")
async def track_visits(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    skip = ["/static", "/favicon", "/shorten", "/toggle", "/admin/toggle"]
    if not any(path.startswith(p) for p in skip):
        asyncio.create_task(log_visit(
            path,
            request.client.host,
            request.headers.get("user-agent", "")
        ))
    return response


# ─── AUTH ROUTES ─────────────────────────────────────────────

@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    user = await get_current_user(request)
    if user:
        return RedirectResponse("/admin" if user.is_admin else "/", status_code=302)
    return templates.TemplateResponse("register.html", {"request": request, "error": None})


@app.post("/register")
async def register(request: Request):
    form = await request.form()
    email = str(form.get("email", "")).strip().lower()
    password = str(form.get("password", ""))
    full_name = str(form.get("full_name", "")).strip()

    if not email or not password:
        return templates.TemplateResponse("register.html", {
            "request": request, "error": "Email and password are required."
        })
    if len(password) < 6:
        return templates.TemplateResponse("register.html", {
            "request": request, "error": "Password must be at least 6 characters."
        })

    async with AsyncSessionLocal() as db:
        existing = await db.execute(select(User).where(User.email == email))
        if existing.scalar_one_or_none():
            return templates.TemplateResponse("register.html", {
                "request": request, "error": "Email already registered."
            })
        user = User(email=email, hashed_password=hash_password(password), full_name=full_name)
        db.add(user)
        await db.commit()
        await db.refresh(user)

    token = create_session_token(user.id)
    response = RedirectResponse("/", status_code=302)
    response.set_cookie("session", token, httponly=True, max_age=86400 * 7)
    return response


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    user = await get_current_user(request)
    if user:
        return RedirectResponse("/admin" if user.is_admin else "/", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@app.post("/login")
async def login(request: Request):
    form = await request.form()
    email = str(form.get("email", "")).strip().lower()
    password = str(form.get("password", ""))

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if not user or not verify_password(password, user.hashed_password):
            return templates.TemplateResponse("login.html", {
                "request": request, "error": "Invalid email or password."
            })

        is_admin = user.is_admin
        user_id = user.id

        # Update last login
        user.last_login = datetime.now(timezone.utc)
        await db.commit()

    # Log login in background to avoid DB lock
    asyncio.create_task(log_login(user_id, request.client.host, request.headers.get("user-agent", "")))

    token = create_session_token(user_id)
    redirect_to = "/admin" if is_admin else "/"
    response = RedirectResponse(redirect_to, status_code=302)
    response.set_cookie("session", token, httponly=True, max_age=86400 * 7)
    return response


@app.get("/logout")
async def logout():
    response = RedirectResponse("/", status_code=302)
    response.delete_cookie("session")
    return response


# ─── MAIN ROUTES (regular users only) ───────────────────────

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    user = await get_current_user(request)
    if user and user.is_admin:
        return RedirectResponse("/admin", status_code=302)
    recent_urls = []
    if user:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(URL).where(URL.user_id == user.id).order_by(URL.created_at.desc()).limit(5)
            )
            recent_urls = result.scalars().all()
    return templates.TemplateResponse("index.html", {
        "request": request, "user": user, "recent_urls": recent_urls, "base_url": BASE_URL
    })


class ShortenRequest(BaseModel):
    url: str


@app.post("/shorten")
async def shorten_url(data: ShortenRequest, request: Request):
    user = await get_current_user(request)
    if not user:
        return JSONResponse({"error": "Login required"}, status_code=401)
    if user.is_admin:
        return JSONResponse({"error": "Admins cannot shorten URLs"}, status_code=403)

    url = data.url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(URL).where(URL.original_url == url, URL.user_id == user.id)
        )
        existing = result.scalar_one_or_none()
        if existing:
            count_result = await db.execute(
                select(func.count(Click.id)).where(Click.url_id == existing.id)
            )
            return JSONResponse({
                "short_url": f"{BASE_URL}/r/{existing.short_code}",
                "short_code": existing.short_code,
                "category": existing.category,
                "is_safe": existing.is_safe,
                "title": existing.title,
                "click_count": count_result.scalar() or 0
            })

        metadata = await scrape_metadata(url)
        ai_result = await analyze_url(url, metadata.get("title", ""), metadata.get("description", ""))

        while True:
            code = generate_short_code()
            check = await db.execute(select(URL).where(URL.short_code == code))
            if not check.scalar_one_or_none():
                break

        url_obj = URL(
            original_url=url,
            short_code=code,
            title=metadata.get("title", "") or url,
            category=ai_result.get("category", "Other"),
            is_safe=not ai_result.get("is_suspicious", False),
            safety_note=ai_result.get("reason", ""),
            user_id=user.id,
        )
        db.add(url_obj)
        await db.commit()
        await db.refresh(url_obj)

    return JSONResponse({
        "short_url": f"{BASE_URL}/r/{code}",
        "short_code": code,
        "category": url_obj.category,
        "is_safe": url_obj.is_safe,
        "safety_note": url_obj.safety_note,
        "title": url_obj.title,
        "click_count": 0
    })


@app.get("/r/{short_code}", response_class=HTMLResponse)
async def redirect_url(short_code: str, request: Request):
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(URL).where(URL.short_code == short_code))
        url_obj = result.scalar_one_or_none()
        if not url_obj:
            raise HTTPException(status_code=404, detail="URL not found")
        if not url_obj.is_safe:
            return templates.TemplateResponse("warning.html", {
                "request": request, "url": url_obj, "base_url": BASE_URL
            })
        click = Click(
            url_id=url_obj.id,
            clicked_at=datetime.now(timezone.utc),
            ip_address=request.client.host,
            user_agent=request.headers.get("user-agent", ""),
            referer=request.headers.get("referer", "")
        )
        db.add(click)
        await db.commit()
    return RedirectResponse(url=url_obj.original_url)


@app.get("/r/{short_code}/go")
async def force_redirect(short_code: str, request: Request):
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(URL).where(URL.short_code == short_code))
        url_obj = result.scalar_one_or_none()
        if not url_obj:
            raise HTTPException(status_code=404, detail="URL not found")
        click = Click(
            url_id=url_obj.id,
            clicked_at=datetime.now(timezone.utc),
            ip_address=request.client.host,
            user_agent=request.headers.get("user-agent", ""),
            referer=request.headers.get("referer", "")
        )
        db.add(click)
        await db.commit()
    return RedirectResponse(url=url_obj.original_url)


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    user = await get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    if user.is_admin:
        return RedirectResponse("/admin", status_code=302)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(URL).where(URL.user_id == user.id).order_by(URL.created_at.desc())
        )
        urls = result.scalars().all()
        url_data = []
        for u in urls:
            count_result = await db.execute(
                select(func.count(Click.id)).where(Click.url_id == u.id)
            )
            url_data.append({"url": u, "click_count": count_result.scalar() or 0})

    total_clicks = sum(d["click_count"] for d in url_data)
    spam_count = sum(1 for d in url_data if not d["url"].is_safe)
    tag_counts = {}
    for d in url_data:
        tag = d["url"].category or "Other"
        tag_counts[tag] = tag_counts.get(tag, 0) + 1

    return templates.TemplateResponse("dashboard.html", {
        "request": request, "user": user, "urls": url_data,
        "total_clicks": total_clicks, "total_links": len(url_data),
        "spam_count": spam_count, "tag_counts": tag_counts, "base_url": BASE_URL
    })


@app.post("/toggle/{short_code}")
async def toggle_url(short_code: str, request: Request):
    user = await get_current_user(request)
    if not user:
        return JSONResponse({"error": "Login required"}, status_code=401)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(URL).where(URL.short_code == short_code, URL.user_id == user.id)
        )
        url_obj = result.scalar_one_or_none()
        if not url_obj:
            raise HTTPException(status_code=404)
        url_obj.is_active = not url_obj.is_active
        await db.commit()
        return JSONResponse({"is_active": url_obj.is_active})


# ─── ADMIN ROUTES ────────────────────────────────────────────

@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    user = await get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    if not user.is_admin:
        return RedirectResponse("/", status_code=302)

    async with AsyncSessionLocal() as db:
        total_users  = (await db.execute(select(func.count(User.id)))).scalar() or 0
        total_links  = (await db.execute(select(func.count(URL.id)))).scalar() or 0
        total_clicks = (await db.execute(select(func.count(Click.id)))).scalar() or 0
        total_visits = (await db.execute(select(func.count(SiteVisit.id)))).scalar() or 0
        total_logins = (await db.execute(select(func.count(LoginLog.id)))).scalar() or 0

        users_result = await db.execute(select(User).order_by(User.created_at.desc()))
        all_users = users_result.scalars().all()

        user_data = []
        for u in all_users:
            link_count  = (await db.execute(select(func.count(URL.id)).where(URL.user_id == u.id))).scalar() or 0
            login_count = (await db.execute(select(func.count(LoginLog.id)).where(LoginLog.user_id == u.id))).scalar() or 0
            user_data.append({"user": u, "link_count": link_count, "login_count": login_count})

        logins_result = await db.execute(
            select(LoginLog).order_by(LoginLog.logged_in_at.desc()).limit(20)
        )
        recent_logins = logins_result.scalars().all()
        login_data = []
        for log in recent_logins:
            log_user = (await db.execute(select(User).where(User.id == log.user_id))).scalar_one_or_none()
            login_data.append({"log": log, "user": log_user})

        visits_result = await db.execute(
            select(SiteVisit).order_by(SiteVisit.visited_at.desc()).limit(20)
        )
        recent_visits = visits_result.scalars().all()

        page_visits_result = await db.execute(
            select(SiteVisit.path, func.count(SiteVisit.id).label("count"))
            .group_by(SiteVisit.path)
            .order_by(func.count(SiteVisit.id).desc())
            .limit(10)
        )
        page_visits = page_visits_result.all()

    return templates.TemplateResponse("admin.html", {
        "request": request, "admin": user,
        "total_users": total_users, "total_links": total_links,
        "total_clicks": total_clicks, "total_visits": total_visits,
        "total_logins": total_logins, "user_data": user_data,
        "login_data": login_data, "recent_visits": recent_visits,
        "page_visits": page_visits,
    })


@app.post("/admin/toggle-user/{user_id}")
async def admin_toggle_user(user_id: int, request: Request):
    admin = await get_current_user(request)
    if not admin or not admin.is_admin:
        return JSONResponse({"error": "Forbidden"}, status_code=403)
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.id == user_id))
        target = result.scalar_one_or_none()
        if not target:
            raise HTTPException(status_code=404)
        target.is_active = not target.is_active
        await db.commit()
        return JSONResponse({"is_active": target.is_active})

@app.get("/setup-admin-xk92p/{email}")
async def setup_admin(email: str):
    """One-time route to make a user admin. Delete from main.py after use."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if not user:
            return JSONResponse({"error": f"User '{email}' not found. Register first."}, status_code=404)
        user.is_admin = True
        await db.commit()
        return JSONResponse({"success": f"✓ {email} is now admin! Remove this route from main.py now."})