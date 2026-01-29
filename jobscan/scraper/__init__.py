"""Job listing scrapers."""

from jobscan.scraper.base import BaseScraper, ScrapingError
from jobscan.scraper.generic import GenericScraper

# Scraper registry - order matters, first match wins
# Add site-specific scrapers before GenericScraper
SCRAPERS: list[type[BaseScraper]] = [
    GenericScraper,  # Fallback - handles any URL
]


def get_scraper(url: str) -> BaseScraper:
    """Get the appropriate scraper for a URL.

    Args:
        url: The URL to find a scraper for.

    Returns:
        A scraper instance that can handle the URL.

    Raises:
        ValueError: If no scraper can handle the URL (shouldn't happen with GenericScraper).
    """
    for scraper_cls in SCRAPERS:
        if scraper_cls.can_handle(url):
            return scraper_cls()
    raise ValueError(f"No scraper found for URL: {url}")


__all__ = ["get_scraper", "BaseScraper", "ScrapingError", "GenericScraper"]
