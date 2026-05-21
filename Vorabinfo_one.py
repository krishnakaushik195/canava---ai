import os
import json
import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI
import csv
import re
import io
import requests
import tarfile
from datetime import datetime

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


# ============================================================
# PIXEL-BASED CHARACTER WIDTHS — Cormorant Garamond 34.6pt
#
# Loaded from font metrics (fontTools) and calibrated to match
# user's real Canva measurement: 93 'a' chars = 1802px box width.
#
# This means wrapping is done in PIXELS not characters —
# every line fills the box as much as physically possible.
# ============================================================

def _load_char_widths():
    """Load Cormorant Garamond char widths from npm font package."""
    try:
        from fontTools.ttLib import TTFont
    except ImportError:
        import subprocess, sys
        subprocess.run([sys.executable, '-m', 'pip', 'install', 'fonttools',
                        '--break-system-packages', '-q'], capture_output=True)
        from fontTools.ttLib import TTFont

    url = 'https://registry.npmjs.org/typeface-cormorant-garamond/-/typeface-cormorant-garamond-0.0.72.tgz'
    r   = requests.get(url, timeout=20)
    tgz = tarfile.open(fileobj=io.BytesIO(r.content), mode='r:gz')
    woff_member = next(m for m in tgz.getmembers()
                       if 'latin-400.woff' in m.name and 'italic' not in m.name)
    font = TTFont(io.BytesIO(tgz.extractfile(woff_member).read()))

    upm         = font['head'].unitsPerEm
    cmap        = font.getBestCmap()
    hmtx        = font['hmtx'].metrics
    font_px     = 34.6 * 1.333          # 46.1px
    px_per_unit = font_px / upm

    # Build Latin + Extended Latin table
    table = {}
    for cp in range(32, 0x024F):
        if cp in cmap:
            table[cp] = hmtx[cmap[cp]][0] * px_per_unit
    if 32 not in table:
        table[32] = font_px * 0.25

    # Calibrate to user real measurement: 93 'a' = 1802px
    cal = 1802.0 / (93 * table[ord('a')])
    table = {k: v * cal for k, v in table.items()}

    # Add Cyrillic — mapped to Latin visual equivalents
    # (user confirmed: Cyrillic 'а' = same width as Latin 'a')
    cyrillic_map = {
        'а':'a','б':'b','в':'B','г':'r','д':'d','е':'e','ё':'e','ж':'x',
        'з':'3','и':'u','й':'u','к':'k','л':'n','м':'m','н':'H','о':'o',
        'п':'n','р':'p','с':'c','т':'T','у':'y','ф':'f','х':'x','ц':'u',
        'ч':'4','ш':'w','щ':'w','ъ':'b','ы':'b','ь':'b','э':'e','ю':'m',
        'я':'R',
        'А':'A','Б':'B','В':'B','Г':'r','Д':'D','Е':'E','Ё':'E','Ж':'X',
        'З':'3','И':'H','Й':'H','К':'K','Л':'A','М':'M','Н':'H','О':'O',
        'П':'H','Р':'P','С':'C','Т':'T','У':'Y','Ф':'F','Х':'X','Ц':'U',
        'Ч':'4','Ш':'W','Щ':'W','Ъ':'B','Ы':'B','Ь':'B','Э':'E','Ю':'M',
        'Я':'R',
    }
    for cyr, lat in cyrillic_map.items():
        cp_lat = ord(lat)
        if cp_lat in table:
            table[ord(cyr)] = table[cp_lat]

    return table

# Load once at startup
print("Loading font metrics...", end=" ", flush=True)
try:
    CHAR_WIDTHS = _load_char_widths()
    FALLBACK_W  = CHAR_WIDTHS[ord('a')]
    print(f"✅ ({len(CHAR_WIDTHS)} chars)")
except Exception as e:
    print(f"⚠ fallback to char count ({e})")
    CHAR_WIDTHS = {}
    FALLBACK_W  = 1802.0 / 93   # 19.38px per char


def char_width(ch):
    """Get pixel width of a single character."""
    return CHAR_WIDTHS.get(ord(ch), FALLBACK_W)

def text_px(text):
    """Get total pixel width of a string."""
    return sum(char_width(ch) for ch in text)

BOX_WIDTH   = 1802.0   # px — body text box width (fixed)
BOX_HEIGHT  = 2190.0   # px — body text box height (fixed)
FONT_PX     = 34.6 * 1.333   # 46.1px
INTRO_INDENT = ""      # no indent
SPACE_PX     = char_width(' ') if CHAR_WIDTHS else FALLBACK_W * 0.55

# ============================================================
# CALIBRATED DIRECTLY FROM CANVA — DO NOT CHANGE
#
# Measured by typing 'aaa...' in body box = 93 Latin chars per line
# Box: 1802px wide | Font: Cormorant Garamond 34.6pt
#
# Per-language MAX_CHARS accounts for character width differences:
#   Latin scripts (German/English/etc.) = 99-102 chars per line
#   Cyrillic (Russian) = 84 chars per line (wider characters)
#
# Each language has its own:
#   Intro budget = MAX_CHARS - 1  (1 space indent)
#   Rule budget  = MAX_CHARS - 3  ("N. " prefix = 3 chars)
#
# LineSpacing is calculated per language to fill BOX_HEIGHT exactly.
# Font: Cormorant Garamond 34.6pt | Box: 1802 × 2190px
# ============================================================

# MAX_CHARS — calibrated directly from Canva 'aaa' test
# Latin 'a' = 93 chars, Cyrillic 'а' = 93 chars (same width in Cormorant Garamond)
# So ALL languages use the same value — one number, universal.
LANG_MAX_CHARS = {lang: 93 for lang in [
    "Deutsch", "Englisch", "Türkisch", "Polnisch", "Russisch",
    "Italienisch", "Spanisch", "Französisch", "Ungarisch", "Rumänisch"
]}



# ============================================================
# HEADING / SUBHEADING TRANSLATIONS
# ============================================================

HEADING_TRANSLATIONS = {
    "Deutsch":     "PFLEGEHINWEIS",
    "Englisch":    "AFTERCARE INSTRUCTIONS",
    "Türkisch":    "BAKIM TALİMATLARI",
    "Polnisch":    "ZALECENIA PIELĘGNACYJNE",
    "Russisch":    "ИНСТРУКЦИИ ПО УХОДУ",
    "Italienisch": "ISTRUZIONI PER LA CURA",
    "Spanisch":    "INSTRUCCIONES DE CUIDADO",
    "Französisch": "INSTRUCTIONS DE SOINS",
    "Ungarisch":   "ÁPOLÁSI UTASÍTÁSOK",
    "Rumänisch":   "INSTRUCȚIUNI DE ÎNGRIJIRE"
}

SUBHEADING_TRANSLATIONS = {
    "Deutsch":     "BITTE LESEN SIE DAS DOKUMENT AUFMERKSAM",
    "Englisch":    "PLEASE READ THIS DOCUMENT CAREFULLY",
    "Türkisch":    "LÜTFEN BU DOKÜMANI DİKKATLİ OKUYUN",
    "Polnisch":    "PROSZĘ PRZECZYTAĆ TEN DOKUMENT UWAŻNIE",
    "Russisch":    "ПОЖАЛУЙСТА, ВНИМАТЕЛЬНО ПРОЧИТАЙТЕ ЭТОТ ДОКУМЕНТ",
    "Italienisch": "SI PREGA DI LEGGERE ATTENTAMENTE QUESTO DOCUMENTO",
    "Spanisch":    "POR FAVOR LEA ESTE DOCUMENTO CON ATENCIÓN",
    "Französisch": "VEUILLEZ LIRE ATTENTIVEMENT CE DOCUMENT",
    "Ungarisch":   "KÉRJÜK, OLVASSA EL FIGYELMESEN EZT A DOKUMENTUMOT",
    "Rumänisch":   "VĂ RUGĂM SĂ CITIȚI CU ATENȚIE ACEST DOCUMENT"
}

LANGUAGES = [
    "Deutsch", "Englisch", "Türkisch", "Polnisch", "Russisch",
    "Italienisch", "Spanisch", "Französisch", "Ungarisch", "Rumänisch"
]


# ============================================================
# GERMAN SOURCE TEXT
# ============================================================

GERMAN_GREETING = "Liebe Kundin, lieber Kunde,"

GERMAN_INTRO_TEMPLATE = (
    "nach einer {treatment} Behandlung ist es wichtig, dass Sie einige Pflegetipps befolgen. "
    "Hier sind einige ausführliche Hinweise, die Sie beachten sollten:"
)

GERMAN_RULES = [
    "Vermeiden Sie Berührungen: Kratzen Sie nicht an der behandelten Stelle, um Infektionen oder Reizungen zu vermeiden.",
    "Kein Wasser: Vermeiden Sie es, die behandelte Stelle in den ersten 24 Stunden mit Wasser in Kontakt zu bringen.",
    "Kein Schwitzen: Verzichten Sie auf intensive sportliche Aktivitäten, die zu starkem Schwitzen führen, während die Behandlung heilt.",
    "Vermeiden Sie Sonneneinstrahlung: Schützen Sie die behandelten Stellen vor direkter Sonneneinstrahlung in den ersten Tagen nach der Behandlung.",
    "Keine Sauna oder Dampfbäder: Vermeiden Sie Sauna, Dampfbäder oder heiße Duschen, um die frisch behandelte Stelle nicht zu belasten.",
    "Kein Make-up auf der behandelten Stelle: Verwenden Sie in den ersten 24 Stunden kein Make-up oder Kosmetikprodukte auf der behandelten Stelle.",
    "Sanfte Reinigung: Reinigen Sie, wenn nötig, die behandelte Stelle vorsichtig und vermeiden Sie aggressive Reinigungsmittel.",
    "Vermeiden Sie Peelings: In den ersten zwei Wochen sollten Sie keine Peelings verwenden.",
    "Keine mechanische Reizung: Reiben oder kratzen Sie die behandelte Stelle nicht, um das Ergebnis nicht zu beeinträchtigen.",
    "Vermeiden Sie Öle und fetthaltige Produkte: Benutzen Sie keine ölhaltigen Hautpflegeprodukte auf den behandelten Bereichen, da sie das Ergebnis beeinflussen können.",
    "Kein Gesichtsdruck: Vermeiden Sie es, Druck auf die behandelte Stelle auszuüben, um Reibung und Abdrücke zu verhindern.",
    "Keine chemischen Behandlungen: Verzichten Sie auf Behandlungen wie Botox oder chemische Peelings in den ersten zwei Wochen nach der Behandlung.",
    "Keine Salben ohne Rücksprache: Verwenden Sie keine medizinischen Salben oder Tropfen ohne Rücksprache mit Ihrem Spezialisten.",
    "Kein Chlorwasser: Vermeiden Sie den Kontakt mit chlorhaltigem Wasser (z. B. in Schwimmbädern), um die frisch behandelte Stelle zu schützen.",
    "Sanftes Abschminken: Sollten Sie sich geschminkt haben, entfernen Sie das Make-up sanft mit einem Wattepad und ohne Druck.",
    "Regelmäßige Nachpflege: Befolgen Sie die Anweisungen zur Nachbehandlung sorgfältig und kommen Sie bei Bedarf zu Nachkontrollen oder Auffrischungen."
]

GERMAN_CLOSING = (
    "Wenn Sie nach der Behandlung Probleme haben, stehen wir Ihnen gerne zur Seite und möchten "
    "sicherstellen, dass Sie bestmöglich betreut werden. Bitte zögern Sie nicht, uns zu kontaktieren, "
    "um Ihre Bedenken oder Fragen mit uns zu besprechen. Unser Ziel ist es, Ihnen eine positive "
    "Erfahrung zu bieten und gemeinsam nach Lösungen zu suchen."
)


# ============================================================
# TEXT WRAPPING — 3 separate functions, one per body part
# ============================================================

def wrap_lines(text, max_px, prefix="", continuation=""):
    """
    PIXEL-BASED line wrapping.
    Measures each word in real pixels using Cormorant Garamond font metrics.
    Fills each line as much as possible without exceeding max_px.

    prefix       = prepended to first line only  (e.g. "1. ")
    continuation = prepended to all wrapped lines (e.g. "   ")
    """
    words  = text.strip().split()
    lines  = []
    current_words = []
    current_px    = text_px(prefix)

    for word in words:
        space_px = char_width(' ') if current_words else 0.0
        word_px  = text_px(word)
        if current_px + space_px + word_px > max_px and current_words:
            pfx = prefix if not lines else continuation
            lines.append(pfx + ' '.join(current_words))
            current_words = [word]
            current_px    = text_px(continuation) + word_px
        else:
            current_words.append(word)
            current_px += space_px + word_px

    if current_words:
        pfx = prefix if not lines else continuation
        lines.append(pfx + ' '.join(current_words))

    return '\n'.join(lines)


def wrap_intro_or_closing(text):
    """PART 2/4 — Intro and Closing: 1 space indent, pixel-measured."""
    return wrap_lines(text, BOX_WIDTH, prefix=INTRO_INDENT, continuation=INTRO_INDENT)


def wrap_rule(number, text):
    """
    PART 3 — Numbered rule with hanging indent, pixel-measured.
    First line  : "N. text..."
    Continuation: "   text..." (spaces = width of prefix)
    """
    prefix = f"{number}. "
    cont   = " " * len(prefix)   # same char count keeps visual alignment
    return wrap_lines(text, BOX_WIDTH, prefix=prefix, continuation=cont)


def build_body(greeting, intro, rules, closing, lang="Deutsch"):
    """
    Assemble full body using pixel-accurate line wrapping.

    PART 1: greeting — no indent
    PART 2: intro    — 1 space indent
    [blank]
    PART 3: rules    — "N. " prefix, hanging indent
    [blank]
    PART 4: closing  — 1 space indent (same as intro)
    """
    part1 = greeting.strip()
    part2 = wrap_intro_or_closing(intro.strip())
    part3 = '\n'.join(wrap_rule(i + 1, rule.strip()) for i, rule in enumerate(rules))
    part4 = wrap_intro_or_closing(closing.strip())
    return f"{part1}\n{part2}\n\n{part3}\n\n{part4}"


# ============================================================
# DIAGNOSTICS
# ============================================================

def count_total_lines(greeting, intro, rules, closing, lang="Deutsch"):
    """Count total visual lines using pixel wrapping — used to calculate line spacing."""
    def line_count(text, prefix="", continuation=""):
        return len(wrap_lines(text, BOX_WIDTH, prefix=prefix, continuation=continuation).split('\n'))

    total  = 1                                          # greeting = 1 line
    total += line_count(intro,   "", "")
    total += 1                                          # blank line
    for i, rule in enumerate(rules):
        prefix = f"{i+1}. "
        cont   = " " * len(prefix)
        total += line_count(rule, prefix, cont)
    total += 1                                          # blank line
    total += line_count(closing, "", "")
    return total


def calculate_line_spacing(greeting, intro, rules, closing, lang=""):
    """
    Calculate exact line spacing so text fills BOX_HEIGHT perfectly.
    Formula: spacing = BOX_HEIGHT / (total_lines × FONT_PX)
    Clamped to 0.80–2.50 safe range.
    """
    BOX_HEIGHT = 2190
    FONT_PX    = 34.6 * 1.333   # 46.1px

    total   = count_total_lines(greeting, intro, rules, closing)
    spacing = BOX_HEIGHT / (total * FONT_PX)
    clamped = round(max(0.80, min(2.50, spacing)), 4)

    flag = ""
    if spacing > 2.0:
        flag = "  ⚠ very loose — translation may be too short"
    elif spacing < 0.85:
        flag = "  ⚠ very tight — auto-resize will help"

    print(f"  ✅  {lang:<14} {total:>2} lines → spacing {clamped}{flag}")
    return clamped


def validate_rules(rules, lang):
    if len(rules) != 16:
        print(f"  ⚠  WARNING ({lang}): expected 16 rules, got {len(rules)}")


def safe_filename(text):
    return re.sub(r'[^\w\s-]', '', text).strip().replace(' ', '_')


# ============================================================
# TRANSLATION
# ============================================================

def translate_content(treatment, lang):
    rules_numbered = "\n".join(f"{i+1}. {rule}" for i, rule in enumerate(GERMAN_RULES))
    german_intro   = GERMAN_INTRO_TEMPLATE.format(treatment=treatment)

    # Calculate target line count based on German (41 lines = full page)
    # If translation will be shorter, ask GPT to expand naturally
    german_lines  = 41   # German reference
    target_lines  = german_lines

    prompt = f"""Translate the following German texts into {lang}.

STRICT RULES:
- Translate EVERYTHING into {lang}. Zero German words in output.
- Translate the treatment name "{treatment}" naturally into {lang}.
- Every output field must be ONE SINGLE LINE — no line breaks inside any field.
- The "rules" array must have EXACTLY 16 items.
- Do not add, remove, or merge rules.

CRITICAL — CONTENT LENGTH (most important rule):
This text is printed on a fixed-size page. The German version fills the page with {target_lines} lines.
Your {lang} translation MUST also produce approximately {target_lines} lines.

MANDATORY for every single rule:
- Each rule MUST be 130-160 characters long.
- Count the characters as you write. If your translation is under 130 chars, you MUST expand it.
- Expand naturally by adding: the reason why, the time period, what to avoid specifically,
  or consequences of not following the rule. Keep it professional and useful.
- Example of TOO SHORT (bad):   "Avoid touching the treated area." (33 chars)
- Example of CORRECT (good):    "Avoid touching or scratching the treated area, as this can cause infections, irritation, or damage to the fresh treatment result." (128 chars)

MANDATORY for intro:
- Must be 2 full sentences, 150-200 characters total.

MANDATORY for closing:
- Must be 3 full sentences, 250-320 characters total.

Do NOT use shortened or telegraphic style. Write complete, professional, flowing sentences.

OUTPUT: Return ONLY valid JSON with exactly these keys:

{{
  "treatment_name": "translated name (title case)",
  "greeting": "translated greeting — single line",
  "intro": "2 sentences, 150-200 chars total, single line, include translated treatment name",
  "rules": [
    "rule 1 — 130-160 chars, complete sentence, no number",
    "rule 2 — 130-160 chars, complete sentence, no number",
    ... exactly 16 items ...
  ],
  "closing": "3 sentences, 250-320 chars total, single line"
}}

TEXTS TO TRANSLATE:

TREATMENT NAME: {treatment}
GREETING: {GERMAN_GREETING}
INTRO: {german_intro}
RULES:
{rules_numbered}
CLOSING: {GERMAN_CLOSING}
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=4000,
        response_format={"type": "json_object"}
    )

    try:
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"  ⚠ JSON parse error for {lang}: {e}")
        return {}


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    print("=" * 62)
    print("  Pflegehinweis Generator — 3-Part Calibrated Wrapping")
    print("=" * 62)
    print(f"\n  Part 1 (greeting) : full width, no indent")
    print(f"  Part 2 (intro)    : 1 space indent, pixel-measured (fills to {BOX_WIDTH:.0f}px)")
    print(f"  Part 3 (rules)    : 'N. ' prefix, pixel-measured")
    print(f"  Part 4 (closing)  : 1 space indent, pixel-measured")
    print(f"  Line spacing      : calculated per language to fill {BOX_HEIGHT:.0f}px height\n")

    treatment = input("Enter treatment name in German (e.g. Aromatherapie): ").strip()

    german_body  = build_body(
        GERMAN_GREETING,
        GERMAN_INTRO_TEMPLATE.format(treatment=treatment),
        GERMAN_RULES,
        GERMAN_CLOSING,
        "Deutsch"
    )
    german_lines   = count_total_lines(
        GERMAN_GREETING,
        GERMAN_INTRO_TEMPLATE.format(treatment=treatment),
        GERMAN_RULES,
        GERMAN_CLOSING
    )
    german_spacing = calculate_line_spacing(
        GERMAN_GREETING,
        GERMAN_INTRO_TEMPLATE.format(treatment=treatment),
        GERMAN_RULES,
        GERMAN_CLOSING,
        "Deutsch"
    )

    print(f"\n--- German preview (first 14 lines) ---")
    for line in german_body.split("\n")[:14]:
        print(f"  |{line}|")
    print(f"\n  Total visual lines : {german_lines}")
    print(f"  Line spacing       : {german_spacing} (Deutsch example)")
    print("----------------------------------------\n")

    confirm = input("Preview looks right? (y to continue / n to quit): ").strip().lower()
    if confirm != "y":
        print("\nQuitting.")
        exit()

    print(f"\nGenerating 10 languages for '{treatment}'...\n")

    rows = []
    treatment_names_by_lang = {"Deutsch": treatment}

    for lang in LANGUAGES:
        print(f"  → {lang}", end="  ", flush=True)

        if lang == "Deutsch":
            greeting       = GERMAN_GREETING
            intro          = GERMAN_INTRO_TEMPLATE.format(treatment=treatment)
            rules          = GERMAN_RULES
            closing        = GERMAN_CLOSING
            treatment_name = treatment
        else:
            data           = translate_content(treatment, lang)
            greeting       = data.get("greeting", GERMAN_GREETING)
            intro          = data.get("intro", GERMAN_INTRO_TEMPLATE.format(treatment=treatment))
            rules          = data.get("rules", GERMAN_RULES)
            closing        = data.get("closing", GERMAN_CLOSING)
            treatment_name = data.get("treatment_name", treatment)

        validate_rules(rules, lang)
        treatment_names_by_lang[lang] = treatment_name

        body         = build_body(greeting, intro, rules, closing, lang)
        line_spacing = calculate_line_spacing(greeting, intro, rules, closing, lang)

        rows.append({
            "Language"     : lang,
            "Treatment"    : treatment_name,
            "Heading"      : HEADING_TRANSLATIONS.get(lang, "PFLEGEHINWEIS"),
            "TreatmentName": treatment_name.upper(),
            "SubHeading"   : SUBHEADING_TRANSLATIONS.get(lang, ""),
            "Body"         : body,
            "LineSpacing"  : line_spacing
        })

    df = pd.DataFrame(rows)

    timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name   = safe_filename(treatment)
    output_file = f"Pflegehinweis_{safe_name}_10Languages_{timestamp}.csv"

    df.to_csv(output_file, index=False, quoting=csv.QUOTE_ALL, encoding="utf-8-sig")

    print(f"\n✅  CSV saved: {output_file}\n")

    print("📋  Canva Field Mapping:")
    print("    Heading       → heading text box")
    print("    TreatmentName → treatment name box (uppercase)")
    print("    SubHeading    → sub-heading box")
    print("    Body          → body text box")
    print("    LineSpacing   → body text box LINE SPACING  ← every slide fills perfectly\n")

    print("📝  Translated treatment names:")
    for lang, name in treatment_names_by_lang.items():
        print(f"    {lang:<14} → {name}")

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║  CANVA BODY TEXT BOX — SET ONCE, NEVER CHANGE               ║
║                                                              ║
║  Font         : Cormorant Garamond 34.6pt                    ║
║  Line spacing : 1.1  ← fixed for all languages              ║
║  Box size     : 1802 × 2190 px — do not resize              ║
║  Auto-resize  : ON  ← safety net                            ║
║                                                              ║
║  3-part wrapping calibrated directly from Canva:            ║
║    Greeting  → full width                                    ║
║    Intro     → 1 space indent, 92 char lines                 ║
║    Rules     → "N. " prefix, 89 char lines                   ║
║    Closing   → 1 space indent, 92 char lines                 ║
╚══════════════════════════════════════════════════════════════╝
""")