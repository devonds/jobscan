"""Google Sheets sync for Slack job postings."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import gspread

if TYPE_CHECKING:
    from jobscan.models.slack import SlackJobPosting


class SheetsSync:
    """Sync Slack job postings from SQLite to Google Sheets."""

    HEADERS = [
        "ID",
        "Posted",
        "Company",
        "Position",
        "Location",
        "Salary",
        "Type",
        "Work Mode",
        "Skills",
        "URL",
        "Match Score",
        "Applied",
        "Source",
        "Relevant?",
        "Engagement Type",
        "Reasoning"
    ]

    def __init__(
        self,
        credentials_path: Path,
        spreadsheet_id: str | None = None,
        worksheet_name: str = "Slack Jobs",
    ) -> None:
        """Initialize the sync client.

        Args:
            credentials_path: Path to Google service account credentials JSON.
            spreadsheet_id: ID of existing spreadsheet, or None to create new.
            worksheet_name: Name of the worksheet to use.
        """
        self.gc = gspread.service_account(filename=str(credentials_path))
        self.worksheet_name = worksheet_name

        if spreadsheet_id:
            self.spreadsheet = self.gc.open_by_key(spreadsheet_id)
        else:
            self.spreadsheet = self._create_spreadsheet()

        self._ensure_worksheet()

    def _create_spreadsheet(self) -> gspread.Spreadsheet:
        """Create a new spreadsheet for Slack jobs."""
        spreadsheet = self.gc.create("Slack Job Postings")
        return spreadsheet

    def _ensure_worksheet(self) -> None:
        """Ensure the worksheet exists with headers."""
        try:
            self.worksheet = self.spreadsheet.worksheet(self.worksheet_name)
        except gspread.WorksheetNotFound:
            self.worksheet = self.spreadsheet.add_worksheet(
                title=self.worksheet_name,
                rows=1000,
                cols=len(self.HEADERS),
            )

        # Check if headers exist
        first_row = self.worksheet.row_values(1)
        if not first_row or first_row != self.HEADERS:
            header_range = f"A1:{chr(64 + len(self.HEADERS))}1"
            self.worksheet.update(header_range, [self.HEADERS])
            # Format header row
            self.worksheet.format(
                header_range,
                {
                    "textFormat": {"bold": True},
                    "backgroundColor": {"red": 0.9, "green": 0.9, "blue": 0.9},
                },
            )

    def _job_to_row(self, job: SlackJobPosting) -> list:
        """Convert a job posting to a spreadsheet row."""
        return [
            job.id,
            job.posted_at.strftime("%Y-%m-%d") if job.posted_at else "",
            job.company or "",
            job.position or "",
            job.location or "",
            job.salary_display() or "",
            job.employment_type or "",
            job.work_mode or "",
            ", ".join(job.skills[:5]) if job.skills else "",  # Limit skills for readability
            job.job_url or "",
            f"{job.match_score:.0f}%" if job.match_score else "",
            "Yes" if job.applied else "No",
            job.channel_name or job.channel_id,
            "Yes" if job.is_relevant else ("No" if job.is_relevant is False else ""),
            job.engagement_type_label or "",
            job.relevance_reason or "",
        ]

    def sync_jobs(self, jobs: list[SlackJobPosting]) -> int:
        """Sync a list of jobs to the spreadsheet.

        This does a full sync - clears existing data and writes all jobs.

        Args:
            jobs: List of jobs to sync.

        Returns:
            Number of jobs synced.
        """
        if not jobs:
            return 0

        # Clear existing data (keep headers)
        self.worksheet.clear()
        self._ensure_worksheet()

        # Convert jobs to rows
        rows = [self._job_to_row(job) for job in jobs]

        # Batch update for efficiency
        if rows:
            end_col = chr(64 + len(self.HEADERS))
            end_row = len(rows) + 1
            self.worksheet.update(f"A2:{end_col}{end_row}", rows)

        return len(rows)

    def append_job(self, job: SlackJobPosting) -> None:
        """Append a single job to the spreadsheet."""
        row = self._job_to_row(job)
        self.worksheet.append_row(row, value_input_option="USER_ENTERED")

    def get_synced_ids(self) -> set[int]:
        """Get the set of job IDs already in the spreadsheet."""
        # Get all values in column A (ID column)
        id_column = self.worksheet.col_values(1)
        ids = set()
        for val in id_column[1:]:  # Skip header
            try:
                ids.add(int(val))
            except (ValueError, TypeError):
                continue
        return ids

    def sync_new_jobs(self, jobs: list[SlackJobPosting]) -> int:
        """Sync only new jobs that aren't already in the spreadsheet.

        Args:
            jobs: List of jobs to potentially sync.

        Returns:
            Number of new jobs synced.
        """
        existing_ids = self.get_synced_ids()
        new_jobs = [j for j in jobs if j.id not in existing_ids]

        for job in new_jobs:
            self.append_job(job)

        return len(new_jobs)

    def get_spreadsheet_url(self) -> str:
        """Get the URL of the spreadsheet."""
        return self.spreadsheet.url

    def get_spreadsheet_id(self) -> str:
        """Get the ID of the spreadsheet."""
        return self.spreadsheet.id


class SyncError(Exception):
    """Error during Google Sheets sync."""

    pass
