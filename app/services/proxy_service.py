import httpx
from fastapi import Request, HTTPException
from fastapi.responses import StreamingResponse
import logging

logger = logging.getLogger(__name__)

class ProxyService:
    def __init__(self):
        # 高并发设置
        limits = httpx.Limits(max_keepalive_connections=100, max_connections=1000)
        timeout = httpx.Timeout(60.0, connect=10.0)
        
        self.client = httpx.AsyncClient(
            base_url="https://generativelanguage.googleapis.com",
            timeout=timeout,
            limits=limits,
            follow_redirects=True
        )

    async def close(self):
        await self.client.aclose()

    async def proxy_request(self, method: str, path: str, request: Request, target_url: str = None):
        """
        代理请求到目标URL。
        """
        if target_url is None:
            target_url = path

        # 提取请求头，过滤掉host和content-length让httpx处理
        headers = dict(request.headers)
        headers.pop("host", None)
        headers.pop("content-length", None)
        
        # 提取查询参数
        params = dict(request.query_params)
        
        # 读取请求体
        body = await request.body()

        try:
            req = self.client.build_request(
                method,
                target_url,
                headers=headers,
                params=params,
                content=body
            )
            
            response = await self.client.send(req, stream=True)
            
            return StreamingResponse(
                response.aiter_bytes(),
                status_code=response.status_code,
                headers=dict(response.headers),
                background=None # 如果需要，可能需要后台任务来关闭响应，但aiter_bytes基本已处理
            )

        except httpx.RequestError as exc:
            logger.error(f"请求 {exc.request.url!r} 时发生错误。")
            raise HTTPException(status_code=502, detail=f"Proxy error: {exc}")

proxy_service = ProxyService()
