"""Slack integration for job channel scraping."""

from jobscan.slack.client import SlackClient, SlackError
from jobscan.slack.parser import JobMessageParser, ParserError

__all__ = ["SlackClient", "SlackError", "JobMessageParser", "ParserError"]
