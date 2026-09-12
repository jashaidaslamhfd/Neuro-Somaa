"""Custom visual provider — prioritizes original/AI motion over pure stock.
Ensures clips don't feel like generic stock footage (per user request)."""

VISUAL_PROVIDER_PRIORITY = [
    "pollinations_ai_motion",  # AI-generated unique motion (Seedance 2.5) — most original
    "own_original_assets",     # In-repo original assets (assets/music/ covers audio; visuals from original libraries)
    "pixabay_premium",         # Higher-quality stock with original feel
    "pexels_premium",          # Licensed stock — used only when needed
    "ai_horde_custom",         # Anonymous AI generation — unique but variable quality
]

def apply_custom_filter(media_items: list) -> list:
    """Apply custom filter to prefer unique/non-stock visuals."""
    # Filter out pure generic stock by prioritizing AI motion and original assets
    # This ensures the pipeline produces unique-feeling content rather than repetitive stock clips
    filtered = sorted(media_items, key=lambda x: 0 if x.get("source") in ["pollinations_ai_motion", "own_original_assets"] else 1)
    return filtered
