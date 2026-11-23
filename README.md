# write-human

A single-file agent skill for editing AI-sounding or overly compressed prose into clear, natural human writing while keeping every fact, number, citation, quote, and technical term intact.

## Why another prose skill

Existing de-slop skills tend to fail in two opposite ways:

- **Linter-style rule lists** (`cursor/unslop`) ban dashes, parentheses, mid-sentence colons, and literal engineering nouns (`vector`, `harness`, `surface`, `primitive`), and chop prose into uniform 9-word sentences. They often overwrite clean human text too.
- **Word-and-staging lists** (`blader/humanizer`) catch rhetorical fluff well, yet omit the psycholinguistic compression habits identified in recent LLM readability research (stacked noun compounds, long dependency distances, dropped `that` disambiguators, and inanimate-subject animacy mismatches). Removing fluff without those guardrails can trigger a compression rebound.

`write-human` puts the full editing procedure in one self-contained [SKILL.md](skills/write-human/SKILL.md) (~105 lines).

## How it works

1. **Restraint and precedence first.** Clean human sentences stay byte-identical; if a passage has fewer than two tells and no parsing friction, the skill returns it unchanged. Frozen spans (quotes, code, LaTeX, `\cite`/`\ref`, numbers, dates, units) and explicit user requests outrank every style rule.
2. **Twelve positive reflexes (`W1–W12`).** Each rule gives a pattern to spot, a concrete replacement move, an explicit keep-if condition, and one fact-preserving Before/After pair. `W1–W3` target staging, gratuitous antithesis, and tidy uplift; `W4–W12` fix parsing friction, reference chains, evaluative style words, repeated templates, punctuation jobs, and cadence inside edited spans.
3. **Register-aware without bloat.** Two primary registers (Technical/Academic and Personal/Essay/Narrative) plus a stackable Reply toggle preserve literal terms of art, calibrated hedges, methods passives, and author stance.

## Install and use

```bash
npx skills add https://github.com/gitRasheed/write-human-skill --skill write-human -g
```

Add `-a claude-code`, `-a codex`, or `-a antigravity` for a single harness. Run it with `/write-human` or `$write-human`.

## Blind head-to-head benchmark

Evaluated blind against `blader/humanizer` (v4) and `cursor/unslop` on 6 independent passages (195–218 words each, 12 binary fidelity checks per passage: dense academic/systems paper, engineering RFC with literal `vector`/`harness`/`surface`/`primitive`, opinion essay, threaded Slack reply with prior context, creative non-fiction scene with verbatim quote, and an already-human control postmortem). Three model families generated 54 outputs; five blind judges across three model families scored independently shuffled `A/B/C` triplets on 5 axes (1–5 scale, 75 edited comparisons + 15 control comparisons):

| Skill | Fidelity | Reading Ease | No Tells / No Staccato | Register & Specifics | Naturalness | Mean | #1 Wins (p1–p5) | Hard Fidelity Fails (≤2) | Control Byte-Identical |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **`write-human`** | **4.84** | **4.87** | **4.73** | **4.91** | **4.77** | **4.82** | **53 / 75 (70.7%)** | **0** | **3 / 3** |
| `blader/humanizer` v4 | 4.53 | 4.79 | 4.40 | 4.51 | 4.31 | 4.51 | 18 / 75 (24.0%) | 5 | 3 / 3 |
| `cursor/unslop` | 3.47 | 3.59 | 3.33 | 3.41 | 3.07 | 3.37 | 4 / 75 (5.3%) | 13 *(18 w/ control)* | 0 / 3 |

Every judge and every generator family ranked `write-human` first overall, with a 15/15 sweep on the opinion essay (5.00 mean) and 0 hard fidelity failures across all 90 evaluations. Two unanimous cell losses in that run (a dropped month inside a cliché opener and a leftover sentence-initial `Notably,`) were patched directly into `W1`.

## Research basis

`write-human` draws from ten empirical studies and two prose-craft references, treating their findings as inspection triggers within each study's actual scope:

- **Clark, Martin & Mahowald (2026, `arXiv:2610.29162`):** Six psycholinguistic compression features in frontier LLMs (rare n-grams, dependency length, reduced object relatives, 3+ stacked noun compounds, ad-hoc denominal verbs, inanimate-subject animacy mismatches) and RL length-penalty transfer.
- **Zamaraeva et al. (2026, `arXiv:2610.10092`):** ~7× rise in `rather than` across ACL-style papers (2019→2026); stance asymmetry, postposed `X, not Y`, and modesty disavowals drive reader annoyance.
- **Li & Xu (2026, `arXiv:2610.14578`):** Uniform Information Density preference optimization: smooth local surprisal transitions while allowing wide global density range.
- **El Attar et al. (2026, `arXiv:2606.04177`):** 284 linguistic features across 30 LLMs and 10 domains; argues against brittle punctuation rules and synonym cycling.
- **Reinhart et al. (PNAS 2025, `arXiv:2410.16107`):** 66 Biber features across instruction-tuned vs. base models (overuse of present/past participial clauses and nominalizations; underuse of `because`).
- **Chakrabarty, Laban & Wu (CHI 2025, `arXiv:2409.14509`):** 8,035 professional-writer edits on 1,057 LLM paragraphs (7 idiosyncrasy categories, abstract noun-pair templates, specificity).
- **Russell, Karpinska & Iyyer (ACL 2025, `arXiv:2501.15654`):** Frequent LLM users detect AI prose at 299/300 accuracy even after paraphrasing and buzzword scrubbing; exposes upbeat wrap-ups, homogeneous quotes, and failed fake casualness.
- **Kobak et al. (*Science Advances* 2025, `arXiv:2406.07016`)** & **Juzek & Ward (COLING 2025, `arXiv:2412.11385`):** Excess LLM vocabulary in 15M PubMed abstracts is predominantly style verbs (66%) and evaluative adjectives (14%).
- **Shaib, Elazar, Li & Wallace (EMNLP 2024, `arXiv:2407.00211`):** Memorized 4–8 token POS syntactic templates persist through alignment and survive vocabulary swaps.
- **Gopen & Swan (*American Scientist* 1990)** & **Williams & Bizup (*Style: Lessons in Clarity and Grace*):** Given-before-New Topic Position and Stress Position cohesion.
