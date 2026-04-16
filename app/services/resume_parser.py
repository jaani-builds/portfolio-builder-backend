from __future__ import annotations

"""
Rule-based resume text parser.

Parses plain-text resumes into the JSON schema used by the
jaani-builds.github.io portfolio template.
"""

import re
from typing import Any

# ── Date / contact patterns ─────────────────────────────────────────────────

_MONTH_ABBR = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
_MONTH_FULL = (
    r"(?:January|February|March|April|May|June|July|August"
    r"|September|October|November|December)"
)
_MONTH = f"(?:{_MONTH_ABBR}|{_MONTH_FULL})"
_YEAR = r"\d{4}"
_DATE = f"(?:{_MONTH}\\.?\\s+{_YEAR}|{_YEAR})"
_END_TOKEN = r"(?:Present|Current|Now|Ongoing)"
_DATE_RANGE_RE = re.compile(
    rf"({_DATE})\s*[-–—~]\s*({_DATE}|{_END_TOKEN})",
    re.IGNORECASE,
)
_YEAR_ONLY_RE = re.compile(r"\b(\d{4})\b")

_EMAIL_RE = re.compile(r"[\w.\-+]+@[\w\-]+\.[\w.]+")
_PHONE_RE = re.compile(r"\+?[\d][\d\s.()\-]{6,}")
_LINKEDIN_RE = re.compile(r"(?:https?://)?(?:www\.)?linkedin\.com/in/[\w\-]+", re.IGNORECASE)
_GITHUB_RE = re.compile(r"(?:https?://)?(?:www\.)?github\.com/[\w\-]+", re.IGNORECASE)

_BULLET_RE = re.compile(r"^[\s]*[•\-\*→>◦▪]\s+")

# ── Section keyword mapping ──────────────────────────────────────────────────

_SECTION_KEYWORDS: dict[str, list[str]] = {
    "summary": [
        "summary", "profile", "objective", "about", "about me",
        "professional summary", "career summary", "career objective",
        "professional profile",
    ],
    "experience": [
        "experience", "work experience", "employment", "professional experience",
        "career history", "employment history", "work history", "positions held",
    ],
    "education": [
        "education", "academic", "qualifications", "academic background",
        "educational background", "degrees", "academic qualifications",
    ],
    "skills": [
        "skills", "technical skills", "core competencies", "competencies",
        "expertise", "technologies", "tech stack", "key skills",
    ],
    "certifications": [
        "certifications", "certificates", "credentials", "licenses",
        "professional development", "accreditations",
    ],
    "recommendations": [
        "recommendations", "recommendation", "references", "reference", "testimonials", "testimonial",
    ],
    "experiments": [
        "experiments", "experiment", "projects", "project", "personal projects", "side projects", "portfolio",
        "open source",
    ],
    "projects": [
        "projects", "personal projects", "side projects", "portfolio",
        "experiments", "open source",
    ],
}

_EMPLOYMENT_TYPES = [
    "Full-time", "Part-time", "Contract", "Freelance",
    "Internship", "Temporary", "Volunteer", "Consultant",
]

_MONTH_NORMALISE = {
    "january": "Jan", "february": "Feb", "march": "Mar", "april": "Apr",
    "may": "May", "june": "Jun", "july": "Jul", "august": "Aug",
    "september": "Sep", "october": "Oct", "november": "Nov", "december": "Dec",
}


# ── Helpers ──────────────────────────────────────────────────────────────────


def _normalise_date(raw: str) -> str:
    for full, abbr in _MONTH_NORMALISE.items():
        raw = re.sub(full, abbr, raw, flags=re.IGNORECASE)
    # Capitalise "Present"
    raw = re.sub(r"\b(current|now|ongoing)\b", "Present", raw, flags=re.IGNORECASE)
    return raw.strip()


def _extract_date_range(text: str) -> tuple[str, str]:
    m = _DATE_RANGE_RE.search(text)
    if m:
        return _normalise_date(m.group(1)), _normalise_date(m.group(2))
    return "", ""


def _extract_year_range(text: str) -> tuple[str, str]:
    years = _YEAR_ONLY_RE.findall(text)
    if len(years) >= 2:
        return years[0], years[1]
    if len(years) == 1:
        return "", years[0]
    return "", ""


def _extract_email(text: str) -> str:
    m = _EMAIL_RE.search(text)
    return m.group(0) if m else ""


def _extract_phone(text: str) -> str:
    for m in _PHONE_RE.finditer(text):
        digits = re.sub(r"\D", "", m.group(0))
        if len(digits) >= 7:
            return m.group(0).strip()
    return ""


def _extract_url(pattern: re.Pattern, text: str) -> str:
    m = pattern.search(text)
    if not m:
        return ""
    url = m.group(0)
    return url if url.startswith("http") else f"https://{url}"


def _is_bullet(line: str) -> bool:
    return bool(_BULLET_RE.match(line))


def _clean_bullet(line: str) -> str:
    return _BULLET_RE.sub("", line).strip()


def _is_contact_line(line: str) -> bool:
    return bool(
        _EMAIL_RE.search(line)
        or _LINKEDIN_RE.search(line)
        or _GITHUB_RE.search(line)
    )


def _title_case_if_allcaps(s: str) -> str:
    """Title-case a string that is fully uppercase (e.g. PDF-extracted names)."""
    stripped = s.strip()
    letters = re.sub(r"[^A-Za-z]", "", stripped)
    if letters and stripped == stripped.upper():
        return stripped.title()
    return stripped


def _looks_like_skill_category(line: str) -> bool:
    """Return True if this line looks like a skills section category header."""
    s = line.strip()
    if not s or _is_bullet(s) or "," in s or ":" in s or len(s) > 60:
        return False
    # No digits, not a sentence (no period mid-string)
    if re.search(r"\d", s) or "." in s:
        return False
    # Either title-case / ALL-CAPS / single word
    return True


def _normalise_header_text(line: str) -> str:
    """Normalise a potential section header for robust keyword matching."""
    s = line.strip().lower()
    s = s.rstrip(":")
    s = s.replace("&", " ").replace("/", " ")
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _detect_section(line: str) -> str | None:
    raw = line.strip()
    if not raw:
        return None

    # Avoid treating normal sentence lines as headers.
    if _is_bullet(raw) or len(raw) > 80 or "." in raw:
        return None

    stripped = _normalise_header_text(raw)
    if not stripped:
        return None

    # Header-ish guardrails: short headline-like lines, or explicit section punctuation/style.
    header_like = (
        raw.endswith(":")
        or raw == raw.upper()
        or len(stripped.split()) <= 6
    )
    if not header_like:
        return None

    for section, keywords in _SECTION_KEYWORDS.items():
        if stripped in keywords:
            return section
        for kw in keywords:
            # Support variants like "Recommendations & Testimonials" or "Projects / Experiments"
            if re.search(rf"(^|\s){re.escape(kw)}($|\s)", stripped):
                return section
    return None


def _is_section_header(line: str) -> bool:
    if _detect_section(line) is not None:
        return True
    stripped = line.strip().rstrip(":")
    # All-caps short words (e.g. "EXPERIENCE")
    return (
        stripped == stripped.upper()
        and stripped.isalpha()
        and 3 <= len(stripped) <= 40
    )


def _split_blocks(lines: list[str]) -> list[list[str]]:
    """Split a list of lines into blocks separated by blank lines."""
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if not line.strip():
            if current:
                blocks.append(current)
                current = []
        else:
            current.append(line)
    if current:
        blocks.append(current)
    return blocks


# ── Section parsers ──────────────────────────────────────────────────────────


def _parse_basics(header_lines: list[str]) -> dict[str, str]:
    all_text = " ".join(header_lines)
    basics: dict[str, str] = {
        "name": "",
        "role": "",
        "email": _extract_email(all_text),
        "phone": _extract_phone(all_text),
        "location": "",
        "linkedin": _extract_url(_LINKEDIN_RE, all_text),
        "github": _extract_url(_GITHUB_RE, all_text),
        "photoUrl": "",
    }

    contact_free: list[str] = [
        l.strip() for l in header_lines
        if l.strip()
        and not _is_contact_line(l)
        and not _PHONE_RE.search(l)
    ]

    if contact_free:
        basics["name"] = _title_case_if_allcaps(contact_free[0])
    if len(contact_free) >= 2:
        basics["role"] = contact_free[1]

    # Location: prefer "City, Country" pattern anywhere in header lines;
    # fall back to 3rd non-contact line.
    _loc_pat = re.compile(r"^[A-Z][a-zA-Z .'-]+,\s*[A-Z][a-zA-Z .'-]+$")
    for l in contact_free[2:]:
        if _loc_pat.match(l.strip()):
            basics["location"] = l.strip()
            break
    if not basics["location"] and len(contact_free) >= 3:
        basics["location"] = contact_free[2]

    # Handle pipe-separated single-line header: "Name | Role | Location"
    if len(contact_free) == 1 and "|" in contact_free[0]:
        parts = [p.strip() for p in contact_free[0].split("|") if p.strip()]
        if len(parts) >= 1:
            basics["name"] = _title_case_if_allcaps(parts[0])
        if len(parts) >= 2:
            basics["role"] = parts[1]
        if len(parts) >= 3:
            basics["location"] = parts[2]

    return basics


def _parse_experience_block(block: list[str]) -> dict[str, Any] | None:
    entry: dict[str, Any] = {
        "title": "", "company": "", "location": "",
        "employmentType": "", "start": "", "end": "", "highlights": [],
    }
    block_text = " ".join(block)

    # Date range
    start, end = _extract_date_range(block_text)
    entry["start"] = start
    entry["end"] = end

    # Employment type
    for etype in _EMPLOYMENT_TYPES:
        if etype.lower() in block_text.lower():
            entry["employmentType"] = etype
            break

    header_lines = [l for l in block if not _is_bullet(l) and l.strip()]
    bullets = [l for l in block if _is_bullet(l)]
    entry["highlights"] = [_clean_bullet(l) for l in bullets if _clean_bullet(l)]

    # First non-bullet line → title | company | location
    def _clean_header(line: str) -> str:
        """Strip date range and employment type hints from a header line."""
        s = _DATE_RANGE_RE.sub("", line)
        for etype in _EMPLOYMENT_TYPES:
            s = re.sub(re.escape(etype), "", s, flags=re.IGNORECASE)
        return s.strip(" ,-|")

    if header_lines:
        first_clean = _clean_header(header_lines[0])
        parts = re.split(r"\s*[|/]\s*|\s+at\s+|\s*,\s*", first_clean)
        parts = [p.strip() for p in parts if p.strip()]

        if len(parts) >= 2:
            # Same-line "Title | Company [| Location]" format
            entry["title"] = parts[0]
            entry["company"] = parts[1]
            if len(parts) >= 3:
                entry["location"] = parts[2]
        elif len(parts) == 1:
            # Title-only first line; look at subsequent header lines for company/location
            entry["title"] = parts[0]
            remaining = header_lines[1:]
            for i, hl in enumerate(remaining):
                cleaned = _clean_header(hl)
                if not cleaned:
                    continue
                sub_parts = re.split(r"\s*[|/,]\s*", cleaned)
                sub_parts = [p.strip() for p in sub_parts if p.strip()]
                if not entry["company"] and sub_parts:
                    entry["company"] = sub_parts[0]
                    if len(sub_parts) >= 2:
                        entry["location"] = sub_parts[1]
                elif not entry["location"] and sub_parts:
                    entry["location"] = sub_parts[0]
                if entry["company"] and entry["location"]:
                    break

    return entry if (entry["title"] or entry["company"]) else None


def _parse_experience(lines: list[str]) -> list[dict]:
    return [
        e for block in _split_blocks(lines)
        if (e := _parse_experience_block(block)) is not None
    ]


def _parse_education_block(block: list[str]) -> dict[str, str] | None:
    entry: dict[str, str] = {"degree": "", "school": "", "start": "", "end": ""}
    block_text = " ".join(block)

    start, end = _extract_date_range(block_text)
    if start:
        entry["start"] = start
        entry["end"] = end
    else:
        entry["start"], entry["end"] = _extract_year_range(block_text)

    header_lines = [
        l.strip() for l in block
        if l.strip() and not _is_bullet(l)
    ]
    if header_lines:
        first = header_lines[0]
        # Remove years from first line for cleaner parsing
        first_clean = _YEAR_ONLY_RE.sub("", first).strip(" -–—,|")
        parts = re.split(r"\s*[|/,]\s*|\s+at\s+", first_clean)
        parts = [p.strip() for p in parts if len(p.strip()) > 1]
        if len(parts) >= 2:
            entry["degree"] = parts[0]
            entry["school"] = parts[1]
        elif len(parts) == 1:
            entry["degree"] = parts[0]
            if len(header_lines) > 1:
                entry["school"] = _YEAR_ONLY_RE.sub("", header_lines[1]).strip(" -–—,|")

    return entry if (entry["degree"] or entry["school"]) else None


def _parse_education(lines: list[str]) -> list[dict]:
    entries: list[dict] = []
    blocks = _split_blocks(lines)

    for block in blocks:
        parsed = _parse_education_block(block)
        if parsed is not None:
            entries.append(parsed)

        # Some resumes list multiple education entries on separate lines
        # without blank lines; parse those lines as independent entries.
        if len(block) > 1:
            for line in block:
                stripped = line.strip()
                if not stripped or _is_bullet(stripped):
                    continue
                line_entry = _parse_education_block([stripped])
                if line_entry is None:
                    continue
                if not any(
                    e.get("degree") == line_entry.get("degree")
                    and e.get("school") == line_entry.get("school")
                    and e.get("start") == line_entry.get("start")
                    and e.get("end") == line_entry.get("end")
                    for e in entries
                ):
                    entries.append(line_entry)

    return entries


def _parse_skills(lines: list[str]) -> dict[str, list[str]]:
    skills: dict[str, list[str]] = {}
    default_cat = "Skills"
    current_cat = default_cat

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # "Category: skill1, skill2" format — highest confidence
        colon_m = re.match(r"^([^:]{2,50}):\s*(.+)$", stripped)
        if colon_m:
            current_cat = colon_m.group(1).strip()
            items = [s.strip() for s in re.split(r"[,;]+", colon_m.group(2)) if s.strip()]
            if items:
                skills.setdefault(current_cat, []).extend(items)
            continue

        # Bullet or comma-separated line → items for current category
        text = _clean_bullet(line) if _is_bullet(line) else stripped
        items = [s.strip() for s in re.split(r"[,;]+", text) if s.strip()]

        if len(items) > 1:
            # Multiple items → skill list for current category
            skills.setdefault(current_cat, []).extend(items)
        elif len(items) == 1:
            single = items[0]
            # A standalone line with no bullet, no commas, and short:
            # treat as a new category header (e.g. "Languages", "Frameworks")
            if not _is_bullet(line) and _looks_like_skill_category(single):
                current_cat = single
            else:
                skills.setdefault(current_cat, []).append(single)

    return skills


def _parse_certifications(lines: list[str]) -> list[str]:
    return [
        _clean_bullet(l) if _is_bullet(l) else l.strip()
        for l in lines
        if l.strip()
    ]


def _parse_recommendations(lines: list[str]) -> list[dict[str, str]]:
    recommendations: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    pending_source = ""

    for raw in lines:
        line = raw.strip()
        if not line:
            continue

        if line.lower() in {"recommendations", "references", "testimonials"}:
            continue

        if "recommendation" in line.lower() and "http" not in line.lower() and " - " not in line:
            pending_source = line
            if current and not current.get("source"):
                current["source"] = line
            continue

        url_match = re.search(r"https?://\S+", line)
        if url_match:
            url = url_match.group(0).rstrip(").,")
            source = pending_source
            if " - " in line:
                source = line.split(" - ", 1)[0].strip()
            if current:
                if source and not current.get("source"):
                    current["source"] = source
                current["linkedinUrl"] = url
            else:
                pending_source = source
            continue

        role_match = re.match(r"^(.+?)\s+-\s+(.+)$", line)
        if role_match and "http" not in line.lower():
            left = role_match.group(1).strip()
            right = role_match.group(2).strip()

            if "recommendation" in left.lower() and not current:
                pending_source = left
                continue

            if current and (current.get("name") or current.get("quote")):
                recommendations.append(current)

            current = {
                "name": left,
                "role": right,
                "quote": "",
                "source": pending_source or "Recommendation",
                "linkedinUrl": "",
            }
            continue

        if current:
            current["quote"] = f"{current.get('quote', '')} {line}".strip()

    if current and (current.get("name") or current.get("quote")):
        recommendations.append(current)

    return recommendations


def _parse_experiments(lines: list[str]) -> list[dict[str, Any]]:
    experiments: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    collecting_links = False

    def _new_experiment(name: str, exp_type: str) -> dict[str, Any]:
        return {
            "name": name,
            "type": exp_type,
            "backend": {"tech": [], "highlights": [], "links": []},
            "frontend": {"tech": [], "highlights": [], "links": []},
            "_bullets": [],
            "_links_text": "",
        }

    def _finalise(exp: dict[str, Any] | None) -> None:
        if not exp or not exp.get("name"):
            return

        bullets = exp.pop("_bullets", [])
        if bullets:
            if exp["backend"]["tech"] and exp["frontend"]["tech"] and len(bullets) >= 2:
                split_at = len(bullets) // 2
                exp["backend"]["highlights"] = bullets[:split_at]
                exp["frontend"]["highlights"] = bullets[split_at:]
            else:
                exp["backend"]["highlights"] = bullets

        links_text = exp.pop("_links_text", "")
        if links_text:
            for m in re.finditer(r"([^,()]+?)\s*\((https?://[^)\s]+)\)", links_text):
                label = m.group(1).strip()
                url = m.group(2).strip()
                link = {"label": label, "url": url}
                lower_label = label.lower()
                if "frontend" in lower_label or "live" in lower_label:
                    exp["frontend"]["links"].append(link)
                else:
                    exp["backend"]["links"].append(link)

        experiments.append(exp)

    for raw in lines:
        line = raw.strip()
        if not line:
            collecting_links = False
            continue

        if line.lower() in {"projects", "experiments"}:
            continue

        header_match = re.match(r"^(.+?)\s*\(([^()]+)\)$", line)
        if header_match and not line.lower().startswith(("backend:", "frontend:", "links:")):
            _finalise(current)
            current = _new_experiment(header_match.group(1).strip(), header_match.group(2).strip())
            collecting_links = False
            continue

        if not current:
            continue

        if line.lower().startswith("backend:"):
            collecting_links = False
            tech = line.split(":", 1)[1]
            current["backend"]["tech"] = [t.strip() for t in re.split(r"[,;]+", tech) if t.strip()]
            continue

        if line.lower().startswith("frontend:"):
            collecting_links = False
            tech = line.split(":", 1)[1]
            current["frontend"]["tech"] = [t.strip() for t in re.split(r"[,;]+", tech) if t.strip()]
            continue

        if _is_bullet(line):
            collecting_links = False
            cleaned = _clean_bullet(line)
            if cleaned:
                current["_bullets"].append(cleaned)
            continue

        if line.lower().startswith("links:"):
            collecting_links = True
            current["_links_text"] = f"{current.get('_links_text', '')} {line.split(':', 1)[1].strip()}".strip()
            continue

        if collecting_links:
            current["_links_text"] = f"{current.get('_links_text', '')} {line}".strip()

    _finalise(current)
    return experiments


# ── Public entry point ───────────────────────────────────────────────────────


def parse_resume(text: str) -> dict[str, Any]:
    """Convert plain-text resume into the portfolio JSON schema."""
    lines = text.splitlines()

    # Segment lines into named sections
    sections: dict[str, list[str]] = {"header": []}
    current = "header"
    for line in lines:
        detected = _detect_section(line)
        if detected or _is_section_header(line):
            # Only switch if we have a clean section-header match
            if detected:
                current = detected
                sections.setdefault(current, [])
                continue
        sections.setdefault(current, []).append(line)

    basics = _parse_basics(sections.get("header", []))

    summary_lines = [l.strip() for l in sections.get("summary", []) if l.strip()]
    summary = " ".join(summary_lines)

    experience = _parse_experience(sections.get("experience", []))
    education = _parse_education(sections.get("education", []))
    skills = _parse_skills(sections.get("skills", []))
    certifications = _parse_certifications(sections.get("certifications", []))
    recommendations = _parse_recommendations(sections.get("recommendations", []))
    experiments = _parse_experiments(sections.get("experiments", []) + sections.get("projects", []))

    return {
        "basics": basics,
        "meta": {
            "title": f"{basics['name']} | {basics['role']}".strip(" |"),
            "description": summary[:200] if summary else "",
        },
        "sectionLabels": {
            "about": "About me",
            "experience": "Experience",
            "education": "Education",
            "skills": "Skills",
            "certifications": "Certifications",
            "experiments": "Experiments",
            "recommendations": "Recommendations",
        },
        "publicUrl": "",
        "summary": summary,
        "pdfUrl": "",
        "experience": experience,
        "education": education,
        "recommendations": recommendations,
        "recommendationsWidget": {
            "enabled": False,
            "provider": "",
            "widgetId": "",
            "profileUrl": "",
        },
        "experiments": experiments,
        "skills": skills,
        "certifications": certifications,
    }
