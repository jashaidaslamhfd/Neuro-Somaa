# Service Dependencies — Neuro-Somaa Pipeline

## LLM / AI Providers
| Provider | Role | Fallback Chain | Status | Terms / Risk |
|---|---|---|---|---|
| Groq | Primary LLM (gpt-oss-120b/20b) | OpenRouter → ALT LLM → Local | Active | Rate limits apply; Aug-14 outage mitigated by rotation. |
| OpenRouter | Last-resort LLM | None (cost-only-on-full-Groq-failure) | Active | Pay-per-use; no SLA. |
| ALT LLM (OpenAI-compatible) | Optional fallback | None (ALT_LLM_STRICT=false) | Optional | Requires ALT_LLM_API_KEY secret. |

## TTS / Voice
| Provider | Voice | Fallback | Status | Terms / Risk |
|---|---|---|---|---|
| Edge TTS (Microsoft) | fr-FR-MauriceNeural (adult male pool) | Chatterbox → Kokoro → Local | Active | Free tier limits; rate= -8%. |
| Chatterbox | Professional narrator (MIT) | Edge TTS | Active | MIT license; 23 languages. |
| Kokoro | ff_siwis (French) | Edge TTS fallback | Active | Open-source TTS model. |

## Media / Visuals
| Provider | Service | Fallback | Status | Terms / Risk |
|---|---|---|---|---|
| Pexels | Stock video clips | Pixabay → AI Horde → Fallback image | Active | License: Pexels License. |
| Pixabay | Stock video clips / images | Pexels → AI Horde | Active | Pixabay License. |
| Pollinations (AI) | Image-to-video (Seedance 2.5) | Static image | Active | Requires POLLINATIONS_KEY. Unknown moderation. |
| AI Horde | Anonymous image generation | Pexels / Pixabay / Fallback | Active | Anonymous; quality variable (previous 448x768 low-res). MIN_IMAGE_STRICT=true enforced. |
| ModelsLab | Viral BGM (AI-generated unique tracks) | Original in-repo beds (assets/music/) | Optional | Requires MODELSLAB_API_KEY. |

## YouTube / Platform
| Service | Role | Status | Terms / Risk |
|---|---|---|---|
| YouTube API (OAuth 2.0) | Upload + analytics sync + scheduled publish | Active | Requires yt-analytics.readonly scope for CTR tracking. No SLA guarantee for API uptime. |
| Facebook / Instagram (Reels) | Cross-posting (optional) | Conditional | Requires FB_ACCESS_TOKEN, FB_PAGE_ID, INSTAGRAM_USER_ID secrets. Automatically disabled if missing. |
