from __future__ import annotations

import re
from typing import Any


_NUMERIC_HINT_RE = re.compile(r"\b\d+(?:[.,]\d+)?\b|%|\$|x\b", re.IGNORECASE)


def _as_str(value: Any) -> str:
    return str(value or "").strip()


def _non_empty(value: Any) -> bool:
    return bool(_as_str(value))


def _count_numeric_highlights(experience: list[dict[str, Any]]) -> int:
    count = 0
    for role in experience:
        for h in (role.get("highlights") or []):
            if isinstance(h, str) and _NUMERIC_HINT_RE.search(h):
                count += 1
    return count


def _score_to_grade(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"


def evaluate_portfolio_insights(resume_json: dict[str, Any], user_meta: dict[str, Any]) -> dict[str, Any]:
    basics = resume_json.get("basics") or {}
    summary = _as_str(resume_json.get("summary"))
    summary_words = len(summary.split()) if summary else 0
    experience = resume_json.get("experience") or []
    education = resume_json.get("education") or []
    skills = resume_json.get("skills") or {}
    certifications = resume_json.get("certifications") or []
    recommendations = resume_json.get("recommendations") or []
    experiments = resume_json.get("experiments") or []
    slug = _as_str(user_meta.get("slug"))
    has_pdf = _non_empty(resume_json.get("pdfUrl"))

    score = 0
    sections = {
        "basics": 0,
        "summary": 0,
        "experience": 0,
        "skills": 0,
        "education": 0,
        "proof": 0,
        "publish": 0,
    }

    checklist_required: list[dict[str, str]] = []
    checklist_recommended: list[dict[str, str]] = []
    checklist_optional: list[dict[str, str]] = []

    strengths: list[str] = []
    risks: list[str] = []

    # Basics (20)
    basics_points = 0
    if _non_empty(basics.get("name")):
        basics_points += 5
    else:
        checklist_required.append({"id": "basics.name", "label": "Add your full name"})
    if _non_empty(basics.get("role")):
        basics_points += 5
    else:
        checklist_required.append({"id": "basics.role", "label": "Add a clear professional title"})
    if _non_empty(basics.get("email")):
        basics_points += 4
    else:
        checklist_required.append({"id": "basics.email", "label": "Add an email contact"})
    if _non_empty(basics.get("location")):
        basics_points += 3
    else:
        checklist_recommended.append({"id": "basics.location", "label": "Add your location"})
    if _non_empty(basics.get("linkedin")) or _non_empty(basics.get("github")):
        basics_points += 3
    else:
        checklist_recommended.append({"id": "basics.links", "label": "Add LinkedIn or GitHub profile links"})
    sections["basics"] = basics_points
    score += basics_points

    # Summary (15)
    summary_points = 0
    if summary_words >= 30:
        summary_points = 15
        strengths.append("Strong summary coverage")
    elif summary_words >= 15:
        summary_points = 10
        checklist_recommended.append({"id": "summary", "label": "Expand summary with scope and impact"})
    elif summary_words > 0:
        summary_points = 5
        checklist_required.append({"id": "summary", "label": "Improve summary to at least 30 words"})
    else:
        checklist_required.append({"id": "summary", "label": "Add a professional summary"})
    sections["summary"] = summary_points
    score += summary_points

    # Experience (25)
    exp_points = 0
    if experience:
        exp_points += min(10, 5 * len(experience))
        complete_roles = 0
        for idx, role in enumerate(experience):
            has_title = _non_empty(role.get("title"))
            has_company = _non_empty(role.get("company"))
            has_dates = _non_empty(role.get("start")) and _non_empty(role.get("end"))
            highlights = [h for h in (role.get("highlights") or []) if _non_empty(h)]

            if has_title and has_company:
                complete_roles += 1
            if not has_title:
                checklist_required.append({"id": f"experience.{idx}.title", "label": f"Add title for role #{idx + 1}"})
            if not has_company:
                checklist_required.append({"id": f"experience.{idx}.company", "label": f"Add company for role #{idx + 1}"})
            if not has_dates:
                checklist_recommended.append({"id": f"experience.{idx}.dates", "label": f"Add start/end dates for role #{idx + 1}"})
            if not highlights:
                checklist_required.append({"id": f"experience.{idx}.highlights", "label": f"Add highlights for role #{idx + 1}"})

        exp_points += min(8, complete_roles * 2)
        numeric_highlights = _count_numeric_highlights(experience)
        if numeric_highlights > 0:
            exp_points += min(7, numeric_highlights)
            strengths.append("Includes quantified achievements")
        else:
            checklist_recommended.append({"id": "experience.metrics", "label": "Add measurable outcomes to experience highlights"})
            risks.append("No quantified impact in experience highlights")
    else:
        checklist_required.append({"id": "experience", "label": "Add at least one work experience entry"})
        risks.append("No work experience listed")

    sections["experience"] = exp_points
    score += exp_points

    # Skills (10)
    skill_points = 0
    if isinstance(skills, dict):
        groups = [k for k, v in skills.items() if _non_empty(k) and isinstance(v, list) and v]
        total_skills = sum(len(skills[g]) for g in groups)
        if len(groups) >= 3:
            skill_points += 6
        elif len(groups) >= 1:
            skill_points += 3
            checklist_recommended.append({"id": "skills.groups", "label": "Add more skill groups (target 3+)"})
        else:
            checklist_required.append({"id": "skills", "label": "Add at least one skill group"})

        if total_skills >= 10:
            skill_points += 4
        elif total_skills >= 5:
            skill_points += 2
            checklist_recommended.append({"id": "skills.depth", "label": "Add more depth to your skill list"})
        elif total_skills > 0:
            skill_points += 1
            checklist_recommended.append({"id": "skills.depth", "label": "Expand your skills with core tools and technologies"})
    sections["skills"] = skill_points
    score += skill_points

    # Education/certifications (10)
    edu_points = 0
    if education:
        edu_points += 7
    else:
        checklist_recommended.append({"id": "education", "label": "Add education background"})
    if certifications:
        edu_points += 3
    else:
        checklist_optional.append({"id": "certifications", "label": "Add certifications (optional boost)"})
    sections["education"] = edu_points
    score += edu_points

    # Proof/differentiation (15)
    proof_points = 0
    if recommendations:
        proof_points += 7
        strengths.append("Has social proof via recommendations")
    else:
        checklist_recommended.append({"id": "recommendations", "label": "Add at least one recommendation/testimonial"})
    if experiments:
        proof_points += 8
        strengths.append("Has project/experiment showcase")
    else:
        checklist_recommended.append({"id": "experiments", "label": "Add at least one project/experiment"})
    sections["proof"] = proof_points
    score += proof_points

    # Publish readiness (5)
    publish_points = 0
    if slug:
        publish_points += 3
    else:
        checklist_required.append({"id": "publish.slug", "label": "Set a public username (slug)"})
    if has_pdf:
        publish_points += 2
    else:
        checklist_optional.append({"id": "publish.pdf", "label": "Upload a PDF for recruiter download"})
    sections["publish"] = publish_points
    score += publish_points

    next_actions = [*checklist_required, *checklist_recommended][:5]

    return {
        "score": int(max(0, min(100, score))),
        "grade": _score_to_grade(score),
        "sections": sections,
        "checklist": {
            "required": checklist_required,
            "recommended": checklist_recommended,
            "optional": checklist_optional,
        },
        "strengths": strengths,
        "risks": risks,
        "next_best_actions": next_actions,
    }
