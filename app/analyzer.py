"""Rule-based resume analysis: ATS-style score, skills, job-description match, and tips.

Everything here runs locally with no API key. The optional AI review lives in ai.py.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict, dataclass, field

from .skills import CASE_SENSITIVE_FORMS, SKILLS

# ---------------------------------------------------------------------------
# Word lists
# ---------------------------------------------------------------------------

ACTION_VERBS = {
    "achieved", "analyzed", "architected", "automated", "built", "collaborated",
    "configured", "created", "debugged", "delivered", "deployed", "designed",
    "developed", "drove", "engineered", "enhanced", "established", "evaluated",
    "executed", "implemented", "improved", "increased", "integrated", "launched",
    "led", "maintained", "managed", "mentored", "migrated", "modeled", "optimized",
    "orchestrated", "organized", "owned", "planned", "presented", "programmed",
    "reduced", "refactored", "researched", "resolved", "scaled", "shipped",
    "simplified", "spearheaded", "streamlined", "tested", "trained", "transformed",
    "wrote", "won", "coordinated", "published", "prototyped", "containerized",
}

WEAK_PHRASES = [
    "responsible for", "worked on", "helped with", "helped to", "involved in",
    "duties included", "tasks included", "assisted with", "participated in",
    "various", "etc", "hard-working", "hardworking", "team player", "go-getter",
    "detail-oriented", "self-motivated", "passionate about",
]

FIRST_PERSON = re.compile(r"\b(I|me|my|myself)\b")

STOPWORDS = set(
    """a about above after again against all also am an and any are as at be because been
    before being below between both but by can could did do does doing down during each few
    for from further had has have having he her here hers herself him himself his how i if in
    into is it its itself just me more most my myself no nor not now of off on once only or
    other our ours ourselves out over own same she should so some such than that the their
    theirs them themselves then there these they this those through to too under until up very
    was we were what when where which while who whom why will with you your yours yourself
    yourselves able across etc must may might shall within without per via using use used
    including include includes like well new good strong excellent work working job role team
    teams candidate candidates experience experienced years year required requirements
    preferred plus ability skills skill knowledge understanding responsibilities company
    looking join opportunity apply us our we'll you'll you're who'd will be""".split()
)

SECTION_PATTERNS = {
    "Summary": r"(summary|objective|profile|about me)",
    "Education": r"(education|academic|qualification)",
    "Experience": r"(experience|employment|work history|internship|internships)",
    "Skills": r"(skills|technologies|tech stack|technical proficiency|tools)",
    "Projects": r"(projects|personal projects|academic projects)",
    "Certifications & Achievements": r"(certification|certifications|achievements|awards|honors|accomplishments)",
}
REQUIRED_SECTIONS = ["Education", "Experience", "Skills", "Projects"]

BULLET_PREFIX = re.compile(r"^\s*([•●▪◦‣∙·\-–—*]|\d+[.)])\s+")
QUANTIFIED = re.compile(
    r"(\d+(\.\d+)?\s?%|\$\s?\d|₹\s?\d|\b\d+\s?[xX]\b|\b\d+\+|\b\d{2,}\b|\b\d+(\.\d+)?\s?(k|m|ms|s|hrs|hours|users|students|clients)\b)",
    re.IGNORECASE,
)
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE = re.compile(r"(\+?\d[\d\s().-]{8,}\d)")
LINKEDIN = re.compile(r"linkedin\.com/in/[\w-]+", re.IGNORECASE)
GITHUB = re.compile(r"github\.com/[\w-]+", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class ScorePart:
    name: str
    score: float
    max: float
    notes: list[str] = field(default_factory=list)


@dataclass
class JobMatch:
    match_percent: int
    matched_skills: list[str]
    missing_skills: list[str]
    matched_keywords: list[str]
    missing_keywords: list[str]


@dataclass
class Analysis:
    score: int
    grade: str
    breakdown: list[ScorePart]
    skills_found: dict[str, list[str]]
    job_match: JobMatch | None
    contact: dict[str, str | None]
    sections: dict[str, bool]
    stats: dict[str, int]
    weak_phrases: dict[str, int]
    suggestions: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _alias_pattern(alias: str) -> re.Pattern[str]:
    # Boundaries that treat +, #, . as part of a token, so "C" doesn't match "C++".
    return re.compile(rf"(?<![\w+#.]){re.escape(alias)}(?![\w+#])")


def find_skills(text: str) -> dict[str, list[str]]:
    """Return the known skills mentioned in text, grouped by category."""
    lower = text.lower()
    found: dict[str, list[str]] = {}
    for category, skills in SKILLS.items():
        for name, aliases in skills.items():
            hit = False
            for alias in aliases:
                if alias in CASE_SENSITIVE_FORMS:
                    hit = any(_alias_pattern(form).search(text) for form in CASE_SENSITIVE_FORMS[alias])
                else:
                    hit = bool(_alias_pattern(alias).search(lower))
                if hit:
                    break
            if hit:
                found.setdefault(category, []).append(name)
    return found


def _flatten(skills: dict[str, list[str]]) -> set[str]:
    return {s for group in skills.values() for s in group}


def job_requirements(job_description: str) -> list[set[str]]:
    """Split a job description into skill requirements.

    Each requirement is a set of alternatives: "FastAPI, Django or Flask" on one line
    becomes one requirement satisfied by any of the three. Other skills are their own
    requirement.
    """
    requirements: list[set[str]] = []
    seen: set[str] = set()
    for line in re.split(r"[\n;]", job_description):
        line_skills = _flatten(find_skills(line)) - seen
        if not line_skills:
            continue
        seen |= line_skills
        if re.search(r"\b(or|either|any of|one of)\b", line, re.IGNORECASE) and len(line_skills) > 1:
            requirements.append(line_skills)
        else:
            requirements.extend({s} for s in line_skills)
    return requirements


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z][a-zA-Z+#.\-]{2,}", text.lower())


def _keyword_candidates(job_description: str, skill_aliases: set[str]) -> list[str]:
    """Frequent meaningful words in the job description that aren't already skills."""
    counts = Counter(
        t.strip(".-")
        for t in _tokens(job_description)
        if t.strip(".-") not in STOPWORDS and t.strip(".-") not in skill_aliases and len(t.strip(".-")) >= 4
    )
    return [word for word, n in counts.most_common(15) if n >= 2]


def detect_sections(text: str) -> dict[str, bool]:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    headings = [ln for ln in lines if len(ln) <= 40]
    result = {}
    for section, pattern in SECTION_PATTERNS.items():
        rx = re.compile(rf"^[^a-zA-Z]*{pattern}\b", re.IGNORECASE)
        result[section] = any(rx.search(h) for h in headings)
    return result


def _content_lines(text: str) -> list[str]:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    bullets = [BULLET_PREFIX.sub("", ln) for ln in lines if BULLET_PREFIX.match(ln)]
    if len(bullets) >= 3:
        return bullets
    # No bullet characters (common with PDF exports): use sentence-like lines instead.
    return [ln for ln in lines if 6 <= len(ln.split()) <= 45]


def _grade(score: int) -> str:
    if score >= 85:
        return "A"
    if score >= 70:
        return "B"
    if score >= 55:
        return "C"
    return "D"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def analyze(resume_text: str, job_description: str | None = None) -> Analysis:
    job_description = (job_description or "").strip() or None
    suggestions: list[str] = []
    parts: list[ScorePart] = []

    # --- Contact info (10) -------------------------------------------------
    email = EMAIL.search(resume_text)
    phone = PHONE.search(resume_text)
    linkedin = LINKEDIN.search(resume_text)
    github = GITHUB.search(resume_text)
    contact = {
        "email": email.group(0) if email else None,
        "phone": phone.group(0).strip() if phone else None,
        "linkedin": linkedin.group(0) if linkedin else None,
        "github": github.group(0) if github else None,
    }
    contact_score = 3 * bool(email) + 3 * bool(phone) + 2 * bool(linkedin) + 2 * bool(github)
    contact_notes = [f"Missing {k}" for k, v in contact.items() if not v]
    parts.append(ScorePart("Contact info", contact_score, 10, contact_notes))
    if not email or not phone:
        suggestions.append("Put your email and phone number at the top so recruiters can reach you.")
    if not github:
        suggestions.append("Add your GitHub profile link. It's the fastest way to show real code.")
    if not linkedin:
        suggestions.append("Add your LinkedIn URL to the header.")

    # --- Sections (15) -----------------------------------------------------
    sections = detect_sections(resume_text)
    required_found = sum(sections[s] for s in REQUIRED_SECTIONS)
    section_score = 12 * required_found / len(REQUIRED_SECTIONS)
    section_score += 1.5 * sections["Summary"] + 1.5 * sections["Certifications & Achievements"]
    missing_sections = [s for s in REQUIRED_SECTIONS if not sections[s]]
    parts.append(
        ScorePart("Sections", round(section_score, 1), 15, [f"No '{s}' heading found" for s in missing_sections])
    )
    for s in missing_sections:
        suggestions.append(f"Add a clear '{s}' heading. ATS software looks for standard section names.")

    # --- Impact: action verbs + numbers (20) --------------------------------
    lines = _content_lines(resume_text)
    n_lines = max(len(lines), 1)
    action_lines = sum(1 for ln in lines if ln.split() and ln.split()[0].lower().strip(",.:") in ACTION_VERBS)
    quantified_lines = sum(1 for ln in lines if QUANTIFIED.search(ln))
    action_ratio = action_lines / n_lines
    quant_ratio = quantified_lines / n_lines
    # Full marks at 60% of bullets starting with a verb and 40% containing a number.
    impact_score = 10 * min(action_ratio / 0.6, 1) + 10 * min(quant_ratio / 0.4, 1)
    impact_notes = [
        f"{action_lines}/{len(lines)} bullet points start with an action verb",
        f"{quantified_lines}/{len(lines)} bullet points include a number or metric",
    ]
    parts.append(ScorePart("Impact", round(impact_score, 1), 20, impact_notes))
    if action_ratio < 0.6:
        suggestions.append(
            "Start more bullet points with strong action verbs (Built, Designed, Reduced, Led) instead of descriptions."
        )
    if quant_ratio < 0.4:
        suggestions.append(
            "Add numbers to show impact: users served, % faster, time saved, accuracy, team size."
        )

    # --- Length (10) ---------------------------------------------------------
    words = len(resume_text.split())
    if 350 <= words <= 900:
        length_score, length_note = 10, f"{words} words, a good length"
    elif 250 <= words < 350 or 900 < words <= 1200:
        length_score, length_note = 6, f"{words} words, slightly {'short' if words < 350 else 'long'}"
    else:
        length_score, length_note = 2, f"{words} words, too {'short' if words < 250 else 'long'}"
    parts.append(ScorePart("Length", length_score, 10, [length_note]))
    if words < 350:
        suggestions.append("Your resume is thin. Add project details, tech used and outcomes.")
    elif words > 900:
        suggestions.append("Trim to one page (about 400 to 800 words) for internship and entry-level roles.")

    # --- Language (10) -------------------------------------------------------
    lower = resume_text.lower()
    weak = {p: len(re.findall(rf"\b{re.escape(p)}\b", lower)) for p in WEAK_PHRASES}
    weak = {p: c for p, c in weak.items() if c}
    first_person = len(FIRST_PERSON.findall(resume_text))
    language_score = max(0, 10 - 1.5 * sum(weak.values()) - 0.5 * first_person)
    language_notes = []
    if weak:
        language_notes.append("Weak phrases: " + ", ".join(f"'{p}'" for p in weak))
    if first_person:
        language_notes.append(f"{first_person} first-person pronouns (I, me, my)")
    parts.append(ScorePart("Language", round(language_score, 1), 10, language_notes))
    if weak:
        suggestions.append(
            "Replace vague phrases like " + ", ".join(f"'{p}'" for p in list(weak)[:3])
            + " with what you actually did and the result."
        )
    if first_person > 2:
        suggestions.append("Drop 'I' and 'my'. Resume bullets read better in implied first person.")

    # --- Skills ------------------------------------------------------------
    skills_found = find_skills(resume_text)
    resume_skills = _flatten(skills_found)

    # --- Job description match (35) ----------------------------------------
    job_match = None
    if job_description:
        requirements = job_requirements(job_description)
        all_aliases = {a for group in SKILLS.values() for aliases in group.values() for a in aliases}
        jd_keywords = _keyword_candidates(job_description, all_aliases)
        matched_skills: list[str] = []
        missing_skills: list[str] = []
        met = 0
        for options in requirements:
            have = sorted(options & resume_skills)
            if have:
                met += 1
                matched_skills.extend(have)
            else:
                missing_skills.append(" or ".join(sorted(options)))
        matched_skills.sort()
        missing_skills.sort()
        matched_kw = [k for k in jd_keywords if re.search(rf"\b{re.escape(k)}", lower)]
        missing_kw = [k for k in jd_keywords if k not in matched_kw]

        skill_ratio = met / len(requirements) if requirements else 1.0
        kw_ratio = len(matched_kw) / len(jd_keywords) if jd_keywords else 1.0
        match = 0.7 * skill_ratio + 0.3 * kw_ratio
        job_match = JobMatch(round(match * 100), matched_skills, missing_skills, matched_kw, missing_kw)
        parts.append(
            ScorePart(
                "Job match",
                round(35 * match, 1),
                35,
                [f"{met}/{len(requirements)} skill requirements met"],
            )
        )
        if missing_skills:
            suggestions.insert(
                0,
                "The job asks for skills your resume doesn't mention: "
                + ", ".join(missing_skills[:8])
                + ". Add the ones you really have, in your skills and in project bullets.",
            )
    elif len(resume_skills) < 6:
        suggestions.append("List more of your technical skills in a dedicated Skills section.")

    # --- Total ---------------------------------------------------------------
    earned = sum(p.score for p in parts)
    possible = sum(p.max for p in parts)
    score = round(100 * earned / possible)

    stats = {
        "word_count": words,
        "bullet_points": len(lines),
        "action_verb_bullets": action_lines,
        "quantified_bullets": quantified_lines,
        "skills_count": len(resume_skills),
    }

    return Analysis(
        score=score,
        grade=_grade(score),
        breakdown=parts,
        skills_found=skills_found,
        job_match=job_match,
        contact=contact,
        sections=sections,
        stats=stats,
        weak_phrases=weak,
        suggestions=suggestions,
    )
