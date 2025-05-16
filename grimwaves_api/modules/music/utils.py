"""Utility functions for music metadata module."""

import re
import unicodedata
from typing import Any

from httpx import AsyncClient

from grimwaves_api.modules.music.constants import RETRY_CONFIG, SOCIAL_MEDIA_PATTERNS


def normalize_text(text: str) -> str:
    """Normalize text for comparison.

    Removes punctuation, converts to lowercase, normalizes unicode (NFC form),
    and handles multiple spaces. Keeps non-ASCII characters.

    Args:
        text: The text to normalize

    Returns:
        Normalized text
    """
    if not text:  # Handle empty string input
        return ""
    # Normalize unicode characters to NFC form (Canonical Composition)
    # This helps in matching characters that can be represented in multiple ways.
    text = unicodedata.normalize("NFC", text)
    # Convert to lowercase
    text = text.lower()
    # Remove punctuation, keeping alphanumeric characters and whitespace
    # This will keep Cyrillic, Greek, etc. characters.
    text = re.sub(r"[^\w\s]", "", text, flags=re.UNICODE)
    # Strip leading/trailing whitespace
    text = text.strip()
    # Replace multiple spaces with a single space
    return re.sub(r"\s+", " ", text, flags=re.UNICODE)


def calculate_similarity(text1: str, text2: str) -> float:
    """Calculate text similarity score between two strings.

    Args:
        text1: First text for comparison
        text2: Second text for comparison

    Returns:
        Similarity score between 0 and 1
    """
    # Normalize both texts
    norm_text1 = normalize_text(text1)
    norm_text2 = normalize_text(text2)

    # If either string is empty, return 0
    if not norm_text1 or not norm_text2:
        return 0.0

    # Check for exact match
    if norm_text1 == norm_text2:
        return 1.0

    # Calculate similarity based on character overlap
    # (This is a simple implementation, more sophisticated algorithms like
    # Levenshtein distance could be used for better results)
    shorter = min(norm_text1, norm_text2, key=len)
    longer = max(norm_text1, norm_text2, key=len)

    if len(shorter) == 0:
        return 0.0

    # Count matching characters
    matches = sum(c1 == c2 for c1, c2 in zip(shorter, longer))
    return matches / len(longer)


def extract_social_media_username(url: str, platform: str) -> str | None:
    """Extract username from social media URL.

    Args:
        url: The social media URL
        platform: The platform name (e.g., "instagram", "twitter")

    Returns:
        The extracted username or None if not found
    """
    if not url or platform not in SOCIAL_MEDIA_PATTERNS:
        return None

    pattern = SOCIAL_MEDIA_PATTERNS[platform]
    match = re.search(pattern, url, re.IGNORECASE)

    if match:
        # For twitter, we might match either the twitter.com or x.com group
        return next((g for g in match.groups() if g), None)

    return None


async def create_http_client(
    base_url: str = "",
    timeout: float = 10.0,
    headers: dict[str, str] | None = None,
    retry_config: dict[str, Any] | None = None,
) -> AsyncClient:
    """Create an HTTP client with specified configuration.

    Args:
        base_url: Base URL for the client
        timeout: Request timeout in seconds
        headers: Custom headers to include in requests
        retry_config: Retry configuration for failed requests

    Returns:
        Configured HTTP client
    """
    # Use default retry config if none provided
    if retry_config is None:
        retry_config = RETRY_CONFIG["DEFAULT"]

    # Set default headers if none provided
    if headers is None:
        headers = {
            "User-Agent": "GrimWaves-API/0.1.0",
            "Accept": "application/json",
        }

    # Create and return an AsyncClient
    return AsyncClient(
        base_url=base_url,
        timeout=timeout,
        headers=headers,
        follow_redirects=True,
    )


def prioritize_releases(
    releases: list[dict[str, Any]],
    release_name: str,
    band_name: str,
    country_code: str | None = None,
) -> list[dict[str, Any]]:
    """Sort releases by relevance based on name matching and other criteria.

    Args:
        releases: List of release dictionaries
        release_name: Name of the release to match
        band_name: Name of the band/artist to match
        country_code: Optional country code for filtering

    Returns:
        Sorted list of releases with most relevant first
    """
    scored_releases: list[Any] = []
    norm_release_name = normalize_text(release_name)
    norm_band_name = normalize_text(band_name)

    for release in releases:
        # Extract names from the release dict
        # This is a placeholder - actual key names will depend on the API implementation
        rel_name = release.get("name", release.get("title", ""))
        rel_artist = release.get("artist", release.get("artist_name", ""))
        rel_country = release.get("country", "")

        # Calculate similarity scores
        name_score = calculate_similarity(rel_name, release_name)
        artist_score = calculate_similarity(rel_artist, band_name)

        # Bonus for exact matches after normalization
        if normalize_text(rel_name) == norm_release_name:
            name_score = 1.0
        if normalize_text(rel_artist) == norm_band_name:
            artist_score = 1.0

        # Country code match (if provided)
        country_score = 0.0
        if country_code and rel_country and rel_country.upper() == country_code.upper():
            country_score = 0.2

        # Calculate total score (weighted)
        total_score = (name_score * 0.6) + (artist_score * 0.3) + country_score

        scored_releases.append((release, total_score))

    # Sort by score in descending order
    scored_releases.sort(key=lambda x: x[1], reverse=True)

    # Return only the releases, not the scores
    return [r[0] for r in scored_releases]
