from fastapi import APIRouter, Request, Response, HTTPException
from fastapi.responses import StreamingResponse
from app.services.proxy_service import proxy_service
from app.schemas.openai import ChatCompletionRequest
from app.services.converter import converter
import httpx
import time
import json

router = APIRouter()

@router.get("/health")
async def health_check():
    return {"status": "ok"}


@router.get("/v1beta/models")
async def list_models_gemini(request: Request):
    """
    Gemini模型列表的专用处理器，确保正确的身份验证。
    代理请求并直接流式传输响应。
    """
    # 1. 提取API密钥
    auth_header = request.headers.get("Authorization")
    api_key = None
    if auth_header and auth_header.startswith("Bearer "):
        api_key = auth_header.split(" ")[1]
    
    if not api_key:
        api_key = request.headers.get("x-goog-api-key")

    if not api_key:
        api_key = request.query_params.get("key")
        
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing API key")

    # 2. 准备并发送请求到Gemini
    target_url = "/v1beta/models"
    headers = {"x-goog-api-key": api_key}
    
    # 提取需要转发的查询参数（例如pageToken）
    params = dict(request.query_params)
    # 如果存在，从参数中移除key，因为它已通过请求头处理
    params.pop("key", None)

    try:
        req = proxy_service.client.build_request(
            "GET",
            target_url,
            headers=headers,
            params=params
        )
        
        response = await proxy_service.client.send(req, stream=True)
        
        # 过滤响应头
        excluded_headers = {"content-encoding", "content-length", "transfer-encoding", "connection"}
        headers = {
            k: v for k, v in response.headers.items()
            if k.lower() not in excluded_headers
        }

        return StreamingResponse(
            response.aiter_bytes(),
            status_code=response.status_code,
            headers=headers,
            background=None
        )
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Proxy error: {exc}")
        
@router.api_route("/v1beta/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def proxy_v1beta(path: str, request: Request):
    """
    原生Gemini API /v1beta的透传。
    如果需要，自动将OpenAI Bearer令牌转换为Gemini格式。
    """
    # 提取请求头
    headers = dict(request.headers)
    headers.pop("host", None)
    headers.pop("content-length", None)
    
    # 提取查询参数
    params = dict(request.query_params)
    
    # 检查是否需要将Authorization头转换为Gemini格式
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        api_key = auth_header.split(" ")[1]
        # 移除Authorization头并添加Gemini风格的身份验证
        headers.pop("authorization", None)
        # 使用x-goog-api-key请求头，更可靠
        if "x-goog-api-key" not in headers:
            headers["x-goog-api-key"] = api_key
    
    # 读取请求体
    body = await request.body()
    
    try:
        req = proxy_service.client.build_request(
            request.method,
            f"/v1beta/{path}",
            headers=headers,
            params=params,
            content=body
        )
        
        response = await proxy_service.client.send(req, stream=True)
        
        # 过滤响应头
        excluded_headers = {"content-encoding", "content-length", "transfer-encoding", "connection"}
        headers = {
            k: v for k, v in response.headers.items()
            if k.lower() not in excluded_headers
        }

        return StreamingResponse(
            response.aiter_bytes(),
            status_code=response.status_code,
            headers=headers,
            background=None
        )
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Proxy error: {exc}")

@router.post("/v1/chat/completions")
async def chat_completions(request: Request):
    # 1. 解析请求
    try:
        body = await request.json()
        openai_request = ChatCompletionRequest(**body)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid request: {e}")

    # 2. 提取API密钥
    auth_header = request.headers.get("Authorization")
    api_key = None
    if auth_header and auth_header.startswith("Bearer "):
        api_key = auth_header.split(" ")[1]
    
    if not api_key:
        api_key = request.headers.get("x-goog-api-key")

    if not api_key:
        # 尝试查询参数
        api_key = request.query_params.get("key")
        
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing API key")

    # 3. 模型映射
    model = openai_request.model
    if model.startswith("gpt-"):
        model = "gemini-1.5-flash" # 默认回退
    
    # 4. 转换请求
    gemini_payload = await converter.openai_to_gemini(openai_request)
    
    # 5. 发送到Gemini
    # 构建URL: https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}
    # 如果流式传输，使用streamGenerateContent
    method = "streamGenerateContent" if openai_request.stream else "generateContent"
    target_url = f"/v1beta/models/{model}:{method}"
    
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": api_key
    }
    
    if openai_request.stream:
        async def stream_generator():
            async with proxy_service.client.stream("POST", target_url, json=gemini_payload, headers=headers, timeout=60.0) as response:
                if response.status_code != 200:
                    error_content = await response.aread()
                    yield f"data: {json.dumps({'error': {'message': error_content.decode(), 'code': response.status_code}})}\n\n"
                    return

                buffer = ""
                async for chunk in response.aiter_text():
                    buffer += chunk
                    while True:
                        # 简单的JSON数组解析逻辑
                        # 我们期望对象被包装在[ ... ]中
                        # 我们寻找匹配的大括号
                        try:
                            # 这是一个简单的解析器，生产环境可能需要改进
                            # 但现在，让我们尝试找到完整的JSON对象
                            start = buffer.find('{')
                            if start == -1:
                                break
                            
                            # 找到对象的结尾（简单方式）
                            # 我们需要计算大括号以确保正确
                            brace_count = 0
                            end = -1
                            for i, char in enumerate(buffer[start:], start):
                                if char == '{':
                                    brace_count += 1
                                elif char == '}':
                                    brace_count -= 1
                                    if brace_count == 0:
                                        end = i + 1
                                        break
                            
                            if end != -1:
                                json_str = buffer[start:end]
                                buffer = buffer[end:]
                                
                                try:
                                    gemini_chunk = json.loads(json_str)
                                    openai_chunk = converter.gemini_to_openai_chunk(gemini_chunk, model)
                                    yield f"data: {json.dumps(openai_chunk)}\n\n"
                                except json.JSONDecodeError:
                                    # 不完整或无效，等待更多数据
                                    # 但我们找到了匹配的大括号，所以它应该是有效的
                                    pass
                            else:
                                break
                        except Exception:
                            break
                            
            yield "data: [DONE]\n\n"

        return StreamingResponse(stream_generator(), media_type="text/event-stream")

    try:
        response = await proxy_service.client.post(
            target_url,
            json=gemini_payload,
            headers=headers,
            timeout=60.0
        )
        response.raise_for_status()
        gemini_response = response.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=exc.response.text)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    # 6. 转换响应
    openai_response = converter.gemini_to_openai(gemini_response, model)
    
    return openai_response

@router.get("/v1/models")
async def list_models(request: Request):
    # 提取API密钥
    auth_header = request.headers.get("Authorization")
    api_key = None
    if auth_header and auth_header.startswith("Bearer "):
        api_key = auth_header.split(" ")[1]
    
    if not api_key:
        api_key = request.headers.get("x-goog-api-key")

    if not api_key:
        api_key = request.query_params.get("key")
        
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing API key")

    target_url = "/v1beta/models"
    headers = {"x-goog-api-key": api_key}
    
    try:
        response = await proxy_service.client.get(target_url, headers=headers, timeout=60.0)
        response.raise_for_status()
        gemini_data = response.json()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
        
    openai_models = []
    if "models" in gemini_data:
        for model in gemini_data["models"]:
            # model["name"]的格式类似"models/gemini-pro"
            model_id = model["name"].replace("models/", "")
            openai_models.append({
                "id": model_id,
                "object": "model",
                "created": int(time.time()),
                "owned_by": "google"
            })
            
    return {
        "object": "list",
        "data": openai_models
    }
