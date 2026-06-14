---
name: marc-morning-briefing
description: Create Marc's daily operating briefing by integrating Vault-Wahrheit, heartbeat, public voice, Substack/business context, and today's focus into one concise action-oriented message. Use for scheduled morning briefings or when Marc asks what matters today.
---

# Marc Morning Briefing

## Purpose
Turn Marc's always-on systems into a single useful morning decision surface. This is not a generic productivity summary; it should reduce noise and point Marc toward one meaningful action.

## Inputs to gather
1. Current date/time in CET/CEST via `date`.
2. Recent cron outputs / session summaries if available:
   - `nagatha-vault-wahrheit` and `nagatha-vault-wahrheit-deep`
   - `nagatha-heartbeat-core`
   - `nagatha-public-voice-rhythm`
   - `nagatha-substack-monitor`
3. Daily Note / current Vault context if MCP is available.
   - Resolve today's Daily Note through the daily-note resolver (`get_daily_note`) when possible; do not assume the filename format (`YYYY-MM-DD.md` vs `YYYYMMDD.md`).
   - Distinguish explicitly between: missing Daily Note, technically existing but operationally thin Daily Note, and fully operational Daily Note.
   - Parse the current Daily Note as Marc's operating surface: `Aktive Aufgaben`, `Tages-Fokus`, `4-Pillar Priority Snapshot`, `Metrics`, `Inbox / Log`, `15-Minuten-Klarheits-Protokoll`, `Evening Shutdown`, and `Weekly Review Feed`.
   - Treat `Aktive Aufgaben` as commitments; treat `Inbox / Log` as raw capture only.
   - Use the 4-pillar snapshot as the primary source for today's Health, Marriage, AI-Business, and Writing-Priming state.
4. Verify today's Vault-Wahrheit artifact separately.
   - Cron status `ok` is not enough: `[SILENT]` can mean no artifact was written.
   - Read/confirm `05-Bridge/Nagatha/Vault-Wahrheiten/<today>.md` or equivalent before saying there is a Vault-Wahrheit for today.
   - If missing, say plainly that today's briefing is based on partial context / yesterday's truth rather than implying today's truth exists.
5. Known durable priorities:
   - paperclip.ai / 0-human agentic company framework
   - 250k CHF/year business goal
   - public voice: human-first AI educator → anti-hype technology guide → operator
   - fitness, marriage, and reduced system-noise.

## Output format
Keep it short enough to read on Telegram.

```markdown
Guten Morgen Marc.

## Lagebild
- 3–5 bullets only. Mention only what changes today's choices.

## Heute zählt
1. One strategic business/public-voice action.
2. One operational/admin action if needed.
3. One personal/non-work stabilizer if evidence supports it.

## Bewusst nicht anfassen
- One thing to ignore today.

## Nagatha-Spiegel
One uncomfortable but useful observation, grounded in available evidence.

## Nächster konkreter Schritt
A 15–45 minute action Marc can actually do today.
```

## Guardrails
- No motivational fluff.
- No broad todo dump.
- If data is missing, say so and use the durable priorities instead of hallucinating.
- Prefer one real action over five plausible actions.
- If today's main constraint is a decision between options, use `identity-driven-decision-review` before recommending: briefly name what kind of person each option trains, then give one identity-evidence next action.
- If Vault-Wahrheit already produced active tasks for today's Daily Note, explicitly reference those instead of inventing a parallel system.
- If today's Daily Note exists but lacks the operating-surface sections, call it `technically present but not operationally prepared` instead of saying it does not exist.
- If today's Vault-Wahrheit artifact is missing, say that plainly; do not let a cron `ok` / `[SILENT]` run masquerade as a completed reflection.
- If delivered proactively, do not ask more than one question.

## Verification
Before finalizing, check:
- Did you resolve today's Daily Note through the actual daily-note resolver or otherwise account for filename conventions?
- Did you classify the Daily Note as missing, thin, or operational?
- Did you verify whether today's Vault-Wahrheit artifact actually exists, not merely whether the cron job ran?
- Does this help Marc decide what to do today?
- Did you avoid restating yesterday's metrics unless they changed behavior?
- Is the final action concrete enough to start immediately?

## Session-specific references
- `references/2026-05-22-artifact-existence-vs-operating-surface.md` — daily note existed as `YYYYMMDD` but was operationally thin; Vault-Wahrheit cron returned `[SILENT]` with no artifact.
