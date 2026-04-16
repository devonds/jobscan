"""Google Sheets job application tracker."""

from datetime import datetime
from pathlib import Path

import gspread

from jobscan.models.job import JobApplication, JobListing


class JobTracker:
    """Track job applications in a Google Sheet."""

    HEADERS = [
        "Date Applied",
        "Company",
        "Position",
        "Job Listing URL",
        "Status",
        "Last Contact At",
    ]

    def __init__(
        self,
        credentials_path: Path,
        spreadsheet_id: str | None = None,
        worksheet_name: str = "Job Applications",
    ) -> None:
        """Initialize the job tracker.

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
        """Create a new spreadsheet for tracking applications."""
        spreadsheet = self.gc.create("Job Applications Tracker")
        # Note: The service account owns this spreadsheet
        # User would need to share it with themselves
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
            self.worksheet.update("A1:F1", [self.HEADERS])
            # Format header row
            self.worksheet.format("A1:F1", {
                "textFormat": {"bold": True},
                "backgroundColor": {"red": 0.9, "green": 0.9, "blue": 0.9},
            })

    def log_application(self, job: JobListing, status: str = "applied") -> None:
        """Log a job application to the spreadsheet.

        Args:
            job: The job listing that was applied to.
            status: The application status.
        """
        application = JobApplication.from_job_listing(job)
        application.status = status

        row = [
            application.date_applied.strftime("%Y-%m-%d"),
            application.company,
            application.position,
            application.job_listing_url,
            application.status,
            "",  # Last contact at - empty initially
        ]

        self.worksheet.append_row(row, value_input_option="USER_ENTERED")

    def update_status(self, row_number: int, status: str) -> None:
        """Update the status of an application.

        Args:
            row_number: The row number (1-indexed, excluding header).
            status: The new status.
        """
        # Row number is 1-indexed and header is row 1, so actual row is row_number + 1
        self.worksheet.update_cell(row_number + 1, 5, status)
        self.worksheet.update_cell(
            row_number + 1, 6, datetime.now().strftime("%Y-%m-%d")
        )

    def get_spreadsheet_url(self) -> str:
        """Get the URL of the spreadsheet."""
        return self.spreadsheet.url

    def get_spreadsheet_id(self) -> str:
        """Get the ID of the spreadsheet."""
        return self.spreadsheet.id


class SheetsError(Exception):
    """Error interacting with Google Sheets."""

    pass
