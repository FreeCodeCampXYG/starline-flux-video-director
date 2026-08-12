# Prior-Art Research

- Researched at: 2026-08-12
- Queries: `continuous AI video generation`, `video storyboard API workflow`, `image to video continuity`
- Catalogs: skills.sh, SkillsMP, GitHub source
- Proxy: local HTTP proxy at `127.0.0.1:10808`
- Rating evidence: unavailable; installs and repository stars are not ratings

| Candidate | Role | Mutable signal observed 2026-08-12 | Mechanism learned | Adopted | Deliberately rejected |
|---|---|---:|---|---|---|
| Black Forest Labs `flux-3-keyframes-continuation` | first-party trust anchor | official BFL source; catalog rating unavailable | exact keyframes, shared continuity variables, prompt from the transition | shared boundary-frame chain and strict media roles | no dependence on v2v because user chose start/end frames |
| Black Forest Labs `flux-3-generate` + `bfl-api` | first-party execution anchor | official BFL source; catalog rating unavailable | strict schema, submit once, 6s polling, terminal states, download all expiring artifacts | deterministic runner, bounded retry, immediate downloads, resumable state | no automatic draft enhancement selection without human choice |
| `prime-skills/runcomfy-agent-skills@video-extend` | popularity anchor | skills.sh about 339.5K installs | continuation prompt describes only what happens next; preserve motion and identity | applied semantically to transitions between shared frames | rejected provider-specific RunComfy/Veo CLI and token flow |
| `fal-ai-community/skills@cinematography` and `storytelling` | complementary direction anchors | skills.sh about 528 and 217 installs | separate narrative beat design from camera craft | STAR beat map plus one-event-per-shot camera contract | rejected broad multi-provider routing and stylistic presets unrelated to this story |
| `affaan-m/ECC@loop-design-check` | loop safety anchor | SkillsMP repository stars are repo-level, not skill quality | decidable stop, retry cap, human judgment before consequential action | max submissions, double execute confirmation, human review verdict | rejected autonomous self-approval and unbounded improvement loop |

## Keep / adapt / reject / invent

- Keep: exact shared frames, strict request schema, submit-once polling, immediate artifact preservation, human creative review.
- Adapt: replace generic continuation with an A→B, B→C boundary-frame graph; use Chinese operational messages and Windows-friendly Python standard library.
- Reject: direct secrets in commands, provider-specific third-party CLIs, automatic high-cost reruns, generated CJK titles, and acceptance based only on API `Ready`.
- Invent: project-level shared-frame validator, secret-redacted request snapshots, free-promo/paid-run explicit confirmation, submission cap, STAR example, and safe resume across a multi-shot chain.

## Evidence limits

- Catalog metrics were observed on 2026-08-12 and can drift.
- SkillsMP queries were noisy; GitHub source and official BFL skills carry more weight for API behavior.
- No live BFL provider render has been run because `BFL_API_KEY` was intentionally not available to this process. Visual-quality claims remain missing evidence.

