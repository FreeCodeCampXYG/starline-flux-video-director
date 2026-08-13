# Creation Handoff

## Result

- Skill: `starline-flux-video-director` v1.2.9
- Job: turn a STAR narrative into a resumable chain of FLUX 3 clips, then package reviewed clips and cover art into an ordered, integrity-checked editing delivery directory.
- Status: release candidate; publication evidence is established only after the feature-branch PR, release and clean-install gates pass.

## Reference skills studied

- BFL `flux-3-keyframes-continuation`: exact media-role and shared-boundary discipline; implemented in schema validation and the sample project.
- BFL `flux-3-generate`/`bfl-api`: strict fields, submit-once polling, all-artifact download; implemented in `scripts/flux_video_loop.py`.
- RunComfy `video-extend`: next-action-only continuation prompts; adapted to each A→B transition.
- ECC `loop-design-check`: bounded, decidable loops and retained human judgment; implemented through confirmation, submission cap and review scorecard.

## Takeaways

- Kept: first-party API boundaries, exact keyframes, bounded retries, human review.
- Adapted: continuous video becomes a shared-frame graph rather than v2v chaining.
- Rejected: provider-specific third-party runtime, stored signed URLs, unbounded retries, automated creative approval.
- Invented: secret-redacted multi-shot resume state, shared-frame path validation, free-promo confirmation mode, a 120-second STAR project, and deterministic delivery packaging with configurable roots and Chinese-safe filenames.

## Advantages and evidence

- Design advantage: adjacent shots cannot accidentally reference different boundary paths; static validation blocks them.
- Design advantage: API Key is read only from the environment and never enters request snapshots.
- Validated advantage: 18/18 local unit tests cover video-loop safety, Playground failure classification, official yt-dlp selection and delivery packaging; packaging tests prove ordered copy, SHA-256 verification, idempotency and conflict refusal. Trigger eval remains 13/13 and package validation passes.
- Validated advantage: v1.2.9 can reproduce `D:\data\AI资料\YYYYMMDD\项目名` on Windows while allowing explicit cross-platform root overrides; it copies rather than moves source artifacts and refuses silent overwrite of different content.
- Hypothesis: shared exact frames should improve visible seam continuity over independent generations; provider-backed and human video review are missing evidence.

## Limits

- v1.2.9 retains explicit one-shot HTTP or SOCKS5 proxy bootstrap. SOCKS5 is normalized to socks5h so GitHub metadata, checksum, binary, and DNS resolution share the same proxy path; proxy values are never persisted.

- `BFL_API_KEY` and seven final keyframe images are not present, by design.
- No paid/free live request was submitted from this process.
- Final titles, narration, exact sync, mixing, and edit approval stay in post-production and human review.
