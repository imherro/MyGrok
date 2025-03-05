#server.py
import logging
from fastapi import FastAPI, HTTPException, Header, Request
from pydantic import BaseModel, ValidationError, Field
from typing import List, Optional, Union
import time
from grok3_api import GrokAPI, check_dependencies   
from contextlib import asynccontextmanager

# Set up logging to file and terminal
logging.basicConfig(
    level=logging.ERROR,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("grok3_api.log"),  # Logs to file
        logging.StreamHandler()  # Logs to terminal
    ]
)
logger = logging.getLogger(__name__)

# Check dependencies at startup
if not check_dependencies():
    raise RuntimeError("Missing dependencies (xdotool, xclip, imagemagick)")

# Initialize GrokAPI with reuse_window=True
grok_api = GrokAPI(reuse_window=True)

# Model for message content (string or list of objects)
class ContentItem(BaseModel):
    type: str
    text: str

# Model for message
class Message(BaseModel):
    role: str
    content: Union[str, List[ContentItem]] = Field(..., description="Message content as string or list of content items")

# Model for request
class ChatRequest(BaseModel):
    model: str
    messages: List[Message]
    max_tokens: Optional[int] = None
    files: Optional[List[str]] = None
    temperature: Optional[float] = None  # Support for field from Roo Code request
    stream: Optional[bool] = None
    stream_options: Optional[dict] = None  # Support for field from Roo Code request

# Lifespan for managing startup and shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting application")
    yield
    if grok_api.window_id:
        grok_api.ask("", close_after=True)  # Close the window
    logger.info("Application shutdown")

# Create the application with lifespan
app = FastAPI(lifespan=lifespan)

@app.exception_handler(ValidationError)
async def validation_exception_handler(request: Request, exc: ValidationError):
    logger.error(f"Validation error for request {await request.json()}: {str(exc)}")
    return HTTPException(status_code=422, detail=str(exc))

@app.post("/v1/chat/completions")
async def chat_completions(request: Request, authorization: str = Header(default=None)):
    
    # logger.info(f"Received request body: {body}")
    # logger.info(f"Authorization header: {authorization}")

    # Try to validate the request
    try:
        parsed_request = ChatRequest(**body)
    except ValidationError as e:
        logger.error(f"Failed to parse request: {str(e)}")
        raise HTTPException(status_code=422, detail=str(e))

    # Collect the full text of all messages, including system context and environment_details
    full_message = ""
    for msg in parsed_request.messages:
        if isinstance(msg.content, str):
            full_message += f"{msg.role}: {msg.content}\n"
        elif isinstance(msg.content, list):
            full_message += f"{msg.role}: " + "\n".join(item.text for item in msg.content if isinstance(item, ContentItem)) + "\n"
    
    if not full_message:
        logger.error("No messages found in request")
        raise HTTPException(status_code=400, detail="No messages found in request")
 

    # Send the full text to GrokAPI
    file_paths = parsed_request.files if parsed_request.files else None
    try:
        response = grok_api.ask(message=full_message, file_paths=file_paths, timeout=120, close_after=False)
        if response.startswith("Error:"):
            logger.error(f"GrokAPI returned error: {response}")
            raise Exception(response)
        # logger.info(f"Received response from GrokAPI: {response}")
    except Exception as e:
        logger.error(f"Error processing request: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing request: {str(e)}")

    # Format the response in OpenAI format
    response_dict = {
        "id": f"chatcmpl-{int(time.time())}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": parsed_request.model,
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
    # logger.info(f"Returning response: {response_dict}")
    
    # If the request specifies stream=True, return the result in streaming format (for now, just return JSON)
    if parsed_request.stream:
        return {"choices": [{"delta": {"content": response}}], "usage": response_dict["usage"]}
    return response_dict

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)