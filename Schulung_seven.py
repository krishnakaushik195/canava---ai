import os
import json
import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI
import csv
import re
from datetime import datetime

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ============================================================
# BOOKLET GENERATOR — 102 columns, 10 languages
# Every Canva text box = one CSV column
#
# BOX SPECS:
#   CG   = Cormorant Garamond
#   Inter = Inter
#   BDS  = Beautifully Delicious Script
#
# Page 1:  Cover (3 boxes)
# Page 2:  TOC heading + 20 entries × 2 (title+num) = 41 boxes
# Page 3:  Ch01 title + script + body = 3 boxes
# Page 4:  Ch02 title + body = 2 boxes
# Page 5:  quote + sub1 + body_L + sub2 + body_R = 5 boxes
# Page 6:  sub_B + body_B + sub_C + body_C = 4 boxes
# Page 7:  Ch03 title + body_L + body_R = 3 boxes
# Page 8:  Ch04 title + body_R + body_L = 3 boxes
# Pages 9-20: each has name + body_L + body_R = 3 × 12 = 36 boxes
# + Language + TopicName = 2
# TOTAL = 3+41+3+2+5+4+3+3+36+2 = 102
# ============================================================

FULL_W  = 96   # full-width body  Inter 9pt
HALF_W  = 45   # half-width body  Inter 9pt
CH_W    = 30   # chapter title    CG 37pt (but varies — used as min)
TOC_W   = 31   # TOC entry        Inter 9.6pt

# Per-page half-body line limits (L=left col, R=right col)
PAGE_LIMITS = {
    9:  {"L": 54, "R": 24},
    10: {"L": 25, "R": 51},
    11: {"L": 54, "R": 26},
    12: {"L": 20, "R": 55},
    13: {"L": 52, "R": 18},
    14: {"L": 25, "R": 53},
    15: {"L": 52, "R": 25},
    16: {"L": 19, "R": 53},
    17: {"L": 56, "R": 26},
    18: {"L": 25, "R": 55},
    19: {"L": 52, "R": 26},
    20: {"L": 21, "R": 49},
}

LANGUAGES = [
    "Deutsch", "Englisch", "Türkisch", "Polnisch", "Russisch",
    "Italienisch", "Spanisch", "Französisch", "Ungarisch", "Rumänisch"
]

def wrap(text, max_chars, max_lines=None):
    words = text.strip().split()
    lines, cur, cur_len = [], [], 0
    for word in words:
        sp = 1 if cur else 0
        if cur_len + sp + len(word) > max_chars and cur:
            lines.append(' '.join(cur))
            cur, cur_len = [word], len(word)
        else:
            cur.append(word)
            cur_len += sp + len(word)
    if cur:
        lines.append(' '.join(cur))
    if max_lines:
        lines = lines[:max_lines]
    return '\n'.join(lines)


# ============================================================
# STEP 1: Generate German content
# ============================================================

def generate_german_content(topic):
    print(f"  Generating German content...", end=" ", flush=True)
    prompt = f"""Create a complete German professional beauty/wellness training booklet for "{topic}".

Generate content for ALL sections. Be specific to "{topic}" throughout.
Write professional German. Each field is ONE continuous text (no extra newlines inside).

LENGTH TARGETS per field:
- p01_body: ~500 chars (4 short paragraphs on what {topic} is)
- p04_body: ~2500 chars (anatomy/skin intro — 27 lines × 96 chars)  
- p05_body_L: ~900 chars (skin layer detail — 18 lines × 53 chars)
- p05_body_R: ~900 chars (skin layer continuation — 17 lines × 55 chars)
- p06_body_B: ~2300 chars (dermis detail — 26 lines × 96 chars)
- p06_body_C: ~1800 chars (subcutis detail — 96 chars/line)
- p07_body_L: ~2000 chars (functions list part 1 — 47 lines × 45 chars)
- p07_body_R: ~1900 chars (functions list part 2 — 44 lines × 45 chars)
- p08_body_R: ~2000 chars MINIMUM — right column of page 8, symptoms+causes+process+course of Akne
  MUST include: Symptome section, detailed explanation of how acne develops,
  Ablauf section, Die Ursache section with bullet list. Fill all 44 lines.
- p08_body_L: ~650 chars — left column bottom of page 8, Akne intro paragraph ONLY.
  Start with "Akne" as heading, then the intro text about Acne vulgaris. Fill all 15 lines.
- Each condition body (cond1_L through cond12_R): sized to fit line limits

CRITICAL PAGE LAYOUT — READ CAREFULLY:
Page 8 has TWO text boxes for AKNE ONLY:
  - p08_body_R = right column: Akne symptoms, development, Ablauf, Ursachen (44 lines × 45 chars = ~2000 chars)
  - p08_body_L = left column bottom: Akne intro paragraph with "Akne" heading (15 lines × 44 chars = ~650 chars)

Pages 9-20 each have ONE condition split across left+right columns:
  cond1 = Neurodermitis    (page 9:  left=54 lines, right=24 lines)
  cond2 = Schuppenflechte  (page 10: left=25 lines, right=51 lines)
  cond3 = Herpes           (page 11: left=54 lines, right=26 lines)
  cond4 = Wundrose         (page 12: left=20 lines, right=55 lines)
  cond5 = Nesselsucht      (page 13: left=52 lines, right=18 lines)
  cond6 = Gürtelrose       (page 14: left=25 lines, right=53 lines)
  cond7 = Pilzinfektionen  (page 15: left=52 lines, right=25 lines)
  cond8 = Sexuell übertragbare Krankheiten (page 16: left=19 lines, right=53 lines)
  cond9 = Haarausfall      (page 17: left=56 lines, right=26 lines)
  cond10 = Warzen          (page 18: left=25 lines, right=55 lines)
  cond11 = Rosazea         (page 19: left=52 lines, right=26 lines)
  cond12 = Hautkrebs       (page 20: left=21 lines, right=49 lines)

Each condition splits mid-sentence across left and right — left ends abruptly, right continues.
Size each cond_L and cond_R to fill their exact line counts (45 chars/line).
  cond_L char target = left_lines × 45
  cond_R char target = right_lines × 45

DO NOT put Akne in cond1-cond12. Akne belongs ONLY in p08_body_R and p08_body_L.

Return ONLY valid JSON:
{{
  "cover_subtitle": "Theorie & Praxis Schulung",
  "toc_entries": [
    {{"title": "Was ist eine {topic}?", "num": "01"}},
    {{"title": "Anatomie der Haut", "num": "02"}},
    {{"title": "Funktion und Aufgaben der Haut", "num": "06"}},
    {{"title": "Krankheiten und Beschwerden", "num": "07"}},
    {{"title": "Vorbeugende Maßnahmen im Studio", "num": "27"}},
    {{"title": "Produktwissen", "num": "30"}},
    {{"title": "Vor der Behandlung", "num": "40"}},
    {{"title": "Hautanalyse", "num": "41"}},
    {{"title": "Körperanalyse", "num": "42"}},
    {{"title": "Anwendungsbereiche", "num": "43"}},
    {{"title": "Technik", "num": "44"}},
    {{"title": "Nach der Behandlung", "num": "48"}},
    {{"title": "Ergebnismessung", "num": "50"}},
    {{"title": "Probleme & Lösungen", "num": "51"}},
    {{"title": "Häufige Fragen und Antworten", "num": "53"}},
    {{"title": "Kundenberatung", "num": "54"}},
    {{"title": "Marketing und Verkauf", "num": "55"}},
    {{"title": "Preisgestaltung", "num": "56"}},
    {{"title": "Reflexionsseite", "num": "57"}},
    {{"title": "Wissenstest", "num": "58"}}
  ],
  "p03_script": "short decorative phrase (max 17 chars) related to {topic}",
  "p01_body": "...",
  "p04_ch_title": "02 Anatomie der Haut",
  "p04_body": "...",
  "p05_quote": "short inspirational quote (max 2 lines) about beauty/care",
  "p05_sub1": "sub-heading starting the first skin layer detail (max 44 chars)",
  "p05_body_L": "...",
  "p05_sub2": "sub-heading for second section (max 46 chars)",
  "p05_body_R": "...",
  "p06_sub_B": "B) Dermis (auch Korium genannt)",
  "p06_body_B": "...",
  "p06_sub_C": "C) Subkutis (auch Hypodermis genannt)",
  "p06_body_C": "...",
  "p07_ch_title": "03 Funktionen und Aufgaben der Haut",
  "p07_body_L": "...",
  "p07_body_R": "...",
  "p08_ch_title": "04 Häufigste Krankheiten & Beschwerden",
  "p08_body_R": "...",
  "p08_body_L": "...",
  "cond1_name": "Neurodermitis",   "cond1_L": "...", "cond1_R": "...",
  "cond2_name": "Schuppenflechte", "cond2_L": "...", "cond2_R": "...",
  "cond3_name": "Herpes",          "cond3_L": "...", "cond3_R": "...",
  "cond4_name": "Wundrose",        "cond4_L": "...", "cond4_R": "...",
  "cond5_name": "Nesselsucht",     "cond5_L": "...", "cond5_R": "...",
  "cond6_name": "Gürtelrose",      "cond6_L": "...", "cond6_R": "...",
  "cond7_name": "Pilzinfektionen", "cond7_L": "...", "cond7_R": "...",
  "cond8_name": "Sexuell übertragbare Krankheiten", "cond8_L": "...", "cond8_R": "...",
  "cond9_name": "Haarausfall",     "cond9_L": "...", "cond9_R": "...",
  "cond10_name": "Warzen",         "cond10_L": "...", "cond10_R": "...",
  "cond11_name": "Rosazea",        "cond11_L": "...", "cond11_R": "...",
  "cond12_name": "Hautkrebs",      "cond12_L": "...", "cond12_R": "...",
  "p_vorbeugende": "preventive measures in studio for {topic} (~1500 chars)",
  "p_produktwissen": "product knowledge for {topic} (~1500 chars)",
  "p_technik": "techniques for {topic} (~1500 chars)",
  "p_nach_behandlung": "aftercare for {topic} (~1200 chars)",
  "p_kundenberatung": "client consultation for {topic} (~1200 chars)",
  "p_marketing": "marketing and pricing for {topic} (~1200 chars)",
  "p_reflexion": "10 reflection questions for students (~800 chars)",
  "p_wissenstest": "10 knowledge test questions with answers (~1000 chars)"
}}
"""
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=12000,
        response_format={"type": "json_object"}
    )
    try:
        data = json.loads(response.choices[0].message.content)
        # Validate key fields aren't too short
        checks = {
            "p08_body_R": (1800, "P8 right col — Akne symptoms/causes"),
            "p08_body_L": (500,  "P8 left col — Akne intro"),
            "p07_body_L": (1800, "P7 left col — functions"),
            "p07_body_R": (1700, "P7 right col — functions cont"),
        }
        for key, (min_chars, label) in checks.items():
            val = data.get(key, "")
            flag = "✅" if len(val) >= min_chars else f"⚠ SHORT ({len(val)}/{min_chars})"
            print(f"\n    {flag} {label}")
        print(f"  ", end="")
        print(f"✅ ({len(data)} fields)")
        return data
    except Exception as e:
        print(f"❌ {e}")
        return {}


# ============================================================
# STEP 2: Translate content
# ============================================================

def translate_content(topic, lang, de_data):
    text_fields = {k: v for k, v in de_data.items() if isinstance(v, str)}
    toc_de = de_data.get("toc_entries", [])

    # Sanitize: remove control characters that break JSON serialization
    def clean(s):
        return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', s) if isinstance(s, str) else s
    text_fields = {k: clean(v) for k, v in text_fields.items()}

    toc_text = "\n".join(f"{i+1}. {e.get('title','')} — {e.get('num','')}"
                          for i, e in enumerate(toc_de))

    # Split into two API calls to avoid token limit issues
    # Call 1: TOC + short fields
    # Call 2: long body fields
    short_keys = ["cover_subtitle","p03_script","p05_quote","p05_sub1","p05_sub2",
                  "p06_sub_B","p06_sub_C","p07_ch_title","p08_ch_title","p04_ch_title",
                  "cond1_name","cond2_name","cond3_name","cond4_name","cond5_name",
                  "cond6_name","cond7_name","cond8_name","cond9_name","cond10_name",
                  "cond11_name","cond12_name"]
    short_fields = {k: text_fields[k] for k in short_keys if k in text_fields}
    long_fields  = {k: v for k, v in text_fields.items() if k not in short_keys}

    result = {}

    # ── Call 1: TOC + short fields ──
    prompt1 = f"""Translate into {lang}. Topic: "{topic}".
RULES: Full {lang} only. No ¿ ¡. Keep page numbers. Professional beauty tone.

TOC ENTRIES (translate titles, keep num unchanged):
{toc_text}

SHORT FIELDS:
{json.dumps(short_fields, ensure_ascii=False, indent=2)}

Return ONLY valid JSON:
{{
  "topic_name": "translated topic",
  "cover_subtitle": "...",
  "toc_entries": [{{"title": "...", "num": "01"}}, ...],
  ...all short field keys translated...
}}"""

    try:
        r1 = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt1}],
            temperature=0.1,
            max_tokens=3000,
            response_format={"type": "json_object"}
        )
        result.update(json.loads(r1.choices[0].message.content))
    except Exception as e:
        print(f"\n    ⚠ Call 1 error: {e}")
        return {}

    # ── Call 2: Long body fields (split in half to avoid token limits) ──
    long_keys = list(long_fields.keys())
    mid = len(long_keys) // 2
    
    for part, keys in [(1, long_keys[:mid]), (2, long_keys[mid:])]:
        chunk = {k: long_fields[k] for k in keys}
        prompt2 = f"""Translate these German training booklet body texts about "{topic}" into {lang}.
RULES: Full {lang} only. No ¿ ¡. Keep same paragraph structure and length.

{json.dumps(chunk, ensure_ascii=False, indent=2)}

Return ONLY valid JSON with same keys, translated values."""
        try:
            r2 = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt2}],
                temperature=0.1,
                max_tokens=4000,
                response_format={"type": "json_object"}
            )
            result.update(json.loads(r2.choices[0].message.content))
        except Exception as e:
            print(f"\n    ⚠ Call 2.{part} error: {e}")

    return result


# ============================================================
# STEP 3: Build row — 102 columns
# ============================================================

def build_row(lang, topic, data, season, year):
    topic_name = data.get("topic_name", topic)
    toc = data.get("toc_entries", [{}]*20)
    # pad to 20
    while len(toc) < 20:
        toc.append({"title": "", "num": ""})

    row = {"Language": lang, "TopicName": topic_name}

    # ── PAGE 1: Cover ──────────────────────────────────────────
    row["Cover_Title"]    = wrap(topic_name.upper(), 6, max_lines=3)
    row["Cover_Subtitle"] = data.get("cover_subtitle", "Theorie & Praxis Schulung")
    row["Cover_Sidebar"]  = f"schulung / {season.lower()} {year}"

    # ── PAGE 2: TOC ────────────────────────────────────────────
    row["TOC_Heading"] = wrap("INHALTSVERZEICHNIS", 11, max_lines=4)
    for i, entry in enumerate(toc[:20], 1):
        row[f"TOC_Entry_{i:02d}_Title"] = wrap(entry.get("title",""), TOC_W)
        row[f"TOC_Entry_{i:02d}_Num"]   = entry.get("num", "")

    # ── PAGE 3: Ch01 ───────────────────────────────────────────
    row["P03_Ch_Title"] = wrap(f"01 Was ist eine {topic_name}?", 30, max_lines=2)
    row["P03_Script"]   = data.get("p03_script", "")
    row["P03_Body"]     = wrap(data.get("p01_body",""), 47)

    # ── PAGE 4: Ch02 ───────────────────────────────────────────
    row["P04_Ch_Title"] = wrap(data.get("p04_ch_title","02 Anatomie der Haut"), 22, max_lines=1)
    row["P04_Body"]     = wrap(data.get("p04_body",""), FULL_W, max_lines=27)

    # ── PAGE 5: continuation ───────────────────────────────────
    row["P05_Quote"]    = data.get("p05_quote","")
    row["P05_Sub1"]     = wrap(data.get("p05_sub1",""), 44, max_lines=2)
    row["P05_Body_L"]   = wrap(data.get("p05_body_L",""), 53, max_lines=18)
    row["P05_Sub2"]     = wrap(data.get("p05_sub2",""), 46, max_lines=1)
    row["P05_Body_R"]   = wrap(data.get("p05_body_R",""), 55, max_lines=17)

    # ── PAGE 6: continuation ───────────────────────────────────
    row["P06_Sub_B"]    = wrap(data.get("p06_sub_B",""), 81, max_lines=1)
    row["P06_Body_B"]   = wrap(data.get("p06_body_B",""), FULL_W, max_lines=26)
    row["P06_Sub_C"]    = wrap(data.get("p06_sub_C",""), 81, max_lines=1)
    row["P06_Body_C"]   = wrap(data.get("p06_body_C",""), FULL_W)

    # ── PAGE 7: Ch03 — 2 columns ───────────────────────────────
    # Left column: functions 1-6 (max 47 lines × 45 chars)
    # Right column: functions 7-11 + closing (max 44 lines × 45 chars)
    row["P07_Ch_Title"]      = wrap(data.get("p07_ch_title","03 Funktionen und Aufgaben der Haut"), 23, max_lines=2)
    row["P07_Body_Left"]     = wrap(data.get("p07_body_L",""), HALF_W, max_lines=47)
    row["P07_Body_Right"]    = wrap(data.get("p07_body_R",""), HALF_W, max_lines=44)

    # ── PAGE 8: Ch04 — 2 columns + separate Akne intro ─────────
    # Right column TOP: symptoms + details of first condition (max 44 lines × 45 chars)
    # Left column BOTTOM: Akne intro paragraph (max 15 lines × 44 chars)
    # (image sits in left column top — no text box there)
    row["P08_Ch_Title"]      = wrap(data.get("p08_ch_title","04 Häufigste Krankheiten & Beschwerden"), 29, max_lines=2)
    row["P08_Body_Right"]    = wrap(data.get("p08_body_R",""), HALF_W, max_lines=44)
    row["P08_Akne_Intro"]    = wrap(data.get("p08_body_L",""), 44,     max_lines=15)

    # ── PAGES 9-20: 12 conditions (each page = name + left col + right col) ──
    # Page 9:  Condition 1 — L=54 lines, R=24 lines
    # Page 10: Condition 2 — L=25 lines, R=51 lines
    # Page 11: Condition 3 — L=54 lines, R=26 lines
    # Page 12: Condition 4 — L=20 lines, R=55 lines
    # Page 13: Condition 5 — L=52 lines, R=18 lines
    # Page 14: Condition 6 — L=25 lines, R=53 lines
    # Page 15: Condition 7 — L=52 lines, R=25 lines
    # Page 16: Condition 8 — L=19 lines, R=53 lines
    # Page 17: Condition 9 — L=56 lines, R=26 lines
    # Page 18: Condition 10 — L=25 lines, R=55 lines
    # Page 19: Condition 11 — L=52 lines, R=26 lines
    # Page 20: Condition 12 — L=21 lines, R=49 lines
    # Hardcoded condition names — always correct regardless of GPT output
    COND_NAMES = {
        1: "Neurodermitis", 2: "Schuppenflechte", 3: "Herpes",
        4: "Wundrose", 5: "Nesselsucht", 6: "Gürtelrose",
        7: "Pilzinfektionen", 8: "Sexuell übertragbare Krankheiten",
        9: "Haarausfall", 10: "Warzen", 11: "Rosazea", 12: "Hautkrebs"
    }
    # Use translated name if available, else German
    for i in range(1, 13):
        page_num = 8 + i
        lim = PAGE_LIMITS[page_num]
        # Use GPT-translated name if it looks translated, otherwise use German
        gpt_name = data.get(f"cond{i}_name", COND_NAMES[i])
        row[f"P{page_num:02d}_Cond{i}_Name"]  = gpt_name if gpt_name else COND_NAMES[i]
        row[f"P{page_num:02d}_Cond{i}_Left"]  = wrap(data.get(f"cond{i}_L",""), HALF_W, max_lines=lim["L"])
        row[f"P{page_num:02d}_Cond{i}_Right"] = wrap(data.get(f"cond{i}_R",""), HALF_W, max_lines=lim["R"])

    # ── Remaining chapters ─────────────────────────────────────
    row["P_Vorbeugende"]    = wrap(data.get("p_vorbeugende",""),    FULL_W)
    row["P_Produktwissen"]  = wrap(data.get("p_produktwissen",""),  FULL_W)
    row["P_Technik"]        = wrap(data.get("p_technik",""),        FULL_W)
    row["P_NachBehandlung"] = wrap(data.get("p_nach_behandlung",""),FULL_W)
    row["P_Kundenberatung"] = wrap(data.get("p_kundenberatung",""), FULL_W)
    row["P_Marketing"]      = wrap(data.get("p_marketing",""),      FULL_W)
    row["P_Reflexion"]      = wrap(data.get("p_reflexion",""),      FULL_W)
    row["P_Wissenstest"]    = wrap(data.get("p_wissenstest",""),    FULL_W)

    return row


# ============================================================
# MAIN
# ============================================================

def safe_filename(text):
    return re.sub(r'[^\w\s-]', '', text).strip().replace(' ', '_')

if __name__ == "__main__":
    print("=" * 62)
    print("  Booklet Generator — Theorie & Praxis Schulung")
    print("=" * 62)
    print("  102 columns | 10 languages | GPT-generated content\n")

    topic = input("Enter topic in German (e.g. Aromatherapie): ").strip()

    now = datetime.now()
    seasons = {1:"Winter",2:"Winter",3:"Frühling",4:"Frühling",5:"Frühling",
               6:"Sommer",7:"Sommer",8:"Sommer",9:"Herbst",10:"Herbst",
               11:"Herbst",12:"Winter"}
    season = seasons[now.month]

    print(f"\nStep 1: Generating German content for '{topic}'...")
    de_data = generate_german_content(topic)
    if not de_data:
        print("❌ Failed. Check API key."); exit()

    rows = []
    print(f"\nStep 2: Translating into 10 languages...")

    for lang in LANGUAGES:
        print(f"  → {lang:<14}", end="", flush=True)
        if lang == "Deutsch":
            data = dict(de_data)
            data["topic_name"] = topic
            print("(source — no API call)")
        else:
            data = translate_content(topic, lang, de_data)
            if not data:
                data = dict(de_data); data["topic_name"] = topic
                print("⚠ fallback")
            else:
                print("✅")
        rows.append(build_row(lang, topic, data, season, now.year))

    df = pd.DataFrame(rows)
    timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"Booklet_{safe_filename(topic)}_10Languages_{timestamp}.csv"
    df.to_csv(output_file, index=False, quoting=csv.QUOTE_ALL, encoding="utf-8-sig")

    print(f"\n✅  CSV saved: {output_file}")
    print(f"    {len(rows)} rows × {len(df.columns)} columns")
    print(f"\n📋  Column structure:")
    print(f"    Language, TopicName                     — 2 cols")
    print(f"    Cover_Title/Subtitle/Sidebar             — 3 cols")
    print(f"    TOC_Heading + 20×(Title+Num)             — 41 cols")
    print(f"    P03: Ch_Title, Script, Body              — 3 cols")
    print(f"    P04: Ch_Title, Body                      — 2 cols")
    print(f"    P05: Quote, Sub1, Body_L, Sub2, Body_R   — 5 cols")
    print(f"    P06: Sub_B, Body_B, Sub_C, Body_C        — 4 cols")
    print(f"    P07: Ch_Title, Body_L, Body_R            — 3 cols")
    print(f"    P08: Ch_Title, Body_R, Body_L            — 3 cols")
    print(f"    P09-P20: 12 conditions × (Name+L+R)      — 36 cols")
    print(f"    P_Vorbeugende … P_Wissenstest             — 8 cols")
    print(f"    TOTAL: {len(df.columns)} columns")