"""Pydantic models for Slack data."""

from datetime import datetime

from pydantic import BaseModel, Field


class SlackMessage(BaseModel):
    """Raw Slack message data."""

    ts: str  # Slack timestamp (unique ID)
    channel_id: str
    user_id: str | None = None
    text: str
    thread_ts: str | None = None  # If in a thread


class ParsedJob(BaseModel):
    """Job data extracted from a Slack message by Claude."""

    is_job_posting: bool = True
    company: str | None = None
    position: str | None = None
    location: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str = "USD"
    employment_type: str | None = None  # 'full_time', 'contract', 'part_time'
    work_mode: str | None = None  # 'remote', 'hybrid', 'onsite'
    skills: list[str] = Field(default_factory=list)
    job_urls: list[str] = Field(default_factory=list)
    description_snippet: str | None = None
    confidence: float = 0.0  # Parser confidence 0-1


class SlackJobPosting(BaseModel):
    """Full job posting record for storage."""

    # Database ID
    id: int | None = None

    # Slack identifiers
    message_ts: str
    channel_id: str
    channel_name: str | None = None
    workspace: str | None = None
    posted_by_user_id: str | None = None

    # Parsed job data
    company: str | None = None
    position: str | None = None
    location: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str = "USD"
    employment_type: str | None = None
    work_mode: str | None = None
    skills: list[str] = Field(default_factory=list)

    # Content
    raw_message: str
    parsed_description: str | None = None
    job_url: str | None = None
    scraped_description: str | None = None

    # Metadata
    posted_at: datetime
    created_at: datetime = Field(default_factory=datetime.now)

    # Tracking
    applied: bool = False
    applied_at: datetime | None = None
    match_score: float | None = None

    @classmethod
    def from_message_and_parsed(
        cls,
        message: SlackMessage,
        parsed: ParsedJob,
        channel_name: str | None = None,
        workspace: str | None = None,
    ) -> "SlackJobPosting":
        """Create a SlackJobPosting from a message and parsed job data."""
        return cls(
            message_ts=message.ts,
            channel_id=message.channel_id,
            channel_name=channel_name,
            workspace=workspace,
            posted_by_user_id=message.user_id,
            posted_at=datetime.fromtimestamp(float(message.ts.split(".")[0])),
            company=parsed.company,
            position=parsed.position,
            location=parsed.location,
            salary_min=parsed.salary_min,
            salary_max=parsed.salary_max,
            salary_currency=parsed.salary_currency,
            employment_type=parsed.employment_type,
            work_mode=parsed.work_mode,
            skills=parsed.skills,
            raw_message=message.text,
            parsed_description=parsed.description_snippet,
            job_url=parsed.job_urls[0] if parsed.job_urls else None,
        )

    def salary_display(self) -> str | None:
        """Format salary for display."""
        if self.salary_min and self.salary_max:
            return f"${self.salary_min:,} - ${self.salary_max:,} {self.salary_currency}"
        elif self.salary_min:
            return f"${self.salary_min:,}+ {self.salary_currency}"
        elif self.salary_max:
            return f"Up to ${self.salary_max:,} {self.salary_currency}"
        return None
