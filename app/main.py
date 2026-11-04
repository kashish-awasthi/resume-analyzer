"""FastAPI app: upload a resume, get a score and feedback."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .ai import AIReviewError, ai_available, ai_review
from .analyzer import analyze
from .parser import MAX_FILE_BYTES, ResumeParseError, extract_text

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "static"
SAMPLES_DIR = ROOT / "samples"

app = FastAPI(
    title="Resume Analyzer",
    description="ATS-style resume scoring, job-description matching and optional AI review.",
    version="1.0.0",
)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "ai_available": ai_available()}


@app.get("/api/sample")
def sample() -> dict:
    """A made-up resume and job posting for trying the app."""
    return {
        "resume_text": (SAMPLES_DIR / "sample_resume.txt").read_text(),
        "job_description": (SAMPLES_DIR / "sample_job.txt").read_text(),
    }


@app.post("/api/analyze")
async def analyze_resume(
    file: UploadFile | None = File(None),
    resume_text: str = Form(""),
    job_description: str = Form(""),
) -> dict:
    """Analyze an uploaded resume file, or pasted resume text."""
    if file is not None and file.filename:
        data = await file.read(MAX_FILE_BYTES + 1)
        try:
            text = extract_text(file.filename, data)
        except ResumeParseError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    elif resume_text.strip():
        text = resume_text.strip()
        if len(text) < 50:
            raise HTTPException(status_code=400, detail="Paste your full resume text.")
    else:
        raise HTTPException(status_code=400, detail="Upload a resume file or paste its text.")

    result = analyze(text, job_description).to_dict()
    result["resume_text"] = text
    return result


@app.post("/api/ai-review")
def ai_review_endpoint(resume_text: str = Form(...), job_description: str = Form("")) -> dict:
    if len(resume_text.strip()) < 50:
        raise HTTPException(status_code=400, detail="Resume text is too short to review.")
    try:
        return ai_review(resume_text, job_description)
    except AIReviewError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
