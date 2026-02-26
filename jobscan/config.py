"""Configuration management for jobscan CLI."""

import os
from pathlib import Path

import tomllib
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator


def get_config_dir() -> Path:
    """Get the XDG config directory for jobscan."""
    xdg_config = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config:
        return Path(xdg_config) / "jobscan"
    return Path.home() / ".config" / "jobscan"


def get_config_path() -> Path:
    """Get the path to the config file."""
    return get_config_dir() / "config.toml"


def get_database_path() -> Path:
    """Get the default database path."""
    return get_config_dir() / "jobscan.db"


class Config(BaseModel):
    """Application configuration."""

    # File paths
    resume_path: Path
    cover_letter_template_path: Path
    output_directory: Path = Field(
        default_factory=lambda: Path.home() / "Documents" / "cover_letters"
    )

    # Google Sheets
    spreadsheet_id: str | None = None
    worksheet_name: str = "Job Applications"

    # Claude API
    anthropic_api_key: str
    model: str = "claude-sonnet-4-5-20250929"
    max_tokens: int = 2048

    # Google credentials
    google_credentials_path: Path | None = None

    # Slack configuration
    slack_user_token: str | None = None
    slack_channels: dict[str, str] = Field(default_factory=dict)  # alias -> channel_id

    # Storage configuration
    database_path: Path = Field(default_factory=get_database_path)

    # Matching configuration
    min_match_score: int = 50

    @field_validator("resume_path", "cover_letter_template_path", "output_directory", mode="before")
    @classmethod
    def expand_path(cls, v: str | Path) -> Path:
        """Expand ~ in paths."""
        if isinstance(v, str):
            return Path(v).expanduser()
        return v.expanduser()

    @field_validator("google_credentials_path", "database_path", mode="before")
    @classmethod
    def expand_optional_path(cls, v: str | Path | None) -> Path | None:
        """Expand ~ in optional paths."""
        if v is None:
            return None
        if isinstance(v, str):
            return Path(v).expanduser()
        return v.expanduser()

    @classmethod
    def load(cls, config_path: Path | None = None) -> "Config":
        """Load configuration from TOML file and environment variables.

        Environment variables take precedence over config file values.
        """
        # Load .env file if it exists
        load_dotenv()

        # Determine config file path
        if config_path is None:
            config_path = get_config_path()

        # Load TOML config if it exists
        config_data: dict = {}
        if config_path.exists():
            with open(config_path, "rb") as f:
                toml_data = tomllib.load(f)

            # Flatten nested structure
            if "user" in toml_data:
                config_data.update(toml_data["user"])
            if "sheets" in toml_data:
                config_data.update(toml_data["sheets"])
            if "cover_letter" in toml_data:
                config_data.update(toml_data["cover_letter"])
            if "slack" in toml_data:
                slack_data = toml_data["slack"]
                if "channels" in slack_data:
                    config_data["slack_channels"] = slack_data["channels"]
            if "storage" in toml_data:
                config_data.update(toml_data["storage"])
            if "matching" in toml_data:
                config_data.update(toml_data["matching"])

        # Override with environment variables
        if api_key := os.environ.get("ANTHROPIC_API_KEY"):
            config_data["anthropic_api_key"] = api_key

        if creds_path := os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON"):
            config_data["google_credentials_path"] = creds_path

        # Slack token from environment only (never from config file for security)
        if slack_token := os.environ.get("SLACK_USER_TOKEN"):
            config_data["slack_user_token"] = slack_token

        return cls(**config_data)

    def ensure_output_directory(self) -> None:
        """Create output directory if it doesn't exist."""
        self.output_directory.mkdir(parents=True, exist_ok=True)

    def validate_paths(self) -> list[str]:
        """Validate that required paths exist. Returns list of errors."""
        errors = []
        if not self.resume_path.exists():
            errors.append(f"Resume not found: {self.resume_path}")
        if not self.cover_letter_template_path.exists():
            errors.append(f"Cover letter template not found: {self.cover_letter_template_path}")
        if self.google_credentials_path and not self.google_credentials_path.exists():
            errors.append(f"Google credentials not found: {self.google_credentials_path}")
        return errors


class ConfigError(Exception):
    """Configuration error."""

    pass
