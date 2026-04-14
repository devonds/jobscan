# jobscan

A collection of CLI tools I'm building to automate the tedious parts of applying to data science jobs.

Job hunting involves a lot of repetitive work—copying job descriptions, tweaking cover letters, tracking applications in spreadsheets. This project is my attempt to automate the boring stuff so I can focus on the parts that actually matter.

## What's here

**Cover letter generator** (`jobscan apply <url>`)

Takes a job listing URL, scrapes the description, generates a customized cover letter using Claude, and saves it as a .docx file. Also logs the application to a Google Sheet for tracking.

More tools coming as I find more things worth automating.

## Setup

Requires Python 3.10+ and [uv](https://github.com/astral-sh/uv).

```bash
# Clone and install
git clone https://github.com/devonds/jobscan.git
cd jobscan
uv sync

# Set up your config
uv run jobscan init
```

You'll need:
- An [Anthropic API key](https://console.anthropic.com/) (set as `ANTHROPIC_API_KEY` in a `.env` file)
- Optionally, a Google service account for Sheets integration (set `GOOGLE_SERVICE_ACCOUNT_JSON` path in `.env`)

## Usage

```bash
uv run jobscan apply "https://job-boards.greenhouse.io/company/jobs/12345"
```

This will:
1. Scrape the job listing
2. Log it to your Google Sheet (if configured)
3. Generate a cover letter tailored to the job
4. Save it as a .docx in your configured output directory

Options:
- `--no-sheet` - Skip Google Sheets logging
- `--no-doc` - Skip document generation (just scrape and log)
- `-o PATH` - Override output directory

## Customizing

You'll want to customize a few things:

**Your resume** - The tool reads your resume from a markdown file. Update the path in `~/.config/jobscan/config.toml`.

**Cover letter style** - The real magic is in your cover letter template file. This isn't a template in the traditional sense—it's a style guide that tells Claude *how* to write. Include:
- Examples of your writing voice
- Things to avoid ("don't say 'I'm passionate about...'")
- Structural preferences

The better your style guide, the less editing you'll need to do on the output.

**Model** - Defaults to Claude Sonnet 4.5. You can change this in the config if you want to experiment.

## Cost

Each cover letter costs about $0.02-0.03 with Claude Sonnet 4.5 (the tool shows exact token usage after each run).

## License

MIT - Use it however you want.
