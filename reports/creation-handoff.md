# Creation Handoff

## Result

- Skill: `starline-flux-video-director` v1.2.0
- Job: turn a STAR narrative into a resumable chain of FHD FLUX 3 i2v clips whose adjacent shots share the exact same boundary frame.
- Status: local, not published.

## Reference skills studied

- BFL `flux-3-keyframes-continuation`: exact media-role and shared-boundary discipline; implemented in schema validation and the sample project.
- BFL `flux-3-generate`/`bfl-api`: strict fields, submit-once polling, all-artifact download; implemented in `scripts/flux_video_loop.py`.
- RunComfy `video-extend`: next-action-only continuation prompts; adapted to each A→B transition.
- ECC `loop-design-check`: bounded, decidable loops and retained human judgment; implemented through confirmation, submission cap and review scorecard.

## Takeaways

- Kept: first-party API boundaries, exact keyframes, bounded retries, human review.
- Adapted: continuous video becomes a shared-frame graph rather than v2v chaining.
- Rejected: provider-specific third-party runtime, stored signed URLs, unbounded retries, automated creative approval.
- Invented: secret-redacted multi-shot resume state, shared-frame path validation, free-promo confirmation mode, and a 120-second STAR project.

## Advantages and evidence

- Design advantage: adjacent shots cannot accidentally reference different boundary paths; static validation blocks them.
- Design advantage: API Key is read only from the environment and never enters request snapshots.
- Validated advantage: 7/7 local unit tests cover boundary mismatch, plan-only missing media, media inlining, signed URL redaction, API-Key gate, and completed-shot resume behavior; trigger eval passed 13/13; package validation passed with zero warnings both in source and an isolated workspace copy.
- Hypothesis: shared exact frames should improve visible seam continuity over independent generations; provider-backed and human video review are missing evidence.

## Limits

- v1.2.0 treats `Generating...` as transient acknowledgement, native Generate `disabled` as an active-render guard, and a matching task card plus stable video URL as completion evidence. It uses human-paced page startup, Reset and media-first input sequencing; handles explicit Rate limited errors through the card Retry then one delayed main Generate; and downloads through the browser or yt-dlp with MP4-header and FFprobe validation.

- `BFL_API_KEY` and seven final keyframe images are not present, by design.
- No paid/free live request was submitted from this process.
- Final titles, narration, exact sync, mixing, and edit approval stay in post-production and human review.
