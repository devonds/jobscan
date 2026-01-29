"""Base scraper interface."""

from abc import ABC, abstractmethod

from jobscan.models.job import JobListing


class BaseScraper(ABC):
    """Abstract base class for job listing scrapers."""

    @abstractmethod
    def scrape(self, url: str) -> JobListing:
        """Scrape a job listing from the given URL.

        Args:
            url: The URL of the job listing page.

        Returns:
            A JobListing object with the extracted data.

        Raises:
            ScrapingError: If the page cannot be scraped.
        """
        pass

    @classmethod
    @abstractmethod
    def can_handle(cls, url: str) -> bool:
        """Check if this scraper can handle the given URL.

        Args:
            url: The URL to check.

        Returns:
            True if this scraper can handle the URL, False otherwise.
        """
        pass


class ScrapingError(Exception):
    """Error during web scraping."""

    pass
