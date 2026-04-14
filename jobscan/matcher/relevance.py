"""Claude-based relevance assessment for job postings."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from anthropic import Anthropic

if TYPE_CHECKING:
    from jobscan.models.slack import SlackJobPosting


RELEVANCE_SYSTEM_PROMPT = """\
You are an AI job relevance assessor. Your task is to evaluate a job posting against \
a specific user's career preferences and determine if it is relevant.

USER PREFERENCES:
1. Location: The user is based in Petaluma, California. They can work in San Francisco (SF) for certain engagements or occasional on-site work. Many postings are for residents of other countries or specific US states - reject these if they strictly require residing outside CA without a remote option.
2. Remote: The user prefers remote work. No fully on-site work is accepted. Occasional travel is acceptable.
3. Position Type: Data Scientist, Analytics Engineer, or Data Science Manager roles.
   - REJECT: Data Engineering roles.
   - REJECT: Data Analyst roles, unless the posting specifies a high end of the salary range above $180k.
4. Engagement Type: The user is interested in both full-time (W2) and consulting (contract/freelance) engagements. You must label the type of engagement.

For each job posting, analyze the details and provide:
1. A boolean `is_relevant` (true if it matches the above criteria, false otherwise).
2. A string `engagement_type_label` (either "Full-Time", "Consulting", or "Unknown").
3. A short `relevance_reason` string explicitly describing why you rejected or accepted this job.

Return a JSON object with:
- is_relevant: boolean
- engagement_type_label: string
- relevance_reason: string

Guidelines:
- If a position is Data Analyst but mentions paying highly, it might be relevant. Otherwise, default to false.
- Be explicit in your reasoning. e.g., "Rejected because it requires residing in the UK." or "Accepted as it's a remote Analytics Engineering role."
"""

class RelevanceAssessor:
    """Assess job posting relevance using Claude."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-5-20250929",
    ) -> None:
        self.client = Anthropic(api_key=api_key)
        self.model = model

    def assess(self, job: SlackJobPosting) -> None:
        """Score the relevance of a job posting and update its fields."""
        job_text = self._build_job_description(job)

        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=RELEVANCE_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"## Job Posting\n\n{job_text}\n\n"
                        "Assess the relevance of this job posting based on the system prompt criteria."
                    ),
                }
            ],
            temperature=0.0,
        )

        content = response.content[0].text
        parsed = self._extract_json(content)

        job.is_relevant = parsed.get("is_relevant", False)
        job.engagement_type_label = parsed.get("engagement_type_label", "Unknown")
        job.relevance_reason = parsed.get("relevance_reason", "Failed to parse reasoning.")

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
