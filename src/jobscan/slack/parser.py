"""Claude-based parser for extracting job data from Slack messages."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from anthropic import Anthropic

from jobscan.models.slack import ParsedJob, SlackMessage

if TYPE_CHECKING:
    pass


class ParserError(Exception):
    """Error during message parsing."""

    pass


SYSTEM_PROMPT = """\
You are a job posting parser. Your task is to analyze Slack messages and \
determine if they contain job postings. If they do, extract structured job info.

For each message, you should:
1. Determine if it's a job posting (is_job_posting: true/false)
2. If it is, extract available information

Return a JSON object with these fields:
- is_job_posting: boolean - true if this is a job posting, false otherwise
- company: string or null - the company name
- position: string or null - the job title/position
- location: string or null - the job location (city, state, country, or "Remote")
- salary_min: integer or null - minimum salary (annual, stated currency, no commas)
- salary_max: integer or null - maximum salary (annual, stated currency, no commas)
- salary_currency: string - "USD", "EUR", "GBP", etc. (default "USD")
- employment_type: string or null - "full_time", "contract", "part_time", etc.
- work_mode: string or null - one of: "remote", "hybrid", "onsite"
- skills: array of strings - technologies, tools, and skills mentioned
- job_urls: array of strings - URLs to job postings or application pages
- description_snippet: string or null - brief description (2-3 sentences max)
- confidence: number 0-1 - your confidence this is a job posting

Guidelines:
- Messages about hiring, recruiting, open positions are job postings
- Messages just discussing jobs, career advice, or articles are NOT job postings
- Extract URLs that look like job links (greenhouse, lever, workday, careers)
- If salary is given as hourly rate, multiply by 2080 for annual equivalent
- If salary is given as a range like "$150-180k", that's $150,000 to $180,000
- Be generous with skill extraction - languages, frameworks, tools, methodologies
- work_mode: "remote" = fully remote, "hybrid" = mix, "onsite" = office-only"""


class JobMessageParser:
    """Parse Slack messages to extract job posting information using Claude."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-5-20250929",
    ) -> None:
        self.client = Anthropic(api_key=api_key)
        self.model = model

    def parse_message(self, message: SlackMessage) -> ParsedJob | None:
        """Parse a Slack message, returning structured job data or None if not a job."""
        # Quick pre-filter: skip very short messages or obvious non-jobs
        if len(message.text) < 50:
            return None

        # Check for job-related keywords as a fast filter
        text_lower = message.text.lower()
        job_keywords = [
            "hiring",
            "job",
            "position",
            "role",
            "opportunity",
            "looking for",
            "we're seeking",
            "open role",
            "apply",
            "remote",
            "salary",
            "compensation",
            "engineer",
            "analyst",
            "manager",
            "developer",
        ]
        if not any(kw in text_lower for kw in job_keywords):
            return None

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                messages=[
                    {
                        "role": "user",
                        "content": (
                            "Parse this Slack message and extract job "
                            f"information if present:\n\n{message.text}"
                        ),
                    }
                ],
                system=SYSTEM_PROMPT,
            )

            # Extract JSON from response
            content = response.content[0].text
            parsed = self._extract_json(content)

            if not parsed.get("is_job_posting", False):
                return None

            return ParsedJob(
                is_job_posting=True,
                company=parsed.get("company"),
                position=parsed.get("position"),
                location=parsed.get("location"),
                salary_min=parsed.get("salary_min"),
                salary_max=parsed.get("salary_max"),
                salary_currency=parsed.get("salary_currency", "USD"),
                employment_type=parsed.get("employment_type"),
                work_mode=parsed.get("work_mode"),
                skills=parsed.get("skills", []),
                job_urls=parsed.get("job_urls", []) or self.extract_urls(message.text),
                description_snippet=parsed.get("description_snippet"),
                confidence=parsed.get("confidence", 0.5),
            )

        except Exception as e:
            raise ParserError(f"Failed to parse message: {e}") from e

    def extract_urls(self, text: str) -> list[str]:
        """Extract URLs from message text."""
        # Match URLs, including Slack's <url|display> format
        slack_url_pattern = r"<(https?://[^|>]+)(?:\|[^>]*)?>?"
        standard_url_pattern = r"https?://[^\s<>\"']+"

        urls = set()

        # Extract Slack-formatted URLs
        for match in re.finditer(slack_url_pattern, text):
            urls.add(match.group(1))

        # Extract standard URLs
        for match in re.finditer(standard_url_pattern, text):
            url = match.group(0).rstrip(".,;:!?)")
            urls.add(url)

        # Filter to likely job URLs
        job_url_patterns = [
            "greenhouse.io",
            "lever.co",
            "workday.com",
            "jobs.",
            "careers.",
            "apply",
            "job",
            "hire",
            "ashbyhq.com",
            "bamboohr.com",
            "smartrecruiters.com",
            "recruitee.com",
            "linkedin.com/jobs",
        ]

        return [
            url
            for url in urls
            if any(pattern in url.lower() for pattern in job_url_patterns)
            or "career" in url.lower()
        ]

    def _extract_json(self, text: str) -> dict:
        """Extract JSON from Claude's response."""
        # Try to find JSON in the response
        json_match = re.search(r"\{[\s\S]*\}", text)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        # If no valid JSON found, try the whole response
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            raise ParserError(f"Could not extract JSON from response: {text[:200]}")

    def parse_messages_batch(
        self,
        messages: list[SlackMessage],
        on_progress: callable | None = None,
    ) -> list[tuple[SlackMessage, ParsedJob]]:
        """Parse multiple messages, returning list of (message, parsed_job) tuples.

        Only returns messages that are job postings.
        """
        results = []
        for i, message in enumerate(messages):
            if on_progress:
                on_progress(i + 1, len(messages))

            try:
                parsed = self.parse_message(message)
                if parsed:
                    results.append((message, parsed))
            except ParserError:
                # Skip messages that fail to parse
                continue

        return results
