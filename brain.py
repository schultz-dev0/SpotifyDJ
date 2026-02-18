"""
brain.py
--------
Converts a natural language music request into a Spotify search query
using Google's Gemini API.

Falls back to basic keyword stripping if all AI models are unavailable
or if no API key has been configured.

To add or change models, edit CANDIDATE_MODELS below.
Models are tried in order - put the fastest/cheapest ones first.
"""

from google import genai
from google.genai import types
from pydantic import BaseModel

# Models are tried top to bottom. Lite models have higher free-tier quotas
# so they are listed first to reduce the chance of hitting rate limits.
CANDIDATE_MODELS = [
    "gemini-2.0-flash-lite",
    "gemini-2.0-flash-lite-001",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
    "gemma-3-4b-it",
]

SEARCH_PROMPT_TEMPLATE = """
You are a Spotify search expert. Convert the user's request into a high-performing search query.

User Request: "{user_prompt}"

Rules for search_query:
1. Use 'genre:' only for clear genres (e.g. dnb, techno, jazz, classical).
2. Use 'year:' for era requests (e.g. year:1990-1995).
3. For moods (relaxing, aggressive, dark), do NOT use 'genre:' - use keywords only.

Examples:
  "relaxing coding music"  ->  "lofi focus chill"
  "90s house music"        ->  "genre:house year:1990-1999"
  "aggressive phonk"       ->  "aggressive genre:phonk"

Output JSON: {{ "reasoning": "short explanation of your choices", "search_query": "the query" }}
"""

# Words stripped out when falling back to keyword search
STOPWORDS = {
    "play", "some", "me", "i", "want", "can", "you",
    "please", "listen", "to", "for", "a", "put", "on", "the",
}


class DJDirectives(BaseModel):
    """Structured output returned by the AI model."""
    reasoning: str
    search_query: str


def _keyword_fallback(user_prompt: str) -> str:
    """
    Strip filler words and return a basic search query.
    Used when the AI is unavailable.
    Example: 'play some high energy dnb'  ->  'high energy dnb'
    """
    words   = user_prompt.lower().split()
    cleaned = [w for w in words if w not in STOPWORDS]
    return " ".join(cleaned)


def get_vibe_params(user_prompt: str, api_key: str) -> DJDirectives:
    """
    Convert a natural language music request into a Spotify search query.

    Tries each model in CANDIDATE_MODELS in order.
    Silently skips on quota (429) or model-not-found (404) errors.
    Returns a keyword-stripped fallback if all models fail.
    """
    if not api_key:
        return DJDirectives(
            reasoning="No Gemini API key configured. Using keyword fallback.",
            search_query=_keyword_fallback(user_prompt),
        )

    client = genai.Client(api_key=api_key)
    prompt = SEARCH_PROMPT_TEMPLATE.format(user_prompt=user_prompt)

    for model_name in CANDIDATE_MODELS:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=DJDirectives,
                ),
            )
            if response.parsed:
                return response.parsed

        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "404" in error_str:
                # Quota exceeded or model unavailable - try the next one
                continue
            # Unexpected error - log it and still try the next model
            print(f"[brain] {model_name}: {error_str}")
            continue

    return DJDirectives(
        reasoning="All AI models unavailable. Using keyword fallback.",
        search_query=_keyword_fallback(user_prompt),
    )