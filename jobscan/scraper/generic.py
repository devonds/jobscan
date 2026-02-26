"""Generic scraper that works with most job listing sites."""

import json
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from jobscan.models.job import JobListing
from jobscan.scraper.base import BaseScraper, ScrapingError


class GenericScraper(BaseScraper):
    """Generic scraper using heuristics to extract job data from any site."""

    def __init__(self, timeout: int = 30) -> None:
        self.timeout = timeout
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }

    @classmethod
    def can_handle(cls, url: str) -> bool:
        """Generic scraper can handle any URL as a fallback."""
        return True

    def scrape(self, url: str) -> JobListing:
        """Scrape job listing from URL using multiple strategies."""
        try:
            response = httpx.get(url, headers=self.headers, timeout=self.timeout, follow_redirects=True)
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise ScrapingError(f"Failed to fetch URL: {e}")

        soup = BeautifulSoup(response.text, "lxml")

        # Try structured data first (schema.org JobPosting)
        job_data = self._extract_schema_org(soup)
        if job_data:
            return JobListing(url=url, **job_data)

        # Fall back to heuristic extraction
        job_data = self._extract_heuristic(soup, url)
        return JobListing(url=url, **job_data)

    def _extract_schema_org(self, soup: BeautifulSoup) -> dict | None:
        """Try to extract job data from schema.org JobPosting structured data."""
        # Look for JSON-LD
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
                # Handle both single object and array
                if isinstance(data, list):
                    for item in data:
                        if item.get("@type") == "JobPosting":
                            return self._parse_job_posting(item)
                elif data.get("@type") == "JobPosting":
                    return self._parse_job_posting(data)
                # Handle @graph structure
                elif "@graph" in data:
                    for item in data["@graph"]:
                        if item.get("@type") == "JobPosting":
                            return self._parse_job_posting(item)
            except (json.JSONDecodeError, TypeError):
                continue
        return None

    def _parse_job_posting(self, data: dict) -> dict:
        """Parse a schema.org JobPosting object."""
        # Extract company name
        company = "Unknown Company"
        if "hiringOrganization" in data:
            org = data["hiringOrganization"]
            if isinstance(org, dict):
                company = org.get("name", company)
            elif isinstance(org, str):
                company = org

        # Extract location
        location = None
        if "jobLocation" in data:
            loc = data["jobLocation"]
            if isinstance(loc, dict):
                address = loc.get("address", {})
                if isinstance(address, dict):
                    parts = [
                        address.get("addressLocality"),
                        address.get("addressRegion"),
                    ]
                    location = ", ".join(p for p in parts if p)
                elif isinstance(address, str):
                    location = address

        # Extract salary
        salary = None
        if "baseSalary" in data:
            sal = data["baseSalary"]
            if isinstance(sal, dict):
                value = sal.get("value", {})
                if isinstance(value, dict):
                    min_val = value.get("minValue")
                    max_val = value.get("maxValue")
                    currency = sal.get("currency", "USD")
                    if min_val and max_val:
                        salary = f"{currency} {min_val:,} - {max_val:,}"
                    elif min_val:
                        salary = f"{currency} {min_val:,}+"

        return {
            "company": company,
            "position": data.get("title", "Unknown Position"),
            "description": data.get("description", ""),
            "location": location,
            "salary": salary,
        }

    def _extract_heuristic(self, soup: BeautifulSoup, url: str) -> dict:
        """Extract job data using heuristics when structured data is unavailable."""
        # Extract title - try common patterns
        position = self._extract_title(soup)

        # Extract company - try common patterns
        company = self._extract_company(soup, url)

        # Extract description - find the largest text block
        description = self._extract_description(soup)

        # Extract location
        location = self._extract_location(soup)

        return {
            "company": company,
            "position": position,
            "description": description,
            "location": location,
        }

    def _extract_title(self, soup: BeautifulSoup) -> str:
        """Extract job title from page."""
        # Try common class/id patterns for job titles
        title_selectors = [
            '[class*="job-title"]',
            '[class*="jobTitle"]',
            '[class*="job_title"]',
            '[class*="position-title"]',
            '[data-testid*="title"]',
            'h1[class*="title"]',
            ".posting-headline h2",
            ".job-header h1",
        ]

        for selector in title_selectors:
            element = soup.select_one(selector)
            if element and element.get_text(strip=True):
                return element.get_text(strip=True)

        # Fall back to first h1
        h1 = soup.find("h1")
        if h1:
            return h1.get_text(strip=True)

        # Fall back to page title
        title_tag = soup.find("title")
        if title_tag:
            title = title_tag.get_text(strip=True)
            # Clean up common suffixes
            for suffix in [" | ", " - ", " at ", " @ "]:
                if suffix in title:
                    return title.split(suffix)[0].strip()
            return title

        return "Unknown Position"

    def _extract_company(self, soup: BeautifulSoup, url: str) -> str:
        """Extract company name from page."""
        # Try common class/id patterns
        company_selectors = [
            '[class*="company-name"]',
            '[class*="companyName"]',
            '[class*="company_name"]',
            '[class*="employer"]',
            '[data-testid*="company"]',
            ".posting-headline h3",
            ".company-header",
        ]

        for selector in company_selectors:
            element = soup.select_one(selector)
            if element and element.get_text(strip=True):
                return element.get_text(strip=True)

        # Try to extract from URL domain
        parsed = urlparse(url)
        domain = parsed.netloc.replace("www.", "")
        # If it's a job board, the company might be in the path
        job_boards = ["greenhouse.io", "lever.co", "jobs.lever.co", "boards.greenhouse.io"]
        if any(board in domain for board in job_boards):
            # Extract company from path (e.g., /company-name/jobs/...)
            parts = parsed.path.strip("/").split("/")
            if parts:
                return parts[0].replace("-", " ").title()

        return "Unknown Company"

    def _extract_description(self, soup: BeautifulSoup) -> str:
        """Extract job description from page."""
        # Try common class patterns for job descriptions
        desc_selectors = [
            '[class*="job-description"]',
            '[class*="jobDescription"]',
            '[class*="job_description"]',
            '[class*="description"]',
            '[data-testid*="description"]',
            ".posting-content",
            ".job-details",
            "#job-description",
            "article",
        ]

        for selector in desc_selectors:
            element = soup.select_one(selector)
            if element:
                text = element.get_text(separator="\n", strip=True)
                if len(text) > 200:  # Reasonable minimum for a job description
                    return text

        # Fall back to finding the largest text block
        text_blocks = []
        for elem in soup.find_all(["div", "section", "article"]):
            text = elem.get_text(separator="\n", strip=True)
            if len(text) > 200:
                text_blocks.append((len(text), text))

        if text_blocks:
            # Return the largest block
            text_blocks.sort(reverse=True)
            return text_blocks[0][1]

        return "No description available."

    def _extract_location(self, soup: BeautifulSoup) -> str | None:
        """Extract job location from page."""
        location_selectors = [
            '[class*="location"]',
            '[class*="job-location"]',
            '[data-testid*="location"]',
            '[class*="address"]',
        ]

        for selector in location_selectors:
            element = soup.select_one(selector)
            if element:
                text = element.get_text(strip=True)
                if text and len(text) < 100:  # Reasonable max for location
                    return text

        return None
