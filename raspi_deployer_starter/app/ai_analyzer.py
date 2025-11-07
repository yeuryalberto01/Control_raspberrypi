from __future__ import annotations

import json

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from .deps import Settings, get_settings

router = APIRouter()


class LogAnalysisRequest(BaseModel):
    logs: str


class AIAnalysis(BaseModel):
    explanation: str
    command: str | None = None


AI_SYSTEM_PROMPT = """
You are a DevOps and Raspberry Pi expert. Analyze the following log snippet.
Provide a concise, one-sentence explanation of the root cause.
If applicable, suggest a single, safe shell command to resolve the issue.
Respond ONLY with a valid JSON object with two keys: "explanation" and "command".
If no command is applicable, the value for "command" should be null.
Example response: {"explanation": "The service failed because the port is already in use.", "command": "lsof -i :8000"}
"""


@router.post("/analyze-logs", response_model=AIAnalysis)
async def analyze_logs(
    request: LogAnalysisRequest,
    settings: Settings = Depends(get_settings),
) -> AIAnalysis:
    """Analyzes a log snippet using a configured external AI API."""
    if not settings.ai_api_endpoint or not settings.ai_api_key:
        raise HTTPException(
            status_code=status.HTTP_424_FAILED_DEPENDENCY,
            detail="The AI Analyzer is not configured. Please set AI_API_ENDPOINT and AI_API_KEY.",
        )

    payload = {
        "model": "gpt-3.5-turbo",  # This can be any model the user's endpoint supports
        "messages": [
            {"role": "system", "content": AI_SYSTEM_PROMPT},
            {"role": "user", "content": request.logs},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.1,
    }

    headers = {"Authorization": f"Bearer {settings.ai_api_key}"}

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                settings.ai_api_endpoint,
                json=payload,
                headers=headers,
                timeout=30.0,
            )
            response.raise_for_status()  # Raise an exception for 4xx or 5xx status codes

        ai_response_data = response.json()
        content_str = ai_response_data.get("choices", [{}])[0].get("message", {}).get("content", "")

        if not content_str:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY, detail="AI returned an empty response."
            )

        # The AI is instructed to return a JSON string, so we parse it.
        parsed_content = json.loads(content_str)
        return AIAnalysis(**parsed_content)

    except httpx.RequestError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Error connecting to the AI API: {e}",
        )
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"AI API returned an error: {e.response.text}",
        )
    except (json.JSONDecodeError, KeyError) as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to parse the response from the AI API: {e}",
        )
