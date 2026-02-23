import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import settings
from app.database import init_db
from app.api import router
from app.telegram_bot import start_telegram_bot, stop_telegram_bot

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

init_db()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting AI Agent...")
    
    if settings.TELEGRAM_BOT_TOKEN:
        asyncio.create_task(start_telegram_bot())
        logger.info("Telegram bot initialization started")
    else:
        logger.warning("TELEGRAM_BOT_TOKEN not set. Telegram bot disabled.")
    
    yield
    
    await stop_telegram_bot()
    logger.info("AI Agent stopped.")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan
)

app.include_router(router)

app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/")
async def root():
    return FileResponse("app/templates/index.html")


@app.get("/health")
def health_check():
    return {"status": "healthy"}
