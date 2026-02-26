"""Job listing data models."""

from datetime import datetime

from pydantic import BaseModel, Field


class JobListing(BaseModel):
    """Represents a scraped job listing."""

    url: str
    company: str
    position: str
    description: str
    location: str | None = None
    salary: str | None = None
    scraped_at: datetime = Field(default_factory=datetime.now)

    def __str__(self) -> str:
        return f"{self.position} at {self.company}"


class JobApplication(BaseModel):
    """Represents a job application record for tracking."""

    date_applied: datetime = Field(default_factory=datetime.now)
    company: str
    position: str
    job_listing_url: str
    status: str = "applied"
    last_contact_at: datetime | None = None

    @classmethod
    def from_job_listing(cls, job: JobListing) -> "JobApplication":
        """Create a job application from a job listing."""
        return cls(
            company=job.company,
            position=job.position,
            job_listing_url=job.url,
        )
