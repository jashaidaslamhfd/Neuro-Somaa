# French Re-Cut Shorts — Premiere Pro / CapCut Template Specification

This is an editor-agnostic template specification. It can be recreated in Premiere Pro or CapCut without locking the project to a particular application version. The automated Python renderer remains the reproducible source of truth for final batch exports.

## Project settings

| Setting | Value |
|---|---|
| Canvas | 1080 × 1920 vertical, 9:16 |
| Frame rate | 30 fps unless source footage requires a documented alternative |
| Audio sample rate | 48 kHz |
| Target duration | 10 seconds for the re-cut experiment |
| Export | H.264 MP4, vertical, high-quality VBR |
| Captions | Burned-in plus matching SRT |
| Safe title band | Central vertical band; avoid extreme bottom/right UI areas |

## Track layout

| Track | Content | Rule |
|---|---|---|
| V5 | Hook overlay/accent graphics | Only during 0.0–3.2s; no logo intro |
| V4 | Captions | Scene-one hook must match voiceover exactly |
| V3 | Visual subject/diagram | Main explanatory layer |
| V2 | Background texture/gradient | Low contrast behind text |
| V1 | Base footage/image | First frame must already show the topic |
| A3 | Optional hook SFX | One soft pulse/tick; never mask first word |
| A2 | BGM | Instrumental, ducked under speech |
| A1 | French voiceover | Starts at 0.1–0.2s; dominant mix |

## Hook timeline template

| Time | Template action |
|---|---|
| 0.00–0.10s | Hard cut to the strongest topic frame |
| 0.10–0.40s | Start French voice; add one visible movement or reaction |
| 0.40–1.30s | Show the everyday phenomenon and first caption phrase |
| 1.30–2.20s | Add a causal visual cue; continue the hook |
| 2.20–3.00s | Begin the mechanism/payoff; avoid a second setup question |
| 3.00–3.20s | Snap into scene two or mechanism diagram |
| 3.20–6.50s | Explain one mechanism with one visual change every 1–1.5s |
| 6.50–8.50s | Add the memorable concrete detail or cautious qualifier |
| 8.50–10.00s | Return to the opening visual state and finish the loop |

## Caption style

Use a bold, Unicode-safe sans-serif typeface. Recommended starting style is white text, a dark stroke or shadow, and one accent color for the key noun or verb. Keep the first hook to one or two lines. Do not place important words in the extreme bottom or right-side interface zones.

The first caption must be the exact normalized equivalent of the spoken hook. Preserve French characters including `é`, `è`, `ê`, `ç`, `œ`, apostrophes, and question marks. Use phrase-sized reveals rather than fast single-word flashes when the hook is short.

## Motion and transition rules

Use direct cuts, short push-ins, or a single controlled crop movement. Avoid long dissolves and transition effects in the first three seconds. Every visual change must either reveal the phenomenon, show the mechanism, or clarify the consequence. Decorative movement without information should be removed.

For the five re-cuts, the first frame should use the corresponding focal action:

| Re-cut | First-frame action |
|---|---|
| Appetite as an internal clock | Clock flips to 16:00 while stomach silhouette pulses |
| Pain under stress | Neural pain signal flashes, then temporarily dims |
| Learned appetite rhythm | Three meal-time clocks cut rapidly into one rhythm |
| Sleep breathing | Sleeping chest rises while waveform changes |
| Stress and memory | Memory card appears behind a stress waveform |

## Audio mix template

Voiceover begins at 0.1–0.2 seconds and must remain intelligible on a phone speaker. Place BGM under the voice and duck it by approximately 5–8 dB while speech is active. Keep any hook sound effect 10–14 dB below the voice and remove it if the first consonants become unclear.

Do not use lyrics, dialogue, sirens, or a large bass drop in the first three seconds. The BGM should support curiosity with a restrained pulse, light texture, or subtle science ambience.

## Export QA

Before exporting, check the hook at 25% preview size and on a phone speaker. Confirm that the first frame is not black, the first spoken word is not clipped, the first caption is readable, and the visual subject matches the narration. After export, run the repository’s `first-three-second` gate, media probe, final asset audit, and thumbnail quality gate.

## CapCut recreation notes

Create a 9:16 project, place voiceover on the primary audio track, and begin it at `00:00.10–00:00.20`. Use one main visual track plus an overlay track for the hook accent. Set the first caption as a single large text layer, then split later captions into phrase-sized blocks. Keep all key text inside the central safe rectangle and preview the result at the smallest available phone canvas.

## Premiere Pro recreation notes

Create a vertical sequence at 1080×1920. Use a nested “HOOK_0_3S” sequence containing the first visual, the first caption, and the opening audio. Keep the voiceover on a dedicated track so BGM ducking can be automated with keyframes. Create a reusable caption style and a dedicated adjustment layer for the controlled hook push-in. Export the nested hook and full sequence only after the first-three-second checklist passes.

## Batch renderer relationship

The Python batch renderer accepts the same scene, image/video, audio, caption, thumbnail, and experiment metadata contract. Use the automated renderer when reproducibility, logs, strict gates, and five-output batch consistency matter. Use the Premiere/CapCut template when manual art direction or editor review is required. Do not mix different timing contracts between the two workflows.
