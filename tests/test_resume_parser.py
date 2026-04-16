import json
import unittest
from pathlib import Path

from app.services.resume_parser import parse_resume


FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


class ResumeParserFixtureTests(unittest.TestCase):
    def _load(self, name: str) -> tuple[dict, dict]:
        sample_path = FIXTURES_DIR / f"{name}.txt"
        expected_path = FIXTURES_DIR / f"{name}.expected.json"

        sample = sample_path.read_text(encoding="utf-8")
        expected = json.loads(expected_path.read_text(encoding="utf-8"))
        return parse_resume(sample), expected

    def _assert_basics(self, actual: dict, expected: dict) -> None:
        basics = actual.get("basics", {})
        for key in ["name", "role", "email", "phone"]:
            self.assertEqual(basics.get(key), expected["basics"][key], f"Mismatch for basics.{key}")

    def _assert_counts(self, actual: dict, expected: dict) -> None:
        self.assertEqual(len(actual.get("experience", [])), expected["counts"]["experience"])
        self.assertEqual(len(actual.get("education", [])), expected["counts"]["education"])
        self.assertEqual(len(actual.get("certifications", [])), expected["counts"]["certifications"])

    def _assert_min_skill_groups(self, actual: dict, expected: dict) -> None:
        self.assertGreaterEqual(len(actual.get("skills", {}).keys()), expected["min_skill_groups"])

    def test_engineering_fixture(self):
        actual, expected = self._load("sample-01-engineering")
        self._assert_basics(actual, expected)
        self._assert_counts(actual, expected)
        self._assert_min_skill_groups(actual, expected)

    def test_product_fixture(self):
        actual, expected = self._load("sample-02-product")
        self._assert_basics(actual, expected)
        self._assert_counts(actual, expected)
        self._assert_min_skill_groups(actual, expected)

    def test_data_science_fixture(self):
        actual, expected = self._load("sample-03-data-science")
        self._assert_basics(actual, expected)
        self._assert_counts(actual, expected)
        self._assert_min_skill_groups(actual, expected)

    def test_compact_format_fixture(self):
        actual, expected = self._load("sample-04-compact-format")
        self._assert_basics(actual, expected)
        self._assert_counts(actual, expected)
        self._assert_min_skill_groups(actual, expected)

    def test_early_career_fixture(self):
        actual, expected = self._load("sample-05-early-career")
        self._assert_basics(actual, expected)
        self._assert_counts(actual, expected)
        self._assert_min_skill_groups(actual, expected)

    def test_engineering_experience_fields(self):
        actual, _ = self._load("sample-01-engineering")
        exp = actual.get("experience", [])
        self.assertTrue(len(exp) > 0, "Expected at least one experience entry")
        first = exp[0]
        self.assertIn("title", first, "Experience entry should have title")
        self.assertIn("company", first, "Experience entry should have company")

    def test_data_science_skills_content(self):
        actual, _ = self._load("sample-03-data-science")
        skills = actual.get("skills", {})
        self.assertTrue(len(skills) > 0, "Expected at least one skill group")
        all_values = " ".join(str(v) for v in skills.values()).lower()
        # Daniel Kim's resume has PyTorch, scikit-learn — at least one should appear
        self.assertTrue(
            any(s in all_values for s in ["pytorch", "scikit", "python", "spark"]),
            f"Expected ML skills in parsed output, got: {all_values}",
        )

    def test_early_career_basics_not_empty(self):
        actual, _ = self._load("sample-05-early-career")
        basics = actual.get("basics", {})
        self.assertTrue(basics.get("name"), "Name should not be empty for early career resume")
        self.assertTrue(basics.get("email"), "Email should not be empty for early career resume")

    def test_parser_handles_missing_sections_gracefully(self):
        """Parser should not crash on minimal input."""
        result = parse_resume("John Doe\njohn@example.com\n")
        self.assertIsInstance(result, dict)
        self.assertIn("basics", result)
        self.assertIsInstance(result.get("experience", []), list)
        self.assertIsInstance(result.get("education", []), list)
        self.assertIsInstance(result.get("skills", {}), dict)

    def test_parser_returns_empty_lists_not_none(self):
        """All list fields should be lists, not None."""
        result = parse_resume("Sarah Smith\nsarah@test.com\n")
        for field in ["experience", "education", "certifications"]:
            value = result.get(field)
            self.assertIsNotNone(value, f"{field} should not be None")
            self.assertIsInstance(value, list, f"{field} should be a list")

    def test_parser_extracts_recommendations_and_experiments(self):
        text = """
Mia Murphy
Engineering Delivery Partner
mia@example.com

Summary
Experienced engineering leader.

Recommendations
LinkedIn Recommendation
Product Partner - Engineering Lead
Delivers clear strategy across stakeholders.
LinkedIn Recommendation - https://www.linkedin.com/in/miamurphy/details/recommendations/

Experiments
Velocity Dashboard (full-stack)
Backend: Docker, Terraform, FastAPI, Kubernetes
Frontend: React, GraphQL, Vanilla JS, HTML
- Built a scalable backend with modern cloud-native tooling.
- Created a polished frontend experience with responsive UI patterns.
Links: Backend Repo (https://github.com/miamurphy/velocity-dashboard-backend), Live Demo (https://velocity-dashboard.example.com)
""".strip()

        result = parse_resume(text)
        recommendations = result.get("recommendations", [])
        experiments = result.get("experiments", [])

        self.assertGreaterEqual(len(recommendations), 1)
        self.assertEqual(recommendations[0].get("name"), "Product Partner")
        self.assertTrue(recommendations[0].get("linkedinUrl", "").startswith("https://"))

        self.assertGreaterEqual(len(experiments), 1)
        self.assertEqual(experiments[0].get("name"), "Velocity Dashboard")
        self.assertGreaterEqual(len(experiments[0].get("backend", {}).get("tech", [])), 1)

    def test_parser_handles_variant_section_headers_without_misrouting(self):
        text = """
Mia Murphy
Engineering Delivery Partner
mia@example.com

CERTIFICATIONS
AWS Certified Developer

Recommendations & Testimonials
LinkedIn Recommendation
Product Partner - Engineering Lead
Excellent stakeholder communication and delivery discipline.
LinkedIn Recommendation - https://www.linkedin.com/in/miamurphy/details/recommendations/

Projects / Experiments
Velocity Dashboard (full-stack)
Backend: FastAPI, Docker
Frontend: React
- Built a scalable backend and clean frontend UX.
""".strip()

        result = parse_resume(text)
        certs = result.get("certifications", [])
        recs = result.get("recommendations", [])
        experiments = result.get("experiments", [])

        self.assertEqual(certs, ["AWS Certified Developer"])
        self.assertGreaterEqual(len(recs), 1)
        self.assertEqual(recs[0].get("name"), "Product Partner")
        self.assertGreaterEqual(len(experiments), 1)
        self.assertEqual(experiments[0].get("name"), "Velocity Dashboard")


if __name__ == "__main__":
    unittest.main()
