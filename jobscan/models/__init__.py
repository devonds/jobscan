"""Data models."""

from jobscan.models.job import JobApplication, JobListing
from jobscan.models.slack import ParsedJob, SlackJobPosting, SlackMessage

__all__ = [
    "JobListing",
    "JobApplication",
    "SlackMessage",
    "ParsedJob",
    "SlackJobPosting",
]
