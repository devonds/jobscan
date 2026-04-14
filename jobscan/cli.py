"""CLI interface for jobscan."""

import click

from jobscan.config import Config, get_config_dir, get_config_path


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
        error_list = "\n".join(f"  - {e}" for e in errors)
        raise click.ClickException(f"Configuration errors:\n{error_list}")

    click.echo(f"Processing job listing: {url}")

    # Import here to avoid circular imports and speed up CLI startup
    from jobscan.cover_letter.generator import CoverLetterGenerator
    from jobscan.scraper import get_scraper
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
    click.echo("Cover letter generated")
    click.echo(
        f"  Tokens: {result.input_tokens:,} in / {result.output_tokens:,} out "
        f"({result.total_tokens:,} total)"
    )
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


# Slack command group
@main.group()
def slack() -> None:
    """Scrape and manage job postings from Slack channels."""
    pass


@slack.command()
@click.option("--channel", "-c", multiple=True, help="Channel ID or alias to scrape")
@click.option("--all", "scrape_all", is_flag=True, help="Scrape all configured channels")
@click.option("--full", is_flag=True, help="Full refresh (ignore last scrape timestamp)")
@click.option("--follow-urls/--no-follow-urls", default=True, help="Scrape linked job URLs")
@click.option("--limit", "-n", default=100, help="Max messages to fetch per channel")
def scrape(
    channel: tuple[str, ...],
    scrape_all: bool,
    full: bool,
    follow_urls: bool,
    limit: int,
) -> None:
    """Scrape job postings from Slack channels."""

    from jobscan.models.slack import SlackJobPosting
    from jobscan.slack import JobMessageParser, SlackClient, SlackError
    from jobscan.storage import Database

    # Load configuration
    try:
        cfg = Config.load()
    except Exception as e:
        raise click.ClickException(f"Configuration error: {e}")

    if not cfg.slack_user_token:
        raise click.ClickException(
            "SLACK_USER_TOKEN environment variable not set.\n"
            "Export your Slack user token to scrape channels."
        )

    if not cfg.slack_channels and not channel:
        raise click.ClickException(
            "No channels configured. Either:\n"
            "  1. Add channels to config.toml under [slack.channels]\n"
            "  2. Use --channel <channel_id> to specify channels"
        )

    # Determine which channels to scrape
    channels_to_scrape: dict[str, str] = {}  # alias -> channel_id

    if scrape_all:
        channels_to_scrape = cfg.slack_channels.copy()
    elif channel:
        for ch in channel:
            # Check if it's an alias or a channel ID
            if ch in cfg.slack_channels:
                channels_to_scrape[ch] = cfg.slack_channels[ch]
            elif ch.startswith("C"):
                channels_to_scrape[ch] = ch
            else:
                raise click.ClickException(
                    f"Unknown channel: {ch}. "
                    "Use a channel ID (starts with C) or a configured alias."
                )
    else:
        channels_to_scrape = cfg.slack_channels.copy()

    if not channels_to_scrape:
        raise click.ClickException("No channels to scrape.")

    # Initialize components
    db = Database(cfg.database_path)
    parser = JobMessageParser(api_key=cfg.anthropic_api_key, model=cfg.model)
    from jobscan.matcher.relevance import RelevanceAssessor
    assessor = RelevanceAssessor(api_key=cfg.anthropic_api_key, model=cfg.model)

    total_jobs = 0
    total_messages = 0

    try:
        with SlackClient(cfg.slack_user_token) as client:
            for alias, channel_id in channels_to_scrape.items():
                click.echo(f"\nScraping channel: {alias} ({channel_id})")

                # Get last scrape timestamp for incremental scraping
                oldest = None
                if not full:
                    oldest = db.get_last_scrape_timestamp(channel_id)
                    if oldest:
                        click.echo(f"  Fetching messages since {oldest}")

                # Fetch messages
                messages = list(client.get_channel_history(
                    channel_id=channel_id,
                    oldest=oldest,
                    limit=limit,
                ))
                click.echo(f"  Found {len(messages)} messages")
                total_messages += len(messages)

                if not messages:
                    continue

                # Parse messages for job postings
                jobs_found = 0
                with click.progressbar(
                    messages,
                    label="  Parsing messages",
                    show_pos=True,
                ) as bar:
                    for msg in bar:
                        try:
                            parsed = parser.parse_message(msg)
                            if parsed:
                                # Create job posting record
                                job = SlackJobPosting.from_message_and_parsed(
                                    message=msg,
                                    parsed=parsed,
                                    channel_name=alias,
                                    workspace=None,  # Could be extracted from config
                                )

                                # Optionally follow URLs to scrape full descriptions
                                if follow_urls and job.job_url:
                                    try:
                                        from jobscan.scraper import get_scraper
                                        scraper = get_scraper(job.job_url)
                                        scraped = scraper.scrape(job.job_url)
                                        job.scraped_description = scraped.description
                                        if not job.company:
                                            job.company = scraped.company
                                        if not job.position:
                                            job.position = scraped.position
                                        if not job.location:
                                            job.location = scraped.location
                                    except Exception:
                                        pass  # Silently skip failed URL scrapes

                                # Assess custom relevance
                                try:
                                    assessor.assess(job)
                                except Exception as e:
                                    click.echo(f"  Relevance assessment failed: {e}", err=True)

                                # Save to database
                                db.upsert_job(job)
                                jobs_found += 1

                        except Exception:
                            continue  # Skip failed parses

                click.echo(f"  Found {jobs_found} job postings")
                total_jobs += jobs_found

                # Record scrape history
                if messages:
                    latest_ts = max(m.ts for m in messages)
                    db.record_scrape(
                        channel_id=channel_id,
                        workspace=None,
                        last_message_ts=latest_ts,
                        messages_processed=len(messages),
                        jobs_found=jobs_found,
                    )

    except SlackError as e:
        raise click.ClickException(f"Slack API error: {e}")

    click.echo(f"\nDone! Processed {total_messages} messages, found {total_jobs} jobs.")


@slack.command("list")
@click.option("--limit", "-n", default=20, help="Number of jobs to show")
@click.option("--company", help="Filter by company name")
@click.option("--remote", is_flag=True, default=False, help="Only show remote jobs")
@click.option("--unapplied", is_flag=True, help="Only show jobs not yet applied to")
@click.option("--format", "output_format", type=click.Choice(["table", "json"]), default="table")
def list_jobs(
    limit: int,
    company: str | None,
    remote: bool,
    unapplied: bool,
    output_format: str,
) -> None:
    """List scraped job postings."""
    import json

    from jobscan.storage import Database

    try:
        cfg = Config.load()
    except Exception as e:
        raise click.ClickException(f"Configuration error: {e}")

    db = Database(cfg.database_path)

    jobs = db.get_jobs(
        company=company,
        work_mode="remote" if remote else None,
        unapplied_only=unapplied,
        limit=limit,
    )

    if not jobs:
        click.echo("No jobs found.")
        return

    if output_format == "json":
        output = [
            {
                "id": j.id,
                "company": j.company,
                "position": j.position,
                "location": j.location,
                "work_mode": j.work_mode,
                "salary": j.salary_display(),
                "skills": j.skills,
                "url": j.job_url,
                "posted_at": j.posted_at.isoformat() if j.posted_at else None,
                "applied": j.applied,
            }
            for j in jobs
        ]
        click.echo(json.dumps(output, indent=2))
    else:
        # Table format
        header = f"{'ID':<6} {'Company':<20} {'Position':<30} {'Location':<15} {'Mode':<8}"
        click.echo(f"\n{header}")
        click.echo("-" * 80)
        for job in jobs:
            company_display = (job.company or "Unknown")[:19]
            position_display = (job.position or "Unknown")[:29]
            location_display = (job.location or "-")[:14]
            mode_display = (job.work_mode or "-")[:7]
            applied_display = "Yes" if job.applied else "No"

            click.echo(
                f"{job.id:<6} {company_display:<20} {position_display:<30} "
                f"{location_display:<15} {mode_display:<8} {applied_display:<8}"
            )

        click.echo(f"\nShowing {len(jobs)} job(s). Use --limit to see more.")


@slack.command()
@click.argument("job_id", type=int)
def show(job_id: int) -> None:
    """Show details of a specific job posting."""
    from jobscan.storage import Database

    try:
        cfg = Config.load()
    except Exception as e:
        raise click.ClickException(f"Configuration error: {e}")

    db = Database(cfg.database_path)
    job = db.get_job_by_id(job_id)

    if not job:
        raise click.ClickException(f"Job {job_id} not found.")

    click.echo(f"\n{'=' * 60}")
    click.echo(f"Job #{job.id}")
    click.echo(f"{'=' * 60}\n")

    click.echo(f"Company:      {job.company or 'Unknown'}")
    click.echo(f"Position:     {job.position or 'Unknown'}")
    click.echo(f"Location:     {job.location or 'Not specified'}")
    click.echo(f"Work Mode:    {job.work_mode or 'Not specified'}")
    click.echo(f"Type:         {job.employment_type or 'Not specified'}")
    click.echo(f"Salary:       {job.salary_display() or 'Not specified'}")
    click.echo(f"Applied:      {'Yes' if job.applied else 'No'}")
    click.echo(f"Match Score:  {job.match_score or 'Not scored'}")

    if job.skills:
        click.echo(f"\nSkills:       {', '.join(job.skills)}")

    if job.job_url:
        click.echo(f"\nJob URL:      {job.job_url}")

    click.echo(f"\nPosted:       {job.posted_at}")
    click.echo(f"Source:       {job.channel_name or job.channel_id}")

    if job.parsed_description:
        click.echo(f"\nDescription:\n{job.parsed_description}")

    if job.scraped_description:
        click.echo(f"\nFull Description:\n{job.scraped_description[:1000]}...")


@slack.command()
@click.argument("job_id", type=int)
def mark_applied(job_id: int) -> None:
    """Mark a job as applied."""
    from jobscan.storage import Database

    try:
        cfg = Config.load()
    except Exception as e:
        raise click.ClickException(f"Configuration error: {e}")

    db = Database(cfg.database_path)

    if db.mark_job_applied(job_id):
        click.echo(f"Marked job #{job_id} as applied.")
    else:
        click.echo(f"Job #{job_id} not found or already marked as applied.")


@slack.command()
def channels() -> None:
    """List configured Slack channels."""
    try:
        cfg = Config.load()
    except Exception as e:
        raise click.ClickException(f"Configuration error: {e}")

    if not cfg.slack_channels:
        click.echo("No channels configured.")
        click.echo("\nAdd channels to your config.toml:")
        click.echo("\n[slack.channels]")
        click.echo('dbt-jobs = "C0123456789"')
        click.echo('locally-optimistic = "C9876543210"')
        return

    click.echo("\nConfigured Slack channels:\n")
    click.echo(f"{'Alias':<25} {'Channel ID':<15}")
    click.echo("-" * 40)
    for alias, channel_id in cfg.slack_channels.items():
        click.echo(f"{alias:<25} {channel_id:<15}")

    click.echo(f"\nTotal: {len(cfg.slack_channels)} channel(s)")


@slack.command()
def stats() -> None:
    """Show statistics about scraped jobs."""
    from jobscan.storage import Database

    try:
        cfg = Config.load()
    except Exception as e:
        raise click.ClickException(f"Configuration error: {e}")

    db = Database(cfg.database_path)

    total = db.count_jobs()
    unapplied = db.count_jobs(unapplied_only=True)
    applied = total - unapplied

    click.echo("\nJob Statistics:")
    click.echo(f"  Total jobs:     {total}")
    click.echo(f"  Applied:        {applied}")
    click.echo(f"  Not applied:    {unapplied}")


@slack.command()
@click.option("--min-score", default=50, help="Minimum match score (0-100)")
@click.option("--limit", "-n", default=10, help="Number of matches to show")
@click.option("--unapplied", is_flag=True, help="Only match against unapplied jobs")
def match(min_score: int, limit: int, unapplied: bool) -> None:
    """Find jobs matching your resume."""
    from jobscan.matcher import ResumeAnalyzer
    from jobscan.storage import Database

    try:
        cfg = Config.load()
    except Exception as e:
        raise click.ClickException(f"Configuration error: {e}")

    # Validate resume exists
    if not cfg.resume_path.exists():
        raise click.ClickException(f"Resume not found: {cfg.resume_path}")

    resume = cfg.resume_path.read_text()

    db = Database(cfg.database_path)
    analyzer = ResumeAnalyzer(api_key=cfg.anthropic_api_key, model=cfg.model)

    # Get jobs to match against
    jobs = db.get_jobs(unapplied_only=unapplied, limit=100)

    if not jobs:
        click.echo("No jobs found to match against.")
        return

    click.echo(f"Analyzing {len(jobs)} jobs against your resume...\n")

    # Find best matches with progress
    with click.progressbar(length=len(jobs), label="Scoring jobs") as bar:
        def on_progress(current, total):
            bar.update(1)

        matches = analyzer.find_best_matches(
            jobs=jobs,
            resume=resume,
            min_score=min_score,
            limit=limit,
            on_progress=on_progress,
        )

    if not matches:
        click.echo(f"\nNo jobs found with match score >= {min_score}.")
        return

    click.echo(f"\n\nTop {len(matches)} Matching Jobs:\n")
    click.echo(f"{'Score':<7} {'ID':<6} {'Company':<20} {'Position':<30}")
    click.echo("=" * 70)

    for job, result in matches:
        company = (job.company or "Unknown")[:19]
        position = (job.position or "Unknown")[:29]
        click.echo(f"{result.score:>5.0f}%  {job.id:<6} {company:<20} {position:<30}")

    # Show details for top match
    if matches:
        top_job, top_result = matches[0]
        click.echo(f"\n\nTop Match Details (Job #{top_job.id}):")
        click.echo("-" * 50)
        click.echo(f"Score: {top_result.score:.0f}%")
        click.echo("\nStrengths:")
        for s in top_result.strengths:
            click.echo(f"  + {s}")
        if top_result.gaps:
            click.echo("\nGaps:")
            for g in top_result.gaps:
                click.echo(f"  - {g}")
        click.echo(f"\nReasoning: {top_result.reasoning}")

        if top_job.job_url:
            click.echo(f"\nApply: {top_job.job_url}")


@slack.command()
def demand() -> None:
    """Analyze skill demand across job postings."""
    from jobscan.matcher import ResumeAnalyzer
    from jobscan.storage import Database

    try:
        cfg = Config.load()
    except Exception as e:
        raise click.ClickException(f"Configuration error: {e}")

    db = Database(cfg.database_path)
    analyzer = ResumeAnalyzer(api_key=cfg.anthropic_api_key, model=cfg.model)

    jobs = db.get_all_jobs()

    if not jobs:
        click.echo("No jobs found. Run 'jobscan slack scrape' first.")
        return

    click.echo(f"Analyzing demand across {len(jobs)} job postings...\n")

    analysis = analyzer.analyze_demand(jobs)

    # Top Skills
    click.echo("Top Skills in Demand:")
    click.echo("-" * 40)
    for skill, count in analysis.top_skills[:15]:
        bar = "#" * min(count, 20)
        click.echo(f"  {skill:<25} {count:>3} {bar}")

    # Top Companies
    if analysis.top_companies:
        click.echo("\n\nTop Hiring Companies:")
        click.echo("-" * 40)
        for company, count in analysis.top_companies[:10]:
            click.echo(f"  {company:<30} {count} posting(s)")

    # Salary Range
    if analysis.salary_range:
        low, high = analysis.salary_range
        click.echo("\n\nSalary Range:")
        click.echo(f"  ${low:,} - ${high:,}")

    # Work Mode Breakdown
    if analysis.work_mode_breakdown:
        click.echo("\n\nWork Mode Breakdown:")
        total = sum(analysis.work_mode_breakdown.values())
        for mode, count in sorted(
            analysis.work_mode_breakdown.items(), key=lambda x: x[1], reverse=True
        ):
            pct = (count / total) * 100
            click.echo(f"  {mode:<15} {count:>3} ({pct:.0f}%)")

    # Employment Type Breakdown
    if analysis.employment_type_breakdown:
        click.echo("\n\nEmployment Type Breakdown:")
        total = sum(analysis.employment_type_breakdown.values())
        for emp_type, count in sorted(
            analysis.employment_type_breakdown.items(), key=lambda x: x[1], reverse=True
        ):
            pct = (count / total) * 100
            click.echo(f"  {emp_type:<15} {count:>3} ({pct:.0f}%)")

    # Common Requirements
    if analysis.common_requirements:
        click.echo("\n\nCommon Requirements:")
        click.echo("-" * 40)
        for req in analysis.common_requirements:
            click.echo(f"  - {req}")


@slack.command()
@click.option("--full", is_flag=True, help="Full sync (replace all data in sheet)")
def sync(full: bool) -> None:
    """Sync jobs to Google Sheets."""
    from jobscan.storage import Database, SheetsSync

    try:
        cfg = Config.load()
    except Exception as e:
        raise click.ClickException(f"Configuration error: {e}")

    if not cfg.google_credentials_path:
        raise click.ClickException(
            "Google credentials not configured.\n"
            "Set GOOGLE_SERVICE_ACCOUNT_JSON environment variable."
        )

    if not cfg.google_credentials_path.exists():
        raise click.ClickException(
            f"Google credentials file not found: {cfg.google_credentials_path}"
        )

    db = Database(cfg.database_path)
    jobs = db.get_all_jobs()

    if not jobs:
        click.echo("No jobs to sync.")
        return

    click.echo(f"Syncing {len(jobs)} jobs to Google Sheets...")

    try:
        sync_client = SheetsSync(
            credentials_path=cfg.google_credentials_path,
            spreadsheet_id=cfg.spreadsheet_id,
            worksheet_name="Slack Jobs",
        )

        if full:
            count = sync_client.sync_jobs(jobs)
            click.echo(f"Full sync complete. {count} jobs synced.")
        else:
            count = sync_client.sync_new_jobs(jobs)
            if count:
                click.echo(f"Synced {count} new jobs.")
            else:
                click.echo("No new jobs to sync.")

        click.echo(f"\nSpreadsheet: {sync_client.get_spreadsheet_url()}")

    except Exception as e:
        raise click.ClickException(f"Sync error: {e}")


if __name__ == "__main__":
    main()
