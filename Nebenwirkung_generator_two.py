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
# Box: 1733px wide × 2168px tall
# Calibrated: 89 'a' chars/line | 65 Cyrillic/line
# ============================================================

def _load_char_widths():
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
    woff = next(m for m in tgz.getmembers()
                if 'latin-400.woff' in m.name and 'italic' not in m.name)
    font = TTFont(io.BytesIO(tgz.extractfile(woff).read()))

    upm         = font['head'].unitsPerEm
    cmap        = font.getBestCmap()
    hmtx        = font['hmtx'].metrics
    font_px     = 34.6 * 1.333
    px_per_unit = font_px / upm

    table = {}
    for cp in range(32, 0x024F):
        if cp in cmap:
            table[cp] = hmtx[cmap[cp]][0] * px_per_unit
    if 32 not in table:
        table[32] = font_px * 0.25

    # Calibrate: 103 'a' per line — DO NOT CHANGE
    cal = 1849.83 / (103 * table[ord('a')])
    table = {k: v * cal for k, v in table.items()}

    # Cyrillic — ALL chars set to real measured width
    # User confirmed: 89 chars/line works correctly (no overflow, no space)
    cyr_px = 1849.83 / 89

    for ch in 'абвгдеёжзийклмнопрстуфхцчшщъыьэюяАБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ':
        table[ord(ch)] = cyr_px

    return table

print("Loading font metrics...", end=" ", flush=True)
try:
    CHAR_WIDTHS = _load_char_widths()
    FALLBACK_W  = CHAR_WIDTHS[ord('a')]
    print(f"✅ ({len(CHAR_WIDTHS)} chars)")
except Exception as e:
    print(f"⚠ fallback ({e})")
    CHAR_WIDTHS = {}
    FALLBACK_W  = 1733.0 / 89

def char_width(ch):  return CHAR_WIDTHS.get(ord(ch), FALLBACK_W)
def text_px(text):   return sum(char_width(ch) for ch in text)

BOX_WIDTH    = 1849.83  # universal for all languages — box never changes
BOX_HEIGHT   = 2168.0
FONT_PX      = 34.6 * 1.333
INTRO_INDENT = ""     # no indent — space was causing the leading space bug


# ============================================================
# PIXEL-BASED WRAPPING (same as first code)
# ============================================================

def wrap_lines(text, max_px, prefix="", continuation=""):
    words = text.strip().split()
    lines, current_words, current_px = [], [], text_px(prefix)
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
    return wrap_lines(text, BOX_WIDTH, prefix="", continuation="")

def wrap_item(number, text):
    prefix = f"{number}. "
    cont   = " " * len(prefix)
    return wrap_lines(text, BOX_WIDTH, prefix=prefix, continuation=cont)

def build_body(greeting, intro, items, closing, lang="", include_greeting=True):
    part1 = greeting.strip() + "\n" if include_greeting else ""
    part2 = wrap_intro_or_closing(intro.strip())
    part3 = '\n'.join(wrap_item(i + 1, item.strip()) for i, item in enumerate(items))
    part4 = wrap_intro_or_closing(closing.strip())
    return f"{part1}{part2}\n\n{part3}\n\n{part4}"

def count_total_lines(greeting, intro, items, closing, lang="", include_greeting=True):
    def lc(text, prefix="", continuation=""):
        return len(wrap_lines(text, BOX_WIDTH, prefix=prefix, continuation=continuation).split('\n'))
    total  = 1 if include_greeting else 0
    total += lc(intro, "", "")
    total += 1
    for i, item in enumerate(items):
        prefix = f"{i+1}. "
        total += lc(item, prefix, " " * len(prefix))
    total += 1
    total += lc(closing, "", "")
    return total

def calculate_line_spacing(greeting, intro, items, closing, lang="", include_greeting=True):
    total = count_total_lines(greeting, intro, items, closing, lang, include_greeting)
    print(f"  ✅  {lang:<14} {total:>2} lines → spacing 1.1 (auto-resize ON)")
    return 1.1


# ============================================================
# HEADINGS
# ============================================================

HEADING_TRANSLATIONS = {
    "Deutsch":     "NEBENWIRKUNGEN / ALTERNATIVEN",
    "Englisch":    "SIDE EFFECTS / ALTERNATIVES",
    "Türkisch":    "YAN ETKİLER / ALTERNATİFLER",
    "Polnisch":    "SKUTKI UBOCZNE / ALTERNATYWY",
    "Russisch":    "ПОБОЧНЫЕ ЭФФЕКТЫ / АЛЬТЕРНАТИВЫ",
    "Italienisch": "EFFETTI COLLATERALI / ALTERNATIVE",
    "Spanisch":    "EFECTOS SECUNDARIOS / ALTERNATIVAS",
    "Französisch": "EFFETS SECONDAIRES / ALTERNATIVES",
    "Ungarisch":   "MELLÉKHATÁSOK / ALTERNATÍVÁK",
    "Rumänisch":   "EFECTE SECUNDARE / ALTERNATIVE"
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
# GERMAN SOURCE — Treatment-agnostic templates
# ============================================================

GERMAN_GREETING = "Liebe Kundin, lieber Kunde,"

GERMAN_PAGE1_INTRO_TEMPLATE = (
    "es ist wichtig zu beachten, dass die Nebenwirkungen der {treatment} Behandlung je nach "
    "individueller Beschaffenheit der Haut, Gesundheitszuständen und der Technik variieren können. "
    "Folgende Punkte bieten allgemeine Informationen zu möglichen Nebenwirkungen:"
)

GERMAN_SIDE_EFFECTS = [
    "Rötungen: Unmittelbar nach der {treatment} Behandlung kann die Haut gelegentlich gerötet erscheinen. Diese Rötung ist auf eine leichte Reizung der oberflächlichen Hautschichten zurückzuführen. In den meisten Fällen ist diese Reaktion mild und vorübergehend und klingt innerhalb weniger Stunden bis einiger Tage von selbst wieder ab.",
    "Empfindlichkeit: Die behandelte Hautpartie kann nach der Behandlung vorübergehend empfindlicher reagieren. Kosmetikprodukte mit reizenden Inhaltsstoffen sowie äußere Einflüsse wie Kälte, Wind oder Sonneneinstrahlung können die Haut in diesem Zeitraum sensibler machen. Diese erhöhte Empfindlichkeit ist eine seltene, vorübergehende Reaktion.",
    "Trockene Haut: Durch die {treatment} Behandlung kann die Haut vorübergehend trockener oder spannender wirken. Wir empfehlen, die Haut mit einer milden, feuchtigkeitsspendenden Pflege zu unterstützen und aggressive Reinigungs- oder Pflegeprodukte zu vermeiden, um die Regeneration zu fördern.",
    "Allergische Reaktionen: Obwohl selten, können allergische Reaktionen auf verwendete Substanzen auftreten. Typische Symptome sind verstärkte Rötungen, Schwellungen oder ausgeprägter Juckreiz. Um das Risiko zu minimieren, empfehlen wir vor der Behandlung unbedingt einen Allergietest.",
    "Unregelmäßiges Ergebnis: In seltenen Fällen kann das Ergebnis auf der Haut ungleichmäßig oder fleckig erscheinen. Diese Unebenheiten sind häufig auf individuelle Hautmerkmale zurückzuführen, wie unterschiedliche Hauttexturen oder den Hautzustand vor der Behandlung.",
    "Temporäre Verfärbungen: Vorübergehende Verfärbungen der Haut sind möglich, insbesondere bei Personen mit heller Haut. Diese Farbveränderungen entstehen durch Pigmente, die sich kurzzeitig in der obersten Hautschicht ablagern, und verschwinden in der Regel innerhalb weniger Tage von selbst.",
    "Weitere Reaktionen: In seltenen Fällen können weitere lokale Reaktionen wie leichter Juckreiz, Spannungsgefühl oder Schwellungen auftreten. Diese sind in der Regel mild und vorübergehend. Sollten Sie stärkere oder anhaltende Beschwerden bemerken, wenden Sie sich bitte umgehend an uns."
]

GERMAN_PAGE1_CLOSING = (
    "Die meisten Kunden erleben nach der {treatment} Behandlung überwiegend positive Ergebnisse "
    "mit keinen oder nur minimalen Nebenwirkungen. Individuelle Reaktionen können variieren, "
    "daher empfehlen wir vorab eine detaillierte Beratung. Bei Unsicherheiten stehen wir Ihnen "
    "gerne zur Verfügung."
)

GERMAN_PAGE2_INTRO = (
    "Sollten Sie an alternativen Behandlungen interessiert sein, präsentieren wir Ihnen hier "
    "anderweitige Methoden und deren Nebenwirkungen. So können Sie eine fundierte Entscheidung "
    "treffen, die Ihren individuellen Bedürfnissen und Vorlieben entspricht."
)

GERMAN_ALTERNATIVES = [
    "Microblading: Microblading ist eine semi-permanente Methode, bei der mit einer feinen Klinge manuell pigmentierte Härchen in die obere Hautschicht eingeritzt werden. Nebenwirkungen: Häufig kommt es zu Rötungen, leichten Schwellungen oder Krustenbildung. Mögliche Risiken sind Entzündungen, Infektionen und Narbenbildung, insbesondere bei unzureichender Nachsorge.",
    "Permanent Make-up (PMU): PMU ist eine Pigmentierung, bei der Farbpigmente mit feinen Nadeln in die Haut eingebracht werden. Die Haltbarkeit beträgt in der Regel mehrere Jahre. Nebenwirkungen: Vorübergehende Schwellungen, Rötungen, Krustenbildung und mögliche Pigmentveränderungen. In seltenen Fällen können Narben oder allergische Reaktionen auftreten.",
    "Riso Rolling: Bei dieser Methode werden mithilfe eines Pigmentiergeräts feine Punkte in die Haut eingebracht, die ein pudrig-weiches Farbergebnis erzeugen. Nebenwirkungen: Vorübergehende Rötungen und Schwellungen sind normal. Es kann zu Krustenbildung kommen. In seltenen Fällen treten allergische Reaktionen oder Pigmentveränderungen auf.",
    "Henna Brows: Henna Brows sind eine pflanzliche Alternative zur klassischen Färbung. Die Haltbarkeit beträgt bei guter Pflege bis zu zwei Wochen auf der Haut. Nebenwirkungen: Allergische Reaktionen auf pflanzliche Inhaltsstoffe sind möglich, ebenso Hautreizungen oder Rötungen, vor allem bei empfindlicher Haut.",
    "Brow Lifting (Laminierung): Beim Brow Lifting werden die natürlichen Härchen mit speziellen Lotionen fixiert und in Form gebracht. Die Form bleibt mehrere Wochen erhalten. Nebenwirkungen: Leichte Rötungen, Reizungen oder ein Brennen an der Anwendungsstelle können auftreten, insbesondere bei empfindlicher Haut.",
    "Brauenseren (Wachstumsförderung): Diese Kosmetikprodukte regen das natürliche Haarwachstum an und sorgen bei regelmäßiger Anwendung für dichtere Ergebnisse. Nebenwirkungen: Leichte Hautreizungen, Juckreiz oder allergische Reaktionen sind möglich, insbesondere bei sensibler Haut.",
    "Brauen-Extensions: Feine synthetische Härchen werden auf die bestehenden Haare oder die Haut geklebt, um einen dichteren Look zu erzeugen. Nebenwirkungen: Allergische Reaktionen auf den Kleber, Hautreizungen und Entzündungen sind möglich."
]

GERMAN_PAGE2_CLOSING = (
    "Es ist wichtig zu beachten, dass diese Alternativmethoden individuell unterschiedlich "
    "wahrgenommen werden und die Risiken variieren können. Vor einer Entscheidung empfehlen wir "
    "eine gründliche Beratung. Bei Unsicherheiten stehen wir Ihnen auch bei diesem Thema gerne "
    "zur Verfügung."
)


# ============================================================
# GPT TRANSLATION
# ============================================================

def translate_content(treatment, lang):
    effects_numbered = "\n".join(f"{i+1}. {e.replace('{treatment}', treatment)}"
                                  for i, e in enumerate(GERMAN_SIDE_EFFECTS))
    alts_numbered    = "\n".join(f"{i+1}. {a}" for i, a in enumerate(GERMAN_ALTERNATIVES))
    page1_intro      = GERMAN_PAGE1_INTRO_TEMPLATE.format(treatment=treatment)
    page1_closing    = GERMAN_PAGE1_CLOSING.format(treatment=treatment)

    # Line count targets based on German
    german_p1_lines = count_total_lines(
        GERMAN_GREETING,
        page1_intro,
        [e.format(treatment=treatment) for e in GERMAN_SIDE_EFFECTS],
        page1_closing,
        lang
    )
    german_p2_lines = count_total_lines(
        GERMAN_GREETING,
        GERMAN_PAGE2_INTRO,
        GERMAN_ALTERNATIVES,
        GERMAN_PAGE2_CLOSING,
        lang
    )

    prompt = f"""Translate the following German beauty texts into {lang}.

STRICT RULES:
- Translate EVERYTHING into {lang}. Zero German words in output.
- Translate the treatment name "{treatment}" into natural {lang}.
- Every field must be ONE SINGLE LINE — no line breaks.
- "side_effects" array must have EXACTLY 7 items.
- "alternatives" array must have EXACTLY 7 items.
- Each array item is ONE long line, no line breaks, no number prefix.

CONTENT LENGTH (critical):
Page 1 must produce ~{german_p1_lines} lines when printed. Page 2 must produce ~{german_p2_lines} lines.
To achieve this:
- Each side_effect item: min 300 characters — write fully with explanation and consequences.
- Each alternative item: min 250 characters — include description, purpose, and side effects.
- intro and closing: translate at full length, min 200 chars each.
- Do NOT shorten. Every item must be a complete, detailed paragraph.

OUTPUT: Return ONLY valid JSON:

{{
  "treatment_name": "translated name (title case)",
  "greeting": "translated greeting",
  "page1_intro": "min 200 chars, single line",
  "side_effects": [
    "effect 1 — min 300 chars, complete paragraph, no number",
    "effect 2 — min 300 chars, complete paragraph, no number",
    "effect 3 — min 300 chars, complete paragraph, no number",
    "effect 4 — min 300 chars, complete paragraph, no number",
    "effect 5 — min 300 chars, complete paragraph, no number",
    "effect 6 — min 300 chars, complete paragraph, no number",
    "effect 7 — min 300 chars, complete paragraph, no number"
  ],
  "page1_closing": "min 200 chars, single line",
  "page2_intro": "min 200 chars, single line",
  "alternatives": [
    "alternative 1 — min 250 chars, complete paragraph, no number",
    "alternative 2 — min 250 chars, complete paragraph, no number",
    "alternative 3 — min 250 chars, complete paragraph, no number",
    "alternative 4 — min 250 chars, complete paragraph, no number",
    "alternative 5 — min 250 chars, complete paragraph, no number",
    "alternative 6 — min 250 chars, complete paragraph, no number",
    "alternative 7 — min 250 chars, complete paragraph, no number"
  ],
  "page2_closing": "min 200 chars, single line"
}}

GERMAN TEXTS:
TREATMENT: {treatment}
GREETING: {GERMAN_GREETING}
PAGE 1 INTRO: {page1_intro}
SIDE EFFECTS (7):
{effects_numbered}
PAGE 1 CLOSING: {page1_closing}
PAGE 2 INTRO: {GERMAN_PAGE2_INTRO}
ALTERNATIVES (7):
{alts_numbered}
PAGE 2 CLOSING: {GERMAN_PAGE2_CLOSING}
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=6000,
        response_format={"type": "json_object"}
    )
    try:
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"  ⚠ JSON parse error: {e}")
        return {}


def safe_filename(text):
    return re.sub(r'[^\w\s-]', '', text).strip().replace(' ', '_')


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    print("=" * 62)
    print("  Nebenwirkungen / Alternativen Generator")
    print("=" * 62)
    print(f"  Box      : {BOX_WIDTH:.0f} × {BOX_HEIGHT:.0f}px")
    print(f"  Font     : Cormorant Garamond 34.6pt")
    print(f"  Wrapping : pixel-measured\n")

    treatment = input("Enter treatment name in German (e.g. Airbrush Brows): ").strip()

    # Build German preview
    de_p1_intro   = GERMAN_PAGE1_INTRO_TEMPLATE.format(treatment=treatment)
    de_p1_closing = GERMAN_PAGE1_CLOSING.format(treatment=treatment)
    de_effects    = [e.format(treatment=treatment) for e in GERMAN_SIDE_EFFECTS]

    german_page1 = build_body(GERMAN_GREETING, de_p1_intro, de_effects, de_p1_closing, "Deutsch", include_greeting=True)
    german_page2 = build_body(GERMAN_GREETING, GERMAN_PAGE2_INTRO, GERMAN_ALTERNATIVES, GERMAN_PAGE2_CLOSING, "Deutsch", include_greeting=False)

    print("\n--- German Page 1 preview (first 10 lines) ---")
    for line in german_page1.split("\n")[:10]:
        print(f"  |{line}|")

    confirm = input("\nPreview OK? (y to continue): ").strip().lower()
    if confirm != "y":
        exit()

    print(f"\nGenerating 10 languages for '{treatment}'...\n")

    rows = []
    names_by_lang = {"Deutsch": treatment}

    for lang in LANGUAGES:
        print(f"  → {lang}", end="  ", flush=True)

        if lang == "Deutsch":
            greeting      = GERMAN_GREETING
            page1_intro   = de_p1_intro
            side_effects  = de_effects
            page1_closing = de_p1_closing
            page2_intro   = GERMAN_PAGE2_INTRO
            alternatives  = GERMAN_ALTERNATIVES
            page2_closing = GERMAN_PAGE2_CLOSING
            treatment_name = treatment
        else:
            data           = translate_content(treatment, lang)
            greeting       = data.get("greeting",      GERMAN_GREETING)
            page1_intro    = data.get("page1_intro",   de_p1_intro)
            side_effects   = data.get("side_effects",  de_effects)
            page1_closing  = data.get("page1_closing", de_p1_closing)
            page2_intro    = data.get("page2_intro",   GERMAN_PAGE2_INTRO)
            alternatives   = data.get("alternatives",  GERMAN_ALTERNATIVES)
            page2_closing  = data.get("page2_closing", GERMAN_PAGE2_CLOSING)
            treatment_name = data.get("treatment_name", treatment)

        # Validate counts
        for label, arr, expected in [("side_effects", side_effects, 7), ("alternatives", alternatives, 7)]:
            if len(arr) != expected:
                print(f"\n    ⚠ {lang} {label}: expected {expected}, got {len(arr)}")

        names_by_lang[lang] = treatment_name

        page1_body = build_body(greeting, page1_intro, side_effects, page1_closing, lang, include_greeting=True)
        page2_body = build_body(greeting, page2_intro, alternatives, page2_closing, lang, include_greeting=False)

        spacing_p1 = calculate_line_spacing(greeting, page1_intro, side_effects, page1_closing, lang, True)
        spacing_p2 = calculate_line_spacing(greeting, page2_intro, alternatives, page2_closing, lang, False)

        rows.append({
            "Language"        : lang,
            "Treatment"       : treatment_name,
            "Heading"         : HEADING_TRANSLATIONS.get(lang, "NEBENWIRKUNGEN / ALTERNATIVEN"),
            "TreatmentName"   : treatment_name.upper(),
            "SubHeading"      : SUBHEADING_TRANSLATIONS.get(lang, ""),
            "Body_Page1"      : page1_body,
            "LineSpacing_Page1": spacing_p1,
            "Body_Page2"      : page2_body,
            "LineSpacing_Page2": spacing_p2,
        })

    df = pd.DataFrame(rows)
    timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name   = safe_filename(treatment)
    output_file = f"Nebenwirkungen_{safe_name}_10Languages_{timestamp}.csv"
    df.to_csv(output_file, index=False, quoting=csv.QUOTE_ALL, encoding="utf-8-sig")

    print(f"\n✅  CSV saved: {output_file}")
    print(f"\n📋  Canva Field Mapping:")
    print(f"    Heading           → heading text box")
    print(f"    TreatmentName     → treatment name box")
    print(f"    SubHeading        → sub-heading box")
    print(f"    Body_Page1        → Page 1 body text box")
    print(f"    LineSpacing_Page1 → Page 1 line spacing field")
    print(f"    Body_Page2        → Page 2 body text box")
    print(f"    LineSpacing_Page2 → Page 2 line spacing field")
    print(f"\n📝  Translated treatment names:")
    for lang, name in names_by_lang.items():
        print(f"    {lang:<14} → {name}")