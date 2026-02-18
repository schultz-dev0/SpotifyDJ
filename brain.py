"""
brain.py
--------
Converts a natural language music request into multiple targeted Spotify
search queries. Running several focused queries and merging the results
gives far better coverage and quantity than a single search.

The AI generates 5-10 queries that each attack the request from a different
angle: genre, mood, era, similar artists, tempo, etc. spotify_client.py
runs them all, deduplicates by URI, shuffles, and queues the result.

Falls back to basic keyword stripping if AI is unavailable.
"""

from __future__ import annotations

from typing import Optional
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

CANDIDATE_MODELS = [
    "gemini-2.0-flash-lite",
    "gemini-2.0-flash-lite-001",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
]

SEARCH_PROMPT_TEMPLATE = """
You are a Spotify search expert powering an AI DJ. Your job is to generate
multiple targeted search queries that together will build a large, varied,
high-quality queue of tracks matching the user's request.

User Request: "{user_prompt}"

---
STRATEGY:
Generate 6 to 10 search queries. Each query should attack the request from
a DIFFERENT angle so the combined results are varied, not repetitive.

Good angles to use (pick the most relevant for this request):
  - Core genre + mood keyword          e.g. "dark minimal techno"
  - Specific sub-genre                 e.g. "industrial techno Berlin"
  - Era-based                          e.g. "techno 1990s Detroit"
  - Artist style reference             e.g. "similar to Aphex Twin ambient"
  - Tempo/energy descriptor            e.g. "fast aggressive techno 140bpm"
  - Instrumental vs vocal              e.g. "techno instrumental no vocals"
  - Label/scene reference              e.g. "Warp Records electronic"
  - Mood-first approach                e.g. "dark hypnotic driving music"
  - Trending/popular angle             e.g. "best techno tracks 2023"
  - Deep cut / underground angle       e.g. "underground techno obscure"

SEARCH QUERY RULES:
- Keep each query short: 2-5 words works best on Spotify
- Do NOT use field filters like genre: or year: — Spotify's search handles
  natural language keywords much better for this use case
- Do NOT repeat the same core words across all queries — diversity is the goal
- Think about what a human would actually type into Spotify to find this

QUEUE SIZE:
How many total tracks to aim for (after deduplication):
  - Quick / casual listen:    20-35
  - Background / work:        40-60
  - Long session (gym/study): 70-100
Default: 40. Scale up for requests that sound like marathon sessions.

---
EXAMPLES:

Request: "dark techno for a late night drive"
queries: [
  "dark techno driving",
  "minimal techno hypnotic",
  "industrial techno Berlin",
  "late night electronic dark",
  "techno underground 2020",
  "atmospheric techno instrumental",
  "fast dark electronic pounding"
]
queue_size: 50

Request: "happy acoustic songs for a sunday morning"
queries: [
  "acoustic happy morning",
  "folk singer songwriter uplifting",
  "acoustic guitar feel good",
  "indie folk sunshine",
  "acoustic pop relaxing",
  "coffeehouse acoustic chill"
]
queue_size: 30

Request: "aggressive workout music"
queries: [
  "aggressive workout metal",
  "heavy rock gym motivation",
  "hardcore punk fast",
  "metal high energy workout",
  "hard rock aggressive driving",
  "metalcore gym pump up",
  "industrial metal workout",
  "punk rock fast aggressive"
]
queue_size: 60

Request: "instrumental focus music no lyrics"
queries: [
  "instrumental focus study",
  "ambient electronic no vocals",
  "lo-fi instrumental chill",
  "piano instrumental concentration",
  "ambient work no lyrics",
  "post-rock instrumental",
  "electronic ambient focus 2022"
]
queue_size: 70

---
Output JSON only. The reasoning field should briefly explain your query strategy.
"""

STOPWORDS = {
    "play", "some", "me", "i", "want", "can", "you",
    "please", "listen", "to", "for", "a", "put", "on", "the",
    "something", "anything", "music", "songs", "tracks",
}


class DJDirectives(BaseModel):
    """Structured output returned by the AI model."""
    reasoning:    str
    queries:      list[str] = Field(default_factory=list)  # multiple search queries
    queue_size:   int = 40                                  # target total tracks


def _keyword_fallback(user_prompt: str) -> DJDirectives:
    words   = user_prompt.lower().split()
    cleaned = [w for w in words if w not in STOPWORDS]
    query   = " ".join(cleaned) or user_prompt
    return DJDirectives(
        reasoning="No Gemini API key configured. Using keyword fallback.",
        queries=[query],
        queue_size=40,
    )


def get_vibe_params(user_prompt: str, api_key: str) -> DJDirectives:
    """
    Convert a natural language request into multiple Spotify search queries.
    Tries each model in CANDIDATE_MODELS in order.
    Returns a keyword fallback if all models fail.
    """
    if not api_key:
        return _keyword_fallback(user_prompt)

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
                d = response.parsed
                d.queue_size = max(1, min(100, d.queue_size))
                # Ensure we always have at least one query
                if not d.queries:
                    d.queries = [_keyword_fallback(user_prompt).queries[0]]
                return d

        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "404" in error_str:
                continue
            print(f"[brain] {model_name}: {error_str}")
            continue

    return DJDirectives(
        reasoning="All AI models unavailable. Using keyword fallback.",
        queries=_keyword_fallback(user_prompt).queries,
        queue_size=40,
    )