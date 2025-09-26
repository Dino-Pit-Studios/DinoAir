"""Mock chat service for testing when LM Studio is unavailable"""

import time
from typing import Any


def mock_chat_completion(request: dict[str, Any]) -> dict[str, Any]:
    """Mock chat completion function that simulates LLM responses"""
    messages = request.get("messages", [])
    user_message = ""

    # Get the last user message
    for msg in reversed(messages):
        if msg.get("role") == "user":
            user_message = msg.get("content", "")
            break

    # Simple mock responses based on input
    if "hello" in user_message.lower():
        response = (
            "Hello! I'm a mock AI assistant. LM Studio is not currently "
            "running, so I'm providing this test response."
        )
    elif "how are you" in user_message.lower():
        response = "I'm doing well, thank you! This is a mock response while LM Studio is offline."
    elif "test" in user_message.lower():
        response = (
            "Test successful! The mock chat service is working correctly. "
            "Start LM Studio to get real AI responses."
        )
    else:
        response = (
            f"I received your message: '{user_message}'. This is a mock "
            "response - start LM Studio for real AI capabilities."
        )

    # Simulate some processing time
    time.sleep(0.5)

    return {
        "choices": [
            {"message": {"role": "assistant", "content": response}, "finish_reason": "stop"}
        ],
        "usage": {
            "prompt_tokens": len(user_message.split()),
            "completion_tokens": len(response.split()),
            "total_tokens": len(user_message.split()) + len(response.split()),
        },
        "model": "mock-assistant",
        "object": "chat.completion",
    }
