# write-human

A single-file agent skill ([SKILL.md](skills/write-human/SKILL.md)) for editing AI-sounding or overly compressed prose into clear human writing while keeping every fact, number, citation, quote, and technical term intact.

## How it works

1. **Leave clean text alone.** Returns a passage unchanged when it has fewer than two tells and no parsing friction. Frozen spans (quotes, code, LaTeX, `\cite`/`\ref`, numbers, dates, units) and explicit user instructions outrank every style rule.
2. **Fix AI staging and parsing friction.** Applies twelve rules (`W1–W12`) that cut chatbot wrappers, gratuitous antithesis, and tidy uplift, then unpack stacked noun compounds, long dependencies, ambiguous references, and flat cadence inside edited spans. Each rule includes a keep-if condition.
3. **Preserve register and domain terms.** Supports Technical/Academic and Personal/Essay/Narrative registers plus a stackable Reply toggle, keeping literal engineering terms (`vector`, `test harness`, `API surface`, `primitive`), calibrated hedges, and the author's stance intact.
4. **Verify before returning.** Checks that numbers, citations, quotes, and code spans survived, total antithesis did not rise, and the edit did not strip glue words into staccato sentences.

## Install and use

```bash
npx skills add https://github.com/gitRasheed/write-human-skill --skill write-human -g
```

Add `-a claude-code`, `-a codex`, or `-a antigravity` for a single harness. Run it with `/write-human` or `$write-human`, optionally with a file path:

```text
/write-human docs/rfc.md
```
