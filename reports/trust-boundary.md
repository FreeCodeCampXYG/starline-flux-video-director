# Trust and Rollback Boundary

- Secret: `BFL_API_KEY` is read from the environment and never persisted or printed.
- Network: real execution contacts the configured BFL submission/polling URLs and downloads returned artifacts.
- Browser automation: optional Playwright mode uses the user's existing ChromeGo `chrome-data` profile and SOCKS5 proxy; Google login, CAPTCHA, account recovery and anti-bot prompts remain human-controlled. The existing ChromeGo window must be closed before launching Playwright because Chromium profiles are lock-protected.
- Cost/free-promo state: the user owns current-plan verification; the script still requires explicit real-run confirmation and enforces `max_submissions`.
- Media: local keyframes are encoded inline for the request; signed URL query credentials are redacted from snapshots.
- Rollback: local state and artifacts can be deleted. Already submitted provider jobs cannot be canceled, undone, or refunded by this skill.
- Judgment: API `Ready` is technical status only. Human review owns creative acceptance.
- Missing evidence: no provider-backed render or human video review was run in this creation session.
- Current provider result: the first API submission returned HTTP 402 `Insufficient credits`; no task was created and no artifact was charged in this run.
