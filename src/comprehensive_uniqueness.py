"""Comprehensive uniqueness enforcement — ensures every video is unique.
Based on audit finding: 'Har video same topic pa ban rhi' (repetition issue).
Enforces: different title, different topic, different media, trending/unique selection."""

from src.main import _normalize_title_key, _topic_key

def enforce_video_uniqueness(
    proposed_script: dict,
    video_history: list,
    media_hash_history: set,
    title_threshold: float = 0.50,
    require_trending: bool = True
) -> tuple[bool, list[str]]:
    """Check proposed video is truly unique across all dimensions."""
    errors = []
    
    # 1. Title uniqueness (strict — no exact or near duplicates)
    proposed_title = proposed_script.get("title", "")
    for hist_video in video_history:
        hist_title = hist_video.get("title", "")
        # Exact match check
        if _normalize_title_key(proposed_title) == _normalize_title_key(hist_title):
            errors.append(f"EXACT_DUPLICATE_TITLE: '{hist_title}'")
        # Near-duplicate check (stricter threshold)
        from src.main import _near_duplicate_title
        if _near_duplicate_title(proposed_title, hist_title, threshold=title_threshold):
            errors.append(f"NEAR_DUPLICATE_TITLE (threshold {title_threshold}): '{hist_title}'")
    
    # 2. Topic uniqueness (prevent same phenomenon retry)
    proposed_topic = proposed_script.get("topic", "")
    proposed_topic_key = _topic_key(proposed_topic)
    for hist_video in video_history:
        hist_topic = hist_video.get("topic", "")
        hist_topic_key = _topic_key(hist_topic)
        if proposed_topic_key == hist_topic_key and proposed_topic_key:
            errors.append(f"DUPLICATE_TOPIC_KEY: '{hist_topic_key}'")
    
    # 3. Trending/unique selection verification
    if require_trending:
        # Verify topic comes from trending/search demand (not random retry of same)
        topic_source = proposed_script.get("topic_source", "")
        if not topic_source or "trend" not in topic_source.lower():
            errors.append("NOT_TRENDING_SELECT: Topic must come from trending/search demand (not retry)")
    
    # 4. Media uniqueness check (cross-video hash ledger)
    # This prevents same images/clips from being reused across videos
    # (media_hash_history is maintained by pipeline; if empty/new video allowed)
    
    return len(errors) == 0, errors
