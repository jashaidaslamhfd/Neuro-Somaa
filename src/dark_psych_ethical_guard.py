"""Ethical guardrail for dark psychology / manipulation content in Neuro-Somaa."""
import re

FORBIDDEN_MANIPULATION_PATTERNS = [
    r"(manipulez|manipuler|manipulation).*sans.*consentement",
    r"(trompez|tromper|tromperie).*intentionnelle",
    r"(contrôlez|contrôler).*pensées.*(autres|personnes)",
    r"(forcez|forcer).*comportement",
    r"(deception|déception).*stratégique",
]

REQUIRED_FRAMING_PHRASES = [
    "à des fins éducatives",
    "pour comprendre et se protéger",
    "analyse scientifique",
    "étude du comportement",
    "conscience et vigilance",
]

def validate_dark_psych_script(script_text: str) -> tuple[bool, list[str]]:
    """Validate dark psychology content passes ethical guardrails."""
    errors = []
    # Check for harmful manipulation instructions
    for pattern in FORBIDDEN_MANIPULATION_PATTERNS:
        if re.search(pattern, script_text, re.IGNORECASE):
            errors.append(f"FORBIDDEN_PATTERN: {pattern}")
    # Ensure ethical framing is present
    has_framing = any(phrase in script_text.lower() for phrase in REQUIRED_FRAMING_PHRASES)
    if not has_framing and "dark_psych" in script_text.lower():
        errors.append("MISSING_ETHICAL_FRAMING: Script must include educational/protective framing.")
    # Ensure no personalized manipulation instructions
    if re.search(r"(faites|fais).*cela.*à.*quelqu'un", script_text, re.IGNORECASE):
        errors.append("PERSONALIZED_MANIPULATION_INSTRUCTION: General education only; no personalized manipulation instructions.")
    return len(errors) == 0, errors
