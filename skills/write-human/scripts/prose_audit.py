#!/usr/bin/env python3
"""Deterministic prose audit & before/after delta tripwire for the write-human skill.

Zero external dependencies (Python 3 stdlib only).
Counts are tripwires that send an editor back to judge function at flagged sentences,
never quotas to optimize blindly.

Usage:
  python3 prose_audit.py --check <file> [--json]
  python3 prose_audit.py --before <old_file> --after <new_file> [--json]
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

# Frozen token patterns (checked for exact preservation in before/after mode)
NUM_RE = re.compile(r"(?<![\w\\])(?<!\w\.)(?<!_\{)(?:(?<![\w)\]}])-)?\d(?:[\d,._]*\d)?")
CITE_RE = re.compile(r"\\[A-Za-z]*cite[A-Za-z]*\*?(?:\[[^\]]*\])*\{([^}]*)\}")
REF_RE = re.compile(r"\\(?:[A-Za-z]*ref|label)\*?\{([^}]*)\}")
INLINE_CODE_RE = re.compile(r"(?<!`)`([^`\n]+)`(?!`)")
FENCE_RE = re.compile(r"^[ \t]*(```|~~~).*?^[ \t]*\1[ \t]*$", re.S | re.M)
URL_RE = re.compile(r"https?://[^\s<>{}\"')\]]+")
MATH_RE = re.compile(r"(?<![\\$])\$(?!\s)[^$\n]+?(?<!\s)\$(?!\d)|\\\(.+?\\\)|\\\[.+?\\\]", re.S)
# Identifiers: any token with a digit, underscore, inner capital or two capitals
IDENT_RE = re.compile(r"\b[A-Za-z][\w.-]*(?:\d|_|(?<=[a-z])[A-Z]|[A-Z]{2})[\w-]*")
# Advisory only: Capitalized words that never occur lowercased in either text
NAME_RE = re.compile(r"\b[A-Z][a-z]{2,}\b")
ADVISORY = ("names_advisory",)
QUOTES = {0x2018: "'", 0x2019: "'", 0x201C: '"', 0x201D: '"', 0x2212: "-"}

# Antithesis family (Zamaraeva et al. 2026). Matched per sentence, in priority order,
# overlapping spans counted once. NOISY keys are the two the paper measured at 38-94% precision.
_NOT = r"(?:\bnot|n't)\b"
_COP = r"(?:\b(?:is|are|was|were)\s+not|\b(?:is|are|was|were)n't|'s\s+not|'re\s+not)\b"
ANTITHESIS_PATTERNS: dict[str, re.Pattern[str]] = {
    "not_only_just_merely_but": re.compile(
        _NOT + r"\s+(?:only|just|merely|simply)\b.{1,160}?(?:\bbut\b|\balso\b|[,;]\s*(?:it|they|this)\b)", re.I
    ),
    "its_not_x_its_y": re.compile(
        _COP + r".{1,80}?[,;:\u2014]\s*(?:it|this|that|they|these)(?:'s|'re|\s+(?:is|are|was|were))\b", re.I
    ),
    "not_v_we_v": re.compile(
        r"\b(?:do|does|did)(?:\s+not|n't)\b.{1,80}?[;:\u2014]\s*(?:we|it|they)\b", re.I
    ),
    "this_is_not_to_say": re.compile(r"\b(?:this|that|which)\s+is\s+not\s+to\s+say\b", re.I),
    "less_about_more_about": re.compile(
        r"\bless\s+about\b.{1,60}?\bmore\s+about\b|\bnot\s+so\s+much\b.{1,60}?\bas\b", re.I
    ),
    "rather_than": re.compile(r"\brather\s+than\b", re.I),
    "instead_of": re.compile(r"\binstead\s+of\b", re.I),
    "as_opposed_to": re.compile(r"\bas\s+opposed\s+to\b", re.I),
    "not_x_but_y": re.compile(
        _NOT + r"[^;:]{1,80}?\bbut\s+(?!(?:we|i|you|he|she|there|then|still|also|only)\b)", re.I
    ),
    "postposed_not": re.compile(
        r"(?:[,;(\u2014]\s*(?:and\s+)?|\s+and\s+)not\s+"
        r"(?!(?:to\s+mention|surprisingly|unlike|least|all|even|yet|including|counting|that|"
        r"necessarily|always|unexpectedly|coincidentally)\b)[a-z]+\b",
        re.I,
    ),
}
NOISY_ANTITHESIS = ("not_x_but_y", "postposed_not", "split_sentence_pivot")
# Heuristics of ours, not the paper's: negated sentence then a corrective restart
SPLIT_NEG_RE = re.compile(_COP + r"|\b(?:do|does|did)\s+not\b|\b(?:do|does|did)n't\b", re.I)
SPLIT_PIVOT_RE = re.compile(
    r"^(?:(?:It|This|That|They|These|Those)(?:'s|'re|\s+(?:is|are|was|were))\b|(?:Rather|Instead),)"
)
SELF_RE = re.compile(r"\b(?:we|our|this\s+(?:paper|work|study|result|finding|analysis|evidence))\b", re.I)
STATUS_RE = re.compile(
    r"\b(?:tested|mechanism|guarantee|definitive|established|conclusive|causal|proof|"
    r"general\s+(?:account|method|claim|result)|final|complete)\b",
    re.I,
)

# Staging, residue & evaluative style-word tripwires
STAGING_PATTERNS: dict[str, re.Pattern[str]] = {
    "chatbot_residue": re.compile(
        r"\b(?:great question|i hope this helps|let me know if you(?:'d| would) like)\b|\b(?:certainly|of course)!",
        re.I,
    ),
    "staged_runup": re.compile(
        r"\b(?:let's dive in|here's the thing|when it comes to|it(?:'s| is) (?:important|worth) (?:to note|noting)|the hard part is|at its core|what really matters|in today's (?:fast-paced|modern|digital))\b",
        re.I,
    ),
    "tidy_uplift": re.compile(
        r"\bultimately,|\b(?:in conclusion|stands as a testament|bright future|unlock(?:s|ing)?\s+(?:new|limitless|full)|paving the way|step in the right direction)\b",
        re.I,
    ),
    "style_words": re.compile(
        r"\b(?:delve[sd]?|delving|underscore[sd]?\s+(?:the|that|how|its|a|an|why)|underscoring|showcase[sd]?|showcasing|pivotal|crucial|intricate|intricacies|tapestry|interplay|groundbreaking|meticulous(?:ly)?|seamlessly|leverage[sd]?|leveraging|harness(?:es|ed|ing)?\s+(?:the|its|their|this|these)|boasts?|serves as|stands as(?! a testament))\b",
        re.I,
    ),
    "trailing_ing_tail": re.compile(
        r",\s+(?:highlighting|underscoring|emphasizing|ensuring|reflecting|symbolizing|contributing|cultivating|fostering|encompassing|showcasing|enabling|streamlining|facilitating|allowing|making|creating|leading)\b",
        re.I,
    ),
    "leading_ing_opener": re.compile(
        r"^(?:Leveraging|Harnessing|Utilizing|Combining|Building on|Drawing on|Driven by|Rooted in|Designed to|Implemented for)\b"
    ),
    "mechanical_opener": re.compile(
        r"^(?:Furthermore|Moreover|Additionally|Consequently|Nonetheless|Nevertheless|Notably|Importantly|Crucially),\s"
    ),
    "bare_this_opener": re.compile(
        r"^This\s+(?:is|was|means|makes|shows|allows|enables|creates|leads|causes|results|prevents|limits|ensures)\b"
    ),
    "abstract_noun_pair": re.compile(
        r"\ba\s+(?:sense|mix|blend|tapestry|web|balance|combination)\s+of\s+[a-z]+\s+and\s+[a-z]+\b",
        re.I,
    ),
}

HYPHEN_STACK_RE = re.compile(
    r"(?<![\w/-])(?!(?:state-of-the-art|end-to-end|out-of-the-box|one-to-one|many-to-many)\b)"
    r"[a-zA-Z]+-[a-zA-Z]+(?:-[a-zA-Z]+)+\b"
)
EM_DASH_RE = re.compile(r"—|(?<!-)---(?!-)|(?<=\s)--(?=\s)")
SPACED_EN_DASH_RE = re.compile(r"(?<=[A-Za-z,]\s)–(?=\s[A-Za-z])")
LATEX_ENV_RE = re.compile(
    r"\\begin\{(equation|align|gather|table|tabular|figure|verbatim|lstlisting|tikzpicture|algorithm)(\*?)\}"
    r".*?\\end\{\1\2\}",
    re.S,
)
OPTIONAL_THAT_RE = re.compile(r"\bthat\b", re.I)


def strip_non_prose(text: str, strip_inline_code: bool = True) -> str:
    """Remove code, YAML frontmatter, rules, table separators and LaTeX non-prose for prose metrics."""
    s = text.replace("\r\n", "\n").translate(QUOTES)
    is_latex = r"\documentclass" in s or r"\begin{document}" in s
    s = re.sub(r"^---\n.*?\n---\n", "", s, count=1, flags=re.S)
    s = FENCE_RE.sub("\n\n", s)
    if strip_inline_code:
        s = re.sub(r"`+[^`\n]+`+", " CODE ", s)
    if r"\begin{document}" in s:
        s = s.split(r"\begin{document}", 1)[1]
    if r"\begin{thebibliography}" in s:
        s = s.split(r"\begin{thebibliography}", 1)[0]
    if is_latex:
        s = re.sub(r"(?<!\\)%.*$", "", s, flags=re.M)
        s = LATEX_ENV_RE.sub("\n\n", s)
    s = re.sub(r"^[ \t]*[-*_|: \t]{3,}[ \t]*$", "", s, flags=re.M)
    return s


_ABBR = r"e\.g|i\.e|cf|etc|vs|approx|resp|Dr|Mr|Mrs|Ms|Prof|Figs?|Eqs?|Secs?|Tabs?|Refs?|No(?=\.\s\d)|al|[A-Z]"


def split_sentences(prose: str) -> list[str]:
    """Block-aware splitter: headings, list items, table rows and blank lines end a sentence."""
    s = re.sub(r"^\s*#+\s+.*$", "\n\n", prose, flags=re.M)
    s = re.sub(r"^\s*\|.*\|\s*$", "\n\n", s, flags=re.M)
    s = re.sub(r"\\(?:\w*section|paragraph|title|caption|author|date)\*?(?:\[[^\]]*\])?\{[^}]*\}", "\n\n", s)
    s = re.sub(r"\\(?:[A-Za-z]*cite[A-Za-z]*|[A-Za-z]*ref|label)\*?(?:\[[^\]]*\])*\{[^}]*\}", " ", s)
    s = MATH_RE.sub(" MATH ", s)
    s = URL_RE.sub(" URL ", s)
    s = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?\{([^}]*)\}", r"\1", s)  # keep \emph{...} text
    s = re.sub(r"\\[a-zA-Z]+\*?", " ", s)
    out: list[str] = []
    for block in re.split(r"\n\s*\n|^[ \t]*(?:[-*+>]|\d+[.)])[ \t]+", s, flags=re.M):
        b = re.sub(r"\s+", " ", block).strip()
        b = re.sub(rf"\b({_ABBR})\.", r"\1<DOT>", b)
        b = re.sub(r"([.!?][\"')\]*_]*)\s+(?=[\"'(\[*_]*[A-Z0-9])", r"\1<SPLIT>", b)
        out += [x.replace("<DOT>", ".").strip() for x in b.split("<SPLIT>")]
    return [x for x in out if re.search(r"[A-Za-z0-9]", x)]


def sentence_lengths(sentences: list[str]) -> list[int]:
    return [len(re.findall(r"[A-Za-z0-9'-]+", s)) for s in sentences]


def uniform_runs(lengths: list[int], tolerance: int = 3, min_run: int = 3) -> int:
    """Count overlapping runs of >=min_run consecutive sentences within +-tolerance words."""
    if len(lengths) < min_run:
        return 0
    runs = 0
    for i in range(len(lengths) - min_run + 1):
        window = lengths[i : i + min_run]
        if max(window) - min(window) <= tolerance:
            runs += 1
    return runs


def _keys(pattern: re.Pattern[str], text: str) -> list[str]:
    return [k.strip() for grp in pattern.findall(text) for k in grp.split(",") if k.strip()]


def frozen_inventory(text: str) -> dict[str, collections.Counter[str]]:
    text = text.replace("\r\n", "\n").translate(QUOTES)
    fences = [m.group(0).strip() for m in FENCE_RE.finditer(text)]
    body = FENCE_RE.sub(" ", text)
    code = INLINE_CODE_RE.findall(body)
    bare = URL_RE.sub(" ", re.sub(r"`+[^`\n]+`+", " ", body))
    bare = CITE_RE.sub(" ", REF_RE.sub(" ", bare))
    return {
        "numbers": collections.Counter(NUM_RE.findall(body)),
        "cites": collections.Counter(_keys(CITE_RE, text)),
        "refs": collections.Counter(_keys(REF_RE, text)),
        "inline_code": collections.Counter(code),
        "code_blocks": collections.Counter(fences),
        "math": collections.Counter(re.sub(r"\s+", " ", m) for m in MATH_RE.findall(body)),
        "urls": collections.Counter(u.rstrip(".,;:") for u in URL_RE.findall(body)),
        # presence only: a rewrite may legitimately repeat a name more or less often
        "identifiers": collections.Counter(set(IDENT_RE.findall(MATH_RE.sub(" ", bare)))),
        "names_advisory": collections.Counter(set(NAME_RE.findall(MATH_RE.sub(" ", bare)))),
        "_words": collections.Counter(set(re.findall(r"[A-Za-z][\w-]*", bare))),
    }


def find_antithesis(sents: list[str]) -> tuple[dict[str, int], list[dict[str, Any]]]:
    counts: collections.Counter[str] = collections.Counter()
    hits: list[dict[str, Any]] = []
    for i, s in enumerate(sents):
        taken: list[tuple[int, int]] = []
        for key, pat in ANTITHESIS_PATTERNS.items():
            for m in pat.finditer(s):
                if any(m.start() < e and b < m.end() for b, e in taken):
                    continue
                taken.append(m.span())
                counts[key] += 1
                dis = bool(SELF_RE.search(s) and STATUS_RE.search(s, m.end()))
                hits.append({"pattern": key, "sentence": s, "disavowal": dis})
        if not taken and i + 1 < len(sents) and SPLIT_NEG_RE.search(s) and SPLIT_PIVOT_RE.match(sents[i + 1]):
            counts["split_sentence_pivot"] += 1
            hits.append({"pattern": "split_sentence_pivot", "sentence": s + " " + sents[i + 1], "disavowal": False})
    return dict(counts), hits


def analyze_text(text: str) -> dict[str, Any]:
    prose = strip_non_prose(text)
    sents = split_sentences(prose)
    lengths = sentence_lengths(sents)
    n_words = sum(lengths)
    mean_len = n_words / len(lengths) if lengths else 0.0
    sd_len = (
        math.sqrt(sum((x - mean_len) ** 2 for x in lengths) / len(lengths))
        if len(lengths) > 1
        else 0.0
    )
    per_1k = 1000.0 / n_words if n_words else 0.0

    antithesis_breakdown, antithesis_hits = find_antithesis(sents)
    antithesis_total = sum(antithesis_breakdown.values())
    strict_total = sum(v for k, v in antithesis_breakdown.items() if k not in NOISY_ANTITHESIS)

    staging_hits: dict[str, list[str]] = {}
    for k, pat in STAGING_PATTERNS.items():
        matches = [m.group(0).strip() for s in sents for m in pat.finditer(s)]
        if matches:
            staging_hits[k] = matches
    clean = " ".join(sents)
    that_count = len(OPTIONAL_THAT_RE.findall(clean))

    return {
        "word_count": n_words,
        "sentence_count": len(sents),
        "sentence_len_mean": round(mean_len, 1),
        "sentence_len_sd": round(sd_len, 1),
        "sentence_len_cv": round(sd_len / mean_len, 2) if mean_len else 0.0,
        "sentence_len_min": min(lengths) if lengths else 0,
        "sentence_len_max": max(lengths) if lengths else 0,
        "uniform_length_runs": uniform_runs(lengths),
        "antithesis_total": antithesis_total,
        "antithesis_strict_total": strict_total,
        "antithesis_per_1k": round(antithesis_total * per_1k, 2),
        "rather_than_per_1k": round(antithesis_breakdown.get("rather_than", 0) * per_1k, 2),
        "antithesis_breakdown": antithesis_breakdown,
        "antithesis_disavowals": sum(h["disavowal"] for h in antithesis_hits),
        "sentence_initial_rather_than": sum(
            bool(re.match(r"(?:Rather than|Instead of)\b", s)) for s in sents
        ),
        "antithesis_hits": antithesis_hits[:40],
        "staging_counts": {k: len(v) for k, v in staging_hits.items()},
        "staging_samples": {k: v[:5] for k, v in staging_hits.items()},
        "em_dashes": len(EM_DASH_RE.findall(prose)),
        "spaced_en_dashes": len(SPACED_EN_DASH_RE.findall(prose)),
        "hyphen_stacks_3plus": HYPHEN_STACK_RE.findall(clean),
        "that_count": that_count,
        "that_per_1k": round(that_count * per_1k, 1),
        "sentences": sents,
    }


def diff_inventories(
    old_inv: dict[str, collections.Counter[str]], new_inv: dict[str, collections.Counter[str]]
) -> dict[str, list[str]]:
    diffs: dict[str, list[str]] = {}
    for key in old_inv:
        if key.startswith("_"):
            continue
        changes = []
        for token in sorted(set(old_inv[key]) | set(new_inv[key])):
            a, b = old_inv[key][token], new_inv[key][token]
            if key in ADVISORY and (
                token.lower() in old_inv["_words"] or token.lower() in new_inv["_words"]
            ):
                continue  # an ordinary word that was capitalized at a sentence start
            if a != b:
                shown = token if len(token) <= 60 else token[:57] + "..."
                changes.append(f"{shown!r}: {a} -> {b}")
        if changes:
            diffs[key] = changes
    return diffs


def print_single_report(path: str, stats: dict[str, Any]) -> None:
    print(f"=== Prose Audit: {path} ===")
    print(
        f"Words: {stats['word_count']} | Sentences: {stats['sentence_count']} | "
        f"Length mean/SD/range: {stats['sentence_len_mean']} / {stats['sentence_len_sd']} / "
        f"{stats['sentence_len_min']}-{stats['sentence_len_max']}"
    )
    print(
        f"Uniform-length runs (3+ within +-3w): {stats['uniform_length_runs']} | "
        f"Em dashes: {stats['em_dashes']} | 'that' /1k: {stats['that_per_1k']}"
    )
    print(
        f"Antithesis family total: {stats['antithesis_total']} ({stats['antithesis_per_1k']}/1k, "
        f"disavowals {stats['antithesis_disavowals']}) {stats['antithesis_breakdown']}"
    )
    for h in stats["antithesis_hits"][:10]:
        print(f"    [{h['pattern']}{' DISAVOWAL' if h['disavowal'] else ''}] {h['sentence'][:160]}")
    if stats["staging_counts"]:
        print("Tripwires:")
        for k, cnt in stats["staging_counts"].items():
            print(f"  - {k}: {cnt} {stats['staging_samples'][k]}")
    else:
        print("Tripwires: none")
    if stats["hyphen_stacks_3plus"]:
        print(f"3+ hyphenated stacks: {stats['hyphen_stacks_3plus'][:8]}")


def _key(sentence: str) -> str:
    return re.sub(r"\s+", " ", sentence).strip()


def compute_delta(old_text: str, new_text: str) -> dict[str, Any]:
    old, new = analyze_text(old_text), analyze_text(new_text)
    inv_diffs = diff_inventories(frozen_inventory(old_text), frozen_inventory(new_text))
    old_keys = collections.Counter(_key(s) for s in old["sentences"])
    new_keys = collections.Counter(_key(s) for s in new["sentences"])
    unchanged = sum((old_keys & new_keys).values())
    unchanged_pct = round(100.0 * unchanged / len(old["sentences"]), 1) if old["sentences"] else 100.0
    len_delta_pct = (
        round(100.0 * (new["word_count"] - old["word_count"]) / old["word_count"], 1)
        if old["word_count"]
        else 0.0
    )
    ob, nb = old["antithesis_breakdown"], new["antithesis_breakdown"]
    rose = sorted(k for k in nb if nb[k] > ob.get(k, 0))

    warnings: list[str] = []
    if any(k not in ADVISORY for k in inv_diffs):
        warnings.append("fidelity_diff")
    if new["antithesis_total"] > old["antithesis_total"]:
        warnings.append(f"antithesis_rose ({old['antithesis_total']} -> {new['antithesis_total']})")
    elif rose:
        warnings.append(f"antithesis_form_swap ({', '.join(rose)})")
    if new["antithesis_per_1k"] > 1.2 * old["antithesis_per_1k"] and new["antithesis_total"] >= 2:
        warnings.append(f"antithesis_rate_rose ({old['antithesis_per_1k']} -> {new['antithesis_per_1k']} /1k)")
    if len_delta_pct < -25.0:
        warnings.append(f"compression_rebound_risk ({len_delta_pct:+.1f}% words)")
    if len_delta_pct > 25.0:
        warnings.append(f"expansion ({len_delta_pct:+.1f}% words)")
    if old["that_count"] >= 4 and new["that_per_1k"] < 0.75 * old["that_per_1k"]:
        warnings.append(f"that_rate_drop ({old['that_per_1k']} -> {new['that_per_1k']} /1k)")
    if new["sentence_count"] >= 4 and (new["sentence_len_sd"] < 3.5 or new["sentence_len_cv"] < 0.3):
        warnings.append(f"low_cadence_variance (SD={new['sentence_len_sd']}, CV={new['sentence_len_cv']})")
    if new["uniform_length_runs"] > old["uniform_length_runs"]:
        warnings.append(f"uniform_runs_rose ({old['uniform_length_runs']} -> {new['uniform_length_runs']})")
    for k in ("em_dashes", "spaced_en_dashes"):
        if new[k] > old[k]:
            warnings.append(f"{k}_rose ({old[k]} -> {new[k]})")
    staged = sorted(k for k, v in new["staging_counts"].items() if v > old["staging_counts"].get(k, 0))
    if staged:
        warnings.append(f"staging_rose ({', '.join(staged)})")
    return {
        "before": {k: v for k, v in old.items() if k != "sentences"},
        "after": {k: v for k, v in new.items() if k != "sentences"},
        "schema": 2,
        "fidelity_diffs": inv_diffs,
        "word_delta_pct": len_delta_pct,
        "untouched_sentences": unchanged,
        "untouched_pct": unchanged_pct,
        "warnings": warnings,
    }


def print_delta_report(before_path: str, after_path: str, d: dict[str, Any]) -> None:
    old, new, inv_diffs = d["before"], d["after"], d["fidelity_diffs"]
    print(f"=== Before -> After Audit ({before_path} -> {after_path}) ===")
    print(
        f"Words: {old['word_count']} -> {new['word_count']} ({d['word_delta_pct']:+.1f}%) | "
        f"Untouched sentences: {d['untouched_sentences']}/{old['sentence_count']} ({d['untouched_pct']}%)"
    )
    print(
        f"Sentence length mean/SD: {old['sentence_len_mean']}/{old['sentence_len_sd']} -> "
        f"{new['sentence_len_mean']}/{new['sentence_len_sd']} | "
        f"Uniform runs: {old['uniform_length_runs']} -> {new['uniform_length_runs']}"
    )
    print(
        f"Antithesis family total: {old['antithesis_total']} -> {new['antithesis_total']} "
        f"({old['antithesis_per_1k']} -> {new['antithesis_per_1k']} /1k; after: {new['antithesis_breakdown']})"
    )
    for h in new["antithesis_hits"][:10]:
        print(f"    [{h['pattern']}{' DISAVOWAL' if h['disavowal'] else ''}] {h['sentence'][:160]}")
    print(
        f"Em dashes: {old['em_dashes']} -> {new['em_dashes']} | "
        f"'that' /1k: {old['that_per_1k']} -> {new['that_per_1k']}"
    )
    if inv_diffs:
        print("FIDELITY DIFFS (verify every change):")
        for k, items in inv_diffs.items():
            print(f"  - {k}: {', '.join(items[:12])}")
    else:
        print("Fidelity (numbers, cites, refs, code, math, urls, identifiers): IDENTICAL")
    if new["staging_counts"]:
        print(f"Remaining tripwires: {new['staging_counts']}")
    if d["warnings"]:
        print(f"TRIPWIRES TO INSPECT: {', '.join(d['warnings'])}")
    else:
        print("Tripwires: clean")


def main() -> int:
    parser = argparse.ArgumentParser(description="Deterministic prose audit for write-human.")
    parser.add_argument("--check", help="Audit a single file.")
    parser.add_argument("--before", help="Original file before editing.")
    parser.add_argument("--after", help="Edited file after editing.")
    parser.add_argument("--json", action="store_true", help="Emit JSON output.")
    parser.add_argument("--strict", action="store_true", help="Exit 2 when any delta warning fires.")
    args = parser.parse_args()

    if args.check:
        text = Path(args.check).read_text(encoding="utf-8")
        stats = analyze_text(text)
        stats_out = {k: v for k, v in stats.items() if k != "sentences"}
        if args.json:
            print(json.dumps(stats_out, indent=2))
        else:
            print_single_report(args.check, stats)
        return 0

    if args.before and args.after:
        old_text = Path(args.before).read_text(encoding="utf-8")
        new_text = Path(args.after).read_text(encoding="utf-8")
        delta = compute_delta(old_text, new_text)
        if args.json:
            print(json.dumps(delta, indent=2))
        else:
            print_delta_report(args.before, args.after, delta)
        return 2 if args.strict and delta["warnings"] else 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
