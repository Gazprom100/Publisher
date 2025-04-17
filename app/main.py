from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.core.config import settings
from app.api.v1 import analytics, auth, channels, content, scheduler
from app.core.security import setup_security
from app.db.session import setup_database
from app.services.telegram import setup_telegram
from app.tasks.celery_app import setup_celery

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# Setup CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/media", StaticFiles(directory="media"), name="media")

# Templates
templates = Jinja2Templates(directory="templates")

@app.on_event("startup")
async def startup_event():
    """Initialize application services on startup."""
    # Setup database
    await setup_database()
    
    # Setup security
    setup_security(app)
    
    # Setup Telegram bot
    setup_telegram()
    
    # Setup Celery
    setup_celery()

# Include routers
app.include_router(
    analytics.router,
    prefix=f"{settings.API_V1_STR}/analytics",
    tags=["analytics"]
)
app.include_router(
    auth.router,
    prefix=f"{settings.API_V1_STR}/auth",
    tags=["auth"]
)
app.include_router(
    channels.router,
    prefix=f"{settings.API_V1_STR}/channels",
    tags=["channels"]
)
app.include_router(
    content.router,
    prefix=f"{settings.API_V1_STR}/content",
    tags=["content"]
)
app.include_router(
    scheduler.router,
    prefix=f"{settings.API_V1_STR}/scheduler",
    tags=["scheduler"]
)

@app.get("/")
async def root():
    """Redirect to dashboard."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/dashboard")

@app.get("/dashboard")
async def dashboard(request):
    """Render dashboard template."""
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "settings": settings}
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000) 