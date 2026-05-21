import os
import json
import io
import requests
import tarfile
import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI
import csv
import re
import sys
from datetime import datetime

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ============================================================
# BOX DIMENSIONS — calibrated from Canva 'aaa' test
#
# Title box : 11 chars/line, 1 line, UPPERCASE, font size 5
# Desc box  : 24 chars/line, EXACTLY 3 lines (60-72 chars)
# Same for ALL 9 boxes
# ============================================================

TITLE_MAX_CHARS = 11
DESC_MAX_CHARS  = 24
DESC_MAX_LINES  = 3
DESC_MAX_TOTAL  = DESC_MAX_CHARS * DESC_MAX_LINES   # 72 — hard ceiling
DESC_MIN_TOTAL  = int(DESC_MAX_CHARS * 2.5)         # 60 — minimum to fill 3 lines


def wrap_chars(text, max_chars):
    """Char-count line wrapping. Returns list of lines."""
    words = text.strip().split()
    lines, cur_words, cur_len = [], [], 0
    for word in words:
        sp = 1 if cur_words else 0
        if cur_len + sp + len(word) > max_chars and cur_words:
            lines.append(' '.join(cur_words))
            cur_words, cur_len = [word], len(word)
        else:
            cur_words.append(word)
            cur_len += sp + len(word)
    if cur_words:
        lines.append(' '.join(cur_words))
    return lines


def count_desc_lines(text):
    return len(wrap_chars(text, DESC_MAX_CHARS))


def wrap_desc(text):
    """Wrap description to max 3 lines × 24 chars."""
    lines = wrap_chars(text, DESC_MAX_CHARS)
    return '\n'.join(lines[:DESC_MAX_LINES])


def desc_fill_pct(text):
    """How full is the last line as % of box width."""
    lines = wrap_chars(text, DESC_MAX_CHARS)
    if not lines:
        return 0
    last = lines[-1]
    return int(len(last) / DESC_MAX_CHARS * 100)


# ============================================================
# TRANSLATED TITLES
# ============================================================

TITLE_TRANSLATIONS = {
    "Deutsch":     "PFLEGEHINWEISE",
    "Englisch":    "AFTERCARE INSTRUCTIONS",
    "Türkisch":    "BAKIM TALİMATLARI",
    "Polnisch":    "INSTRUKCJE PIELĘGNACJI",
    "Russisch":    "ИНСТРУКЦИИ ПО УХОДУ",
    "Italienisch": "ISTRUZIONI PER LA CURA",
    "Spanisch":    "INSTRUCCIONES DE CUIDADO",
    "Französisch": "INSTRUCTIONS D'ENTRETIEN",
    "Ungarisch":   "ÁPOLÁSI ÚTMUTATÓ",
    "Rumänisch":   "INSTRUCȚIUNI DE ÎNGRIJIRE"
}

LANGUAGES = [
    "Deutsch", "Englisch", "Türkisch", "Polnisch", "Russisch",
    "Italienisch", "Spanisch", "Französisch", "Ungarisch", "Rumänisch"
]

# ============================================================
# GERMAN SOURCE — 9 RULES
# Each description: 60-72 chars to fill all 3 lines
# ============================================================

GERMAN_RULES = [
    {
        "title": "KEIN WASSER",
        "description": "Brauen in den ersten 24 Stunden trocken halten, kein Waschen."
    },
    {
        "title": "SONNE",
        "description": "Direkte Sonne meiden, Hut und Sonnencreme zum Schutz tragen."
    },
    {
        "title": "KOSMETIK",
        "description": "2 Wochen: keine Peelings, kein Laser, kein Botox anwenden."
    },
    {
        "title": "BERÜHRUNG",
        "description": "Behandelte Stellen nicht berühren, reiben oder kratzen."
    },
    {
        "title": "ZUPFEN",
        "description": "Mindestens 1 Woche kein Zupfen und kein Rasieren im Bereich."
    },
    {
        "title": "MAKE-UP",
        "description": "Mindestens 24 Stunden kein Make-up auf die Brauen auftragen."
    },
    {
        "title": "HITZE",
        "description": "Keine Sauna, kein Dampfbad und keine heißen Duschen nehmen."
    },
    {
        "title": "KEIN ÖL",
        "description": "24 Std. keine ölhaltigen Produkte auf behandelte Stellen geben."
    },
    {
        "title": "KEIN CHLOR",
        "description": "Erste Woche: Schwimmbäder und Chlorwasser konsequent meiden."
    },
]


# ============================================================
# GPT TRANSLATION
# ============================================================

def translate_content(treatment, lang):
    rules_text = "\n\n".join([
        f"Rule {i+1}:\nTitle: {r['title']}\nDescription: {r['description']}"
        for i, r in enumerate(GERMAN_RULES)
    ])

    prompt = f"""Translate the following German beauty aftercare texts into {lang}.

STRICT RULES:
- Translate EVERYTHING into {lang}. Zero German words in output.
- Translate the treatment name "{treatment}" into natural {lang}.
- Every field is a SINGLE LINE — no line breaks inside any field.

TITLE RULES (box is very small — critical):
- Each title MUST be MAX {TITLE_MAX_CHARS} characters including spaces.
- Titles must be SHORT: 1-3 words only, displayed in UPPERCASE.
- If direct translation exceeds {TITLE_MAX_CHARS} chars, use a shorter synonym or abbreviation.
- Good examples: "NO WATER" (8✅), "PAS D'EAU" (9✅), "БЕЗ ВОДЫ" (8✅)
- Bad example: "AVOID WATER" (11✅ exactly), "KEIN WASSER" (11✅ exactly)

DESCRIPTION RULES (must fill exactly 3 lines — critical):
- Each description MUST be between {DESC_MIN_TOTAL} and {DESC_MAX_TOTAL} characters total.
- The box fits 24 characters per line × 3 lines.
- Your description must be long enough to fill all 3 lines ({DESC_MIN_TOTAL}+ chars).
- If direct translation is under {DESC_MIN_TOTAL} chars, EXPAND with useful detail.
- If direct translation is over {DESC_MAX_TOTAL} chars, SHORTEN to fit.
- COUNT your characters. Under {DESC_MIN_TOTAL} = too short. Over {DESC_MAX_TOTAL} = too long.

OUTPUT: Return ONLY valid JSON:

{{
  "treatment_name": "translated name (title case)",
  "rule1_title": "max {TITLE_MAX_CHARS} chars",
  "rule1_desc": "{DESC_MIN_TOTAL}-{DESC_MAX_TOTAL} chars, single line",
  "rule2_title": "max {TITLE_MAX_CHARS} chars",
  "rule2_desc": "{DESC_MIN_TOTAL}-{DESC_MAX_TOTAL} chars, single line",
  "rule3_title": "max {TITLE_MAX_CHARS} chars",
  "rule3_desc": "{DESC_MIN_TOTAL}-{DESC_MAX_TOTAL} chars, single line",
  "rule4_title": "max {TITLE_MAX_CHARS} chars",
  "rule4_desc": "{DESC_MIN_TOTAL}-{DESC_MAX_TOTAL} chars, single line",
  "rule5_title": "max {TITLE_MAX_CHARS} chars",
  "rule5_desc": "{DESC_MIN_TOTAL}-{DESC_MAX_TOTAL} chars, single line",
  "rule6_title": "max {TITLE_MAX_CHARS} chars",
  "rule6_desc": "{DESC_MIN_TOTAL}-{DESC_MAX_TOTAL} chars, single line",
  "rule7_title": "max {TITLE_MAX_CHARS} chars",
  "rule7_desc": "{DESC_MIN_TOTAL}-{DESC_MAX_TOTAL} chars, single line",
  "rule8_title": "max {TITLE_MAX_CHARS} chars",
  "rule8_desc": "{DESC_MIN_TOTAL}-{DESC_MAX_TOTAL} chars, single line",
  "rule9_title": "max {TITLE_MAX_CHARS} chars",
  "rule9_desc": "{DESC_MIN_TOTAL}-{DESC_MAX_TOTAL} chars, single line"
}}

GERMAN TEXTS TO TRANSLATE:
Treatment: {treatment}

{rules_text}
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=2000,
        response_format={"type": "json_object"}
    )

    try:
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"  ⚠  JSON parse error for {lang}: {e}")
        return {}


def fix_short_desc(desc, rule_num, lang, max_retries=1):
    """If description is too short (<60 chars), ask GPT to expand it."""
    for attempt in range(max_retries + 1):
        if len(desc) >= DESC_MIN_TOTAL:
            return desc

        chars_needed = DESC_MIN_TOTAL - len(desc)
        retry_prompt = f"""This aftercare description for {lang} is too short:
"{desc}"
It is {len(desc)} characters but needs {DESC_MIN_TOTAL}-{DESC_MAX_TOTAL} characters to fill 3 lines.
Expand it by ~{chars_needed} more characters with useful aftercare detail.
Keep it under {DESC_MAX_TOTAL} characters total.
Return ONLY valid json: {{"desc": "expanded description here"}}"""

        try:
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": retry_prompt}],
                temperature=0.1,
                max_tokens=200,
                response_format={"type": "json_object"}
            )
            fixed = json.loads(resp.choices[0].message.content)
            desc  = fixed.get("desc", desc)
        except:
            break

    return desc


def safe_filename(text):
    return re.sub(r'[^\w\s-]', '', text).strip().replace(' ', '_')


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    print("\n" + "="*58)
    print("  Visual 9-Box Aftercare Generator")
    print("="*58)
    print(f"  Title box : max {TITLE_MAX_CHARS} chars, 1 line, UPPERCASE")
    print(f"  Desc box  : {DESC_MIN_TOTAL}-{DESC_MAX_TOTAL} chars = fills all 3 lines")
    print(f"  9 boxes   : same dimensions for all\n")

    treatment = input("Enter treatment name in German (e.g. Airbrush Brows): ").strip()

    print(f"\n📸 Image URL for Canva Bulk Create")
    print("  Paste a direct image URL or press Enter to skip:")
    image_url = input("  Image URL: ").strip()

    print(f"\nGenerating 10 languages for '{treatment}'...\n")

    rows      = []
    names_by_lang = {}
    warnings  = []

    for lang in LANGUAGES:
        print(f"  → {lang:<14}", end="", flush=True)

        if lang == "Deutsch":
            treatment_name = treatment
            rules_data = {}
            for i, r in enumerate(GERMAN_RULES, 1):
                rules_data[f"rule{i}_title"] = r["title"]
                rules_data[f"rule{i}_desc"]  = r["description"]
            print("(source — no API call)")
        else:
            data = translate_content(treatment, lang)
            treatment_name = data.get("treatment_name", treatment)
            rules_data = {}
            for i, r in enumerate(GERMAN_RULES, 1):
                rules_data[f"rule{i}_title"] = data.get(f"rule{i}_title", r["title"])
                rules_data[f"rule{i}_desc"]  = data.get(f"rule{i}_desc",  r["description"])
            print("✅")

        # Validate + fix all 9 rules
        for i in range(1, 10):
            title_key = f"rule{i}_title"
            desc_key  = f"rule{i}_desc"

            # Title: uppercase + length check
            title = rules_data[title_key].upper().strip()
            if len(title) > TITLE_MAX_CHARS:
                warnings.append(f"{lang} rule{i} title '{title}' = {len(title)} chars (max {TITLE_MAX_CHARS})")
            rules_data[title_key] = title

            # Desc: check length, auto-fix if too short
            desc = rules_data[desc_key].strip()
            if len(desc) < DESC_MIN_TOTAL and lang != "Deutsch":
                desc = fix_short_desc(desc, i, lang)
            n_lines = count_desc_lines(desc)
            if n_lines > DESC_MAX_LINES:
                warnings.append(f"{lang} rule{i} desc overflow ({n_lines} lines) — truncated")
            if len(desc) < DESC_MIN_TOTAL:
                warnings.append(f"{lang} rule{i} desc too short ({len(desc)} chars, min {DESC_MIN_TOTAL})")
            rules_data[desc_key] = wrap_desc(desc)

        # Print per-language desc fill summary
        fills = []
        for i in range(1, 10):
            lines = count_desc_lines(rules_data[f"rule{i}_desc"].replace('\n', ' '))
            fills.append(lines)
        all_full = all(f == DESC_MAX_LINES for f in fills)
        fill_str = ''.join(str(f) for f in fills)
        print(f"         desc lines: [{fill_str}] {'✅' if all_full else '⚠'}")

        names_by_lang[lang] = treatment_name

        row = {
            "Language":      lang,
            "Treatment":     treatment_name,
            "TreatmentName": treatment_name.upper(),
            "Subtitle":      TITLE_TRANSLATIONS.get(lang, "PFLEGEHINWEISE"),
        }
        if image_url:
            row["ImageURL"] = image_url
        row.update(rules_data)
        rows.append(row)

    # Summary
    if warnings:
        print(f"\n⚠  Warnings ({len(warnings)}):")
        for w in warnings:
            print(f"   {w}")
    else:
        print("\n✅  All titles and descriptions within limits")

    # Save CSV
    df = pd.DataFrame(rows)
    timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name   = safe_filename(treatment)
    output_file = f"Visual_Aftercare_{safe_name}_10Languages_{timestamp}.csv"
    df.to_csv(output_file, index=False, quoting=csv.QUOTE_ALL, encoding="utf-8-sig")

    print(f"\n✅  CSV saved: {output_file}")
    print(f"\n📋  Column structure:")
    print(f"    TreatmentName → main title")
    print(f"    Subtitle      → translated page subtitle")
    if image_url:
        print(f"    ImageURL      → background image")
    print(f"    rule1_title … rule9_title → box titles (UPPERCASE, max {TITLE_MAX_CHARS} chars)")
    print(f"    rule1_desc  … rule9_desc  → box descriptions (3 lines each)")
    print(f"\n📝  Translated treatment names:")
    for lang, name in names_by_lang.items():
        print(f"    {lang:<14} → {name}")