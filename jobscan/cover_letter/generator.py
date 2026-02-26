"""Cover letter generation using Claude API."""

from dataclasses import dataclass

from anthropic import Anthropic

from jobscan.models.job import JobListing

# Pricing per million tokens (as of 2025)
PRICING = {
    "claude-sonnet-4-5-20250929": {"input": 3.00, "output": 15.00},
    "claude-sonnet-4-5": {"input": 3.00, "output": 15.00},
    "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00},
    "claude-opus-4-5-20251101": {"input": 15.00, "output": 75.00},
}

# Default pricing for unknown models
DEFAULT_PRICING = {"input": 3.00, "output": 15.00}


@dataclass
class GenerationResult:
    """Result of cover letter generation including token usage."""

    content: str
    input_tokens: int
    output_tokens: int
    model: str

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def estimate_cost(self) -> float:
        """Estimate cost in USD based on token usage."""
        pricing = PRICING.get(self.model, DEFAULT_PRICING)
        input_cost = (self.input_tokens / 1_000_000) * pricing["input"]
        output_cost = (self.output_tokens / 1_000_000) * pricing["output"]
        return input_cost + output_cost


class CoverLetterGenerator:
    """Generate customized cover letters using Claude API."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-5-20250929",
        max_tokens: int = 2048,
    ) -> None:
        """Initialize the generator.

        Args:
            api_key: Anthropic API key.
            model: Claude model to use.
            max_tokens: Maximum tokens in response.
        """
        self.client = Anthropic(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens

    def generate(
        self,
        job: JobListing,
        resume: str,
        template: str,
    ) -> GenerationResult:
        """Generate a customized cover letter.

        Args:
            job: The job listing to apply to.
            resume: The applicant's resume text.
            template: A cover letter template or style guide.

        Returns:
            GenerationResult with content and token usage.
        """
        prompt = self._build_prompt(job, resume, template)

        message = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )

        return GenerationResult(
            content=message.content[0].text,
            input_tokens=message.usage.input_tokens,
            output_tokens=message.usage.output_tokens,
            model=self.model,
        )

    def _build_prompt(
        self,
        job: JobListing,
        resume: str,
        template: str,
    ) -> str:
        """Build the prompt for cover letter generation."""
        return f"""You are a professional writer helping craft a cover letter. Your task is to write in the voice and style specified below - NOT in a generic corporate tone.

## The Job I'm Applying For

**Company:** {job.company}
**Position:** {job.position}
{f"**Location:** {job.location}" if job.location else ""}

**Job Description:**
{job.description}

---

## My Background (Resume)

{resume}

---

## Writing Style Guide & Examples

IMPORTANT: The following section defines HOW to write - the tone, voice, and style. If examples are provided, study them carefully and match that voice. If things to avoid are listed, do NOT do those things.

{template}

---

## Your Task

Write a cover letter that:

1. **Matches the voice and style** from the guide above - this is the most important requirement
2. **Connects specific experience** from my resume to specific requirements in the job description
3. **Shows genuine understanding** of what the company/role needs (don't just repeat the job posting)
4. **Uses concrete details** - specific projects, metrics, technologies - not vague claims
5. **Stays concise** - 3-4 paragraphs, under 400 words
6. **Sounds human** - like a real person wrote it, not a template

DO NOT:
- Use generic phrases like "I am excited to apply" or "I believe I would be a great fit"
- Include placeholder text like [Your Name] - use real content
- Include date headers or recipient addresses - start with the greeting
- Use buzzwords without substance
- Simply restate my resume or the job description

Write the cover letter now, matching the voice from the style guide:"""


class GeneratorError(Exception):
    """Error generating cover letter."""

    pass
