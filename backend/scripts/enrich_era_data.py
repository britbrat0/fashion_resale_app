#!/usr/bin/env python3
"""
Enrich era_data.json using two sources:
  1. Wikipedia: scrape "Xs in fashion" articles for brand/garment mentions
  2. Claude API: ask Claude to expand every descriptor category per era

Usage (from backend/):
  python scripts/enrich_era_data.py [--dry-run]
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ── Config ────────────────────────────────────────────────────────────────────

ERA_DATA_PATH = Path(__file__).parent.parent / "app" / "vintage" / "era_data.json"

DESCRIPTOR_CATEGORIES = [
    "brands", "fabrics", "prints", "silhouettes",
    "colors", "aesthetics", "key_garments",
]

# Wikipedia articles to try per era (decade → article slug)
WIKI_ARTICLES = {
    "1700-1749": ["1700s_in_fashion", "Rococo_fashion"],
    "1750-1799": ["1750s_in_fashion", "1760s_in_fashion", "1770s_in_fashion", "1780s_in_fashion", "1790s_in_fashion"],
    "1800-1824": ["1800s_in_fashion", "1810s_in_fashion", "1820s_in_fashion", "Regency_era"],
    "1825-1849": ["1830s_in_fashion", "1840s_in_fashion"],
    "1850-1874": ["1850s_in_fashion", "1860s_in_fashion", "1870s_in_fashion", "Victorian_fashion"],
    "1875-1899": ["1880s_in_fashion", "1890s_in_fashion"],
    "1900s":     ["1900s_in_fashion", "Edwardian_fashion"],
    "1910s":     ["1910s_in_fashion"],
    "1920s":     ["1920s_in_fashion", "Flapper"],
    "1930s":     ["1930s_in_fashion"],
    "1940s":     ["1940s_in_fashion", "Utility_clothing"],
    "1950s":     ["1950s_in_fashion"],
    "early-1960s": ["1960s_in_fashion", "Mod_(subculture)"],
    "late-1960s":  ["1960s_in_fashion", "Hippie"],
    "early-1970s": ["1970s_in_fashion", "Glam_rock"],
    "late-1970s":  ["1970s_in_fashion", "Disco", "Punk_fashion"],
    "early-1980s": ["1980s_in_fashion", "New_wave_music"],
    "late-1980s":  ["1980s_in_fashion", "Power_dressing"],
    "early-1990s": ["1990s_in_fashion", "Grunge_fashion"],
    "late-1990s":  ["1990s_in_fashion", "Minimalism_(fashion)"],
    "early-2000s": ["2000s_in_fashion", "Y2K_fashion"],
    "late-2000s":  ["2000s_in_fashion", "Boho-chic"],
    "early-2010s": ["2010s_in_fashion"],
    "late-2010s":  ["2010s_in_fashion"],
}


# ── Wikipedia scraper ─────────────────────────────────────────────────────────

def _fetch_wiki_text(slug: str) -> str:
    url = f"https://en.wikipedia.org/wiki/{slug}"
    headers = {"User-Agent": "era-enrichment-bot/1.0 (educational project)"}
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            return ""
        soup = BeautifulSoup(resp.text, "html.parser")
        # Remove infoboxes and references
        for tag in soup.select(".infobox, .reflist, .navbox, [class*='sidebar']"):
            tag.decompose()
        # Get main content paragraphs
        content = soup.select("#mw-content-text p, #mw-content-text li")
        return " ".join(el.get_text(" ", strip=True) for el in content)
    except Exception as e:
        print(f"  Wikipedia fetch failed for {slug}: {e}")
        return ""


def scrape_wikipedia_for_era(era_id: str) -> str:
    """Return combined Wikipedia text for an era."""
    slugs = WIKI_ARTICLES.get(era_id, [])
    if not slugs:
        return ""
    texts = []
    for slug in slugs:
        text = _fetch_wiki_text(slug)
        if text:
            texts.append(text[:4000])  # cap per article
        time.sleep(0.5)
    return "\n\n".join(texts)[:8000]  # cap total


# ── Claude enrichment ─────────────────────────────────────────────────────────

def enrich_era_with_claude(era: dict, wiki_context: str, client) -> dict:
    """Ask Claude to expand all descriptor categories for one era."""

    current = {cat: era.get(cat, []) for cat in DESCRIPTOR_CATEGORIES}
    current_json = json.dumps(current, indent=2)

    wiki_section = ""
    if wiki_context.strip():
        wiki_section = f"""
Wikipedia context (use this to find additional authentic items):
<wikipedia>
{wiki_context[:6000]}
</wikipedia>
"""

    prompt = f"""You are an expert in vintage and historical fashion.

Era: {era['label']} ({era['period']}, {era['start_year']}–{era['end_year']})

Current descriptor data:
{current_json}
{wiki_section}
Your task: expand each descriptor category with additional AUTHENTIC items from this era.
Rules:
- Only add items genuinely associated with this specific era (not just the decade in general)
- For brands: real labels/designers who produced garments in this period (include mid-market, mail-order, and department store brands, not just haute couture)
- For fabrics: specific fabric names used in garments of the era
- For prints: named print styles (e.g. "Liberty floral", "abstract op-art")
- For silhouettes: specific garment shapes and cuts
- For colors: specific color names and palettes popular in the era
- For aesthetics: style movements, subcultures, and looks (e.g. "mod", "preppy", "prairie")
- For key_garments: specific garment names (e.g. "wrap dress", "pea coat")
- Do NOT repeat items already in the current lists
- Aim for 8–15 NEW items per category (fewer if the era is narrow)
- Use the same parenthetical notation for context where helpful (e.g. "Qiana (synthetic silk)")

Respond ONLY with valid JSON in this exact format:
{{
  "brands": ["new item 1", "new item 2", ...],
  "fabrics": [...],
  "prints": [...],
  "silhouettes": [...],
  "colors": [...],
  "aesthetics": [...],
  "key_garments": [...]
}}"""

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


# ── Merge helpers ─────────────────────────────────────────────────────────────

def _normalize(val: str) -> str:
    """Lowercase, strip parentheticals, strip punctuation for dedup comparison."""
    return re.sub(r"\s*\([^)]*\)", "", val).strip().lower()


def merge_lists(existing: list, additions: list) -> list:
    """Append additions not already present (case-insensitive, ignoring parentheticals)."""
    seen = {_normalize(v) for v in existing}
    merged = list(existing)
    for item in additions:
        norm = _normalize(item)
        if norm and norm not in seen:
            merged.append(item)
            seen.add(norm)
    return merged


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Print changes without saving")
    parser.add_argument("--era", help="Only process one era ID (e.g. early-1970s)")
    args = parser.parse_args()

    # Load era data
    with ERA_DATA_PATH.open() as f:
        eras: list[dict] = json.load(f)

    # Set up Anthropic client
    try:
        import os
        from anthropic import Anthropic
        # Try to get key from environment or .env file
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            env_path = Path(__file__).parent.parent / ".env"
            if env_path.exists():
                for line in env_path.read_text().splitlines():
                    if line.startswith("ANTHROPIC_API_KEY="):
                        api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
        if not api_key:
            print("ERROR: ANTHROPIC_API_KEY not found in environment or .env file")
            sys.exit(1)
        client = Anthropic(api_key=api_key)
    except ImportError:
        print("ERROR: anthropic package not installed")
        sys.exit(1)

    target_eras = [e for e in eras if not args.era or e["id"] == args.era]
    print(f"Enriching {len(target_eras)} era(s)…\n")

    for i, era in enumerate(target_eras):
        era_id = era["id"]
        print(f"[{i+1}/{len(target_eras)}] {era['label']} ({era_id})")

        # Step 1: Wikipedia
        print(f"  Fetching Wikipedia…")
        wiki_text = scrape_wikipedia_for_era(era_id)
        print(f"  Got {len(wiki_text)} chars from Wikipedia")

        # Step 2: Claude
        print(f"  Asking Claude to enrich…")
        additions = None
        for attempt in range(3):
            try:
                additions = enrich_era_with_claude(era, wiki_text, client)
                break
            except Exception as e:
                wait = 15 * (attempt + 1)
                print(f"  Claude failed (attempt {attempt+1}/3): {e} — retrying in {wait}s")
                time.sleep(wait)
        if additions is None:
            print(f"  Skipping era after 3 failed attempts")
            continue

        # Step 3: Merge
        total_added = 0
        for cat in DESCRIPTOR_CATEGORIES:
            new_items = additions.get(cat, [])
            before = len(era.get(cat, []))
            era[cat] = merge_lists(era.get(cat, []), new_items)
            added = len(era[cat]) - before
            total_added += added
            if added:
                print(f"  {cat}: +{added} items → {len(era[cat])} total")

        if not total_added:
            print("  No new items added")

        if not args.dry_run:
            # Save after each era so progress isn't lost on crash
            with ERA_DATA_PATH.open("w") as f:
                json.dump(eras, f, indent=2, ensure_ascii=False)
            print(f"  Saved.")
        else:
            print(f"  [dry-run] Would add {total_added} items total")

        print()
        time.sleep(2)  # polite pause between eras

    print("Done.")


if __name__ == "__main__":
    main()
