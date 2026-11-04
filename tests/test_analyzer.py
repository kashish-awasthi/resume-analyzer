from pathlib import Path

from app.analyzer import analyze, detect_sections, find_skills, job_requirements

SAMPLES = Path(__file__).resolve().parent.parent / "samples"
RESUME = (SAMPLES / "sample_resume.txt").read_text()
JOB = (SAMPLES / "sample_job.txt").read_text()


def all_skills(text):
    return {s for group in find_skills(text).values() for s in group}


def test_finds_common_skills():
    skills = all_skills("Built apps with React Native, FastAPI, PostgreSQL and Docker on AWS.")
    assert {"React Native", "FastAPI", "PostgreSQL", "Docker", "AWS"} <= skills


def test_short_names_need_exact_case():
    assert "Go" in all_skills("Backend services in Go and Python")
    assert "Go" not in all_skills("Ready to go the extra mile")
    assert "R" not in all_skills("r and d")


def test_c_does_not_match_cpp_or_csharp():
    skills = all_skills("Languages: C++, C#")
    assert "C++" in skills and "C#" in skills
    assert "C" not in skills


def test_java_does_not_match_javascript():
    skills = all_skills("Frontend in JavaScript")
    assert "JavaScript" in skills
    assert "Java" not in skills


def test_detects_sections():
    sections = detect_sections(RESUME)
    assert all(sections[s] for s in ["Education", "Experience", "Skills", "Projects"])


def test_or_requirements_are_alternatives():
    reqs = job_requirements("Experience with FastAPI, Django or Flask\nKnowledge of Docker")
    assert {"FastAPI", "Django", "Flask"} in reqs
    assert {"Docker"} in reqs


def test_job_match_counts_alternatives_once():
    result = analyze(RESUME, JOB)
    assert result.job_match is not None
    # Resume has FastAPI, so Django/Flask should not be reported missing.
    assert not any("Django" in m for m in result.job_match.missing_skills)
    assert "Kubernetes" in result.job_match.missing_skills
    assert 0 < result.job_match.match_percent < 100


def test_score_without_job_description():
    result = analyze(RESUME)
    assert result.job_match is None
    assert 0 <= result.score <= 100
    assert all(p.name != "Job match" for p in result.breakdown)


def test_flags_weak_phrases_and_missing_contact():
    text = "\n".join(
        [
            "EXPERIENCE",
            "- Responsible for the website",
            "- Worked on many various things",
            "- Helped with testing",
            "SKILLS",
            "Python",
        ]
    ) * 3
    result = analyze(text)
    assert "responsible for" in result.weak_phrases
    assert result.contact["email"] is None
    assert any("email" in s for s in result.suggestions)


def test_strong_resume_scores_higher_than_weak():
    weak = "EXPERIENCE\n- Responsible for coding\n- Worked on stuff\n- Helped with things\n" * 3
    assert analyze(RESUME).score > analyze(weak).score


def test_counts_quantified_and_action_bullets():
    result = analyze(RESUME)
    assert result.stats["action_verb_bullets"] >= 5
    assert result.stats["quantified_bullets"] >= 4
