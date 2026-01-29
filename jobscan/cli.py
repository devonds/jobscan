"""CLI interface for jobscan."""

import click

from jobscan.config import Config, ConfigError, get_config_dir, get_config_path


@click.group()
@click.version_option(package_name="jobscan")
def main() -> None:
    """Jobscan - Automate your job applications."""
    pass


@main.command()
@click.argument("url")
@click.option("--no-sheet", is_flag=True, help="Skip Google Sheets logging")
@click.option("--no-doc", is_flag=True, help="Skip DOCX generation")
@click.option("--output", "-o", type=click.Path(), help="Output directory for cover letter")
def apply(url: str, no_sheet: bool, no_doc: bool, output: str | None) -> None:
    """Apply to a job listing.

    URL is the job listing page to process.
    """
    # Load configuration
    try:
        config = Config.load()
    except Exception as e:
        raise click.ClickException(
            f"Configuration error: {e}\n\nRun 'jobscan init' to set up configuration."
        )

    # Validate paths
    errors = config.validate_paths()
    if errors:
        raise click.ClickException("Configuration errors:\n" + "\n".join(f"  - {e}" for e in errors))

    click.echo(f"Processing job listing: {url}")

    # Import here to avoid circular imports and speed up CLI startup
    from jobscan.scraper import get_scraper
    from jobscan.cover_letter.generator import CoverLetterGenerator
    from jobscan.sheets.tracker import JobTracker

    # 1. Scrape job listing
    click.echo("Scraping job listing...")
    scraper = get_scraper(url)
    job = scraper.scrape(url)
    click.echo(f"Found: {job.position} at {job.company}")

    # 2. Log to Google Sheets
    if not no_sheet and config.google_credentials_path:
        click.echo("Logging to Google Sheets...")
        tracker = JobTracker(
            credentials_path=config.google_credentials_path,
            spreadsheet_id=config.spreadsheet_id,
            worksheet_name=config.worksheet_name,
        )
        tracker.log_application(job)
        click.echo("Logged to Google Sheets")
    elif not no_sheet:
        click.echo("Skipping Google Sheets (no credentials configured)")

    # 3. Generate cover letter
    click.echo("Generating cover letter...")
    resume = config.resume_path.read_text()
    template = config.cover_letter_template_path.read_text()

    generator = CoverLetterGenerator(
        api_key=config.anthropic_api_key,
        model=config.model,
        max_tokens=config.max_tokens,
    )
    result = generator.generate(job=job, resume=resume, template=template)

    # Display token usage and cost
    cost = result.estimate_cost()
    click.echo(f"Cover letter generated")
    click.echo(f"  Tokens: {result.input_tokens:,} in / {result.output_tokens:,} out ({result.total_tokens:,} total)")
    click.echo(f"  Estimated cost: ${cost:.4f}")

    # 4. Export to DOCX
    if not no_doc:
        from pathlib import Path
        from jobscan.cover_letter.docx import DocxExporter

        output_dir = Path(output) if output else config.output_directory
        output_dir.mkdir(parents=True, exist_ok=True)

        click.echo("Exporting to DOCX...")
        exporter = DocxExporter()
        docx_path = exporter.export(
            content=result.content,
            output_dir=output_dir,
            company=job.company,
            position=job.position,
        )
        click.echo(f"Cover letter saved: {docx_path}")

    click.echo("Done!")


@main.command()
def init() -> None:
    """Initialize jobscan configuration."""
    config_dir = get_config_dir()
    config_path = get_config_path()

    # Create config directory
    config_dir.mkdir(parents=True, exist_ok=True)

    if config_path.exists():
        click.echo(f"Configuration already exists at: {config_path}")
        if not click.confirm("Overwrite?"):
            return

    # Get user input
    click.echo("\nLet's set up your jobscan configuration.\n")

    resume_path = click.prompt(
        "Path to your resume (markdown or text)",
        type=click.Path(),
    )
    template_path = click.prompt(
        "Path to your cover letter template",
        type=click.Path(),
    )
    output_dir = click.prompt(
        "Directory to save cover letters",
        default="~/Documents/cover_letters",
        type=click.Path(),
    )

    # Write config file
    config_content = f'''[user]
resume_path = "{resume_path}"
cover_letter_template_path = "{template_path}"

[sheets]
# spreadsheet_id = ""  # Will be created on first run if not set
worksheet_name = "Job Applications"

[cover_letter]
output_directory = "{output_dir}"
model = "claude-sonnet-4-5-20250929"
max_tokens = 2048
'''

    config_path.write_text(config_content)
    click.echo(f"\nConfiguration saved to: {config_path}")
    click.echo("\nNext steps:")
    click.echo("1. Set ANTHROPIC_API_KEY environment variable")
    click.echo("2. Set GOOGLE_SERVICE_ACCOUNT_JSON environment variable (optional)")
    click.echo("3. Run 'jobscan apply <url>' to apply to a job")


@main.command()
def config() -> None:
    """Show current configuration."""
    config_path = get_config_path()

    if not config_path.exists():
        click.echo(f"No configuration found at: {config_path}")
        click.echo("Run 'jobscan init' to create one.")
        return

    click.echo(f"Configuration file: {config_path}\n")
    click.echo(config_path.read_text())


if __name__ == "__main__":
    main()
