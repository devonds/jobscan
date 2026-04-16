"""Slack API client for fetching channel messages."""

from __future__ import annotations

import time
from collections.abc import Iterator

import httpx

from jobscan.models.slack import SlackMessage


class SlackError(Exception):
    """Slack API error."""

    def __init__(self, message: str, error_code: str | None = None) -> None:
        super().__init__(message)
        self.error_code = error_code


class SlackClient:
    """HTTP client for Slack Web API using user tokens."""

    BASE_URL = "https://slack.com/api"

    # Rate limiting: Tier 3 methods allow ~50 requests per minute
    RATE_LIMIT_DELAY = 1.2  # seconds between requests

    def __init__(self, user_token: str, timeout: int = 30) -> None:
        if not user_token:
            raise SlackError("Slack user token is required")
        if not user_token.startswith(("xoxp-", "xoxc-", "xoxb-")):
            raise SlackError(
                "Invalid Slack token format. Expected xoxp-, xoxc-, or xoxb- prefix"
            )

        self.token = user_token
        self.client = httpx.Client(
            base_url=self.BASE_URL,
            headers={"Authorization": f"Bearer {user_token}"},
            timeout=timeout,
        )
        self._last_request_time = 0.0

    def _rate_limit(self) -> None:
        """Enforce rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.RATE_LIMIT_DELAY:
            time.sleep(self.RATE_LIMIT_DELAY - elapsed)
        self._last_request_time = time.time()

    def _request(self, method: str, **params) -> dict:
        """Make a rate-limited request to Slack API."""
        self._rate_limit()

        response = self.client.get(method, params=params)
        response.raise_for_status()

        data = response.json()
        if not data.get("ok"):
            error = data.get("error", "unknown_error")
            raise SlackError(f"Slack API error: {error}", error_code=error)

        return data

    def get_channel_info(self, channel_id: str) -> dict:
        """Get information about a channel."""
        data = self._request("conversations.info", channel=channel_id)
        return data.get("channel", {})

    def list_channels(self, types: str = "public_channel,private_channel") -> list[dict]:
        """List channels the user has access to."""
        channels = []
        cursor = None

        while True:
            params = {"types": types, "limit": 200}
            if cursor:
                params["cursor"] = cursor

            data = self._request("conversations.list", **params)
            channels.extend(data.get("channels", []))

            cursor = data.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break

        return channels

    def get_channel_history(
        self,
        channel_id: str,
        oldest: str | None = None,
        limit: int = 100,
    ) -> Iterator[SlackMessage]:
        """Fetch messages from a channel with automatic pagination.

        Args:
            channel_id: The Slack channel ID
            oldest: Only return messages after this timestamp (for incremental scraping)
            limit: Maximum number of messages to return per page (max 1000)

        Yields:
            SlackMessage objects for each message in the channel
        """
        cursor = None

        while True:
            params = {"channel": channel_id, "limit": min(limit, 200)}
            if oldest:
                params["oldest"] = oldest
            if cursor:
                params["cursor"] = cursor

            data = self._request("conversations.history", **params)

            for msg in data.get("messages", []):
                # Skip non-message types (like channel_join)
                if msg.get("type") != "message":
                    continue
                # Skip bot messages and system messages
                if msg.get("subtype") in ("bot_message", "channel_join", "channel_leave"):
                    continue

                yield SlackMessage(
                    ts=msg["ts"],
                    channel_id=channel_id,
                    user_id=msg.get("user"),
                    text=msg.get("text", ""),
                    thread_ts=msg.get("thread_ts"),
                )

            cursor = data.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break

    def get_thread_replies(
        self,
        channel_id: str,
        thread_ts: str,
    ) -> list[SlackMessage]:
        """Fetch replies in a thread."""
        messages = []
        cursor = None

        while True:
            params = {"channel": channel_id, "ts": thread_ts, "limit": 200}
            if cursor:
                params["cursor"] = cursor

            data = self._request("conversations.replies", **params)

            for msg in data.get("messages", [])[1:]:  # Skip the parent message
                if msg.get("type") != "message":
                    continue

                messages.append(
                    SlackMessage(
                        ts=msg["ts"],
                        channel_id=channel_id,
                        user_id=msg.get("user"),
                        text=msg.get("text", ""),
                        thread_ts=thread_ts,
                    )
                )

            cursor = data.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break

        return messages

    def close(self) -> None:
        """Close the HTTP client."""
        self.client.close()

    def __enter__(self) -> SlackClient:
        return self

    def __exit__(self, *args) -> None:
        self.close()
