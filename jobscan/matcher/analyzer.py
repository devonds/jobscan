"""Claude-based resume-to-job matching and demand analysis."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from anthropic import Anthropic

if TYPE_CHECKING:
    from jobscan.models.slack import SlackJobPosting


@dataclass
class MatchResult:
    """Result of matching a resume against a job posting."""

    score: float  # 0-100
    strengths: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    reasoning: str = ""


@dataclass
class DemandAnalysis:
    """Analysis of skill demand across job postings."""

    top_skills: list[tuple[str, int]] = field(default_factory=list)  # (skill, count)
    top_companies: list[tuple[str, int]] = field(default_factory=list)
    salary_range: tuple[int, int] | None = None
    common_requirements: list[str] = field(default_factory=list)
    work_mode_breakdown: dict[str, int] = field(default_factory=dict)
    employment_type_breakdown: dict[str, int] = field(default_factory=dict)


MATCH_SYSTEM_PROMPT = """\
You are a job matching expert. Your task is to evaluate how well a candidate's \
resume matches a job posting.

Analyze the resume against the job requirements and provide:
1. A match score from 0-100 (100 = perfect match)
2. List of strengths (qualifications that match the job)
3. List of gaps (missing requirements)
4. Brief reasoning for the score

Return a JSON object with:
- score: integer 0-100
- strengths: array of strings (3-5 items)
- gaps: array of strings (missing skills/requirements)
- reasoning: string (2-3 sentences explaining the score)

Scoring guidelines:
- 90-100: Exceptional match, meets/exceeds all requirements
- 75-89: Strong match, meets most requirements
- 60-74: Good match, meets core requirements with some gaps
- 40-59: Partial match, significant gaps but relevant experience
- 20-39: Weak match, some transferable skills
- 0-19: Poor match, few relevant qualifications"""


DEMAND_SYSTEM_PROMPT = """\
You are a job market analyst. Analyze a collection of job postings to identify \
trends in skill demand.

For each analysis, provide:
1. Top skills and technologies mentioned (ranked by frequency)
2. Common requirements and qualifications
3. Salary trends if available
4. Work mode preferences (remote/hybrid/onsite)
5. Employment type breakdown (full-time/contract/etc)

Return a JSON object with:
- top_skills: array of [skill, count] pairs, sorted by count descending
- common_requirements: array of common qualifications/requirements
- insights: array of 3-5 key observations about the job market"""


class ResumeAnalyzer:
    """Analyze resume fit against job postings using Claude."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-5-20250929",
    ) -> None:
        self.client = Anthropic(api_key=api_key)
        self.model = model

    def score_match(
        self,
        job: SlackJobPosting,
        resume: str,
    ) -> MatchResult:
        """Score how well a resume matches a job posting."""
        # Build job description from available data
        job_text = self._build_job_description(job)

        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=MATCH_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"## Job Posting\n\n{job_text}\n\n"
                        f"## Resume\n\n{resume}\n\n"
                        "Analyze the match between this resume and job posting."
                    ),
                }
            ],
        )

        content = response.content[0].text
        parsed = self._extract_json(content)

        return MatchResult(
            score=float(parsed.get("score", 0)),
            strengths=parsed.get("strengths", []),
            gaps=parsed.get("gaps", []),
            reasoning=parsed.get("reasoning", ""),
        )

    def find_best_matches(
        self,
        jobs: list[SlackJobPosting],
        resume: str,
        min_score: float = 50.0,
        limit: int = 10,
        on_progress: callable | None = None,
    ) -> list[tuple[SlackJobPosting, MatchResult]]:
        """Find and rank the best matching jobs for a resume."""
        results = []

        for i, job in enumerate(jobs):
            if on_progress:
                on_progress(i + 1, len(jobs))

            try:
                result = self.score_match(job, resume)
                if result.score >= min_score:
                    results.append((job, result))
            except Exception:
                continue

        # Sort by score descending
        results.sort(key=lambda x: x[1].score, reverse=True)
        return results[:limit]

    def analyze_demand(
        self,
        jobs: list[SlackJobPosting],
    ) -> DemandAnalysis:
        """Analyze skill demand across multiple job postings."""
        if not jobs:
            return DemandAnalysis()

        # Aggregate basic stats locally (faster than AI for simple counts)
        skill_counts: dict[str, int] = {}
        company_counts: dict[str, int] = {}
        work_modes: dict[str, int] = {}
        employment_types: dict[str, int] = {}
        salaries: list[int] = []

        for job in jobs:
            # Count skills
            for skill in job.skills:
                skill_lower = skill.lower()
                skill_counts[skill_lower] = skill_counts.get(skill_lower, 0) + 1

            # Count companies
            if job.company:
                company_counts[job.company] = company_counts.get(job.company, 0) + 1

            # Count work modes
            if job.work_mode:
                work_modes[job.work_mode] = work_modes.get(job.work_mode, 0) + 1

            # Count employment types
            if job.employment_type:
                employment_types[job.employment_type] = (
                    employment_types.get(job.employment_type, 0) + 1
                )

            # Collect salaries
            if job.salary_min:
                salaries.append(job.salary_min)
            if job.salary_max:
                salaries.append(job.salary_max)

        # Sort and limit results
        top_skills = sorted(skill_counts.items(), key=lambda x: x[1], reverse=True)[:20]
        top_companies = sorted(company_counts.items(), key=lambda x: x[1], reverse=True)[
            :10
        ]

        salary_range = None
        if salaries:
            salary_range = (min(salaries), max(salaries))

        # Use Claude to extract common requirements and insights
        common_requirements = self._analyze_requirements(jobs)

        return DemandAnalysis(
            top_skills=top_skills,
            top_companies=top_companies,
            salary_range=salary_range,
            common_requirements=common_requirements,
            work_mode_breakdown=work_modes,
            employment_type_breakdown=employment_types,
        )

    def _analyze_requirements(self, jobs: list[SlackJobPosting]) -> list[str]:
        """Use Claude to identify common requirements across jobs."""
        # Sample jobs if there are too many
        sample = jobs[:20] if len(jobs) > 20 else jobs

        # Build job summaries
        summaries = []
        for job in sample:
            summary = f"- {job.position or 'Unknown'} at {job.company or 'Unknown'}"
            if job.skills:
                summary += f": {', '.join(job.skills[:5])}"
            summaries.append(summary)

        job_list = "\n".join(summaries)

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=512,
                system=(
                    "Extract 5-8 common requirements/qualifications from these "
                    "job postings. Return a JSON array of strings."
                ),
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"Job postings:\n{job_list}\n\n"
                            "What are the most common requirements across these roles?"
                        ),
                    }
                ],
            )

            content = response.content[0].text
            # Try to extract JSON array
            match = re.search(r"\[[\s\S]*\]", content)
            if match:
                return json.loads(match.group())

        except Exception:
            pass

        return []

    def _build_job_description(self, job: SlackJobPosting) -> str:
        """Build a text description of a job for matching."""
        parts = []

        if job.company:
            parts.append(f"Company: {job.company}")
        if job.position:
            parts.append(f"Position: {job.position}")
        if job.location:
            parts.append(f"Location: {job.location}")
        if job.work_mode:
            parts.append(f"Work Mode: {job.work_mode}")
        if job.employment_type:
            parts.append(f"Type: {job.employment_type}")
        if job.salary_display():
            parts.append(f"Salary: {job.salary_display()}")
        if job.skills:
            parts.append(f"Skills: {', '.join(job.skills)}")

        # Add description
        if job.scraped_description:
            parts.append(f"\nDescription:\n{job.scraped_description}")
        elif job.parsed_description:
            parts.append(f"\nDescription:\n{job.parsed_description}")
        elif job.raw_message:
            parts.append(f"\nOriginal Post:\n{job.raw_message}")

        return "\n".join(parts)

    def _extract_json(self, text: str) -> dict:
        """Extract JSON from Claude's response."""
        json_match = re.search(r"\{[\s\S]*\}", text)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {}
