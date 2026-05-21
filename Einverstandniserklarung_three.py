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

BOX_WIDTH_P1  = 1971.15
MAX_LINES_P1  = 3
FONT_PX       = 34.6 * 1.333

def _load_char_widths():
    try:
        from fontTools.ttLib import TTFont
    except ImportError:
        import subprocess
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
    px_per_unit = FONT_PX / upm

    table = {}
    for cp in range(32, 0x024F):
        if cp in cmap:
            table[cp] = hmtx[cmap[cp]][0] * px_per_unit
    if 32 not in table:
        table[32] = FONT_PX * 0.25

    a_px = table[ord('a')]
    cal  = BOX_WIDTH_P1 / (102 * a_px)
    table = {k: v * cal for k, v in table.items()}
    a_px = table[ord('a')]

    P_px = BOX_WIDTH_P1 / 58

    cyr_lower = {
        'а':1.0190,'б':1.1209,'в':1.1209,'г':0.9171,'д':1.1209,'е':1.0190,'ё':1.0190,
        'ж':1.4266,'з':0.9171,'и':1.1209,'й':1.1209,'к':1.0190,'л':1.0190,'м':1.3247,
        'н':1.1209,'о':1.0190,'п':1.1209,'р':1.0190,'с':0.9171,'т':1.0190,'у':1.0190,
        'ф':1.3247,'х':1.0190,'ц':1.1209,'ч':1.0190,'ш':1.4266,'щ':1.5285,'ъ':1.1209,
        'ы':1.3247,'ь':1.0190,'э':1.0190,'ю':1.5285,'я':1.1209,
    }
    cyr_upper = {
        'А':1.00,'Б':1.00,'В':1.00,'Г':0.80,'Д':1.00,'Е':0.90,'Ё':0.90,
        'Ж':1.20,'З':0.90,'И':1.00,'Й':1.00,'К':1.00,'Л':1.00,'М':1.20,
        'Н':1.00,'О':1.10,'П':1.00,'Р':0.90,'С':1.00,'Т':1.00,'У':0.90,
        'Ф':1.10,'Х':1.00,'Ц':1.00,'Ч':0.90,'Ш':1.20,'Щ':1.30,'Ъ':1.00,
        'Ы':1.20,'Ь':1.00,'Э':1.00,'Ю':1.40,'Я':1.00,
    }
    for ch, ratio in cyr_lower.items():
        table[ord(ch)] = a_px * ratio
    for ch, ratio in cyr_upper.items():
        table[ord(ch)] = P_px * ratio

    return table


print("Loading font metrics...", end=" ", flush=True)
try:
    CHAR_WIDTHS = _load_char_widths()
    FALLBACK_W  = CHAR_WIDTHS[ord('a')]
    fit_a = int(BOX_WIDTH_P1 / CHAR_WIDTHS[ord('a')])
    fit_P = int(BOX_WIDTH_P1 / CHAR_WIDTHS[ord('П')])
    print(f"✅  a={fit_a}/line  П={fit_P}/line")
except Exception as e:
    print(f"⚠  fallback to char count ({e})")
    CHAR_WIDTHS = {}
    FALLBACK_W  = BOX_WIDTH_P1 / 102


def char_w(ch):
    return CHAR_WIDTHS.get(ord(ch), FALLBACK_W)

def text_px(text):
    return sum(char_w(c) for c in text)


def wrap_pixels(text, box_width, prefix="", continuation=""):
    words = text.strip().split()
    lines = []
    cur_words = []
    cur_px    = text_px(prefix)

    for word in words:
        sp_px   = char_w(' ') if cur_words else 0.0
        word_px = text_px(word)
        if cur_px + sp_px + word_px > box_width and cur_words:
            pfx = prefix if not lines else continuation
            lines.append(pfx + ' '.join(cur_words))
            cur_words = [word]
            cur_px    = text_px(continuation) + word_px
        else:
            cur_words.append(word)
            cur_px += sp_px + word_px

    if cur_words:
        pfx = prefix if not lines else continuation
        lines.append(pfx + ' '.join(cur_words))

    return lines


def wrap_plain(text, box_width=BOX_WIDTH_P1):
    return '\n'.join(wrap_pixels(text, box_width))


def wrap_item(number, text, box_width, list_indent="        "):
    prefix = list_indent + f"{number}."
    cont   = list_indent + (" " * len(f"{number}."))
    return '\n'.join(wrap_pixels(text, box_width, prefix=prefix, continuation=cont))


def count_lines_plain(text, box_width=BOX_WIDTH_P1):
    return len(wrap_pixels(text, box_width))


def build_page1(eligibility_box, lang="Deutsch"):
    lines = wrap_pixels(eligibility_box, BOX_WIDTH_P1)
    if len(lines) > MAX_LINES_P1:
        print(f"\n  ⚠  {lang} Page1 = {len(lines)} lines (max {MAX_LINES_P1}) — text too long!")
    return '\n'.join(lines)


BOX_WIDTH_P2  = BOX_WIDTH_P1
LIST_INDENT   = "        "

def build_page2(para1, para2, para3, para4, intro, aftercare,
                consent1, consent2, consent3):
    p1 = wrap_plain(para1, BOX_WIDTH_P2)
    p2 = wrap_plain(para2, BOX_WIDTH_P2)
    p3 = wrap_plain(para3, BOX_WIDTH_P2)
    p4 = wrap_plain(para4, BOX_WIDTH_P2)
    p_intro = wrap_plain(intro, BOX_WIDTH_P2)
    items = '\n'.join(
        wrap_item(i + 1, item.strip(), BOX_WIDTH_P2, LIST_INDENT)
        for i, item in enumerate(aftercare)
    )
    c1 = wrap_plain(consent1, BOX_WIDTH_P2)
    c2 = wrap_plain(consent2, BOX_WIDTH_P2)
    c3 = wrap_plain(consent3, BOX_WIDTH_P2)
    return (f"{p1}\n\n{p2}\n\n{p3}\n\n{p4}\n\n"
            f"{p_intro}\n{items}\n\n"
            f"{c1}\n\n{c2}\n\n{c3}")


HEADING_TRANSLATIONS = {
    "Deutsch":     "EINVERSTÄNDNISERKLÄRUNG",
    "Englisch":    "CONSENT FORM",
    "Türkisch":    "ONAY FORMU",
    "Polnisch":    "FORMULARZ ZGODY",
    "Russisch":    "ФОРМА СОГЛАСИЯ",
    "Italienisch": "MODULO DI CONSENSO",
    "Spanisch":    "FORMULARIO DE CONSENTIMIENTO",
    "Französisch": "FORMULAIRE DE CONSENTEMENT",
    "Ungarisch":   "HOZZÁJÁRULÁSI NYILATKOZAT",
    "Rumänisch":   "FORMULAR DE CONSIMȚĂMÂNT"
}

SUBHEADING_TRANSLATIONS = {
    "Deutsch":     "BITTE LESEN SIE DAS DOKUMENT AUFMERKSAM UND UNTERSCHREIBEN SIE ES",
    "Englisch":    "PLEASE READ THIS DOCUMENT CAREFULLY AND SIGN IT",
    "Türkisch":    "LÜTFEN BU DOKÜMANI DİKKATLİ OKUYUN VE İMZALAYIN",
    "Polnisch":    "PROSZĘ PRZECZYTAĆ TEN DOKUMENT UWAŻNIE I GO PODPISAĆ",
    "Russisch":    "ПОЖАЛУЙСТА, ВНИМАТЕЛЬНО ПРОЧИТАЙТЕ ЭТОТ ДОКУМЕНТ И ПОДПИШИТЕ ЕГО",
    "Italienisch": "SI PREGA DI LEGGERE ATTENTAMENTE QUESTO DOCUMENTO E FIRMARLO",
    "Spanisch":    "POR FAVOR LEA ESTE DOCUMENTO CON ATENCIÓN Y FÍRMELO",
    "Französisch": "VEUILLEZ LIRE ATTENTIVEMENT CE DOCUMENT ET LE SIGNER",
    "Ungarisch":   "KÉRJÜK, OLVASSA EL FIGYELMESEN EZT A DOKUMENTUMOT ÉS ÍRJA ALÁ",
    "Rumänisch":   "VĂ RUGĂM SĂ CITIȚI CU ATENȚIE ACEST DOCUMENT ȘI SĂ-L SEMNAȚI"
}

LANGUAGES = [
    "Deutsch", "Englisch", "Türkisch", "Polnisch", "Russisch",
    "Italienisch", "Spanisch", "Französisch", "Ungarisch", "Rumänisch"
]

FORM_FIELDS_DE = {
    "Name": "Name", "Straße": "Straße", "Ort": "Ort",
    "Postleitzahl": "Postleitzahl", "Telefon": "Telefon", "Geburtstag": "Geburtstag",
    "Sachlagen_Intro": "Liegt eine der folgenden Sachlagen vor:",
    "Anmerkungen": "Anmerkungen zu oben genannten Sachlagen:",
    "Ort_Datum": "Ort, Datum", "Unterschrift": "Unterschrift"
}

MEDICAL_CONDITIONS_DE = [
    "Ekzeme", "Dermatitis", "Psoriasis", "Herpes Simplex", "Allergien",
    "Cremen am Auge/Braue", "Offene Wunden", "Schilddrüsenerkrankung",
    "Chemotherapie", "Infektionskrankheiten", "Fieberhafte Infekte",
    "Augenerkrankungen", "Epileptiker", "Hepatitis Erkrankung",
    "Cortisonbehandlung", "Akute Erkrankung", "Chirurgischer Eingriff",
    "Fettige Haut", "Schwangerschaft"
]

GERMAN_ELIGIBILITY_BOX_TEMPLATE = (
    "Die {treatment} Behandlung darf nur vorgenommen werden, wenn kein Hinweis auf eine "
    "entgegenstehende Kontraindikation vorliegt. Eine wahrheitsgemäße Beantwortung der "
    "nachfolgenden Fragen ist Voraussetzung. Die Behandlung erfolgt auf eigenes Risiko."
)

GERMAN_PAGE2_PARA1 = (
    "Sollten während des vorgesehenen Behandlungszeitraums Veränderungen in Bezug auf die oben genannten "
    "Indikationen des Gesundheitszustandes auftreten, so ist der Kunde verpflichtet, diese umgehend bekannt zu "
    "geben und gegebenenfalls einen Arzt aufzusuchen."
)
GERMAN_PAGE2_PARA2_TEMPLATE = (
    "Vor der {treatment} Behandlung wird der Behandlungsbereich gründlich gereinigt und professionell vorbereitet. "
    "Die Kosmetikerin analysiert den Bereich und bespricht die gewünschten Ergebnisse individuell mit dem Kunden. "
    "Die Behandlung wird sorgfältig nach aktuellen Fachstandards durchgeführt, wobei alle notwendigen Schritte "
    "unternommen werden, um ein optimales und sicheres Ergebnis zu erzielen. "
    "Nach der Behandlung wird das Ergebnis abschließend kontrolliert und bei Bedarf perfektioniert."
)
GERMAN_PAGE2_PARA3_TEMPLATE = (
    "Das Ergebnis der {treatment} Behandlung ist unmittelbar sichtbar und kann mehrere Wochen anhalten, "
    "abhängig von Hauttyp, individueller Pflege und weiteren persönlichen Faktoren. "
    "Die Behandlung bietet eine gezielte und natürliche Verbesserung, ohne dass täglich aufwändige Zusatzpflege erforderlich ist."
)
GERMAN_PAGE2_PARA4_TEMPLATE = (
    "Die Anzahl der Folgebehandlungen kann je nach individuellen Faktoren variieren. In der Regel wird eine "
    "Auffrischung alle 6 bis 8 Wochen empfohlen. Dies hängt von verschiedenen Faktoren ab, wie zum Beispiel dem "
    "Hauttyp, der täglichen Pflege und der gewünschten Intensität des Ergebnisses. Nach der ersten {treatment} "
    "Behandlung oder dem Wechsel eines Studios kann es vorkommen, dass das Ergebnis nicht die volle Haltbarkeit "
    "erreicht. Auch eine allergische Reaktion kann nicht vollständig ausgeschlossen werden. Dem Kunden ist hiermit "
    "bewusst, dass die endgültige Haltbarkeit und das Erscheinungsbild des Ergebnisses nicht mit Sicherheit "
    "vorhergesagt werden können."
)
GERMAN_PAGE2_INTRO_TEMPLATE = (
    "Nach der {treatment} Behandlung gibt es einige wichtige Punkte zu beachten, "
    "um das bestmögliche Ergebnis zu erzielen und die Haltbarkeit zu maximieren:"
)
GERMAN_AFTERCARE = [
    "Vermeiden Sie es, die behandelte Stelle in den ersten 24 Stunden nach der Behandlung zu berühren oder zu reiben.",
    "Vermeiden Sie den Kontakt mit Wasser auf der behandelten Stelle in den ersten 24 Stunden.",
    "Hohe Temperaturen oder Dampf sollten in den ersten 48 Stunden vermieden werden.",
    "Tragen Sie in den ersten 24 Stunden kein Make-up auf die behandelte Stelle auf.",
    "Ölhaltige Produkte können das Ergebnis der Behandlung beeinträchtigen.",
    "Scrubs oder Peelings im Behandlungsbereich vermeiden, da diese das Ergebnis schneller entfernen können.",
    "Verwenden Sie, wenn nötig, milde Reinigungsmittel, die das Behandlungsergebnis nicht beeinträchtigen.",
    "Vermeiden Sie direkte Sonneneinstrahlung in den ersten 48 Stunden nach der Behandlung.",
    "Schwimmen in Pools oder Baden im Meer sollte in den ersten Tagen vermieden werden.",
    "Vermeiden Sie starkes Schwitzen in den ersten 24 Stunden nach der Behandlung.",
    "In den ersten 72 Stunden sollten keine anderen kosmetischen Behandlungen im Behandlungsbereich durchgeführt werden.",
    "Chemische Produkte sollten nicht mit der behandelten Stelle in Kontakt kommen.",
    "In den ersten Stunden kann das Ergebnis intensiver erscheinen und sich später etwas verändern."
]
GERMAN_PAGE2_CONSENT1 = (
    "Ich, der Kunde, bin mir bewusst, dass bei unsachgemäßer Pflege im Nachhinein eine allergische Reaktion oder "
    "Entzündung auftreten kann."
)
GERMAN_PAGE2_CONSENT2 = (
    "Ich bin mit der Durchführung der Behandlung einverstanden und wurde umfassend über alle Risiken und "
    "möglichen Nebenwirkungen aufgeklärt. Ich bestätige, dass ich über die richtige Nachbehandlung informiert "
    "wurde. Ich habe die oben stehenden Informationen gelesen, verstanden und alle Fragen wurden mir vollständig "
    "und verständlich beantwortet. Ich hatte ausreichend Zeit, meine Entscheidung zu überdenken."
)
GERMAN_PAGE2_CONSENT3 = (
    "Alle hier gemachten Angaben unterliegen dem Datenschutz und werden streng vertraulich behandelt. Ich habe "
    "diese Informationen vor der Anwendung gelesen und stimme mit meiner Unterschrift zu."
)


def translate_content(treatment, lang, german_eligibility):
    # Build treatment-specific German paragraphs
    german_para2 = GERMAN_PAGE2_PARA2_TEMPLATE.format(treatment=treatment)
    german_para3 = GERMAN_PAGE2_PARA3_TEMPLATE.format(treatment=treatment)
    german_para4 = GERMAN_PAGE2_PARA4_TEMPLATE.format(treatment=treatment)
    german_intro = GERMAN_PAGE2_INTRO_TEMPLATE.format(treatment=treatment)
    aftercare_numbered  = "\n".join(f"{i+1}. {item}" for i, item in enumerate(GERMAN_AFTERCARE))
    conditions_numbered = "\n".join(f"{i+1}. {c}"    for i, c    in enumerate(MEDICAL_CONDITIONS_DE))

    is_cyrillic   = lang == "Russisch"
    # Russian pixel wrapping: average ~93 chars/line (mixed case)
    # 3 lines × 93 = ~280 chars total budget (verified by pixel simulation)
    # Latin: 102 chars/line → 306 total
    max_line      = 93  if is_cyrillic else 102
    max_p1_chars  = 280 if is_cyrillic else max_line * MAX_LINES_P1
    max_p1_chars  = max_line * MAX_LINES_P1

    prompt = f"""Translate the following German texts into {lang}.

STRICT RULES:
- Translate EVERYTHING into {lang}. Zero German words in output.
- Translate the treatment name "{treatment}" into natural {lang}.
- Every field must be ONE SINGLE LINE — no line breaks inside any field.
- The "aftercare" array must have EXACTLY 13 items.
- The "conditions" array must have EXACTLY 19 items.
- Each array item is ONE line, no line breaks, no number prefix.

CRITICAL — ELIGIBILITY BOX LENGTH:
The eligibility_box is printed in a fixed box of exactly 3 lines.
{"Each line fits approximately " + str(max_line) + " characters. Total budget = " + str(max_p1_chars) + " chars." if not is_cyrillic else "Total budget = " + str(max_p1_chars) + " characters across all 3 lines."}

{"You must write EXACTLY 3 sentences. Each sentence MAX " + str(max_line) + " chars, MIN " + str(int(max_line*0.80)) + " chars. HARD LIMIT: No single sentence may exceed " + str(max_line) + " characters." if not is_cyrillic else "Write exactly 3 complete sentences. Total combined length must be " + str(int(max_p1_chars*0.85)) + "-" + str(max_p1_chars) + " characters. Do NOT write very short sentences — each must be substantive."}

Here are the 3 sentences to translate:
Sentence 1: The {treatment} treatment may only be performed when there are absolutely no contraindications or opposing medical reasons present.
Sentence 2: Truthful and complete answers to all of the following health questions are a mandatory prerequisite for this treatment to proceed.
Sentence 3: The client acknowledges this treatment is performed entirely at their own personal risk and responsibility, and the practitioner bears no liability.

Join all 3 sentences into ONE single line (no line breaks) for the eligibility_box field.

CRITICAL — PAGE 2 CONTENT LENGTH:
Page 2 must be as detailed and complete as the German original. Do NOT shorten paragraphs.
Each field must match the German length as closely as possible in {lang}:
  page2_para1  : ~250 characters — full sentence about health changes during treatment period
  page2_para2  : ~550 characters — full procedure description (5 steps: clean, measure, shape, apply, perfect)
  page2_para3  : ~250 characters — results description (visibility, duration, benefits)
  page2_para4  : ~620 characters — full follow-up paragraph (frequency, factors, first treatment, allergy disclaimer)
  consent1     : ~170 characters — client aware of allergic reaction risk
  consent2     : ~400 characters — full consent paragraph (4 sentences: agree, informed, read/understood, time)
  consent3     : ~190 characters — data protection confirmation

If your translation of any paragraph is shorter than these targets, EXPAND with the full meaning.
Write complete, professional medical/legal sentences. Do not omit any content from the German original.

OUTPUT: Return ONLY valid JSON:

{{
  "treatment_name": "translated name (title case)",
  "form_name": "the word for Name/Full Name in {lang} — e.g. 'Name' or 'Nom' or 'Имя'",
  "form_strasse": "the word for Street address in {lang}",
  "form_ort": "the word for City/Town in {lang}",
  "form_postleitzahl": "the word for Postal Code/ZIP in {lang}",
  "form_telefon": "the word for Phone/Telephone in {lang}",
  "form_geburtstag": "the word for Date of Birth in {lang}",
  "form_sachlagen_intro": "translate 'Liegt eine der folgenden Sachlagen vor:' — end with colon, NO opening punctuation like ¿ or «",
  "form_anmerkungen": "translate this sentence: 'Anmerkungen zu oben genannten Sachlagen:'",
  "form_ort_datum": "the words for Place, Date in {lang}",
  "form_unterschrift": "the word for Signature in {lang}",
  "conditions": ["condition 1", "condition 2", "... exactly 19 items ..."],
  "eligibility_box": "max {max_p1_chars} chars total, single line",
  "page2_para1": "min 230 chars — full paragraph, single line",
  "page2_para2": "min 500 chars — full paragraph, single line",
  "page2_para3": "min 230 chars — full paragraph, single line",
  "page2_para4": "min 580 chars — full paragraph, single line",
  "page2_intro": "single line",
  "aftercare": ["rule 1", "rule 2", "... exactly 13 items ..."],
  "consent1": "min 120 chars — full sentence, single line",
  "consent2": "min 370 chars — full paragraph, single line",
  "consent3": "min 170 chars — full paragraph, single line"
}}

CRITICAL — PAGE 2 PARAGRAPH LENGTH:
The paragraphs must be translated at FULL LENGTH — do not shorten them.
Each paragraph has a minimum character count listed above.
If your translation is shorter than the minimum, EXPAND it with equivalent meaning.
The German original lengths are your reference targets:
  page2_para1 = 254 chars, page2_para2 = 546 chars, page2_para3 = 256 chars
  page2_para4 = 622 chars, consent1 = 134 chars, consent2 = 404 chars, consent3 = 190 chars

GERMAN TEXTS:
TREATMENT NAME: {treatment}
FORM FIELDS: Name / Straße / Ort / Postleitzahl / Telefon / Geburtstag
SACHLAGEN INTRO: {FORM_FIELDS_DE["Sachlagen_Intro"]}
ANMERKUNGEN: {FORM_FIELDS_DE["Anmerkungen"]}
ORT DATUM: {FORM_FIELDS_DE["Ort_Datum"]}
UNTERSCHRIFT: {FORM_FIELDS_DE["Unterschrift"]}

MEDICAL CONDITIONS (19):
{conditions_numbered}

ELIGIBILITY BOX (max {max_p1_chars} chars):
{german_eligibility}

PAGE 2 PARA 1: {GERMAN_PAGE2_PARA1}
PAGE 2 PARA 2: {german_para2}
PAGE 2 PARA 3: {german_para3}
PAGE 2 PARA 4: {german_para4}
PAGE 2 INTRO:  {german_intro}

AFTERCARE (13 items):
{aftercare_numbered}

CONSENT 1: {GERMAN_PAGE2_CONSENT1}
CONSENT 2: {GERMAN_PAGE2_CONSENT2}
CONSENT 3: {GERMAN_PAGE2_CONSENT3}
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=8000,
        response_format={"type": "json_object"}
    )

    try:
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"  ⚠  JSON parse error for {lang}: {e}")
        return {}


def safe_filename(text):
    return re.sub(r'[^\w\s-]', '', text).strip().replace(' ', '_')


def clean_form_label(text):
    """Remove inverted punctuation (¿¡) and other opening marks GPT adds.
    Form labels should never start with ¿ ¡ « „ ‹ or similar."""
    return text.strip().lstrip('¿¡«„‹»›')


# Page 2 minimum char targets (based on German source lengths)
P2_MIN_CHARS = {
    "page2_para1": 230,
    "page2_para2": 500,
    "page2_para3": 230,
    "page2_para4": 580,
    "consent1":    120,
    "consent2":    370,
    "consent3":    170,
}


def validate_and_fix_page2(fields, lang, max_retries=1):
    """
    Check Page 2 paragraphs meet minimum length.
    If any are too short, ask GPT to expand them in one batch call.
    """
    short_fields = {
        k: v for k, v in fields.items()
        if k in P2_MIN_CHARS and len(v) < P2_MIN_CHARS[k]
    }

    if not short_fields or max_retries == 0:
        return fields

    # Build retry prompt listing all short fields
    field_details = "\n".join(
        f"  {k}: currently {len(v)} chars, needs min {P2_MIN_CHARS[k]} chars\n  Current text: \"{v}\""
        for k, v in short_fields.items()
    )

    retry_prompt = f"""The following {lang} translations are too short for their text boxes.
Expand each one to meet the minimum character count while keeping the full meaning.
Do NOT add meaningless filler — expand with genuine equivalent content.

{field_details}

Return ONLY valid json with the expanded versions:
{{{', '.join(f'"{k}": "expanded text"' for k in short_fields)}}}"""

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": retry_prompt}],
            temperature=0.1,
            max_tokens=3000,
            response_format={"type": "json_object"}
        )
        fixed = json.loads(resp.choices[0].message.content)
        for k, v in fixed.items():
            if k in fields:
                fields[k] = v
    except Exception as e:
        print(f"\n    ⚠  P2 retry failed: {e}")

    return fields


def validate_and_fix_eligibility(eligibility_box, lang, treatment, german_eligibility, max_line, max_p1_chars, max_retries=2):
    import re as _re

    def check(text):
        lines  = wrap_pixels(text, BOX_WIDTH_P1)
        fills  = [int(text_px(l) / BOX_WIDTH_P1 * 100) for l in lines]
        n      = len(lines)
        # Split into sentences to check individual lengths
        sents  = _re.split(r'(?<=[.!?])\s+', text.strip())
        long_s = [s for s in sents if len(s) > max_line]
        ok     = (n <= MAX_LINES_P1) and (fills[-1] >= 75 if fills else False) and not long_s
        return lines, fills, n, sents, long_s, ok

    for attempt in range(max_retries + 1):
        lines, fills, n, sents, long_s, ok = check(eligibility_box)

        if ok or attempt == max_retries:
            return eligibility_box, lines, fills

        # Build specific feedback
        line_fills = ' | '.join(f"L{i+1}:{f}%" for i, f in enumerate(fills))
        sent_info  = '\n'.join(
            f"  Sentence {i+1} ({len(s)} chars {'⚠ TOO LONG' if len(s) > max_line else '✅'}): \"{s}\""
            for i, s in enumerate(sents)
        )

        retry_prompt = f"""The eligibility_box for {lang} has problems.
Current: {n} lines, fills: {line_fills}

Sentence lengths (MAX {max_line} chars each):
{sent_info}

RULES — rewrite all 3 sentences:
- EXACTLY 3 sentences joined into ONE single line.
- Each sentence MAX {max_line} chars. MIN {int(max_line*0.80)} chars.
- If a sentence is over {max_line} chars → shorten it.
- If last line fill is under 70% → expand sentence 3.
- Do NOT exceed {max_line} chars per sentence under any circumstance.

Return ONLY valid json: {{"eligibility_box": "3 rewritten sentences, single line"}}"""

        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": retry_prompt}],
            temperature=0.1,
            max_tokens=500,
            response_format={"type": "json_object"}
        )
        try:
            fixed = json.loads(resp.choices[0].message.content)
            eligibility_box = fixed.get("eligibility_box", eligibility_box)
        except:
            break

    lines = wrap_pixels(eligibility_box, BOX_WIDTH_P1)
    fills = [int(text_px(l) / BOX_WIDTH_P1 * 100) for l in lines]
    return eligibility_box, lines, fills


if __name__ == "__main__":
    print("\n" + "="*62)
    print("  Einverständniserklärung Generator — Pixel-Accurate Wrapping")
    print("="*62)
    print(f"  Page 1 box : {BOX_WIDTH_P1:.0f}px wide, max {MAX_LINES_P1} lines")
    print(f"  Latin  'a' : 102 chars/line  |  Cyrillic 'П' : 58 chars/line")
    print(f"  Wrapping   : pixel-measured (Cormorant Garamond 34.6pt)\n")

    treatment = input("Enter treatment name in German (e.g. Airbrush Brows): ").strip()
    print(f"\nGenerating 10 languages for '{treatment}'...\n")

    rows = []
    names_by_lang = {"Deutsch": treatment}

    for lang in LANGUAGES:
        print(f"  → {lang:<14}", end="", flush=True)

        german_eligibility = GERMAN_ELIGIBILITY_BOX_TEMPLATE.format(treatment=treatment)

        if lang == "Deutsch":
            treatment_name    = treatment
            form_name         = FORM_FIELDS_DE["Name"]
            form_strasse      = FORM_FIELDS_DE["Straße"]
            form_ort          = FORM_FIELDS_DE["Ort"]
            form_postleitzahl = FORM_FIELDS_DE["Postleitzahl"]
            form_telefon      = FORM_FIELDS_DE["Telefon"]
            form_geburtstag   = FORM_FIELDS_DE["Geburtstag"]
            form_sachlagen    = FORM_FIELDS_DE["Sachlagen_Intro"]
            form_anmerkungen  = FORM_FIELDS_DE["Anmerkungen"]
            form_ort_datum    = FORM_FIELDS_DE["Ort_Datum"]
            form_unterschrift = FORM_FIELDS_DE["Unterschrift"]
            conditions        = MEDICAL_CONDITIONS_DE
            eligibility_box   = german_eligibility
            para1 = GERMAN_PAGE2_PARA1
            para2 = GERMAN_PAGE2_PARA2_TEMPLATE.format(treatment=treatment)
            para3 = GERMAN_PAGE2_PARA3_TEMPLATE.format(treatment=treatment)
            para4 = GERMAN_PAGE2_PARA4_TEMPLATE.format(treatment=treatment)
            intro             = GERMAN_PAGE2_INTRO_TEMPLATE.format(treatment=treatment)
            aftercare         = GERMAN_AFTERCARE
            consent1, consent2, consent3 = (GERMAN_PAGE2_CONSENT1,
                                             GERMAN_PAGE2_CONSENT2,
                                             GERMAN_PAGE2_CONSENT3)
            print("(source — no API call)")
        else:
            data              = translate_content(treatment, lang, german_eligibility)
            treatment_name    = data.get("treatment_name",    treatment)
            form_name         = data.get("form_name",         "Name")
            form_strasse      = data.get("form_strasse",      "Straße")
            form_ort          = data.get("form_ort",          "Ort")
            form_postleitzahl = data.get("form_postleitzahl", "Postleitzahl")
            form_telefon      = data.get("form_telefon",      "Telefon")
            form_geburtstag   = data.get("form_geburtstag",   "Geburtstag")
            form_sachlagen    = clean_form_label(data.get("form_sachlagen_intro", FORM_FIELDS_DE["Sachlagen_Intro"]))
            form_anmerkungen  = clean_form_label(data.get("form_anmerkungen",  FORM_FIELDS_DE["Anmerkungen"]))
            form_ort_datum    = data.get("form_ort_datum",    "Ort, Datum")
            form_unterschrift = data.get("form_unterschrift", "Unterschrift")
            conditions        = data.get("conditions",        MEDICAL_CONDITIONS_DE)
            eligibility_box   = data.get("eligibility_box",  german_eligibility)
            para1             = data.get("page2_para1",       GERMAN_PAGE2_PARA1)
            para2             = data.get("page2_para2",       GERMAN_PAGE2_PARA2_TEMPLATE.format(treatment=treatment))
            para3             = data.get("page2_para3",       GERMAN_PAGE2_PARA3_TEMPLATE.format(treatment=treatment))
            para4             = data.get("page2_para4",       GERMAN_PAGE2_PARA4_TEMPLATE.format(treatment=treatment))
            intro             = data.get("page2_intro",       GERMAN_PAGE2_INTRO_TEMPLATE.format(treatment=treatment))
            aftercare         = data.get("aftercare",         GERMAN_AFTERCARE)
            consent1          = data.get("consent1",          GERMAN_PAGE2_CONSENT1)
            consent2          = data.get("consent2",          GERMAN_PAGE2_CONSENT2)
            consent3          = data.get("consent3",          GERMAN_PAGE2_CONSENT3)

        if len(conditions) != 19:
            print(f"\n    ⚠  {lang}: expected 19 conditions, got {len(conditions)}")
        if len(aftercare) != 13:
            print(f"\n    ⚠  {lang}: expected 13 aftercare items, got {len(aftercare)}")

        is_cyrillic  = lang == "Russisch"
        max_line     = 93 if is_cyrillic else 102
        max_p1_chars = 280 if is_cyrillic else max_line * MAX_LINES_P1

        if lang == "Deutsch":
            p1_line_list = wrap_pixels(eligibility_box, BOX_WIDTH_P1)
            fills = [int(text_px(l) / BOX_WIDTH_P1 * 100) for l in p1_line_list]
        else:
            eligibility_box, p1_line_list, fills = validate_and_fix_eligibility(
                eligibility_box, lang, treatment, german_eligibility, max_line, max_p1_chars
            )

        p1_body = build_page1(eligibility_box, lang)
        p2_body = build_page2(para1, para2, para3, para4, intro, aftercare,
                               consent1, consent2, consent3)

        p1_lines     = len(p1_line_list)
        ok           = p1_lines <= MAX_LINES_P1
        last_fill    = fills[-1] if fills else 0
        fill_warn    = f" ⚠ last line {last_fill}%" if last_fill < 75 else f" (last line {last_fill}%)"
        overflow_str = f"⚠  OVERFLOW ({p1_lines} lines!)" if not ok else ""
        if lang == "Deutsch":
            print(f"Page1: {p1_lines}/{MAX_LINES_P1} lines{fill_warn} {'✅' if ok else overflow_str}")
        else:
            print(f"{'✅' if ok else '⚠'}  Page1: {p1_lines}/{MAX_LINES_P1} lines{fill_warn} {overflow_str}")

        names_by_lang[lang] = treatment_name

        row = {
            "Language":       lang,
            "Treatment":      treatment_name,
            "Heading":        HEADING_TRANSLATIONS.get(lang, "EINVERSTÄNDNISERKLÄRUNG"),
            "TreatmentName":  treatment_name.upper(),
            "SubHeading":     SUBHEADING_TRANSLATIONS.get(lang, ""),
            "Field_Name":          form_name,
            "Field_Strasse":       form_strasse,
            "Field_Ort":           form_ort,
            "Field_Postleitzahl":  form_postleitzahl,
            "Field_Telefon":       form_telefon,
            "Field_Geburtstag":    form_geburtstag,
            "Field_Sachlagen_Intro": form_sachlagen,
            "Field_Anmerkungen":   form_anmerkungen,
            "Field_Ort_Datum":     form_ort_datum,
            "Field_Unterschrift":  form_unterschrift,
            "Body_Page1":     p1_body,
            "Body_Page2":     p2_body,
        }
        for i, cond in enumerate(conditions, 1):
            row[f"Condition_{i:02d}"] = cond
        rows.append(row)

    df = pd.DataFrame(rows)
    timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name   = safe_filename(treatment)
    output_file = f"Einverstaendniserklaerung_{safe_name}_10Languages_{timestamp}.csv"
    df.to_csv(output_file, index=False, quoting=csv.QUOTE_ALL, encoding="utf-8-sig")

    print(f"\n✅  CSV saved: {output_file}")
    print(f"\n📋  Column structure:")
    print(f"    Headers      : Heading, TreatmentName, SubHeading")
    print(f"    Form fields  : Field_Name … Field_Unterschrift (10 columns)")
    print(f"    Conditions   : Condition_01 … Condition_19 (19 columns)")
    print(f"    Body text    : Body_Page1, Body_Page2")
    print(f"\n📝  Translated treatment names:")
    for lang, name in names_by_lang.items():
        print(f"    {lang:<14} → {name}")