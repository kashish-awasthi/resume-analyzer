"""Optional AI review using the Anthropic API.

Enabled when AI_MODEL is set and credentials are available (ANTHROPIC_API_KEY, or an
`ant auth login` profile). The rest of the app works without it.
"""

from __future__ import annotations

import json
import os

import anthropic


SYSTEM_PROMPT = """You review resumes for students and early-career software engineers.

Be specific and honest. Point to actual lines in the resume. Never invent experience,
skills, employers or numbers the candidate didn't write; when a rewritten bullet would
benefit from a metric the resume doesn't give, use a placeholder like [X%] so the
candidate fills in the real value.

If a job description is given, judge fit against it. If not, judge against typical
software engineering roles at the candidate's level."""

REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "overall_impression": {
            "type": "string",
            "description": "2-3 sentences: how a recruiter would read this resume.",
        },
        "strengths": {"type": "array", "items": {"type": "string"}},
        "improvements": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "issue": {"type": "string"},
                    "fix": {"type": "string"},
                },
                "required": ["issue", "fix"],
                "additionalProperties": False,
            },
        },
        "rewritten_bullets": {
            "type": "array",
            "description": "Up to 5 of the weakest bullet points, rewritten.",
            "items": {
                "type": "object",
                "properties": {
                    "original": {"type": "string"},
                    "improved": {"type": "string"},
                },
                "required": ["original", "improved"],
                "additionalProperties": False,
            },
        },
        "missing_for_job": {
            "type": "array",
            "description": "Skills or experience the job wants that the resume doesn't show. Empty if no job description.",
            "items": {"type": "string"},
        },
    },
    "required": ["overall_impression", "strengths", "improvements", "rewritten_bullets", "missing_for_job"],
    "additionalProperties": False,
}


class AIReviewError(RuntimeError):
    """A user-facing error from the AI review."""


def _model() -> str | None:
    return os.environ.get("AI_MODEL") or None


def ai_available() -> bool:
    """Best-effort check so the UI can hide the AI option when it isn't configured."""
    if not _model():
        return False
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return True
    return os.path.isdir(os.path.expanduser("~/.config/anthropic"))


def ai_review(resume_text: str, job_description: str | None = None, client: anthropic.Anthropic | None = None) -> dict:
    model = _model()
    if not model:
        raise AIReviewError("AI review is off. Set the AI_MODEL environment variable on the server.")
    client = client or anthropic.Anthropic()

    content = f"<resume>\n{resume_text}\n</resume>"
    if job_description and job_description.strip():
        content += f"\n\n<job_description>\n{job_description.strip()}\n</job_description>"
    content += "\n\nReview this resume."

    try:
        response = client.beta.messages.create(
            model=model,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            system=SYSTEM_PROMPT,
            output_config={
                "effort": "medium",
                "format": {"type": "json_schema", "schema": REVIEW_SCHEMA},
            },
            messages=[{"role": "user", "content": content}],
        )
    except anthropic.AuthenticationError as exc:
        raise AIReviewError("AI review isn't set up: the API key is missing or invalid.") from exc
    except anthropic.RateLimitError as exc:
        raise AIReviewError("AI review is busy right now. Try again in a minute.") from exc
    except anthropic.APIStatusError as exc:
        raise AIReviewError(f"AI review failed ({exc.status_code}). Try again later.") from exc
    except anthropic.APIConnectionError as exc:
        raise AIReviewError("Couldn't reach the AI service. Check your internet connection.") from exc

    if response.stop_reason == "refusal":
        raise AIReviewError("The AI declined to review this file.")
    if response.stop_reason == "max_tokens":
        raise AIReviewError("The AI review was cut off. Try a shorter resume.")

    text = next((b.text for b in response.content if b.type == "text"), None)
    if not text:
        raise AIReviewError("The AI returned an empty review.")
    return json.loads(text)
