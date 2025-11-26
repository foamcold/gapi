<div align="center">

# 🚀 Gemini API 代理服务

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11+-brightgreen.svg)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](https://www.docker.com/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688.svg)](https://fastapi.tiangolo.com/)

**高性能 Gemini API 代理服务，完美兼容 OpenAI API 格式**

[特性](#特性) • [快速开始](#快速开始) • [API 使用](#api-使用) • [配置](#配置) • [开发](#开发指南)

</div>

---

## ✨ 特性

- 🔄 **双格式支持**
  - OpenAI API 兼容接口 (`/v1/*`)
  - Gemini 原生接口透传 (`/v1beta/*`)
  
- 🎨 **多模态兼容**
  - 图像输入（支持 URL 和 Base64）
  - 函数调用（Function Calling）
  - 流式响应（Streaming）

- 🐳 **开箱即用**
  - Docker / Docker Compose 一键部署
  - 无需复杂配置
  - 健康检查支持

---

## 🚀 快速开始

### 方式 1：Docker Compose（推荐）

```bash
# 克隆项目
git clone https://github.com/yourusername/gapi.git
cd gapi

# 启动服务
docker-compose up -d

# 检查服务状态
curl http://localhost:8000/health
```

### 方式 2：Docker 手动构建

```bash
# 构建镜像
docker build -t gapi:latest .

# 运行容器
docker run -d \
  --name gemini-api-proxy \
  -p 8000:8000 \
  gapi:latest

# 检查健康状态
docker ps
curl http://localhost:8000/health
```

### 方式 3：本地开发

```bash
# 安装依赖
pip install -r requirements.txt

# 启动服务
python main.py

# 或使用 uvicorn（支持热重载）
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

---

## 📖 API 使用

### OpenAI 兼容接口

#### 聊天补全

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer YOUR_GEMINI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemini-1.5-flash",
    "messages": [
      {"role": "user", "content": "你好，介绍一下自己"}
    ]
  }'
```

#### 流式响应

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer YOUR_GEMINI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemini-1.5-flash",
    "messages": [{"role": "user", "content": "讲个笑话"}],
    "stream": true
  }'
```

#### Python 示例

```python
import openai

# 配置代理
openai.api_base = "http://localhost:8000/v1"
openai.api_key = "YOUR_GEMINI_API_KEY"

# 调用
response = openai.ChatCompletion.create(
    model="gemini-1.5-flash",
    messages=[
        {"role": "user", "content": "用Python写一个快速排序"}
    ]
)

print(response.choices[0].message.content)
```

#### 多模态示例（图像输入）

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer YOUR_GEMINI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemini-1.5-flash",
    "messages": [{
      "role": "user",
      "content": [
        {"type": "text", "text": "这张图片里有什么？"},
        {
          "type": "image_url",
          "image_url": {
            "url": "https://example.com/image.jpg"
          }
        }
      ]
    }]
  }'
```

#### 函数调用示例

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer YOUR_GEMINI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemini-1.5-flash",
    "messages": [{"role": "user", "content": "北京今天天气怎么样？"}],
    "tools": [{
      "type": "function",
      "function": {
        "name": "get_weather",
        "description": "获取指定城市的天气信息",
        "parameters": {
          "type": "object",
          "properties": {
            "city": {"type": "string", "description": "城市名称"}
          },
          "required": ["city"]
        }
      }
    }]
  }'
```

#### 获取模型列表

```bash
curl http://localhost:8000/v1/models \
  -H "Authorization: Bearer YOUR_GEMINI_API_KEY"
```

### Gemini 原生接口

所有 `/v1beta/*` 路径将直接透传到 Gemini API：

```bash
curl http://localhost:8000/v1beta/models \
  -H "Authorization: Bearer YOUR_GEMINI_API_KEY"
```

---

## ⚙️ 配置

### 环境变量

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `PORT` | 服务监听端口 | `8000` |

### Docker Compose 配置

编辑 `docker-compose.yml`：

```yaml
services:
  gapi:
    ports:
      - "8000:8000"  # 修改主机端口
    environment:
      - PORT=8000    # 修改容器内端口
```

### .env 文件（可选）

创建 `.env` 文件：

```bash
PORT=8000
```

---

## 🏗️ 架构说明

```
gapi/
├── app/
│   ├── api/
│   │   └── routes.py          # API 路由定义
│   ├── core/
│   │   └── config.py          # 配置管理
│   ├── schemas/
│   │   └── openai.py          # OpenAI 数据模型
│   └── services/
│       ├── converter.py       # 格式转换服务
│       └── proxy_service.py   # 代理服务
├── main.py                    # 应用入口
├── requirements.txt           # 依赖列表
├── Dockerfile                 # Docker 镜像构建
└── docker-compose.yml         # Docker Compose 配置
```

### 核心模块

- **routes.py**：处理所有 API 请求路由
  - `/v1/chat/completions`：OpenAI 兼容的聊天接口
  - `/v1/models`：模型列表（OpenAI 格式）
  - `/v1beta/*`：Gemini 原生接口透传

- **converter.py**：格式转换核心
  - OpenAI → Gemini 请求转换
  - Gemini → OpenAI 响应转换
  - 支持多模态和工具调用

- **proxy_service.py**：HTTP 代理服务
  - 高并发连接池管理
  - 流式响应处理
  - 错误处理和重试

---

## 🛠️ 开发指南

### 本地开发环境

```bash
# 安装开发依赖
pip install -r requirements.txt

# 启动开发服务器（支持热重载）
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 测试

```bash
# 健康检查
curl http://localhost:8000/health

# 测试 OpenAI 接口
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"gemini-1.5-flash","messages":[{"role":"user","content":"test"}]}'
```

### 代码结构建议

- 遵循 FastAPI 最佳实践
- 保持异步处理（`async/await`）
- 使用 Pydantic 模型验证
- 添加适当的日志记录

---

## 📝 API Key 说明

本服务不存储任何 API Key，所有密钥直接透传给 Google Gemini API。

获取 Gemini API Key：
1. 访问 [Google AI Studio](https://makersuite.google.com/app/apikey)
2. 创建或登录 Google 账号
3. 生成 API Key

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

1. Fork 本项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

---

## 📄 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件

---

## 🌟 致谢

- [FastAPI](https://fastapi.tiangolo.com/) - 现代化的 Python Web 框架
- [Google Gemini](https://ai.google.dev/) - 强大的 AI 模型
- [OpenAI](https://openai.com/) - API 格式标准

---

<div align="center">

**如果这个项目对你有帮助，请给一个 ⭐️**

Made with ❤️ by [Your Name]

</div>
