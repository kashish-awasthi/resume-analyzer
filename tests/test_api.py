import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from docx import Document
from fastapi.testclient import TestClient

from app import ai
from app.main import app
from app.parser import ResumeParseError, extract_text

client = TestClient(app)
RESUME = (Path(__file__).resolve().parent.parent / "samples" / "sample_resume.txt").read_text()


def make_docx(text: str) -> bytes:
    doc = Document()
    for line in text.splitlines():
        doc.add_paragraph(line)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ---------- parser ----------


def test_extracts_docx():
    text = extract_text("resume.docx", make_docx(RESUME))
    assert "FastAPI" in text


def test_rejects_unknown_type():
    with pytest.raises(ResumeParseError):
        extract_text("resume.exe", b"x" * 100)


def test_rejects_empty_file():
    with pytest.raises(ResumeParseError):
        extract_text("resume.txt", b"")


# ---------- API ----------


def test_health():
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_index_page():
    res = client.get("/")
    assert res.status_code == 200
    assert "Resume Analyzer" in res.text


def test_analyze_uploaded_file():
    res = client.post(
        "/api/analyze",
        files={"file": ("resume.docx", make_docx(RESUME))},
        data={"job_description": "Python and Kubernetes required"},
    )
    assert res.status_code == 200
    body = res.json()
    assert 0 <= body["score"] <= 100
    assert "Kubernetes" in body["job_match"]["missing_skills"]


def test_analyze_pasted_text():
    res = client.post("/api/analyze", data={"resume_text": RESUME})
    assert res.status_code == 200
    assert res.json()["job_match"] is None


def test_analyze_requires_input():
    res = client.post("/api/analyze", data={})
    assert res.status_code == 400


def test_analyze_bad_file_type():
    res = client.post("/api/analyze", files={"file": ("resume.png", b"\x89PNG" * 50)})
    assert res.status_code == 400
    assert "Unsupported" in res.json()["detail"]


def test_sample_endpoint():
    body = client.get("/api/sample").json()
    assert "EDUCATION" in body["resume_text"]


# ---------- AI review (with a fake API client, no network) ----------

FAKE_REVIEW = {
    "overall_impression": "Solid student resume.",
    "strengths": ["Real projects"],
    "improvements": [{"issue": "Vague bullet", "fix": "Add a metric"}],
    "rewritten_bullets": [{"original": "Worked on bug fixes", "improved": "Fixed [X] bugs"}],
    "missing_for_job": [],
}


class FakeMessages:
    def __init__(self, stop_reason="end_turn"):
        self.stop_reason = stop_reason
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(
            stop_reason=self.stop_reason,
            content=[SimpleNamespace(type="text", text=json.dumps(FAKE_REVIEW))],
        )


def fake_client(stop_reason="end_turn"):
    messages = FakeMessages(stop_reason)
    return SimpleNamespace(beta=SimpleNamespace(messages=messages)), messages


def test_ai_review_parses_structured_output(monkeypatch):
    monkeypatch.setenv("AI_MODEL", "test-model")
    fake, messages = fake_client()
    review = ai.ai_review(RESUME, "Backend role", client=fake)
    assert review == FAKE_REVIEW
    assert messages.kwargs["model"] == "test-model"
    assert "job_description" in messages.kwargs["messages"][0]["content"]
    assert messages.kwargs["output_config"]["format"]["type"] == "json_schema"


def test_ai_review_handles_refusal(monkeypatch):
    monkeypatch.setenv("AI_MODEL", "test-model")
    fake, _ = fake_client(stop_reason="refusal")
    with pytest.raises(ai.AIReviewError):
        ai.ai_review(RESUME, client=fake)


def test_ai_endpoint(monkeypatch):
    monkeypatch.setattr("app.main.ai_review", lambda text, jd: FAKE_REVIEW)
    res = client.post("/api/ai-review", data={"resume_text": RESUME})
    assert res.status_code == 200
    assert res.json()["strengths"] == ["Real projects"]
