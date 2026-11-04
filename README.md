# Resume Analyzer

![CI](https://github.com/kashish-awasthi/resume-analyzer/actions/workflows/ci.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.12%2B-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

Upload a resume, paste a job description, and get:

- An **ATS-style score out of 100**, with a breakdown of where points were lost
- A **job match**: which required skills you have, and which are missing
- **Specific fixes**: weak phrases, bullets without numbers, missing sections and contact links
- An optional **AI review** with recruiter-style feedback and rewritten bullet points

The scoring runs locally with no API key. The AI review turns on when an Anthropic API key and model are set.

<!-- Add a screenshot: docs/screenshot.png -->

## How it works

| Check | Points | What it looks at |
|---|---|---|
| Job match | 35 | Skills the job asks for (treats "FastAPI, Django or Flask" as alternatives) and repeated keywords from the posting |
| Impact | 20 | Share of bullet points that start with an action verb and include a number |
| Sections | 15 | Education, Experience, Skills and Projects headings (plus Summary and Certifications) |
| Contact info | 10 | Email, phone, LinkedIn, GitHub |
| Length | 10 | 350 to 900 words is the target for early-career resumes |
| Language | 10 | Weak phrases ("responsible for", "worked on") and first-person pronouns |

With no job description, the score is calculated from the other 65 points, scaled to 100.

Skills are matched against a dictionary of about 70 technologies with aliases (e.g. `node.js` / `nodejs`). Short names like `Go`, `R` and `C` only match with exact casing and boundaries, so "go the extra mile" isn't counted as Go, and `C++` isn't counted as `C`.

## Tech stack

- **Backend:** Python, FastAPI, pypdf, python-docx
- **AI:** Anthropic API with structured JSON output
- **Frontend:** HTML, CSS and vanilla JavaScript (no build step), light and dark mode
- **Quality:** pytest (24 tests), GitHub Actions CI, Docker

## Run it locally

```bash
git clone https://github.com/kashish-awasthi/resume-analyzer.git
cd resume-analyzer
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

Open http://localhost:8000 and click **Try a sample**.

To turn on the AI review:

```bash
export ANTHROPIC_API_KEY=your-key-here
export AI_MODEL=model-id-from-the-anthropic-docs
uvicorn app.main:app --reload
```

### With Docker

```bash
docker build -t resume-analyzer .
docker run -p 8000:8000 -e ANTHROPIC_API_KEY -e AI_MODEL resume-analyzer
```

## API

Interactive docs are at `/docs` when the server is running.

| Method | Path | Body | Returns |
|---|---|---|---|
| `POST` | `/api/analyze` | form: `file` (PDF/DOCX/TXT) or `resume_text`, optional `job_description` | Score, breakdown, skills, job match, suggestions |
| `POST` | `/api/ai-review` | form: `resume_text`, optional `job_description` | AI review as JSON |
| `GET` | `/api/health` | | Status, and whether AI review is on |

```bash
curl -F file=@resume.pdf -F job_description="Python, Docker, AWS" http://localhost:8000/api/analyze
```

## Tests

```bash
pytest -q
```

The AI tests use a fake API client, so they run without a key or network.

## Project structure

```
app/
  main.py       FastAPI routes
  analyzer.py   Scoring, job matching, suggestions
  skills.py     Skills dictionary
  parser.py     PDF / DOCX / TXT text extraction
  ai.py         Optional AI review
static/         Frontend (index.html, style.css, app.js)
samples/        A made-up resume and job posting
tests/          pytest suite
```

## Privacy

Resumes are processed in memory and never written to disk. With AI review on, the resume text is sent to the Anthropic API.

## Ideas for next steps

- Scanned PDF support with OCR
- Compare one resume against several job postings at once
- Export the report as a PDF

## License

MIT
