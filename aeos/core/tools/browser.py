"""Browser tool -- fetch web/documentation content."""

from __future__ import annotations

import httpx


async def fetch_url(url: str, timeout: int = 30) -> str:
    """Fetch a URL and return its text content."""
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        resp = await client.get(url, headers={"User-Agent": "AEOS/0.1 (autonomous-agent)"})
        resp.raise_for_status()
        return resp.text


async def fetch_json(url: str, timeout: int = 30) -> dict:
    """Fetch a URL and parse JSON."""
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()
