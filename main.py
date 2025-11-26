from fastapi import FastAPI
from app.api.routes import router as api_router
from app.core.config import settings

from contextlib import asynccontextmanager
from app.services.proxy_service import proxy_service

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动
    yield
    # 关闭
    await proxy_service.close()

app = FastAPI(title="Gemini Proxy", lifespan=lifespan)

app.include_router(api_router)

if __name__ == "__main__":
    # 直接运行支持（开发环境）
    # 生产环境推荐使用：
    # - Docker: docker-compose up
    # - 或手动: uvicorn main:app --host 0.0.0.0 --port 8000
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=settings.PORT)

