"""Content scoring agent (Google Gemini, free tier, via the current google-genai SDK)."""
import json
import re

from google import genai
from google.genai import types
from fastapi import APIRouter, HTTPException, Depends

from core import GEMINI_API_KEY, get_current_user, logger
from models import ScoreIn, ScoreResult

router = APIRouter()

_client = genai.Client(api_key=GEMINI_API_KEY)
MODEL = "gemini-2.0-flash"

SYSTEM_PROMPT = """You are a senior marketing governance agent. Evaluate marketing content briefs and return STRICT JSON only.

Scoring criteria:
1. brand_alignment_score (0-100): tone, voice, professional polish, messaging coherence.
2. completeness_score (0-100): does the brief have enough context (audience, goal, CTA, channel)? Is content ready to review or will it bounce back?
3. content_classification: "routine" (recurring social, blog, email) OR "innovation" (launches, new positioning, partnerships, pricing changes).
4. risk_flags: list any of ["pricing", "legal", "partnership", "announcement", "competitor_claim", "regulatory"] that apply. Empty list if none.
5. overall_score (0-100): weighted average reflecting readiness.
6. recommended_tier:
   - "auto_approve" if routine, no risk flags, completeness >= 80, brand >= 80.
   - "ceo_required" if any of: risk_flags non-empty (esp. pricing/legal/partnership/announcement) OR classification is "innovation".
   - "product_only" otherwise.
7. reasoning: 2-3 sentence explanation.
8. questions_to_resolve: list of specific questions if completeness < 80, else [].

Return ONLY valid JSON. No markdown, no preface."""


def extract_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return json.loads(match.group(0))
    raise ValueError("No JSON found in LLM response")


@router.post("/score", response_model=ScoreResult)
async def score_content(body: ScoreIn, user: dict = Depends(get_current_user)):
    user_text = f"""Title: {body.title}
Request Type: {body.request_type}

Brief:
{body.brief}

Content:
{body.content}

Return JSON with keys: brand_alignment_score, completeness_score, content_classification, risk_flags, overall_score, recommended_tier, reasoning, questions_to_resolve."""

    try:
        response = await _client.aio.models.generate_content(
            model=MODEL,
            contents=user_text,
            config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT),
        )
        raw_text = response.text
    except Exception as e:
        logger.error(f"Gemini call failed: {e}")
        raise HTTPException(status_code=502, detail=f"Scoring request failed: {e}")

    try:
        data = extract_json(raw_text)
        data["brand_alignment_score"] = int(data.get("brand_alignment_score", 0))
        data["completeness_score"] = int(data.get("completeness_score", 0))
        data["overall_score"] = int(data.get("overall_score", 0))
        data["risk_flags"] = list(data.get("risk_flags", []) or [])
        data["questions_to_resolve"] = list(data.get("questions_to_resolve", []) or [])
        return ScoreResult(**data)
    except Exception as e:
        logger.error(f"Score parse failed: {e}; raw={raw_text}")
        raise HTTPException(status_code=502, detail=f"Scoring failed: {e}")