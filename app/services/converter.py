from typing import List, Dict, Any, Optional
from app.schemas.openai import ChatCompletionRequest, ChatMessage
import time
import uuid

import httpx
import base64
import json

class Converter:
    @staticmethod
    async def openai_to_gemini(request: ChatCompletionRequest) -> Dict[str, Any]:
        contents = []
        system_instruction = None
        
        for msg in request.messages:
            if msg.role == "system":
                system_instruction = {"parts": [{"text": msg.content}]}
            elif msg.role == "user":
                parts = []
                if isinstance(msg.content, str):
                    parts.append({"text": msg.content})
                elif isinstance(msg.content, list):
                    for item in msg.content:
                        if item.get("type") == "text":
                            parts.append({"text": item["text"]})
                        elif item.get("type") == "image_url":
                            image_url = item["image_url"]["url"]
                            mime_type = "image/jpeg" # 默认
                            data = None

                            if image_url.startswith("data:"):
                                # Base64编码
                                header, encoded = image_url.split(",", 1)
                                data = encoded
                                if "image/png" in header:
                                    mime_type = "image/png"
                                elif "image/jpeg" in header:
                                    mime_type = "image/jpeg"
                                elif "image/webp" in header:
                                    mime_type = "image/webp"
                                elif "image/heic" in header:
                                    mime_type = "image/heic"
                            else:
                                # URL - 下载它
                                async with httpx.AsyncClient() as client:
                                    resp = await client.get(image_url)
                                    if resp.status_code == 200:
                                        data = base64.b64encode(resp.content).decode("utf-8")
                                        content_type = resp.headers.get("content-type")
                                        if content_type:
                                            mime_type = content_type
                            
                            if data:
                                parts.append({
                                    "inline_data": {
                                        "mime_type": mime_type,
                                        "data": data
                                    }
                                })
                contents.append({"role": "user", "parts": parts})
            elif msg.role == "assistant":
                parts = []
                if msg.tool_calls:
                    for tool_call in msg.tool_calls:
                        parts.append({
                            "functionCall": {
                                "name": tool_call["function"]["name"],
                                "args": json.loads(tool_call["function"]["arguments"])
                            }
                        })
                if msg.content:
                    parts.append({"text": msg.content})
                contents.append({"role": "model", "parts": parts})
            elif msg.role == "tool":
                # OpenAI tool响应 -> Gemini functionResponse
                # 我们需要匹配tool call id吗？Gemini不使用相同ID方式，它依赖顺序或名称。
                # 但对于代理，我们只需要构造一个有效的functionResponse。
                # 我们假设名称可用，或者我们可能需要推断它。
                # OpenAI 'tool'消息有时有'name'，但'tool_call_id'是关键。
                # 如果未提供，我们可能需要回查以前的消息来找到名称，
                # 但让我们假设'name'已填充，或者我们无法轻松支持它而不保留状态。
                # 实际上，OpenAI 'tool'消息通常没有name，只有tool_call_id。
                # Gemini需要'name'。
                # 这对于无状态代理来说是一个问题。
                # 然而，许多客户端在tool消息中发送'name'，或者我们可以尝试猜测。
                # 或者我们可以只是传递内容，希望Gemini能解决（它不会）。
                
                # 解决方案：如果缺少name，我们可能会失败。
                # 但让我们检查ChatMessage模型中是否有'name'字段。是的，有。
                # 如果客户端发送它，很好。如果没有，我们就麻烦了。
                # 标准的OpenAI客户端可能不会发送它。
                
                function_name = msg.name
                if not function_name:
                    # 尝试在匹配tool_call_id的前一个assistant消息中找到它
                    # 这需要向后迭代。
                    for prev_msg in reversed(request.messages):
                        if prev_msg.role == "assistant" and prev_msg.tool_calls:
                            for tc in prev_msg.tool_calls:
                                if tc["id"] == msg.tool_call_id: # msg.tool_call_id可能还不在ChatMessage schema中？
                                    # 等等，ChatMessage schema需要tool_call_id对应role='tool'
                                    function_name = tc["function"]["name"]
                                    break
                        if function_name:
                            break
                
                if function_name:
                    contents.append({
                        "role": "function",
                        "parts": [{
                            "functionResponse": {
                                "name": function_name,
                                "response": {"content": msg.content} # Gemini通常期期一个dict
                            }
                        }]
                    })
                else:
                    # 回退方案：只是作为用户文本发送？
                    contents.append({"role": "user", "parts": [{"text": f"Tool output: {msg.content}"}]})

        tools = None
        if request.tools:
            tools_list = []
            for tool in request.tools:
                if tool["type"] == "function":
                    tools_list.append({
                        "name": tool["function"]["name"],
                        "description": tool["function"].get("description"),
                        "parameters": tool["function"].get("parameters")
                    })
            if tools_list:
                tools = [{"function_declarations": tools_list}]
        
        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": request.temperature,
                "topP": request.top_p,
                "maxOutputTokens": request.max_tokens,
                "stopSequences": request.stop if isinstance(request.stop, list) else [request.stop] if request.stop else None
            }
        }
        
        if tools:
            payload["tools"] = tools
            
        if request.tool_choice:
            # 映射tool_choice
            # OpenAI: "auto", "none", 或 {"type": "function", "function": {"name": "..."}}
            # Gemini: "AUTO", "ANY", "NONE"
            mode = "AUTO"
            allowed_function_names = None
            
            if isinstance(request.tool_choice, str):
                if request.tool_choice == "none":
                    mode = "NONE"
                elif request.tool_choice == "auto":
                    mode = "AUTO"
                elif request.tool_choice == "required": # OpenAI没有'required'但有些有
                    mode = "ANY"
            elif isinstance(request.tool_choice, dict):
                if request.tool_choice.get("type") == "function":
                    mode = "ANY"
                    allowed_function_names = [request.tool_choice["function"]["name"]]
            
            tool_config = {
                "function_calling_config": {
                    "mode": mode
                }
            }
            if allowed_function_names:
                tool_config["function_calling_config"]["allowed_function_names"] = allowed_function_names
            
            payload["tool_config"] = tool_config
        
        if system_instruction:
            payload["system_instruction"] = system_instruction
            
        return payload

    @staticmethod
    def gemini_to_openai(response: Dict[str, Any], model: str) -> Dict[str, Any]:
        choices = []
        if "candidates" in response:
            for i, candidate in enumerate(response["candidates"]):
                message = {"role": "assistant", "content": None}
                finish_reason = "stop"
                
                if "content" in candidate and "parts" in candidate["content"]:
                    content_str = ""
                    tool_calls = []
                    
                    for part in candidate["content"]["parts"]:
                        if "text" in part:
                            content_str += part["text"]
                        elif "functionCall" in part:
                            fc = part["functionCall"]
                            tool_calls.append({
                                "id": f"call_{uuid.uuid4().hex[:8]}", # Gemini不提供ID，生成一个
                                "type": "function",
                                "function": {
                                    "name": fc["name"],
                                    "arguments": json.dumps(fc["args"])
                                }
                            })
                    
                    if content_str:
                        message["content"] = content_str
                    if tool_calls:
                        message["tool_calls"] = tool_calls
                        finish_reason = "tool_calls"
                
                if candidate.get("finishReason") == "MAX_TOKENS":
                    finish_reason = "length"
                # 添加其他结束原因映射
                
                choices.append({
                    "index": i,
                    "message": message,
                    "finish_reason": finish_reason
                })
        
        return {
            "id": f"chatcmpl-{uuid.uuid4()}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": choices,
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0
            }
        }

    @staticmethod
    def gemini_to_openai_chunk(response: Dict[str, Any], model: str) -> Dict[str, Any]:
        choices = []
        if "candidates" in response:
            for i, candidate in enumerate(response["candidates"]):
                content = ""
                tool_calls = None
                
                if "content" in candidate and "parts" in candidate["content"]:
                    for part in candidate["content"]["parts"]:
                        if "text" in part:
                            content += part["text"]
                        elif "functionCall" in part:
                            fc = part["functionCall"]
                            # 对于流式传输，我们可能需要先发送带有ID的初始工具调用，然后发送参数。
                            # 但由于Gemini将args作为dict发送，我们可以一次性发送所有内容？
                            # OpenAI期期tool_calls有'index'。
                            tool_calls = [{
                                "index": 0, # 假设单个工具调用，或者处理多个
                                "id": f"call_{uuid.uuid4().hex[:8]}",
                                "type": "function",
                                "function": {
                                    "name": fc["name"],
                                    "arguments": json.dumps(fc["args"])
                                }
                            }]
                
                finish_reason = None
                if candidate.get("finishReason") == "MAX_TOKENS":
                    finish_reason = "length"
                elif candidate.get("finishReason") == "STOP":
                    finish_reason = "stop"
                
                delta = {}
                if content:
                    delta["content"] = content
                if tool_calls:
                    delta["tool_calls"] = tool_calls
                
                choices.append({
                    "index": i,
                    "delta": delta,
                    "finish_reason": finish_reason
                })
        
        return {
            "id": f"chatcmpl-{uuid.uuid4()}",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": model,
            "choices": choices
        }

converter = Converter()
