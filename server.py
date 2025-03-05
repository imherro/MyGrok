import logging
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
from typing import List, Optional
import time
from grok3_api import GrokAPI, check_dependencies  # Импорт твоего API
from contextlib import asynccontextmanager

# Настраиваем логирование
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Проверяем зависимости при старте
if not check_dependencies():
    raise RuntimeError("Missing dependencies (xdotool, xclip, imagemagick)")

# Инициализируем GrokAPI с reuse_window=True
grok_api = GrokAPI(reuse_window=True)

# Модель для сообщений
class Message(BaseModel):
    role: str
    content: str

# Модель для запроса
class ChatRequest(BaseModel):
    model: str
    messages: List[Message]
    max_tokens: Optional[int] = None
    files: Optional[List[str]] = None

# Lifespan для управления стартом и завершением
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting application")
    yield
    if grok_api.window_id:
        grok_api.ask("", close_after=True)  # Закрываем окно
    logger.info("Application shutdown")

# Создаём приложение с lifespan
app = FastAPI(lifespan=lifespan)

@app.post("/v1/chat/completions")
async def chat_completions(request: ChatRequest, authorization: str = Header(default=None)):
    # Логируем входящий запрос и заголовки
    logger.info(f"Received request: {request.dict()}")
    logger.info(f"Authorization header: {authorization}")

    # Собираем последнее сообщение пользователя
    user_message = None
    for msg in request.messages:
        if msg.role == "user":
            user_message = msg.content
            break
    
    if not user_message:
        logger.error("No user message found in request")
        raise HTTPException(status_code=400, detail="No user message found")

    # Пока отправляем только последнее сообщение
    full_message = user_message
    file_paths = request.files if request.files else None
    logger.info(f"Sending to GrokAPI: message='{full_message}', files={file_paths}")

    # Отправляем запрос в GrokAPI
    try:
        response = grok_api.ask(message=full_message, file_paths=file_paths, timeout=60, close_after=False)
        if response.startswith("Error:"):
            logger.error(f"GrokAPI returned error: {response}")
            raise Exception(response)
        logger.info(f"Received response from GrokAPI: {response}")
    except Exception as e:
        logger.error(f"Error processing request: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing request: {str(e)}")

    # Формируем ответ в формате OpenAI
    response_dict = {
        "id": f"chatcmpl-{int(time.time())}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": request.model,
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": response
            },
            "finish_reason": "stop"
        }],
        "usage": {
            "prompt_tokens": len(full_message.split()),
            "completion_tokens": len(response.split()),
            "total_tokens": len(full_message.split()) + len(response.split())
        }
    }
    logger.info(f"Returning response: {response_dict}")
    return response_dict

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)