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
# BOOKLET GENERATOR — 10 languages
# Every Canva text box = one CSV column
#
# Page 1:  Cover (3 boxes)
# Page 2:  TOC heading only
# Page 3:  Ch01 title + script + body = 3 boxes
# Page 4:  Ch02 title + body = 2 boxes
# Page 5:  quote + sub1 + body_L + sub2 + body_R = 5 boxes
# Page 6:  sub_B + body_B + sub_C + body_C = 4 boxes
# Page 7:  Ch03 title + body_L + body_R = 3 boxes
# Page 8:  Ch04 title + body_R + body_L = 3 boxes
# Pages 9-20:  Cond_Left + Cond_Right = 2 × 12 = 24 boxes
# Pages 21-30: hygiene + oils chapters
# Pages 31-40: product knowledge pages, each has H1+Body1+H2+Body2 = 4 boxes
#
# Column count: 89 (pages 1-30) + 40 (pages 31-40) = 129 total
# Canva limit: 150 cols — 21 cols of headroom remaining
# ============================================================

FULL_W = 96
HALF_W = 45

# Line widths for product pages 31-40
# heading: ~38 chars (Cormorant Garamond 14pt, one line)
# body:    ~46 chars per line (Inter 9pt)
PROD_H_W  = 38   # heading max chars
PROD_B_W  = 46   # body max chars

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

# Max lines per body box on product pages 31-40 (from your specs)
PROD_LINES = {
    31: (19, 19),   # Fuß-/Handbalsam, Gesichtsmaske
    32: (23, 20),   # Körpermaske, Peeling
    33: (19, 18),   # Serum, Augenpads
    34: (18, 18),   # Duftessenzen, Duftkompressen
    35: (17, 20),   # Aromaschalen, Hot-Stone-Massage Set
    36: (19, 21),   # Cold-Stone Massage Set, Bambus- oder Edelsteinstäbe
    37: (17, 18),   # Massagekugeln, Aromaroller
    38: (18, 19),   # Massagehandschuhe, Pipetten
    39: (18, 18),   # Kopfhautöl-Applikator, Massageölflaschen mit Pumpspender
    40: (19, 17),   # Mischschalen, Spatel
    41: (20, 17),   # Bedampfungsgerät, Sonstige Verbrauchsmaterialien
    42: (25, 24),   # Händedesinfektion, Flächendesinfektion
    43: (25, 22),   # Einweghandschuhe + Massageauflage
    44: (24, 26),   # Handtücher, Decke Wärmedecke & Wärmekissen
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
    data = {}

    # ── Call 1: Cover + TOC + Pages 3+5 (p04 is now separate) ──
    print(f"    1a Cover+TOC+P3+P5...", end=" ", flush=True)
    prompt1 = (
        f'Write complete professional German beauty training content for "{topic}". '
        'Return ONLY valid JSON with ACTUAL German text — no placeholders:\n'
        '{\n'
        '  "cover_subtitle": "Theorie & Praxis Schulung",\n'
        '  "toc_entries": ['
        '{"title":"Was ist eine ' + topic + '?","num":"01"},'
        '{"title":"Anatomie der Haut","num":"02"},'
        '{"title":"Funktion und Aufgaben der Haut","num":"06"},'
        '{"title":"Krankheiten und Beschwerden","num":"07"},'
        '{"title":"Vorbeugende Maßnahmen im Studio","num":"27"},'
        '{"title":"Produktwissen","num":"30"},'
        '{"title":"Vor der Behandlung","num":"40"},'
        '{"title":"Hautanalyse","num":"41"},'
        '{"title":"Körperanalyse","num":"42"},'
        '{"title":"Anwendungsbereiche","num":"43"},'
        '{"title":"Technik","num":"44"},'
        '{"title":"Nach der Behandlung","num":"48"},'
        '{"title":"Ergebnismessung","num":"50"},'
        '{"title":"Probleme & Lösungen","num":"51"},'
        '{"title":"Häufige Fragen und Antworten","num":"53"},'
        '{"title":"Kundenberatung","num":"54"},'
        '{"title":"Marketing und Verkauf","num":"55"},'
        '{"title":"Preisgestaltung","num":"56"},'
        '{"title":"Reflexionsseite","num":"57"},'
        '{"title":"Wissenstest","num":"58"}],\n'
        '  "p03_script": "body care",\n'
        f'  "p01_body": "WRITE 4 full detailed German paragraphs about {topic} — each paragraph must be 500+ chars, total minimum 2000 chars. Do NOT shorten.",\n'
        '  "p05_quote": "In der Pflege finden Haut und Seele ihre Harmonie",\n'
        '  "p05_sub1": "In der untersten Schicht der Basalschicht entwickeln",\n'
        '  "p05_body_L": "WRITE EXACTLY 954 chars: Keratinozyten entstehen wandern reifen, Keratinisierung Verhornung Eigenschaften, epidermale Lipide Schutzbarriere Feuchtigkeit binden, trockene Haut Lipidmangel spannt rau, Hydrolipidfilm Schweiß+Talgdrüsen Haut geschmeidig, Barriere Bakterien+Pilze",\n'
        '  "p05_sub2": "Der wässrige Teil dieses Films,",\n'
        '  "p05_body_R": "WRITE EXACTLY 935 chars: Säureschutzmantel Milchsäure+Aminosäuren+Fettsäuren+Pyrrolidincarbonsäure+NMFs Keratinisierungsnebenprodukte, pH-Wert 5.4-5.9 hautfreundlicher Mikroorganismus schädliche Keime abtöten, Enzyme Abschuppung steuern Hornschicht reparieren, Epidermis Dicke 0.1mm Augen 0.05mm Fußsohlen 1-5mm"\n'
        '}\n'
        'Write ALL values as actual German text of the specified length.'
    )
    try:
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt1}],
            temperature=0.3, max_tokens=8000,
            response_format={"type": "json_object"}
        )
        data.update(json.loads(r.choices[0].message.content))
        print(f"✅")
    except Exception as e:
        print(f"❌ {e}")

    # ── Call 1b-NEW: Page 4 Epidermis — dedicated call ──────────
    print(f"    1b-new P4 Epidermis...", end=" ", flush=True)
    prompt_p04 = (
        f'Write a detailed professional German anatomy text for a beauty training booklet about "{topic}". '
        'CRITICAL: p04_body MUST be 2592 characters of actual German text — count carefully. '
        'Return ONLY valid JSON:\n'
        '{\n'
        '  "p04_ch_title": "02 Anatomie der Haut",\n'
        '  "p04_body": "WRITE EXACTLY 2592 chars: Begin with overview of skin as largest organ with 3 main layers. Then write A) Epidermis section with ALL 5 sub-layers, each described in 250+ chars: 1.Basalschicht — continuous cell division, keratinocytes produced, melanocytes, stem cells, attachment to dermis via hemidesmosomes. 2.Stachelzellschicht — spinous layer, desmosomes connect cells, Langerhans immune cells, keratin filaments begin forming, mechanical strength. 3.Körnerzellenschicht — keratohyalin granules, lamellar granules release lipids, cornification begins, cells lose organelles, barrier lipid formation. 4.Glanzschicht — only in thick skin on palms and soles, eleidin protein, translucent, no organelles, transition zone. 5.Hornschicht — stratum corneum, dead corneocytes filled with keratin, brick-and-mortar structure, barrier function, prevents water loss, protection from pathogens and UV. Keep writing until you reach 2592 chars."\n'
        '}\n'
        'Write ACTUAL continuous professional German prose — not keyword lists. Reach exactly 2592 chars.'
    )
    try:
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt_p04}],
            temperature=0.3, max_tokens=5000,
            response_format={"type": "json_object"}
        )
        data.update(json.loads(r.choices[0].message.content))
        print(f"✅ ({len(data.get('p04_body',''))} chars)")
    except Exception as e:
        print(f"❌ {e}")

    # ── Call 1b: Page 6 Dermis + Subkutis ──
    print(f"    1b/4 P6 Dermis+Subkutis...", end=" ", flush=True)
    prompt1b = (
        f'Write detailed German anatomy content for a beauty training booklet about "{topic}". '
        'Return ONLY valid JSON with ACTUAL German text:\n'
        '{\n'
        '  "p06_sub_B": "B) Dermis (auch Korium genannt)",\n'
        '  "p06_body_B": "WRITE EXACTLY 2496 chars: Dermis flexible feste Mittelschicht, zwei Schichten Stratum reticulare+Stratum papillare, Kollagen+Elastin Bindegewebsfasern jung+kräftig+elastisch, Hyaluronsäure gelartiger Feuchtigkeitsbinder Volumen, Außeneinwirkungen Lebensweise+Sonne+Temperatur+Ernährung+Medikamente auf Kollagen+Elastin, Alterung Produktion langsamer Falten+weniger glatt, Schutz Körper vor äußeren Einflüssen, Fibroblasten+Mastzellen Defekte heilen, Blutgefäße Epidermis Nährstoffe Abfall, Talgdrüsen Talg+Lipide, Schweißdrüsen Wasser+Milchsäure, Lymphgefäße+sensorische Rezeptoren+Haarwurzeln",\n'
        '  "p06_sub_C": "C) Subkutis (auch Hypodermis genannt)",\n'
        '  "p06_body_C": "WRITE EXACTLY 3360 chars: tiefste Hautschicht lockeres Bindegewebe+Fettzellen+Blutgefäße, Isolierung+Polsterung Hauptaufgabe, Fettgewebe Wärme speichern Kälte schützen Stoßdämpfer Organe, Flüssigkeitshaushalt regulieren, Triglyceride Energiespeicher Brennstoff, Blutgefäße Sauerstoff+Nährstoffe umliegende Gewebe, Körpertemperaturregulierung Erweiterung+Verengung Blutfluss+Wärmeabgabe, ästhetische Formgebung Körperkonturen Fettverteilung, Subkutis wichtige Komponente Isolierung+Polsterung+Energiespeicherung+Flüssigkeitshaushalt, Fettzellen Anzahl je Körperteil variiert, Verteilung Männer vs Frauen verschieden Struktur Hautpartie, individuelle Anatomie ästhetische Wahrnehmung Hautgesundheit Verständnis, Zusammenspiel alle drei Hautschichten für optimale Hautfunktion und Schutz des gesamten Körpers"\n'
        '}\n'
        'Write ALL values as actual German text of the specified length.'
    )
    try:
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt1b}],
            temperature=0.3, max_tokens=5000,
            response_format={"type": "json_object"}
        )
        data.update(json.loads(r.choices[0].message.content))
        print(f"✅")
    except Exception as e:
        print(f"❌ {e}")

    # ── Call 2: Pages 7-8 ──
    print(f"    2/4 P7-8...", end=" ", flush=True)
    prompt2 = (
        f'Write professional German training content for "{topic}" booklet. '
        'Return ONLY valid JSON with ACTUAL German text:\n'
        '{\n'
        '  "p07_ch_title": "03 Funktionen und Aufgaben der Haut",\n'
        '  "p07_body_L": "WRITE EXACTLY 2115 chars: Einleitung Haut größtes Organ Vielzahl Funktionen. Dann 6 nummerierte Funktionen je 300 chars: 1.Schutz: Barriere Mikroorganismen+UV+Chemikalien+Verletzungen, Epidermis Hornzellen Stratum corneum schützende Schicht. 2.Temperaturregulierung: Schwitzen überschüssige Wärme abgeben Körpertemperatur senken, Kälte Blutgefäße zusammenziehen Wärmeabgabe reduzieren. 3.Sinneswahrnehmung: Nervenenden Berührung+Temperatur+Schmerz+Druck, taktile Reize Verletzungsschutz Schmerzempfindungen. 4.Ausscheidung: Schweißproduktion Wasser+Salze+Stoffwechselprodukte ausscheiden. 5.Aufnahme: begrenzte Stoffe aufnehmen transdermal Medikamente. 6.Vitamin-D-Synthese: UV-B-Strahlung Vorstadium Vitamin D gebildet",\n'
        '  "p07_body_R": "WRITE EXACTLY 1980 chars: Fortsetzung Vitamin D Leber+Nieren aktives Vitamin D umgewandelt. Dann 5 Funktionen je 300 chars: 7.Immunabwehr: Immunzellen Infektionen bekämpfen Krankheitserreger abwehren Teil des Immunsystems. 8.Absorption: Substanzen aufnehmen Medikamente+Chemikalien+Toxine begrenzt durch Haut. 9.Wasserdichtigkeit: wasserabweisend Wasser eindringen verhindern, übermäßiges Verdunsten begrenzen Feuchtigkeitsverlust. 10.Haar+Nagelwachstum: Haarfollikel Haare produzieren, Matrix Nagelwurzeln Nägel wachsen. 11.Nährstoffspeicherung: Fettgewebe Subkutis Nährstoffe speichern bei Bedarf freisetzen verwenden. Abschlusssatz Bedeutung Hautgesundheit schützen pflegen Veränderungen beachten.",\n'
        '  "p08_ch_title": "04 Häufigste Krankheiten & Beschwerden",\n'
        '  "p08_body_R": "WRITE EXACTLY 1980 chars: Symptome Abschnitt 200 chars: Pickel+kleine Eiterbläschen, Mitesser Komedonen, Papeln gerötete Hauterhöhungen, Pusteln eitergefüllte Bläschen, fettige Haut. Entwicklung 500 chars: übermäßige Talgproduktion+gesteigerte Verhornung abgestorbene Hautzellen Talgdrüsenfollikel Hornpropf Follikelausgang, Talg nicht abfließen staut sich weitet Talgdrüsenfollikel aus Mitesser Folge. Mitesser zurückbilden entzündliche Veränderungen Bakterien Stoffwechselaktivität Talgfollikel Keime Fettsubstanzen Papeln+Pusteln. Ablauf 300 chars: meistens selbst abklingen, 2-7% Narben, Frauen bis 25.Lebensjahr. Ursachen 400 chars: Erbliche Faktoren+Medikamente, Menstruationszyklus+Schwangerschaft, Klima+Luftfeuchtigkeit+UV, Psyche+Stress, Sexualhormone+Hautfette+Neuropeptide, Zucker+Kohlenhydrate+Milch, Nikotin.",\n'
        '  "p08_body_L": "WRITE EXACTLY 660 chars: Akne als Überschrift. Acne vulgaris weltweit häufigste Hauterkrankung nicht ansteckend, Pubertät meistens, 70-95% Jugendliche 15-18 Jahre aknebedingte Hautveränderung, eher junge Männer, Talgbildung+Verhornungsstörung Talgdrüsenfollikel, Nacken+Gesicht+Dekolleté+Brust+Rücken betroffen, selten Achseln+Genital+Gesäß+Leiste, 15-30% Patienten medizinische Therapie nötig."\n'
        '}\n'
        'Write ALL values as actual German text.'
    )
    try:
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt2}],
            temperature=0.3, max_tokens=8000,
            response_format={"type": "json_object"}
        )
        data.update(json.loads(r.choices[0].message.content))
        print(f"✅")
    except Exception as e:
        print(f"❌ {e}")

    # ── Calls 3-14: 12 conditions ──
    COND_SPECS = [
        (1,"Neurodermitis",       2430,1080),
        (2,"Schuppenflechte",     1125,2295),
        (3,"Herpes",              2430,1170),
        (4,"Wundrose",             900,2475),
        (5,"Nesselsucht",         2340, 810),
        (6,"Gürtelrose",          1125,2385),
        (7,"Pilzinfektionen",     2340,1125),
        (8,"Sexuell übertragbare Krankheiten", 855,2385),
        (9,"Haarausfall",         2520,1170),
        (10,"Warzen",             1125,2475),
        (11,"Rosazea",            2340,1170),
        (12,"Hautkrebs",           945,2205),
    ]
    COND_CONTENT = {
        1:  ("chronische Erkrankung, Babys+Kinder, atopische Dermatitis, Körperstellen Wangen+Arme+Beine+Kniekehlen, Juckreiz Schlaf+Konzentration, Symptome Bläschen+trockene Haut+Schuppen+Schübe, Ursachen FLG-Gen+Immunsystem+Allergene Hausstaubmilben+Pollen+Nahrungsmittel",
             "Textilien Wolle+Zigarettenrauch+Hitze+Kälte, familiäre Veranlagung, Umweltverschmutzung, Häufigkeit 10-20% Kinder 2-5% Erwachsene, Beginn 3-6 Lebensmonat, Folgen Infektionen+Antibiotika+Herpes+Asthma+Heuschnupfen"),
        2:  ("chronische Erkrankung, Gelenke+Nägel betroffen, Schübe, nicht heilbar, Psoriasis vulgaris 80% silbrig glänzende Plaques klar abgegrenzt, Körperstellen Kopf+Ellbogen+Knie+Rücken",
             "symmetrisches Auftreten, Psoriasis inversa Hautfalten+Leisten+Achseln, Nagelpsoriasis Tüpfelnagel+Ölnagel, Psoriasis pustulosa Eiterbläschen, Psoriasis guttata Kinder+Streptokokken, Ursachen Keratinozyten 10x schneller"),
        3:  ("HSV1 Lippenherpes+Augen+Ohren, HSV2 Genitalherpes, beide Viren gleiche Symptome, lebenslang in Nervenknoten, Reaktivierung Stress+UV+Hormone, 80% Kleinkindalter HSV1, Rezidiv nach Erstansteckung, Windpocken+Gürtelrose durch Herpesviren",
             "Übertragung Küssen+Sex+persönliche Gegenstände, Schwangere Vorsicht Neugeborene, antivirale Medikamente, Kondome kein vollständiger Schutz, psychologische Belastung Scham+Stigma, Impfstoffforschung aktuell"),
        4:  ("Erysipel+Phlegmone durch Hautverletzung, Bakterien eindringen, Haut anschwellen+rot+schmerzen, obere Hautschichten, Erysipel vs Phlegmone Tiefe, Symptome Rötungen zungenförmig+Blasen+Lymphknotenschwellung+Fieber",
             "mehr Symptome Daumen+Handgelenk, Ursachen Streptokokken+Staphylokokken, Risikofaktoren Diabetes+Übergewicht+Lymphabfluss+Venenschwäche, Häufigkeit 2-250 von 10.000, Folgen Abszess+Lymphödem+Blutvergiftung+Hirnhautentzündung"),
        5:  ("Urtikaria Quaddeln+Rötungen wie Brennnessel, 20-25% Menschen, akut vs chronisch 6 Wochen, Symptome Hautrötungen+Quaddeln+Juckreiz+Angioödem, Akute Urtikaria durch Infekte, Chronische Urtikaria mittleres Alter Frauen doppelt, spontan vs induzierbar, Ursachen akut: Viren+Bakterien+Pollen+Wärme+Kälte+Arzneimittel",
             "Ursachen chronisch: Autoimmunreaktion+Magenschleimhautentzündung+Aromastoffe, Folgen Depression+Angioödem Rachenraum+Atemnot+notärztliche Behandlung, frühzeitige Intervention unerlässlich"),
        6:  ("Windpocken Zusammenhang Varizella-Zoster, streifenförmiger Hautausschlag Rumpf+Brustkorb, nur eine Körperhälfte, 2-4 Wochen Dauer, Impfung ab 60 Jahre 2018, ansteckend nur ohne Windpocken, Symptome Abgeschlagenheit+Fieber+Kribbeln+Schmerz+Knötchen",
             "Bläschen+gelbliche Krusten+einseitig, Ursachen Varizella in Nervenwurzeln lebenslang, Reaktivierung Erkrankung+Stress+Alter, Häufigkeit 300.000/Jahr, Folgen Narben+Pigmentstörungen+Hornhautentzündung+Hörminderung+Lähmungen, Schwangerschaft ungefährlich"),
        7:  ("Faden- und Hefepilze, Fußpilz Tinea pedis zwischen Zehen schuppig+rot+Risse, Nagelpilz gelb+verdickt+ablösend, Leistenflechte junge Männer Sport, Ringelflechte roter Ring, Scherpilzflechte Kinder Kopfhaut Haustiere, Candida Kleinkindern Windelbereich+Frauen Brust+Achseln+Leiste",
             "Candida oral Säuglinge+Zahnersatz, Mundwinkel Risse, vaginale Pilzinfektionen, Rötung+Schuppung+infizierte Inseln, Nagelfalzentzündung, Malassezia fettige Haut Kleiepilz Wirbelsäule+Brustkorb blasse Flecken Winter stärker+Sommer verblassen"),
        8:  ("Gonorrhoe/Tripper sexuell übertragbar meldepflichtig, Erreger empfindlich kein Toilette, Verlauf ohne schwere Symptome, brennen+jucken Wasserlassen, weißlicher Ausfluss Frauen, Blutbahn Hautausschläge+Fieber, Unfruchtbarkeit",
             "Syphilis Bakterien Hautausschlag Bauch+Brust+Rücken hell-dunkelrote Flecken+Knötchen, Nervensystem Angriff, Chlamydien 300.000/Jahr häufigste STD symptomfrei+Unfruchtbarkeit, Feigwarzen HPV Kondylome Genital+Anal, emotionale Auswirkungen Angst+Unbehagen"),
        9:  ("100 Haare/Tag normal, verkürzter Haarlebenszyklus Atrophie Follikel, lokal vs diffus, hormonelle Alopezie DHT-Hormon Männer Glatze, Psoriasis+Alopecia areata, Schilddrüse+Eisenmangel, Symptome kahle Stellen, 3 Formen: 1.Genetisch Geheimratsecken+Glatze Männer Scheitel Frauen, 2.Kreisrund ovale Stellen, 3.Diffus gleichmäßig, Begleitsymptome Jucken+Schuppen+Brennen+Angst+Scham, Häufigkeit Frauen=Männer",
             "ältere Männer akzeptiert jüngere Frauen Schönheitsfehler ernstes Problem, Ursachen: 1.Genetisch DHT Haarfollikel Empfindlichkeit beide Geschlechter Männer häufiger, 2.Kreisrund Immunsystem gegen Haarwachstum, 3.Diffus Frauen häufiger hormonell Schwangerschaft+Schilddrüse+Medikamente+Stress+Eisenmangel+Zink"),
        10: ("Hautwucherungen gutartig, Viren ansteckend weit verbreitet, alle Altersgruppen Kinder häufiger, harmlos verschwinden selbst Wochen+Monate, Behandlungen möglich, Alterswarzen nicht ansteckend, Symptome: Juckreiz+Druck+Schmerz Fußsohlen, Dornwarzen Fußsohlen+Fersen nach innen, Gewöhnliche Warzen Stecknadelkopf bis Erbse Handrücken+Finger, Flachwarzen Gesicht+Stirn+Wangen",
             "Mosaikwarzen weiß Stecknadelkopf Fußballen flacher, Pinselwarzen fadenförmig dornig Gesicht, Feigwarzen HPV Genital sexuell anders behandelt, Hautkrebs Verwechslung sehr selten, Hühneraugen Unterschied Druckkern, Behandlung Salizylsäure+flüssiger Stickstoff+Laser"),
        11: ("rote Flecken+kleine Adern+Pusteln Gesicht, Schübe psychisch belastend Selbstbewusstsein, nicht bekannt als Erkrankung, Symptome: Wangen+Kinn+Stirn+Nase chronisch nicht ansteckend, 4 Typen: Typ1 Rötung+Äderchen, Typ2 Knötchen+Pusteln, Typ3 verdickte Haut Nase, Typ4 Augenentzündungen, trockene Haut+Mischformen, kein Akne keine Talgproduktion, Ursachen: Entzündungsreaktionen+Blutgefäße+Genetik+Schutzfunktion gestört+Milben+Sonnenlicht",
             "starke Hitze+Kälte+Stress+Kortison als Ursachen, Häufigkeit 2-5% Erwachsene ab 30 helle Haut Frauen häufiger, Verlauf Schübe+Phasen abwechselnd, Beschwerden lange gleich, Folgen Rhinophym Knollennase Männer psychisch belastend"),
        12: ("UV-Strahlen schädigen DNS und Hautzellen entarten beginnen unkontrolliert zu wuchern. Das bedeutet jede Zelle kann bösartig werden. Verschiedene Arten: 1. Schwarzer Hautkrebs (Melanom) entsteht wenn sich Pigmentzellen (Melanozyten) in der Haut zurückbilden. 2. Heller Hautkrebs zwei Unterkategorien: Basalzellkarzinom (Basaliom) zeigt sich mit kleinen Äderchen auf glänzender Hautoberfläche. Stachelzellkarzinom (Spinaliom) durch raue warzenartige Oberfläche und Schuppen gekennzeichnet. Häufigkeit: Hautkrebs ist eine der häufigsten Tumorarten",
             "Schätzungen zufolge erkranken jährlich mehr als 250.000 Menschen in Deutschland an hellem Hautkrebs und etwa 23.000 an schwarzem Hautkrebs. Jeder sollte sich vor schädlichen UV-Strahlen schützen. Risikogruppen: heller Hauttyp, viele Muttermale, UV-empfindlich erfordern besondere Aufmerksamkeit beim Sonnenschutz. Körperstellen: Bei hellem Hautkrebs besonders sonnenexponierte Stellen wie Nase, Stirn und Ohren betroffen. Das Melanom tritt bei Männern am häufigsten am Rücken auf, bei Frauen an den Beinen. Entstehungsdauer: Hautkrebs kann innerhalb kurzer Zeit entstehen. Personen jeden Alters können betroffen sein. Ursachen: UV-Strahlung natürlich und künstlich, Erbanlagen, insbesondere Sonnenbrände, heller Hauttyp, angeborene oder erworbene Pigmentmale, vorhergehende Erkrankung von schwarzem Hautkrebs. Diagnose: Schwarzer Hautkrebs tritt nur in einem bestimmten Prozentsatz der Fälle aus bestehenden Muttermalen auf, die in Farbe und Größe variieren. Die meisten entstehen jedoch von Grund auf neu auf zuvor unveränderter Haut."),
    }

    for idx, (i, name, tL, tR) in enumerate(COND_SPECS):
        print(f"    cond{i:02d}/{len(COND_SPECS)} {name}...", end=" ", flush=True)
        cL, cR = COND_CONTENT[i]
        prompt_c = (
            f'Write detailed German medical content about "{name}" for a beauty training booklet.\n'
            f'The text is split across TWO columns — left ends mid-sentence, right continues.\n'
            f'Return ONLY valid JSON with EXACTLY these keys and lengths:\n'
            '{{\n'
            f'  "cond{i}_name": "{name}",\n'
            f'  "cond{i}_L": "WRITE EXACTLY {tL} chars about {name}: {cL}. Text must END ABRUPTLY MID-SENTENCE as it continues in right column.",\n'
            f'  "cond{i}_R": "WRITE EXACTLY {tR} chars continuing mid-sentence from left column: {cR}. Complete all topics fully."\n'
            '}}\n'
            f'CRITICAL: cond{i}_L must be {tL} chars. cond{i}_R must be {tR} chars. Write full professional German medical text. No placeholders.'
        )
        try:
            r = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt_c}],
                temperature=0.3, max_tokens=5000,
                response_format={"type": "json_object"}
            )
            cdata = json.loads(r.choices[0].message.content)
            data.update(cdata)
            aL = len(data.get(f"cond{i}_L", ""))
            aR = len(data.get(f"cond{i}_R", ""))
            fL = "✅" if aL >= tL*0.7 else f"⚠{aL}"
            fR = "✅" if aR >= tR*0.7 else f"⚠{aR}"
            print(f"L:{fL} R:{fR}")
        except Exception as e:
            print(f"❌ {e}")

    # ── Pages 21-23: Hygiene ──
    print(f"    p21-23 hygiene...", end=" ", flush=True)
    prompt_hygiene = (
        f'Write German beauty studio hygiene content for "{topic}". ACTUAL German text only.\n'
        'Return ONLY valid JSON:\n'
        '{\n'
        f'  "p21_body_top": "WRITE EXACTLY 1824 chars: Aromatherapie Gesundheitsrisiken trotz Wellness, ätherische Öle konzentriert physiologisch+psychologisch, Sicherheitsaspekte+Kontraindikationen. Hygiene Landesregierung Hygienevorschriften. Gesetzlich AIDS+Virushepatitis B+C verhindern. Drei Hygienebereiche: Hygiene+Produktgüte Hersteller, Hygienestandards Studio, Hygienemaßnahmen Kunde.",\n'
        f'  "p21_body_right": "WRITE EXACTLY 1166 chars: GMP Good Manufacturing Procedure, Qualitätsprüfung Geräte+Zubehör+Hautpflegecremes. Einweg-Materialien einmal, mehrfach verwendbare gereinigt+desinfiziert+sterilisiert. Lagerung Anästhetika+Seren+Cremes Alkohol Konservierung 1-2 Jahre. Nicht eingehalten: Irritationen+Verheilungsrisiken. Cremes Milchbakterien-Anreicherung hygienische Risiken.",\n'
        f'  "p22_body": "WRITE EXACTLY 1802 chars: Kosmetikerinnen gesetzlich verpflichtet Aufklärung+Hygienevorschriften berufliche Anforderungen. Bullet-Liste: Fußböden laminiert+gefliest Bodendesinfektionsmittel, Arbeitsbereiche leicht reinigbar, Liege gereinigt, Behandlungstücher 90° gewaschen, Hände desinfizieren+Einweghandschuhe+Gesichtsmasken, Materialien vordesinfiziert, Steril verpackte Werkzeuge nur bei Kunde öffnen, Handstück Folie, Öle Mischtöpfchen, Behandlungsbereich Antiseptikum, Wischpads Laborwasser erneuern+Entsorgungsbehälter, Einwegmaterialien entsorgen, Arbeitsbereich reinigen+desinfizieren Hersteller-Hinweise, Sterilisation Heißluft+Dampfsterilisator.",\n'
        f'  "p23_body": "WRITE EXACTLY 2597 chars: Kosmetikerinnen Pflicht aufklären Risiken+Reaktionen+Sicherheitsmaßnahmen mündlich+schriftlich Einverständniserklärung. Pflegehinweis nach Behandlung. Maßnahmen: Hochwertige Cremes Spatel+Pumpspender, eigene Kosmetika+Parfüms verzichten, Hitze+Sonneneinstrahlung+Sauna+Schwitzen vermeiden, Alkohol+scharfes Essen+Rauchen meiden, Körperstellen nicht berühren, Wärmegefühl+Kribbeln+Rötungen beruhigende Pflegeprodukte ohne Kratzen, Hautregeneration Aromatherapie 7-10 Tage, allergische Symptome Rücksprache+ärztliche Abklärung. Hygieneverordnung verbindlich, vorausschauend denken, regelmäßige Fortbildung ätherische Öle."\n'
        '}\nWrite ALL values as actual German text.'
    )
    try:
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt_hygiene}],
            temperature=0.3, max_tokens=6000,
            response_format={"type": "json_object"}
        )
        data.update(json.loads(r.choices[0].message.content))
        print(f"✅")
    except Exception as e:
        print(f"❌ {e}")

    # ── Pages 24-30: Oils ──
    print(f"    p24-30 oils...", end=" ", flush=True)
    prompt_oils = (
        f'Write German descriptions of carrier and essential oils for "{topic}" beauty training booklet.\n'
        'Each oil gets its own key. Write ACTUAL German text of specified length. ONLY valid JSON:\n'
        '{\n'
        '  "p24_h1": "Jojobaöl",\n'
        '  "p24_body_L": "WRITE 644 chars: Jojobaöl außergewöhnliches Trägeröl chemisch flüssiges Wachs, Jojobapflanze Samen, hohe Stabilität+Haltbarkeit, Hautelastizität+Feuchtigkeit ohne Poren verstopfen, Aromamassagen Gesicht+Kopf+empfindliche Haut geeignet.",\n'
        '  "p24_body_R": "WRITE 552 chars: Vitamin E+antioxidative Wirkstoffe freie Radikale+Zellregeneration, schnell einziehend kein Fettfilm, Aroma-Handmassagen+Wellnesssequenzen+warme Kompressentechniken, leicht+tief pflegend ätherische Öle hautschonend.",\n'
        '  "p25_h1": "Mandelöl",\n'
        '  "p25_body_top": "WRITE 1242 chars: beliebtestes Trägeröl mild+hautfreundlich Wellness+Kosmetik, Süßmandel Kerne weiche Textur Massage+Pflegebasis, Vitamin E+Fettsäuren+Mineralstoffe Hautbarriere+Regeneration, Transporteur ätherische Öle gleichmäßig verteilt langanhaltend angenehm, alle Hauttypen sensibel+trocken+gereizt Geschmeidigkeit+Feuchtigkeitsschutz ohne fettend, Wellnessmassagen Ganzkörper+Rücken+Reflexzone sanfter Gleiteffekt.",\n'
        '  "p25_h2": "Aprikosenkernöl",\n'
        '  "p25_body_bot": "WRITE 1150 chars: sanftestes Trägeröl Aprikosenkerne, Linolsäure+Ölsäure+Vitamin A Premiumöl sensibel+trocken+reaktiv, leichtes reizarmes Basisöl Gesichtsanwendungen+Kopf+Dekolleté feinfaserige Hautstruktur, gleichmäßig tief einziehend Feuchtigkeit+beruhigend+Trockenheit+Hautbarriere, ätherische Öle sanft transportiert harmonische Duftentfaltung, Aroma-Gesichtsrituale+Handverwöhnmassagen+Maskeneinwirkzeiten.",\n'
        '  "p26_h1": "Traubenkernöl",\n'
        '  "p26_body_top": "WRITE 1196 chars: leichte Textur schnelle Einziehfähigkeit beliebtestes Trägeröl Wellnessmassagen, Weintraube Samen Linolsäure+OPC Radikalfänger, Ganzkörper+Fuß+lymphstimulierend Aromamassagen, kontrollierten Gleitfilm ohne beschweren gleichmäßiges Arbeiten, ölige+empfindliche+Mischhaut kein Fettfilm natürliche Balance, frische Massageempfindung, ätherische Öle frisches klares Duftprofil vitalisierend Körper+Wellnessrituale.",\n'
        '  "p26_h2": "Kokosöl",\n'
        '  "p26_body_bot": "WRITE 1150 chars: fraktioniertes Kokosöl rein+temperaturstabil+leicht feste Fettbestandteile entfernt, farblos+geruchsneutral+flüssig Raumtemperatur aromatherapeutisch ideal, seidig+nicht fettend weichen Charakter Massagen, Hot-Stone+Bambusmassagen+Wärme oxidiert kaum hitzestabil, pflegend+feuchtigkeitsbewahrend+schützend kein Glänzen kein Rückstand, nicht komedogen Gesicht+Kopfhautrituale, ätherische Öle klar+gleichmäßig intensiv+harmonisch.",\n'
        '  "p27_h1": "Lavendelöl",\n'
        '  "p27_body_top": "WRITE 1058 chars: beliebtestes ätherisches Öl beruhigend+hautfreundlich, Blüten Lavendelpflanze sanft blumig-frisch Entspannung+Wohlbefinden, natürliche Hautregeneration+ausgleichend irritierte Haut+Spannungen reduzieren, Massagen+Aromabad+Hautpflege Trägeröle gut kombinierbar, alle Hauttypen sensibel+gereizt Geschmeidigkeit beruhigt gerötete Stellen, entspanntes wohltuendes Massageerlebnis.",\n'
        '  "p27_h2": "Orangenöl",\n'
        '  "p27_body_bot": "WRITE 828 chars: erfrischendes ätherisches Öl stimmungsaufhellend+belebend, Schalen süßer Orangen fruchtig-süß Sinne aktiviert positive Energie, Durchblutung+trockenere Stellen+Regeneration Trägeröle optimal verteilt, alle Hauttypen frisches geschmeidiges Hautgefühl Wellness+Kosmetikmassagen Vitalität belebendes Erlebnis Körper+Sinne.",\n'
        '  "p28_h1": "Bergamotteöl",\n'
        '  "p28_body_top": "WRITE 782 chars: sanft ausgleichendes ätherisches Öl entspannend Körper+Geist, Schalen Bergamottefrucht frisch zitrusartig Stress mindern innere Ruhe, Hautregeneration+beruhigend empfindliche Haut Trägeröle gleichmäßig angenehm, nahezu alle Hauttypen harmonisches frisches Hautgefühl Wohlbefinden+Entspannung.",\n'
        '  "p28_h2": "Rosmarinöl",\n'
        '  "p28_body_bot": "WRITE 828 chars: belebendes ätherisches Öl anregend Körper+Geist, Blätter+Blüten Rosmarinstrauch frisch krautig Energie+Konzentration, Durchblutung+Hautregeneration+Verspannungen lösen Trägeröle optimal wirksam, nahezu alle Hauttypen müde+beanspruchte Haut vitalisierendes Hautgefühl anregende wohltuende Erfahrung.",\n'
        '  "p29_h1": "Ylang-Ylangöl",\n'
        '  "p29_body_top": "WRITE 920 chars: harmonisierendes ätherisches Öl entspannend+pflegend Haut+Sinne, Blüten Ylang-Ylang-Baum intensiv blumig-süß Stress mindern innere Ausgeglichenheit, Geschmeidigkeit+trockene Stellen+Regeneration Trägeröle gleichmäßig langanhaltend duftend, alle Hauttypen zartes pflegendes Hautgefühl entspannte harmonische Atmosphäre.",\n'
        '  "p29_h2": "Sandelholzöl",\n'
        '  "p29_body_bot": "WRITE 828 chars: beruhigendes ätherisches Öl ausgleichend Körper+Geist, Holz Sandelholzbaum warm holzig Entspannung innere Ruhe, trockene Stellen+Hautregeneration+Geschmeidigkeit Trägeröle optimal langanhaltend, alle Hauttypen auch sensibel Wohlbefinden entspannend harmonisches sinnliches Erlebnis.",\n'
        '  "p30_h1": "Kamillenöl",\n'
        '  "p30_body_top": "WRITE 782 chars: sanftes beruhigendes ätherisches Öl hautfreundlich+entzündungshemmend, Blüten Kamille mild süßlich-blumig Entspannung+Wohlbefinden, beruhigend+Regeneration empfindlicher gereizter Haut Rötungen mindern Trägeröle gleichmäßig, alle Hauttypen sensibel Entspannung Geschmeidigkeit wohltuendes Pflegeerlebnis.",\n'
        '  "p30_h2": "Pfefferminzöl",\n'
        '  "p30_body_bot": "WRITE 828 chars: erfrischendes ätherisches Öl kühlend+belebend Körper+Sinne, Blätter Pfefferminze klar frisch Energie Sinne anregt, kühlend+Durchblutung stimuliert+Regeneration beanspruchter Hautpartien Trägeröle optimal vitalisierend, alle Hauttypen frisches vitalisierendes Hautgefühl belebendes Massageerlebnis Wohlbefinden."\n'
        '}\nWrite ALL values as actual German text of the specified length.'
    )
    try:
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt_oils}],
            temperature=0.3, max_tokens=12000,
            response_format={"type": "json_object"}
        )
        data.update(json.loads(r.choices[0].message.content))
        print(f"✅")
    except Exception as e:
        print(f"❌ {e}")

    # ── Chapters A ──
    print(f"    chapters-A...", end=" ", flush=True)
    prompt_chA = (
        f'Write detailed German professional beauty training content for "{topic}". ACTUAL German text only.\n'
        'Return ONLY valid JSON:\n'
        '{\n'
        f'  "p_vorbeugende": "WRITE EXACTLY 3360 chars of ACTUAL German prose — do not stop early: Vorbeugende Maßnahmen für {topic} im Studio. Abschnitte: 1.Hygiene+Desinfektion Geräte+Hände+Liegen je 400 chars, 2.Kontraindikationen Liste mit Erklärung je 400 chars, 3.Kundendokumentation+Anamnese 300 chars, 4.Allergietest Vorgehen 300 chars, 5.Raumvorbereitung+Materialhygiene 300 chars, 6.Sicherheitsmaßnahmen+Notfallprotokoll 300 chars, 7.Qualitätssicherung+Nachsorge 360 chars",\n'
        f'  "p_produktwissen": "WRITE EXACTLY 3360 chars of ACTUAL German prose — do not stop early: Produktwissen für {topic}. Abschnitte: 1.Inhaltsstoffe+Wirkstoffe mit Funktion je 500 chars, 2.Qualitätsmerkmale+Zertifizierungen 400 chars, 3.Lagerung+Haltbarkeit+Temperatur 300 chars, 4.Dosierung+Anwendungsreihenfolge 400 chars, 5.Kombinationen+Synergien 300 chars, 6.Unverträglichkeiten+Gegenanzeigen 300 chars, 7.INCI-Kennzeichnung+Deklaration 360 chars",\n'
        f'  "p_technik": "WRITE EXACTLY 3360 chars of ACTUAL German prose — do not stop early: Technik für {topic}. Abschnitte: 1.Raumvorbereitung+Kundenvorbereitung 400 chars, 2.Schritt-für-Schritt Behandlungsablauf detailliert 800 chars, 3.Anwendungsmethoden+Techniken 400 chars, 4.Druckpunkte+Grifftechniken 300 chars, 5.Behandlungsdauer+Wiederholungen 200 chars, 6.Nachbereitung+Dokumentation 300 chars, 7.Qualitätskontrolle+Ergebnismessung 360 chars"\n'
        '}\nWrite ALL values as actual German text of the specified exact length.'
    )
    try:
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt_chA}],
            temperature=0.3, max_tokens=12000,
            response_format={"type": "json_object"}
        )
        data.update(json.loads(r.choices[0].message.content))
        print(f"✅")
    except Exception as e:
        print(f"❌ {e}")

    # ── Chapters B ──
    print(f"    chapters-B...", end=" ", flush=True)
    prompt_chB = (
        f'Write detailed German professional beauty training content for "{topic}". ACTUAL German text only.\n'
        'Return ONLY valid JSON:\n'
        '{\n'
        f'  "p_nach_behandlung": "WRITE EXACTLY 2880 chars: Nach {topic} Behandlung. Abschnitte: 1.Sofortige Pflegehinweise 400 chars, 2.Was vermeiden 24h+48h+1Woche je 200 chars, 3.Reaktionen beobachten+wann Arzt 400 chars, 4.Produktempfehlungen Heimanwendung 400 chars, 5.Kundenkommunikation+Nachsorgetermine 400 chars, 6.Dokumentation+Ergebnisprüfung 480 chars",\n'
        f'  "p_kundenberatung": "WRITE EXACTLY 2880 chars: Kundenberatung {topic}. Abschnitte: 1.Erstgespräch Ablauf+Atmosphäre 400 chars, 2.Anamnese alle Fragen Liste 400 chars, 3.Behandlungsziele definieren+Erwartungen 400 chars, 4.Kontraindikationen prüfen+kommunizieren 400 chars, 5.Einwände behandeln+Lösungen 300 chars, 6.Behandlungsplan+Preise kommunizieren 480 chars, 7.Nachsorgetermine vereinbaren 300 chars",\n'
        f'  "p_marketing": "WRITE EXACTLY 2880 chars: Marketing {topic}. Abschnitte: 1.Zielgruppe definieren+Personas 400 chars, 2.Preisgestaltung+Kalkulation 400 chars, 3.Social Media Strategie+Content 400 chars, 4.Before-After Fotos+Testimonials 300 chars, 5.Kundenbindung+Treueprogramme 300 chars, 6.Pakete+Angebote gestalten 300 chars, 7.Empfehlungsmarketing+Online-Bewertungen 480 chars, 8.Kooperationen+Events 300 chars",\n'
        f'  "p_reflexion": "WRITE EXACTLY 2400 chars: 10 Reflexionsfragen für {topic} Schulung. Je Frage: Fragenummer+Fragetext+ausführliche Erklärung warum wichtig 240 chars. Themen: Anamnese, Kontraindikationen, Technik, Produktwahl, Kundenkommunikation, Hygiene, Nachsorge, Ergebnismessung, Marketing, Eigene Entwicklung",\n'
        f'  "p_wissenstest": "WRITE EXACTLY 2400 chars: 10 Wissensfragen mit Antworten über {topic}. Je Frage: Fragenummer+Frage+ausführliche Antwort 240 chars. Themen: Hautschichten, Funktionen, Krankheiten, Produktwissen, Technik, Hygiene, Kontraindikationen, Kundenberatung, Marketing, Wirkungsweise"\n'
        '}\nWrite ALL values as actual German text of the specified exact length.'
    )
    try:
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt_chB}],
            temperature=0.3, max_tokens=12000,
            response_format={"type": "json_object"}
        )
        data.update(json.loads(r.choices[0].message.content))
        print(f"✅")
    except Exception as e:
        print(f"❌ {e}")

    # ── Pages 31-40: Product knowledge — translate-ready German defaults ──
    # These are STATIC German texts baked into the code.
    # translate_content() will translate them like any other field.
    print(f"    p31-40 products (static defaults)...", end=" ", flush=True)

    # Page 31
    data["p31_h1"]    = "Fuß-/Handbalsam"
    data["p31_body1"] = ("Ein hochwertiger Fuß- und Handbalsam bietet intensive Pflege für beanspruchte, "
        "trockene und sensible Haut. Er wird gezielt eingesetzt, um die Haut zu beruhigen, die natürliche "
        "Regeneration zu unterstützen und Spannungsgefühle sowie Rötungen zu lindern.\n\n"
        "Auf der Haut zieht der Balsam gut ein, schützt die Hautbarriere und hinterlässt ein "
        "geschmeidiges, gepflegtes Hautgefühl. Durch seine reichhaltige Textur eignet er sich ideal "
        "für regelmäßige Pflege- und Massageanwendungen an Händen und Füßen.\n\n"
        "Der Fuß- und Handbalsam ist für alle Hauttypen geeignet, besonders für empfindliche oder "
        "strapazierte Haut. In Wellness-, Pflege- und Kosmetikanwendungen unterstützt er das "
        "Wohlbefinden und sorgt für ein spürbar gepflegtes, komfortables Ergebnis.")
    data["p31_h2"]    = "Gesichtsmaske"
    data["p31_body2"] = ("Die Gesichtsmaske wird gezielt eingesetzt, um die Haut Ihrer Kundin intensiv zu pflegen, "
        "zu beruhigen und die natürliche Regeneration zu unterstützen. Sie versorgt die Haut mit wertvollen "
        "Wirkstoffen, fördert die Durchblutung, glättet die Hautoberfläche und kann Rötungen oder "
        "Irritationen mindern.\n\n"
        "Für sensible Haut eignen sich Masken mit Aloe Vera oder Haferextrakt, die beruhigend und "
        "ausgleichend wirken. Bei gestresster / müder Haut bieten Masken mit Hyaluronsäure oder "
        "Panthenol intensive Feuchtigkeit und Unterstützung der Regeneration. Für fettige / unreine "
        "Haut sind Masken mit Tonerde oder Teebaumöl ideal, da sie klärend und ausgleichend wirken.\n\n"
        "Der angenehme aromatherapeutische Duft unterstützt während der Anwendung die Entspannung, "
        "steigert das Wohlbefinden und schafft ein ganzheitliches Pflegeerlebnis. So können Sie jede "
        "Gesichtsmaske individuell, sicher und professionell auf die Bedürfnisse Ihrer Kundin abstimmen.")

    # Page 32
    data["p32_h1"]    = "Körpermaske"
    data["p32_body1"] = ("Die Körpermaske wird gezielt eingesetzt, um die Haut Ihrer Kundin intensiv zu pflegen, "
        "zu beruhigen und die natürliche Regeneration am gesamten Körper zu unterstützen. Sie versorgt die "
        "Haut mit wertvollen Inhaltsstoffen, verbessert die Elastizität und hinterlässt ein spürbar "
        "geschmeidiges Hautgefühl. Gleichzeitig kann sie Spannungen mindern, Trockenheit ausgleichen "
        "und die Hautbarriere stärken.\n\n"
        "Für trockene / sensible Haut eignen sich Masken mit Sheabutter oder Aloe Vera, die intensiv "
        "pflegen und beruhigen. Bei gestresster Haut bieten Masken mit Hyaluronsäure oder Jojobaöl "
        "feuchtigkeitsspendende und regenerierende Effekte. Für fettige oder unreine Haut sind Masken "
        "mit Tonerde oder Meersalz ideal, da sie ausgleichend und klärend wirken.\n\n"
        "Der aromatherapeutische Duft unterstützt während der Anwendung die Entspannung, steigert das "
        "Wohlbefinden und verwandelt die Behandlung in ein ganzheitliches Pflegeerlebnis. So können "
        "Sie jede Körpermaske individuell auf die Bedürfnisse Ihrer Kundin abstimmen.")
    data["p32_h2"]    = "Peeling"
    data["p32_body2"] = ("Ein Peeling wird eingesetzt, um die Haut Ihrer Kundin sanft zu erneuern, abgestorbene "
        "Zellen zu entfernen und die Durchblutung zu aktivieren. Gleichzeitig bereitet es die Haut "
        "optimal auf nachfolgende Behandlung vor.\n\n"
        "Bei empfindlicher / trockener Haut sind Peelings mit feinem Zucker oder Haferflocken in "
        "Kombination mit pflegenden Ölen wie Mandel- oder Jojobaöl ideal. Gestresste / müde Haut "
        "profitiert von Peelings mit Fruchtsäuren oder Hyaluronsäure, die Feuchtigkeit spenden und "
        "vitalisieren. Für fettige / unreine Haut sind Peelings mit Tonerde oder Salzkristallen "
        "empfehlenswert, da sie klärend und ausgleichend wirken.\n\n"
        "Während der Anwendung sorgt der aromatherapeutische Duft für zusätzliche Entspannung und "
        "Wohlbefinden. So können Sie die Behandlung individuell gestalten und professionell durchführen.")

    # Page 33
    data["p33_h1"]    = "Serum"
    data["p33_body1"] = ("Ein Serum wird gezielt eingesetzt, um die Haut Ihrer Kundin intensiv zu pflegen, zu "
        "regenerieren und die Aufnahme nachfolgender Pflegeprodukte zu optimieren. Es enthält "
        "hochkonzentrierte Wirkstoffe, die tief in die Haut einziehen, die Zellregeneration fördern "
        "und die Hautstruktur sichtbar verbessern.\n\n"
        "Für unterschiedliche Hauttypen eignen sich verschiedene Inhaltsstoffe: Bei sensibler Haut "
        "sind Seren mit Aloe Vera oder Panthenol ideal, da sie beruhigen und Irritationen lindern. "
        "Gestresste oder müde Haut profitiert von Seren mit Hyaluronsäure oder Vitamin C, die "
        "Feuchtigkeit spenden und revitalisieren. Für trockene Haut sind Seren mit Jojobaöl oder "
        "Squalan besonders pflegend und rückfettend.\n\n"
        "Der angenehme aromatherapeutische Duft unterstützt während der Anwendung die Entspannung "
        "und das Wohlbefinden.")
    data["p33_h2"]    = "Augenpads"
    data["p33_body2"] = ("Augenpads werden verwendet, um die zarte Haut rund um die Augen gezielt zu pflegen, "
        "zu beruhigen und sichtbar zu regenerieren. Sie enthalten Wirkstoffe, die Schwellungen mindern, "
        "feine Linien glätten und die Haut geschmeidig halten, während die Durchblutung unterstützt wird.\n\n"
        "Bei empfindlicher / gestresster Haut sind Pads mit Aloe Vera oder Panthenol ideal, da sie "
        "beruhigen und Irritationen lindern. Müde Augenpartien profitieren von Pads mit Koffein oder "
        "Gurkenextrakt, die erfrischen und beleben. Bei trockener / feiner Haut sind Pads mit "
        "Hyaluronsäure oder Vitamin E empfehlenswert, da sie Feuchtigkeit spenden und pflegen.\n\n"
        "Der angenehme aromatherapeutische Duft trägt während der Anwendung zusätzlich zur "
        "Entspannung und Wohlbefinden bei.")

    # Page 34
    data["p34_h1"]    = "Duftessenzen"
    data["p34_body1"] = ("Duftessenzen sind hochkonzentrierte, aromatische Extrakte aus Pflanzen, Blüten, "
        "Früchten, Kräutern oder Harzen, die gezielt zur Raumbeduftung oder Applikation in der "
        "Aromatherapie eingesetzt werden. Sie wirken nicht nur über den Geruchssinn, sondern können "
        "über psychophysiologische Reaktionen auch das Wohlbefinden, die Entspannung, die Stimmung "
        "und die Konzentration beeinflussen.\n\n"
        "In der Praxis werden Duftessenzen oft in Diffusern, Ölbrennern, als Kerzen oder als Sprays "
        "eingesetzt, um den Behandlungsraum gezielt zu aromatisieren. Je nach Zusammensetzung können "
        "sie beruhigend, anregend oder ausgleichend wirken. Durch diese gezielte Anwendung schaffen "
        "Sie eine angenehme Atmosphäre, unterstützen die Behandlung Ihrer Kundin und verstärken die "
        "Wirkung der aromatherapeutischen Anwendungen.")
    data["p34_h2"]    = "Duftkompressen"
    data["p34_body2"] = ("Duftkompressen sind speziell vorbereitete Tücher oder Stoffbeutel, die mit ätherischen "
        "Ölen getränkt werden, um die Wirkstoffe gezielt auf bestimmte Körperbereiche aufzubringen. "
        "Sie dienen dazu, die Haut sanft zu erwärmen, die Durchblutung zu fördern und die wohltuende "
        "Wirkung der Aromatherapie lokal zu unterstützen.\n\n"
        "Die Kompressen können warm oder kalt angewendet werden, je nach gewünschtem Effekt, und "
        "lassen sich leicht an Hals, Schultern, Rücken oder anderen Bereichen platzieren. Durch die "
        "gezielte Applikation geben sie die enthaltenen ätherischen Öle kontrolliert ab, sorgen für "
        "angenehme Duftwirkung und steigern das Wohlbefinden Ihrer Kundin. Duftkompressen sind "
        "wiederverwendbar oder als Einmalprodukt verfügbar und ermöglichen eine flexible, sichere und "
        "professionelle Anwendung in der Aromatherapie.")

    # Page 35
    data["p35_h1"]    = "Aromaschalen"
    data["p35_body1"] = ("Aromaschalen sind speziell geformte Gefäße, die in der Aromatherapie verwendet werden, "
        "um ätherische Öle sicher zu erhitzen oder zu verdampfen. Sie bestehen häufig aus "
        "hitzebeständigem Keramik- oder Glasmaterial und verfügen über eine Mulde oder Schale für "
        "das Öl sowie Platz für ein Teelicht oder einen Diffusoraufsatz. Durch die Schale wird das "
        "Öl gleichmäßig erwärmt, sodass sich der Duft langsam und kontrolliert im Raum verteilt.\n\n"
        "Die Aromaschale ist handlich, stabil und leicht zu reinigen, wodurch sie sich ideal für den "
        "professionellen Einsatz im Behandlungsraum eignet. Sie ermöglicht eine gezielte und sichere "
        "Anwendung ätherischer Öle und unterstützt die Atmosphäre der Aromatherapie, ohne dass das "
        "Öl direkt mit offenem Feuer oder unkontrollierter Hitze in Kontakt kommt.")
    data["p35_h2"]    = "Hot-Stone-Massage Set"
    data["p35_body2"] = ("Ein Hot-Stone-Massage-Set besteht aus sorgfältig ausgewählten, glatten Basalt- oder "
        "Marmorsteinen in verschiedenen Größen, die speziell für Wärmebehandlungen am Körper "
        "entwickelt wurden. Die Steine werden vor der Behandlung auf eine angenehme Temperatur "
        "erwärmt und in Kombination mit Massagegriffen eingesetzt, um Muskelverspannungen zu lösen, "
        "die Durchblutung zu fördern und die Entspannung zu intensivieren.\n\n"
        "Das Set enthält in der Regel flache, ovale Steine für größere Körperpartien sowie kleinere "
        "Steine für gezielte Anwendungen an Schultern, Händen oder Füßen. Die Steine sind "
        "hitzebeständig, glatt poliert und leicht zu reinigen, sodass sie sich ideal für den "
        "professionellen Einsatz eignen. Mit einem Hot-Stone-Set können Sie jede Massage individuell "
        "gestalten, die Wärme gezielt einsetzen und so ein tief entspannendes, wohltuendes "
        "Behandlungserlebnis für Ihre Kundin schaffen.")

    # Page 36
    data["p36_h1"]    = "Cold-Stone Massage Set"
    data["p36_body1"] = ("Ein Cold-Stone-Set besteht aus speziell ausgewählten, glatten Steinen, die für "
        "Kälteanwendungen am Körper entwickelt wurden. Die Steine werden vor der Behandlung gekühlt, "
        "beispielsweise im Kühlschrank oder Gefrierfach, und gezielt auf verspannte oder gereizte "
        "Hautpartien gelegt, um Schwellungen zu reduzieren, die Durchblutung zu fördern und die Haut "
        "zu beruhigen.\n\n"
        "Das Set enthält unterschiedliche Steinformen und -größen, um sowohl größere Körperbereiche "
        "als auch kleinere, empfindliche Zonen wie Gesicht, Augenpartie oder Hände gezielt zu "
        "behandeln. Die Steine sind glatt poliert, hygienisch und leicht zu reinigen, wodurch sie "
        "sich optimal für den professionellen Einsatz eignen. Mit einem Cold-Stone-Set können Sie "
        "jede Behandlung individuell gestalten, gezielt Kältereize setzen und so ein erfrischendes, "
        "wohltuendes Erlebnis für Ihre Kundin schaffen.")
    data["p36_h2"]    = "Bambus- oder Edelsteinstäbe"
    data["p36_body2"] = ("Bambus- oder Edelsteinstäbe sind handliche Werkzeuge, die in der Aromatherapie und "
        "Massage gezielt zur Stimulation bestimmter Körperbereiche eingesetzt werden. Bambusstäbe "
        "sind leicht, stabil und eignen sich besonders für druckvolle Massagebewegungen, um "
        "Verspannungen zu lösen, die Durchblutung zu fördern und die Muskulatur sanft zu aktivieren.\n\n"
        "Edelsteinstäbe bestehen aus polierten Halbedel- oder Kristallsteinen und werden häufig zur "
        "energetischen Behandlung oder zur gezielten Unterstützung von Aromatherapieanwendungen "
        "verwendet. Sie können sowohl zur sanften Massage als auch zur punktuellen Stimulation "
        "genutzt werden und geben Wärme oder Kälte besonders gut weiter, je nach "
        "Anwendungsvorbereitung. Beide Stabarten sind handlich, leicht zu reinigen und ermöglichen "
        "eine präzise, professionelle und individuell abgestimmte Behandlung, die Körper und Sinne "
        "gleichermaßen anspricht.")

    # Page 37
    data["p37_h1"]    = "Massagekugeln"
    data["p37_body1"] = ("Massagekugeln sind handliche, runde Werkzeuge, die gezielt eingesetzt werden, um "
        "verspannte Muskeln zu lockern, die Durchblutung zu fördern und die Haut sanft zu stimulieren.\n\n"
        "Sie können aus verschiedenen Materialien wie Holz, Silikon oder Edelsteinen bestehen und "
        "sind in unterschiedlichen Größen erhältlich, um sowohl größere Körperbereiche als auch "
        "kleinere, empfindliche Zonen zu behandeln.\n\n"
        "Durch Rollen, Drücken oder punktuelle Anwendung lösen Massagekugeln Verspannungen, "
        "aktivieren die Mikrozirkulation und unterstützen die Entspannung. Sie sind leicht zu "
        "handhaben, hygienisch und einfach zu reinigen, wodurch sie sich ideal für den "
        "professionellen Einsatz eignen.")
    data["p37_h2"]    = "Aromaroller"
    data["p37_body2"] = ("Ein Aromaroller ist ein handliches, tragbares Werkzeug, das mit einer Mischung aus "
        "ätherischen Ölen befüllt ist und direkt auf die Haut aufgetragen wird. Er ermöglicht eine "
        "gezielte, dosierte Anwendung an bestimmten Körperstellen wie Handgelenken, Schläfen, Nacken "
        "oder Brust, um die wohltuenden Effekte der Aromatherapie lokal zu nutzen.\n\n"
        "Aromaroller sind einfach zu handhaben, hygienisch verschlossen und ermöglichen eine präzise "
        "Dosierung der Öle, sodass eine sichere und komfortable Anwendung gewährleistet ist. Je nach "
        "Zusammensetzung der Öle können sie beruhigend, ausgleichend oder belebend wirken. Mit einem "
        "Aromaroller können Sie jede Anwendung individuell anpassen, gezielt auf die Bedürfnisse "
        "Ihrer Kundin eingehen und ein intensives, wohltuendes Aromatherapie-Erlebnis schaffen.")

    # Page 38
    data["p38_h1"]    = "Massagehandschuhe"
    data["p38_body1"] = ("Massagehandschuhe sind speziell entwickelte Handschuhe, die während der Aromatherapie "
        "oder Massage eingesetzt werden, um die Haut Ihrer Kundin zu stimulieren, die Durchblutung "
        "zu fördern und Verspannungen zu lösen.\n\n"
        "Sie bestehen meist aus weichem, flexiblem Material mit Noppen oder Struktur, die eine sanfte "
        "Massagewirkung verstärken und gleichzeitig die Aufnahme von Pflegeprodukten wie Ölen oder "
        "Cremes unterstützen.\n\n"
        "Durch ihre flexible Passform ermöglichen Massagehandschuhe eine gleichmäßige "
        "Druckverteilung und eine gezielte Behandlung von größeren Körperbereichen wie Rücken, Armen "
        "oder Beinen. Sie sind leicht zu reinigen, wiederverwendbar und ideal für den "
        "professionellen Einsatz.")
    data["p38_h2"]    = "Pipetten"
    data["p38_body2"] = ("Pipetten sind präzise Dosierwerkzeuge, die in der Aromatherapie verwendet werden, um "
        "ätherische Öle und andere flüssige Wirkstoffe kontrolliert zu entnehmen und aufzutragen. "
        "Je nach Einsatzbereich kommen unterschiedliche Typen zum Einsatz, wie zum Beispiel "
        "Glaspipetten mit Gummisauger, Kophautpipetten für größere Flüssigkeitsmengen oder "
        "Mikropipetten für sehr kleine, genaue Tropfenmengen.\n\n"
        "Sie ermöglichen eine exakte Dosierung, verhindern Verschwendung und sorgen dafür, dass die "
        "Inhaltsstoffe hygienisch und sicher auf die Haut oder in Mischungen aufgetragen werden können.\n\n"
        "Pipetten sind leicht zu reinigen oder steril zu verwenden und sind unverzichtbar, wenn Sie "
        "ätherische Öle individuell zusammenstellen, Mischungen herstellen oder Produkte wie Seren, "
        "Öle und Duftessenzen gezielt dosieren möchten.")

    # Page 39
    data["p39_h1"]    = "Kopfhautöl-Applikator"
    data["p39_body1"] = ("Ein Kopfhautöl-Applikator ist ein spezielles Werkzeug, das entwickelt wurde, um "
        "pflegende Öle gezielt und gleichmäßig auf die Kopfhaut aufzutragen. Er ermöglicht eine "
        "präzise Dosierung, sodass das Öl direkt an die Haarwurzeln gelangt, ohne Haarlängen "
        "unnötig zu beschweren.\n\n"
        "Der Applikator besteht meist aus einem handlichen Fläschchen mit feiner Spitze oder "
        "Bürstchen, das eine einfache, saubere und kontrollierte Anwendung erlaubt.\n\n"
        "Mit diesem Werkzeug können Sie pflegende, beruhigende oder stimulierende Öle punktgenau "
        "verteilen, die Durchblutung der Kopfhaut fördern und die Wirkung der Aromatherapie oder "
        "Haarpflegebehandlung intensivieren.")
    data["p39_h2"]    = "Massageölflaschen mit Pumpspender"
    data["p39_body2"] = ("Massageölflaschen mit Pumpspender sind praktische Behälter, die eine einfache, "
        "kontrollierte Dosierung von Massage- und Aromatherapieölen ermöglichen. Durch den "
        "Pumpspender lässt sich das Öl sparsam und hygienisch entnehmen, ohne dass die Flasche "
        "geöffnet oder verschüttet wird.\n\n"
        "Die Flaschen bestehen meist aus bruchsicherem Glas oder Kunststoff und sind leicht "
        "nachfüllbar. Sie eignen sich ideal für den professionellen Einsatz, da sie eine schnelle, "
        "saubere Anwendung erlauben und das Öl gleichmäßig auf Hände oder Haut auftragen.\n\n"
        "Zusätzlich erleichtern die Flaschen die Organisation im Behandlungsbereich: Sie sorgen für "
        "Ordnung und helfen, unterschiedliche Öle übersichtlich zu lagern. So wird jede Massage "
        "nicht nur effizient, sondern auch professionell vorbereitet.")

    # Page 40
    data["p40_h1"]    = "Mischschalen"
    data["p40_body1"] = ("Mischschalen aus Glas oder Edelstahl sind unverzichtbare Werkzeuge in der "
        "Aromatherapie, um ätherische Öle, Trägeröle oder Pflegeprodukte sicher und hygienisch zu "
        "mischen. Sie ermöglichen eine exakte Dosierung, ein gleichmäßiges Vermengen der "
        "Inhaltsstoffe und verhindern Verschwendung oder Kontamination.\n\n"
        "Glas eignet sich besonders für empfindliche oder lichtempfindliche Öle, da es neutral "
        "reagiert und Gerüche nicht annimmt. Edelstahl ist robust, leicht zu reinigen und besonders "
        "langlebig, was es ideal für den professionellen Einsatz macht.\n\n"
        "Mit diesen Mischschalen können Sie individuelle Ölmischungen, Seren oder Masken exakt "
        "vorbereiten und so jede Behandlung sicher, sauber und professionell auf die Bedürfnisse "
        "Ihrer Kundin abstimmen.")
    data["p40_h2"]    = "Spatel"
    data["p40_body2"] = ("Spatel sind handliche Werkzeuge, die in der Aromatherapie eingesetzt werden, um "
        "Cremes, Masken, Peelings oder andere Produkte hygienisch und präzise zu entnehmen und "
        "aufzutragen. Sie verhindern den direkten Kontakt mit den Händen, reduzieren Kontamination "
        "und sorgen für eine gleichmäßige Verteilung der Produkte auf der Haut.\n\n"
        "Spatel bestehen häufig aus Edelstahl, Kunststoff oder Silikon, sind leicht zu reinigen und "
        "wiederverwendbar, wodurch sie ideal für den professionellen Einsatz geeignet sind.\n\n"
        "Zudem ermöglichen unterschiedliche Spatelformen, selbst Reste aus schmalen Gefäßen oder "
        "Tiegeln restlos zu entleeren und so die Ergiebigkeit der Produkte zu maximieren.")

    # Page 41
    data["p41_h1"]    = "Bedampfungsgerät"
    data["p41_body1"] = ("Ein Bedampfungsgerät ist ein professionelles Gerät, das Wasserdampf erzeugt, um die "
        "Haut während kosmetischer oder aromatherapeutischer Anwendungen sanft zu erwärmen und zu "
        "öffnen. Es wird gezielt eingesetzt, um die Poren zu öffnen, die Durchblutung zu fördern "
        "und die Aufnahme von Pflegeprodukten wie Masken, Seren oder ätherischen Ölen zu verbessern.\n\n"
        "Das Gerät besteht aus einem Tank für Wasser, einem Heizelement und meist einem flexiblen "
        "Auslass oder Aufsatz, der den Dampf gleichmäßig auf Gesicht, Hals oder Dekolleté leitet. "
        "Viele Modelle bieten einstellbare Temperaturen und Dampfstärken, sodass die Anwendung "
        "individuell, sicher und angenehm gestaltet werden kann. Mit einem Bedampfungsgerät können "
        "Sie jede Behandlung professionell, hygienisch und effektiv durchführen und die Wirkung der "
        "Aromatherapie für Ihre Kundin deutlich verstärken.")
    data["p41_h2"]    = "Sonstige Verbrauchsmaterialien"
    data["p41_body2"] = ("Kleine Hilfsmittel wie Wattepads, Zewa, Einwegtücher oder Kosmetikstäbchen sind "
        "unverzichtbare Begleiter jeder professionellen Aromatherapie- oder Wellnessanwendung. Sie "
        "dienen der Hygiene, dem sauberen Auftragen oder Entfernen von Pflegeprodukten und "
        "erleichtern die Arbeit während der Behandlung.\n\n"
        "Die Materialien sind meist einzeln verpackt oder in Rollen erhältlich, weich, hautfreundlich "
        "und leicht zu entsorgen. Sie ermöglichen eine schnelle, saubere und hygienische Anwendung, "
        "verhindern Kreuzkontaminationen und tragen dazu bei, dass jede Behandlung komfortabel und "
        "professionell durchgeführt werden kann. So sorgen Sie auch bei kleinen Dingen für ein "
        "rundum gepflegtes und sicheres Behandlungserlebnis für Ihre Kundin.")

    # Page 42
    data["p42_h1"]    = "Händedesinfektion"
    data["p42_body1"] = ("Die Händedesinfektion ist ein unverzichtbares Produkt für jede professionelle "
        "Aromatherapie- oder Wellnessanwendung. Sie entfernt zuverlässig Bakterien, Viren und andere "
        "Mikroorganismen von der Haut und schützt so sowohl Behandler als auch Kunden.\n\n"
        "Darreichungsform: Flüssigkeit in Flaschen, häufig mit Pump- oder Sprühmechanismus für "
        "einfache Dosierung.\n\n"
        "Eigenschaften: Schnell trocknend, rückstandsfrei und hautverträglich, auch bei häufiger "
        "Anwendung.\n\n"
        "Kaufhinweise: Achten Sie auf einen Alkoholgehalt von mindestens 70 %, auf hautfreundliche "
        "Zusätze wie Aloe oder Glycerin, eine praktische Handhabung (z. B. Pumpflasche) und "
        "ausreichendes Volumen für mehrere Behandlungen.\n\n"
        "Einsatz in der Praxis: Benetzen Sie Ihre Hände vor und nach jeder Behandlung gründlich, "
        "lassen Sie die Desinfektion kurz einwirken und trocknen. Dies gewährleistet maximale "
        "Hygiene und minimiert das Infektionsrisiko.")
    data["p42_h2"]    = "Flächendesinfektion"
    data["p42_body2"] = ("Die Flächendesinfektion entfernt zuverlässig Bakterien, Viren und andere "
        "Mikroorganismen von Oberflächen und Geräten und sorgt so für maximale Hygiene.\n\n"
        "Darreichungsform: Flüssigkeit oder Spray in Flaschen, häufig mit Pump- oder "
        "Sprühmechanismus für einfache, gleichmäßige Dosierung.\n\n"
        "Eigenschaften: Schnell wirksam, rückstandsfrei und materialverträglich, oft mit "
        "hautfreundlichen Zusätzen für Hände oder Kontaktflächen.\n\n"
        "Kaufhinweise: Achten Sie auf eine nachgewiesene Wirksamkeit gegen Bakterien, Viren und "
        "Pilze, auf gute Materialverträglichkeit und eine praktische Handhabung (z. B. Sprühflasche) "
        "sowie ausreichendes Volumen für mehrere Behandlungen.\n\n"
        "Einsatz in der Praxis: Sprühen oder wischen Sie die Desinfektionslösung auf alle "
        "behandlungsrelevanten Flächen vor und nach jeder Anwendung auf, lassen Sie sie kurz "
        "einwirken und trocknen. So gewährleisten Sie ein sicheres, hygienisches Umfeld für Ihre "
        "Kundin und minimieren das Infektionsrisiko.")

    # Page 43 — Einweghandschuhe + Massageauflage
    data["p43_h1"]    = "Einweghandschuhe"
    data["p43_body1"] = ("Einweghandschuhe schützen sowohl Behandlerin als auch Kundin vor direkten "
        "Hautkontakten, Verunreinigungen und der Übertragung von Mikroorganismen.\n\n"
        "Darreichungsform: In Rollen oder Boxen verpackt, meist aus Latex, Nitril oder Vinyl, "
        "einzeln entnehmbar für hygienische Anwendung.\n\n"
        "Eigenschaften: Einmalig verwendbar, elastisch, hautverträglich und in verschiedenen Größen "
        "erhältlich, um sicheren Sitz und Bewegungsfreiheit zu gewährleisten.\n\n"
        "Kaufhinweise: Achten Sie auf die passende Materialart (z. B. latexfrei bei Allergien), "
        "geprüfte Qualität nach medizinischen Standards, ausreichende Packungsgröße und gute "
        "Passform.\n\n"
        "Einsatz in der Praxis: Ziehen Sie die Handschuhe vor jeder Behandlung an, wechseln Sie "
        "sie bei Bedarf zwischen den Anwendungen und entsorgen Sie sie nach einmaligem Gebrauch. "
        "So gewährleisten Sie maximale Hygiene und minimieren das Infektionsrisiko in Ihrem "
        "Behandlungsraum.")
    data["p43_h2"]    = "Massageauflage"
    data["p43_body2"] = ("Die Massageauflage sorgt für Komfort und Unterstützung der Kundin während der "
        "Behandlung, schützt die Liegefläche und erleichtert gleichzeitig hygienisches Arbeiten.\n\n"
        "Darreichungsform: Meist aus weichem, pflegeleichtem Material wie Kunstleder, Baumwolle "
        "oder Schaumstoff, in verschiedenen Größen und Stärken erhältlich, teilweise mit "
        "Aussparungen für Gesicht oder Arme.\n\n"
        "Eigenschaften: Bequem, rutschfest, leicht zu reinigen und robust, ideal für den "
        "professionellen Einsatz in Kosmetik- und Wellnessstudios.\n\n"
        "Kaufhinweise: Achten Sie auf angenehme Polsterung, hautfreundliches Material, einfache "
        "Reinigung und passende Größe für Ihre Behandlungsliege.\n\n"
        "Einsatz in der Praxis: Legen Sie die Auflage auf die Liege und wechseln Sie diese nach "
        "jeder Anwendung. So schaffen Sie ein hygienisches, bequemes und professionelles "
        "Behandlungserlebnis.")

    # Page 44
    data["p44_h1"]    = "Handtücher"
    data["p44_body1"] = ("Handtücher dienen der Hygiene, dem Schutz der Liegeflächen und der Abdeckung der "
        "Kundin während der Behandlung, gleichzeitig bieten sie Komfort und Wärme.\n\n"
        "Darreichungsform: Meist aus Baumwolle oder Mikrofaser, in unterschiedlichen Größen für "
        "Körper, Gesicht oder Hände erhältlich, häufig in Rollen oder Stapeln für einfache "
        "Handhabung.\n\n"
        "Eigenschaften: Weich, saugfähig, hautfreundlich, langlebig und leicht zu reinigen, ideal "
        "für den professionellen Einsatz.\n\n"
        "Kaufhinweise: Achten Sie auf hochwertige Materialien, gute Saugfähigkeit, pflegeleichte "
        "Wascheigenschaften und ausreichende Menge für mehrere Behandlungen.\n\n"
        "Einsatz in der Praxis: Legen Sie Handtücher auf Liegen oder Decken, nutzen Sie sie zum "
        "Abdecken oder Abtrocknen der Kundin und wechseln oder waschen Sie sie nach jeder Anwendung. "
        "So gewährleisten Sie Hygiene, Komfort und ein professionelles Behandlungserlebnis.")
    data["p44_h2"]    = "Decke, Wärmedecke & Wärmekissen"
    data["p44_body2"] = ("Diese Produkte sorgen für Wärme, Komfort und Geborgenheit, unterstützen die "
        "Entspannung und tragen dazu bei, dass sich Ihre Kundin während der Behandlung rundum "
        "wohlfühlt.\n\n"
        "Darreichungsform: Decken aus Baumwolle, Fleece oder Mikrofaser; elektrische Wärmedecken "
        "mit Temperaturregelung; Wärmekissen mit Kern aus Gel, Körnern oder Gel-Granulat, zum "
        "Erwärmen oder Kühlen geeignet.\n\n"
        "Eigenschaften: Hautfreundlich, wärmespeichernd, langlebig und leicht zu reinigen. "
        "Elektrische Produkte verfügen über sichere Temperaturregler und Abschaltautomatik.\n\n"
        "Kaufhinweise: Achten Sie auf angenehmes Material, ausreichende Größe, einfache Handhabung "
        "und Sicherheitsfunktionen.\n\n"
        "Einsatz in der Praxis: Legen Sie Decken oder Wärmedecken über die Kundin oder platzieren "
        "Sie Wärmekissen gezielt auf Körperpartien, um Muskelverspannungen zu lösen, die "
        "Durchblutung zu fördern und ein wohltuendes Wärmegefühl zu erzeugen.")

    print(f"✅")

    checks = {
        "p04_body": 2400, "p05_body_L": 850, "p05_body_R": 800,
        "p06_body_B": 2000, "p06_body_C": 2800,
        "p07_body_L": 1800, "p07_body_R": 1600,
        "p08_body_R": 1600, "p08_body_L": 500,
        "cond1_L": 2000, "cond12_L": 700, "cond12_R": 1800,
        "p_vorbeugende": 2500, "p_produktwissen": 2500, "p_technik": 2500,
    }
    print(f"  Validation:")
    for k, m in checks.items():
        v = data.get(k, "")
        flag = "✅" if len(v) >= m else f"⚠ {len(v)}/{m}"
        print(f"    {flag} {k}")
    return data


# ============================================================
# STEP 2: Translate content
# ============================================================

def translate_content(topic, lang, de_data):
    text_fields = {k: v for k, v in de_data.items() if isinstance(v, str)}
    toc_de = de_data.get("toc_entries", [])

    def clean(s):
        return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', s) if isinstance(s, str) else s
    text_fields = {k: clean(v) for k, v in text_fields.items()}

    toc_text = "\n".join(f"{i+1}. {e.get('title','')} — {e.get('num','')}"
                          for i, e in enumerate(toc_de))

    short_keys = ["cover_subtitle","p03_script","p05_quote","p05_sub1","p05_sub2",
                  "p06_sub_B","p06_sub_C","p07_ch_title","p08_ch_title","p04_ch_title",
                  "cond1_name","cond2_name","cond3_name","cond4_name","cond5_name",
                  "cond6_name","cond7_name","cond8_name","cond9_name","cond10_name",
                  "cond11_name","cond12_name",
                  # Page 31-40 headings — short, translate in call 1
                  "p31_h1","p31_h2","p32_h1","p32_h2","p33_h1","p33_h2",
                  "p34_h1","p34_h2","p35_h1","p35_h2","p36_h1","p36_h2",
                  "p37_h1","p37_h2","p38_h1","p38_h2","p39_h1","p39_h2",
                  "p40_h1","p40_h2",
                  # Page 41-44 headings
                  "p41_h1","p41_h2","p42_h1","p42_h2",
                  "p43_h1","p43_h2","p44_h1","p44_h2"]

    short_fields = {k: text_fields[k] for k in short_keys if k in text_fields}
    long_fields  = {k: v for k, v in text_fields.items() if k not in short_keys and v.strip()}
    long_keys    = list(long_fields.keys())
    chunk_size   = 6
    chunks = [(i//chunk_size + 1, long_keys[i:i+chunk_size])
              for i in range(0, len(long_keys), chunk_size)]

    result = {k: text_fields[k] for k in text_fields}

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

    for attempt in range(2):
        try:
            r1 = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt1}],
                temperature=0.1, max_tokens=3000,
                response_format={"type": "json_object"}
            )
            result.update(json.loads(r1.choices[0].message.content))
            break
        except Exception as e:
            if attempt == 1:
                print(f"\n    ⚠ Call 1 failed: {e}")
                return {}

    for part, keys in chunks:
        chunk = {k: long_fields[k] for k in keys}
        prompt2 = f"""Translate these German training booklet body texts about "{topic}" into {lang}.
RULES: Full {lang} only. No ¿ ¡. Keep same paragraph structure and length.
IMPORTANT: Translate ALL fields completely — do not skip or shorten any field.

{json.dumps(chunk, ensure_ascii=False, indent=2)}

Return ONLY valid JSON with same keys, translated values."""

        for attempt in range(3):
            try:
                r2 = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt2}],
                    temperature=0.1, max_tokens=8000,
                    response_format={"type": "json_object"}
                )
                partial = json.loads(r2.choices[0].message.content)
                result.update(partial)
                missing = [k for k in keys if k not in partial or not partial[k]]
                if missing:
                    print(f"\n    ⚠ Part {part} missing {len(missing)} fields, retry {attempt+1}...", end="")
                    if attempt < 2:
                        continue
                    else:
                        print(f" using German fallback for: {missing[:3]}{'...' if len(missing)>3 else ''}")
                break
            except Exception as e:
                if attempt == 2:
                    print(f"\n    ⚠ Call 2.{part} failed — using German fallback for {len(keys)} fields")

    return result


# ============================================================
# STEP 3: Build pages per language
# ============================================================

COND_NAMES = {
    1: "Neurodermitis", 2: "Schuppenflechte", 3: "Herpes",
    4: "Wundrose", 5: "Nesselsucht", 6: "Gürtelrose",
    7: "Pilzinfektionen", 8: "Sexuell übertragbare Krankheiten",
    9: "Haarausfall", 10: "Warzen", 11: "Rosazea", 12: "Hautkrebs"
}

def build_pages(lang, topic, data, season, year):
    """Returns 40 rows — one per page (pages 1-40)."""
    topic_name = data.get("topic_name", topic) or topic
    toc = data.get("toc_entries", [{}]*20)
    while len(toc) < 20:
        toc.append({"title": "", "num": ""})

    base  = {"Language": lang, "TopicName": topic_name}
    pages = []

    # ── PAGE 1: Cover ──────────────────────────────────────────
    pages.append({**base, "PageNum": "01",
        "Cover_Title":    wrap(topic_name.upper(), 6, max_lines=3),
        "Cover_Subtitle": wrap(data.get("cover_subtitle", "Theorie & Praxis Schulung"), 31, max_lines=1),
        "Cover_Sidebar":  wrap(f"schulung / {season.lower()} {year}", 34, max_lines=1)})

    # ── PAGE 2: TOC heading only ────────────────────────────────
    pages.append({**base, "PageNum": "02",
        "TOC_Heading": wrap("INHALTSVERZEICHNIS", 11, max_lines=4)})

    # ── PAGE 3: Ch01 ───────────────────────────────────────────
    pages.append({**base, "PageNum": "03",
        "P03_Ch_Title": wrap(f"01 Was ist eine {topic_name}?", 30, max_lines=2),
        "P03_Script":   data.get("p03_script", ""),
        "P03_Body":     wrap(data.get("p01_body", ""), 47)})

    # ── PAGE 4: Ch02 ───────────────────────────────────────────
    pages.append({**base, "PageNum": "04",
        "P04_Ch_Title": wrap(data.get("p04_ch_title", "02 Anatomie der Haut"), 22, max_lines=1),
        "P04_Body":     wrap(data.get("p04_body", ""), FULL_W, max_lines=27)})

    # ── PAGE 5: continuation ───────────────────────────────────
    pages.append({**base, "PageNum": "05",
        "P05_Quote":  wrap(data.get("p05_quote", ""), 44, max_lines=2),
        "P05_Sub1":   wrap(data.get("p05_sub1", ""), 44, max_lines=2),
        "P05_Body_L": wrap(data.get("p05_body_L", ""), 53, max_lines=18),
        "P05_Sub2":   wrap(data.get("p05_sub2", ""), 46, max_lines=1),
        "P05_Body_R": wrap(data.get("p05_body_R", ""), 55, max_lines=17)})

    # ── PAGE 6: continuation ───────────────────────────────────
    pages.append({**base, "PageNum": "06",
        "P06_Sub_B":  wrap(data.get("p06_sub_B", ""), 81, max_lines=1),
        "P06_Body_B": wrap(data.get("p06_body_B", ""), FULL_W, max_lines=26),
        "P06_Sub_C":  wrap(data.get("p06_sub_C", ""), 81, max_lines=1),
        "P06_Body_C": wrap(data.get("p06_body_C", ""), FULL_W)})

    # ── PAGE 7: Ch03 ───────────────────────────────────────────
    pages.append({**base, "PageNum": "07",
        "P07_Ch_Title":   wrap(data.get("p07_ch_title", "03 Funktionen und Aufgaben der Haut"), 23, max_lines=2),
        "P07_Body_Left":  wrap(data.get("p07_body_L", ""), HALF_W, max_lines=47),
        "P07_Body_Right": wrap(data.get("p07_body_R", ""), HALF_W, max_lines=44)})

    # ── PAGE 8: Ch04 ───────────────────────────────────────────
    pages.append({**base, "PageNum": "08",
        "P08_Ch_Title":   wrap(data.get("p08_ch_title", "04 Häufigste Krankheiten & Beschwerden"), 29, max_lines=2),
        "P08_Body_Right": wrap(data.get("p08_body_R", ""), HALF_W, max_lines=44),
        "P08_Akne_Intro": wrap(data.get("p08_body_L", ""), 44, max_lines=15)})

    # ── PAGES 9-20: 12 conditions — NO Cond_Name column ────────
    for i in range(1, 13):
        page_num = 8 + i
        lim = PAGE_LIMITS[page_num]
        pages.append({**base, "PageNum": f"{page_num:02d}",
            f"P{page_num:02d}_Cond_Left":  wrap(data.get(f"cond{i}_L", ""), HALF_W, max_lines=lim["L"]),
            f"P{page_num:02d}_Cond_Right": wrap(data.get(f"cond{i}_R", ""), HALF_W, max_lines=lim["R"])})

    # ── PAGE 21: Vorbeugende Maßnahmen ─────────────────────────
    pages.append({**base, "PageNum": "21",
        "P21_Ch_Title":    wrap("05 Vorbeugende Maßnahmen im Studio", 29, max_lines=2),
        "P21_Body_Top":    wrap(data.get("p21_body_top", ""), 96, max_lines=19),
        "P21_Sub_Heading": wrap("Hygiene und Produktgüte der Hersteller", 21, max_lines=2),
        "P21_Body_Right":  wrap(data.get("p21_body_right", ""), 53, max_lines=22),
        "P21_Quote":       wrap(data.get("p21_quote", "Pflege ist der Schlüssel zur zeitlosen Schönheit. — Francis Bacon"), 23, max_lines=3)})

    # ── PAGE 22: Hygienestandards ───────────────────────────────
    pages.append({**base, "PageNum": "22",
        "P22_Sub_Heading": wrap("Hygienestandards im Studio", 21, max_lines=2),
        "P22_Body":        wrap(data.get("p22_body", ""), 53, max_lines=34),
        "P22_Quote":       wrap(data.get("p22_quote", "Die Haut ist das schönste Kleid, das wir tragen. Pflege es gut. — Audrey Hepburn"), 22, max_lines=3)})

    # ── PAGE 23: Hygienemaßnahmen ───────────────────────────────
    pages.append({**base, "PageNum": "23",
        "P23_Sub_Heading": wrap("Hygienemaßnahmen des Kunden", 21, max_lines=2),
        "P23_Body":        wrap(data.get("p23_body", ""), 53, max_lines=49),
        "P23_Quote":       wrap(data.get("p23_quote", "Die beste Foundation ist eine gesunde Haut. — Estée Lauder"), 18, max_lines=3)})

    # ── PAGE 24: Jojobaöl ───────────────────────────────────────
    pages.append({**base, "PageNum": "24",
        "P24_Ch_Title": wrap("06 Produktwissen", 14, max_lines=2),
        "P24_H1":       data.get("p24_h1", "Jojobaöl"),
        "P24_Body_L":   wrap(data.get("p24_body_L", ""), 46, max_lines=14),
        "P24_Body_R":   wrap(data.get("p24_body_R", ""), 46, max_lines=12)})

    # ── PAGES 25-30: Oil pairs ──────────────────────────────────
    oil_pages = [
        ("25", "p25_h1", "p25_body_top", 27, "p25_h2", "p25_body_bot", 25),
        ("26", "p26_h1", "p26_body_top", 26, "p26_h2", "p26_body_bot", 25),
        ("27", "p27_h1", "p27_body_top", 23, "p27_h2", "p27_body_bot", 18),
        ("28", "p28_h1", "p28_body_top", 17, "p28_h2", "p28_body_bot", 18),
        ("29", "p29_h1", "p29_body_top", 20, "p29_h2", "p29_body_bot", 18),
        ("30", "p30_h1", "p30_body_top", 17, "p30_h2", "p30_body_bot", 18),
    ]
    for pg, h1k, b1k, l1, h2k, b2k, l2 in oil_pages:
        pages.append({**base, "PageNum": pg,
            f"P{pg}_H1":       data.get(h1k, ""),
            f"P{pg}_Body_Top": wrap(data.get(b1k, ""), 46, max_lines=l1),
            f"P{pg}_H2":       data.get(h2k, ""),
            f"P{pg}_Body_Bot": wrap(data.get(b2k, ""), 46, max_lines=l2)})

    # ── PAGES 31-40: Product knowledge pages ───────────────────
    # Each page: H1 (heading 1) + Body1 + H2 (heading 2) + Body2
    # Headings: Cormorant Garamond 14pt, one line, ~38 chars max
    # Bodies:   Inter 9pt, ~46 chars/line
    prod_pages = [
        ("31", "p31_h1", "p31_body1", PROD_LINES[31][0], "p31_h2", "p31_body2", PROD_LINES[31][1]),
        ("32", "p32_h1", "p32_body1", PROD_LINES[32][0], "p32_h2", "p32_body2", PROD_LINES[32][1]),
        ("33", "p33_h1", "p33_body1", PROD_LINES[33][0], "p33_h2", "p33_body2", PROD_LINES[33][1]),
        ("34", "p34_h1", "p34_body1", PROD_LINES[34][0], "p34_h2", "p34_body2", PROD_LINES[34][1]),
        ("35", "p35_h1", "p35_body1", PROD_LINES[35][0], "p35_h2", "p35_body2", PROD_LINES[35][1]),
        ("36", "p36_h1", "p36_body1", PROD_LINES[36][0], "p36_h2", "p36_body2", PROD_LINES[36][1]),
        ("37", "p37_h1", "p37_body1", PROD_LINES[37][0], "p37_h2", "p37_body2", PROD_LINES[37][1]),
        ("38", "p38_h1", "p38_body1", PROD_LINES[38][0], "p38_h2", "p38_body2", PROD_LINES[38][1]),
        ("39", "p39_h1", "p39_body1", PROD_LINES[39][0], "p39_h2", "p39_body2", PROD_LINES[39][1]),
        ("40", "p40_h1", "p40_body1", PROD_LINES[40][0], "p40_h2", "p40_body2", PROD_LINES[40][1]),
        ("41", "p41_h1", "p41_body1", PROD_LINES[41][0], "p41_h2", "p41_body2", PROD_LINES[41][1]),
        ("42", "p42_h1", "p42_body1", PROD_LINES[42][0], "p42_h2", "p42_body2", PROD_LINES[42][1]),
        ("43", "p43_h1", "p43_body1", PROD_LINES[43][0], "p43_h2", "p43_body2", PROD_LINES[43][1]),
        ("44", "p44_h1", "p44_body1", PROD_LINES[44][0], "p44_h2", "p44_body2", PROD_LINES[44][1]),
    ]
    for pg, h1k, b1k, l1, h2k, b2k, l2 in prod_pages:
        pages.append({**base, "PageNum": pg,
            f"P{pg}_H1":    wrap(data.get(h1k, ""), PROD_H_W, max_lines=1),
            f"P{pg}_Body1": wrap(data.get(b1k, ""), PROD_B_W, max_lines=l1),
            f"P{pg}_H2":    wrap(data.get(h2k, ""), PROD_H_W, max_lines=1),
            f"P{pg}_Body2": wrap(data.get(b2k, ""), PROD_B_W, max_lines=l2)})

    return pages  # 44 pages total


# ============================================================
# CSV2 — STEP 1: Generate German content for pages 45-65
# ============================================================

def generate_german_content_csv2(topic):
    data = {}

    # ── Call A: Pages 45-48 (Vor der Behandlung, Hautanalyse, Körperanalyse, Anwendungsbereiche) ──
    print(f"    A p45-48...", end=" ", flush=True)
    prompt_a = (
        f'Write detailed German professional beauty training content for "{topic}". ACTUAL German text only.\n'
        'Return ONLY valid JSON:\n'
        '{\n'
        f'  "p45_ch_title": "07 Vor der Behandlung",\n'
        f'  "p45_intro": "WRITE 2 lines intro about preparation importance, max 190 chars: sorgfältige Vorbereitung entscheidend Bedürfnisse Erwartungen Sicherheit gewährleisten.",\n'
        f'  "p45_p1": "WRITE 3-line numbered point about: 1. Vorgespräch und Beratung — ausführliches Gespräch individuelle Wünsche Allergien Kontraindikationen Schwangerschaft Wirkweise ätherische Öle. Max 270 chars.",\n'
        f'  "p45_p2": "WRITE 3-line numbered point about: 2. Einverständniserklärung — sicherer Rahmen Einverständniserklärung Minderjährige Erziehungsberechtigten Dokumentation rechtliche Absicherung. Max 270 chars.",\n'
        f'  "p45_p3": "WRITE 3-line numbered point about: 3. Duftauswahl und Anamnese — Riechprobe Auswahl Öle gemeinsam Kunde angenehm emotionale körperliche Wirkung. Max 270 chars.",\n'
        f'  "p45_p4": "WRITE 3-line numbered point about: 4. Raumklima und Atmosphäre — angenehm temperiert ruhig dezent beleuchtet harmonische Atmosphäre Spannungen Aromen. Max 270 chars.",\n'
        f'  "p45_p5": "WRITE 3-line numbered point about: 5. Hygiene — strenge Hygienestandards Utensilien Spatel Schalen Liegefläche gereinigt desinfiziert. Max 270 chars.",\n'
        f'  "p45_p6": "WRITE 3-line numbered point about: 6. Individuelle Analyse — aktuelles Befinden belebend entspannend lindernd ätherische Öle Massageplanung. Max 270 chars.",\n'
        f'  "p45_p7": "WRITE 3-line numbered point about: 7. Vorbereitung der Materialien — Materialien vorgewärmte Öle Handtücher Griffnähe reibungsloser ruhiger Ablauf. Max 270 chars.",\n'
        f'  "p45_p8": "WRITE 3-line numbered point about: 8. Klientenaufklärung — kurz erklären Körperregionen Hinweise Ruhepausen Wasser Sonne bestimmte Öle. Max 270 chars.",\n'
        f'  "p45_p9": "WRITE 3-line numbered point about: 9. Professionelles Arbeiten — ruhig achtsam gelassen fließender Rhythmus Vertrauen präzise sichere Durchführung. Max 270 chars.",\n'
        f'  "p46_ch_title": "08 Hautanalyse",\n'
        f'  "p46_body": "WRITE EXACTLY 3500 chars: 1.Die Bedeutung der Hautanalyse — erster Schritt professionelle Behandlung maßgeschneiderte Anwendung individuelle Bedürfnisse Textur Teint Feuchtigkeit emotionales Befinden ätherische Öle. 2.Bestimmung des Hauttyps — Normale Haut Basis Wirkstofföle, Trockene Haut reichhaltige Trägeröle beruhigende Essenzen, Fettige Haut leichte nicht-komedogene Öle klärende Düfte, Mischhaut differenzierte Auswahl Balance. Massageplanung Techniken Griffstärken. 3.Vorbereitung und Kundeninstruktion — Hydratisierung Sonnenschutz gründliche Reinigung Verzicht bestimmte Produkte Medikamenteninformation Vorabinformationsblätter. Abschluss Fundament erfolgreiche Behandlung bestmögliche Ergebnisse.",\n'
        f'  "p47_ch_title": "09 Körperanalyse",\n'
        f'  "p47_body": "WRITE EXACTLY 3200 chars: Körperanalyse Methode Bestimmung Anteile menschlicher Körper. Bioelektrische Impedanzanalyse BIA schwaches Wechselstromsignal Körperzusammensetzung Körperfett Körperwasser Muskelmasse medizinisch kosmetisch. Durchführung Körperanalyse — spezielle Körperfettwaage vier Elektroden Füße elektrischer Widerstand Körperzusammensetzung berechnen. Die richtige Körperzusammensetzung — optimale Lebensqualität Gesundheit Übergewicht Untergewicht Fettanteile Muskelmasse fettfreie Körpermasse Leistungsfähigkeit. Wieviel Prozent Körperfett normal — Frauen mehr Männer Alter Faustregel Frauen 21-36% Männer 12-25%. Ziel einer Analyse — nicht nur Gewicht verstehen Veränderungen Fettlevel kosmetische Behandlungen Training Ernährung. Hinweis — Körperanalysewaagen weniger genau zwei Elektroden elektrischer Widerstand vier Elektroden Berechnungen genaue Ergebnisse Messwegs aufrechter Stand gebeugten Knien.",\n'
        f'  "p48_ch_title": "10 Anwendungsbereiche",\n'
        f'  "p48_body": "WRITE EXACTLY 2800 chars: Anwendungsbereiche {topic} verstehen bestmögliche Pflege individuelle Beratung. Gesicht Hals Hautpflege angenehmes Hautgefühl Durchblutung Gesichtsmuskulatur. Beine Oberschenkel Waden Massage ätherische Öle wohltuend schwere müde Beine Durchblutung Spannungen. Gesäß pflegt Haut angenehmes Hautgefühl Massage Entspannung Wohlbefinden. Rücken entspannend Muskulatur Nervensystem Verspannungen Wärmegefühl. Dekolleté sanft gepflegt Feuchtigkeitsgefühl Aromatherapie geschmeidiges Hautgefühl. Arme Massage ätherische Öle Mikrozirkulation Pflege Geschmeidigkeit. Bauch sanfte Massage Duftstoffe angenehmes Entspannungsgefühl beruhigend Körperempfinden Wohlbefinden. Zielsetzungen Aromatherapie: Pflege Hautgefühl ätherische Öle Basisöle Hautempfinden Spannungsgefühle. Durchblutung Mikrozirkulation Massage Duftstoffe lokale Durchblutung Vitalität Leichtigkeit. Entspannung Stressabbau beruhigend Nervensystem Muskelverspannungen mentale Entspannung. Begleitende Unterstützung Spannungen Wellnessmaßnahme keine medizinische Behandlung. Regeneration nach Belastung körperliche Beanspruchung Entspannung Muskulatur Geist Wohlbefinden Lockerungsgefühl."\n'
        '}\nWrite ALL values as actual German text.'
    )
    try:
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt_a}],
            temperature=0.3, max_tokens=12000,
            response_format={"type": "json_object"}
        )
        data.update(json.loads(r.choices[0].message.content))
        print(f"✅")
    except Exception as e:
        print(f"❌ {e}")

    # ── Call B: Page 49-52 Technik (12 columns of massage technique) ──
    print(f"    B p49-52 Technik...", end=" ", flush=True)
    prompt_b = (
        f'Write detailed German massage technique content for "{topic}" beauty training booklet.\n'
        'Return ONLY valid JSON:\n'
        '{\n'
        f'  "p49_ch_title": "11 Technik",\n'
        f'  "p49_intro": "WRITE 4 lines intro max 380 chars: Bevor Anwendung direkt an Kunden Handgriffe präzises Mischen Essenzen vorab üben nötige Sicherheit entwickeln. Körperstelle gewählte Anwendungsmethode individuelle Ölkomposition optimal abgestimmt Arbeitsplatz professionell vorbereitet.",\n'
        f'  "p49_subtitle": "Aroma-Ganzkörpermassage",\n'
        f'  "p49_col1": "WRITE EXACTLY 1100 chars: Vorbereitung Ölkomposition Trägeröl Mandel Jojoba Basisöl Glasschale 50ml Basisöl 8-12 Tropfen ätherische Essenzen sanft verschwenken Wasserbad Stövchen angenehme Körpertemperatur erwärmen. Kaltes Öl Nervensystem schockieren Entspannungsprozess unterbrechen angewärmtes Öl Poren öffnet Eindringen Wirkstoffe Haut intensiv.",\n'
        f'  "p49_col2": "WRITE EXACTLY 1100 chars: Lagerung erster achtsamer Kontakt korrekte Lagerung Fundament Kunde sicher Muskulatur vollständig loslassen. Bauchlage Knierolle Fußrücken Druck unteren Rücken nehmen. Körper großes vorgewärmtes Laken abdecken jeweils zu behandelnde Körperregion freigelebt Intimsphäre Auskühlung. Hände tiefe Atemzüge flach Rücken Moment Stille energetische Einstimmung Behandlung beginnt.",\n'
        f'  "p49_col3": "WRITE EXACTLY 1100 chars: Behandlungsablauf Rückseite Rücken meisten Nervenstränge verlaufen effektive Entspannung. Aromaöl großzügig auftragen lange fließende Streichbewegungen Kreuzbein aufwärts Nacken Schulteraußenseiten zurück leichten mittleren Druck Haut angenehm gleitet Spannung aufbauen. Sanfte Knetungen Muskelgruppen Wirbelsäule Handballen Daumen gleichmäßigen mitteltiefen Druck langsam.",\n'
        f'  "p50_col4": "WRITE EXACTLY 1800 chars: Rhythmisch symmetrisch Muskulatur lockern Durchblutung fördern Druck individuell angepasst angenehme tief entspannende Wirkung keine Schmerzen. Aroma-Zelt Hände Kopf Duft tief einatmen Entspannungsgefühl Sinneswahrnehmung ätherische Öle. Rückseite Beine Richtung Herzens venöser Rückstrom Lymphzirkulation. Waden lange gleitende Streichbewegungen sanfte Knetungen Oberschenkelmuskulatur leichte Streichungen mitteltiefer Druck Verspannungen lösen Durchblutung Öle fördern. Beine zudecken Atemzüge Wirkung Massage nachklingen.",\n'
        f'  "p50_col5": "WRITE EXACTLY 1800 chars: Übergang Behandlung Vorderseite Wechsel Bauch Rückenlage ruhig diskret. Laken hoch Privatsphäre langsam komfortabel positionieren Knierolle Kniekehlen Lendenwirbelsäule entlasten entspannte Liegeposition. Beinvorderseiten Aromaöl große fließende Streichbewegungen Fußrücken Leiste Druck Schienbein Kniescheibe reduzieren Reizungen vermeiden. Fließende Streichungen rhythmisches Kneten Oberschenkelmuskulatur Verspannungen Durchblutung. Armen Handflächen kreisende Daumenbewegungen sensible Reflexpunkte ätherische Öle reagieren.",\n'
        f'  "p50_col6": "WRITE EXACTLY 1800 chars: Sanften Druck gleichmäßige ruhige Bewegungen angenehmes Gefühl Entspannung erzeugen. Bauchmassage Uhrzeigersinn Fingerspitzen emotionales Zentrum beruhigen Wohlbefinden fördern sanfte Unterstützung Verdauung erzielen. Finale Dekolleté Nacken Ganzkörpermassage Abschluss viele Menschen meiste Spannung speichern. Brustbein warmes Aromaöl flache große Handflächenbewegungen fächerförmig Mitte außen Schultern leicht mittelweich spürbar komfortabel. Bewegungen gleichmäßig fließend sanftes Aufsteigen Duftmoleküle Entspannung Geruchssinn verstärkt.",\n'
        f'  "p51_col7": "WRITE EXACTLY 1800 chars: Nackenbereich Hände sanft unter Nacken Finger leicht gespreizt gleichmäßigen sanften Zug Schulteransatz Hinterhauptkamm Haaransatz leicht mittel Nackenmuskulatur dehnen keinesfalls schmerzhaft langsam rhythmisch Muskeln Zeit entspannen tiefes Gefühl Lockerung wahrnimmt. Kreisende Daumenbewegungen Nackenansatz punktuelle Verspannungen sanft lösen fließend natürlichen Verlauf Muskeln Duftnoten ätherische Öle bewusst eingeatmet Entspannung verstärken.",\n'
        f'  "p51_col8": "WRITE EXACTLY 1800 chars: Abschluss verweilen Atemzüge Kopfende Hände locker Nacken Schultern Massage in Ruhe ausklingen Wirkung Behandlung vollständig wahrnehmen. Kunden behutsam zudecken Wärme Geborgenheit erhalten Sitzung offiziell endet. Nachruhe Aktivierung Stoffwechsels manuelle Arbeit beendet wichtigste Phase Aromatherapie Nachruhe. Kunden warm zudecken fünf bis zehn Minuten allein ruhen aufgenommene Essenzen verarbeiten Nervensystem regenerieren.",\n'
        f'  "p51_col9": "WRITE EXACTLY 1800 chars: Ganzkörpermassage Stoffwechsel Entgiftungsprozesse stark anregt Kunden nach Aufstehen Glas stilles Wasser milden Kräutertee reichen. Wertvolles Öl nach Möglichkeit erst nach einigen Stunden abspülen Wirkstoffe Depotwirkung Haut voll entfalten gemeinsam erarbeitetes Gefühl Entspannung Alltag nachwirkt Infos schriftlicher Pflegehinweis mitgegeben.",\n'
        f'  "p52_col10": "WRITE EXACTLY 1800 chars: Fließende Effleurage Ölverteilung Anwendung Effleurage großflächige Streichungen. Warmes Öl eigene Handflächen niemals direkt auf Kunden lange ruhige Züge. Hände gleiten Lendenwirbelsäule parallel Wirbelsäule aufwärts Schultern umfassen sanft Außenseiten Rücken wieder unten. Fließende Bewegung mehrmals zunehmendem angenehmen Druck Rezeptoren Haut Berührung gewöhnen Duft ätherische Öle Raum verteilen Entspannung limbisches System eingeleitet. Intensive Bearbeitung Rückenmuskulatur Petrissage Gewebe erwärmt Knetung gesamte Handfläche Finger lange Rückenmuskelstrecker Musculus erector spinae sanft bestimmt greifen gegeneinander verschieben langsam unten nach oben vor.",\n'
        f'  "p52_col11": "WRITE EXACTLY 1800 chars: Technik Zirkelns Daumenballen flache Daumenkuppen kleine kreisende Bewegungen direkt neben Wirbelsäule niemals Dornfortsätzen tiefsitzende Myogelosen Muskelhärten aufspüren ausstreichen. Feedback Kunden Druck Wohlweh-Schmerz Loslassen fördert. Schultergürtel Schulterblätter Schulterbereich besondere Aufmerksamkeit Sägegriffe fächerförmige Ausstreichen Fingerbeeren unterhalb Schulterblattgräte. Muskulatur unter Schulterblatt lockern Arm vorsichtig leicht angewinkelt Rücken Schulterblatt hervortritt sanftem Druck inneren Rand Schulterblatt tiefe Spannungen. Bewegungen Mitte zurück Oberarme ausstreichen gelöste Energie angeregte Lymphflüssigkeit abzutransportieren.",\n'
        f'  "p52_col12": "WRITE EXACTLY 1800 chars: Nacken Kopfansatzmassage Nacken empfindlicher Bereich Spannungen sammeln Zangengriffen großen Trapezmuskel Daumen Fingern kneten sanft gleichmäßig langsam mittleren Druck Muskulatur lockern keine Beschwerden. Haaransatz vor Basis Hinterhauptbeins Occiput punktuelle Kreisungen zentraler Entspannungspunkt Verspannungen lösen tiefes Wohlgefühl entstehen. Kreisungen sanftes Ausstreichen Nackens Muskeln gedehnt entspannt. Alle Bewegungen gleichmäßig ausgeführt ruckartige Gesten vermeiden Entspannungseffekt sofort unterbrechen. Kunden zwischendurch bewusst Wirkung wahrnehmen Nackenbereich vollständig gelockert."\n'
        '}\nWrite ALL values as actual German text.'
    )
    try:
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt_b}],
            temperature=0.3, max_tokens=12000,
            response_format={"type": "json_object"}
        )
        data.update(json.loads(r.choices[0].message.content))
        print(f"✅")
    except Exception as e:
        print(f"❌ {e}")

    # ── Call C: Pages 53-57 (Nach der Behandlung + Probleme) ──
    print(f"    C p53-57...", end=" ", flush=True)
    prompt_c = (
        f'Write German beauty training content for "{topic}". ACTUAL German text only.\n'
        'Return ONLY valid JSON:\n'
        '{\n'
        f'  "p53_ch_title": "12 Nach der Behandlung",\n'
        f'  "p53_body_top": "WRITE EXACTLY 800 chars: Behandlung Zellaktivität stimuliert Durchblutung Lymphzirkulation gefördert Hautstruktur verbessert. Heilungsprozess variiert Behandlungstechnik Intensität individuelle Voraussetzungen. Haut regeneriert weniger Tage bis Wochen nach Behandlung. Genaue Dauer Heilungsprozesses verschiedene Faktoren Art Behandlung Hautempfindlichkeit Pflege nach Behandlung. Kosmetikerinnen Hautheilungsprozess verstehen Kunden einfach erklären. Des Weiteren Kundin Bescheid wissen Bereiche richtig gepflegt. Kunden klareres Bild Haut entwickelt Heilungsprozess wahrgenomme",\n'
        f'  "p53_body_bot": "WRITE EXACTLY 700 chars: Ergebnis auswirkt. Vorteile Behandlung Haut nach nicht fachgerechter Anwendung reagieren. Blutergüsse Schmerzen Rötungen behandelten Stellen. Seltenere Fälle schwerwiegendere Nebenwirkungen Infektionen allergische Reaktionen. Nach Behandlung Verhaltensweisen beachten: 1. Vermeiden direkter Sonneneinstrahlung Haut empfindlicher anfälliger Sonnenschäden direkte Sonneneinstrahlung vermeiden Breitbandspektrum Sonnenschutz LSF 30.",\n'
        f'  "p53_quote": "Die Haut ist der Spiegel der Seele. — Johann Wolfgang von Goethe",\n'
        f'  "p54_body_mid": "WRITE EXACTLY 700 chars: 2. Verwenden beruhigender Produkte beruhigende feuchtigkeitsspendende Hautpflegeprodukte beruhigen hydratisieren reizende Inhaltsstoffe vermeiden. 3. Verzichten aggressiver Hautpflegeprodukte Retinol AHA BHA Säuren Haut reizen. 4. Kein Rubbeln Schrubben Haut zusätzlich reizen sanfte Produkte Techniken. 5. Kein Make-up Maderotherapie Zeitraum behandelten Bereiche Haut atmen. 6. Vermeiden übermäßigem Schwitzen intensive körperliche Aktivität Poren verstopfen Haut reizen.",\n'
        f'  "p54_body_bot": "WRITE EXACTLY 700 chars: 7. Ausreichend Wasser trinken Haut hydratisiert halten Heilung Regeneration fördern. 8. Anweisungen Kosmetikerin folgen spezifische Anweisungen Nachbehandlung Ergebnisse erzielen. 9. Geduld haben Haut vorübergehend gerötet gereizt Haut genügend Zeit erholen. Wichtig Kundin Anweisungen Kosmetikerin befolgt optimale Ergebnisse mögliche Nebenwirkungen minimieren. Kosmetikerin kein Dermatologe keine Diagnosen medizinische Ratschläge Dermatologen konsultieren Anomalien auftreten.",\n'
        f'  "p55_ch_title": "13 Ergebnismessung",\n'
        f'  "p55_body": "WRITE EXACTLY 3200 chars: Ergebnismessung nach Behandlung entscheidende Bedeutung gewünschte Ergebnisse erzielt Kunden zufriedenstellen. 1.Vorher-Nachher-Fotos — hochauflösende Fotos Hautpartien nach Behandlung Fotos aufnehmen direkter Vergleich sichtbare Verbesserungen Hauttextur Hydratation Teint Hautzustand visuelle Methode äußerst effektiv Fortschritt Laufe Zeit dokumentieren. 2.Hautanalyse — vor nach Behandlung umfassende Hautanalyse objektive Veränderungen Feuchtigkeitsgehalt Elastizität Porengröße Faltentiefe Hautbild spezielle Hautmessgeräte professionelle Hautanalyse-Tools wissenschaftliche Herangehensweise quantitative Daten Fortschritt Zahlen. 3.Kundenfeedback — unschätzbarem Wert nach jeder Behandlung Kunden befragen Feedback erfassen Zufriedenheit Ergebnissen Hautgefühl Verbesserungen allgemeines Wohlbefinden subtile Veränderungen Fotos Messungen Effektivität Behandlung individuell anpassen. 4.Hautzustandstagebuch — Kunden ermutigen Hautzustandstagebuch führen eigene Beobachtungen Veränderungen Empfindungen jeder Behandlung festhalten Fortschritte selbst verfolgen dokumentieren Kunden stärker Behandlungsprozess einbeziehen Bewusstsein Bedürfnisse Haut schärfen. Ergebnismessung integraler Bestandteil verschiedene Messmethoden kombinieren umfassendes Bild Veränderungen Fortschritte Behandlung gegebenenfalls anpassen Kunde erzielten Ergebnissen zufrieden.",\n'
        f'  "p56_ch_title": "14 Probleme & Lösungen seitens des Dienstleisters",\n'
        f'  "p56_sub_intro": "Selbst erfahrene Kosmetikerinnen können bei einer Maderotherapie auf verschiedene Probleme stoßen. Hier sind einige mögliche Szenarien und die entsprechenden Lösungen.",\n'
        f'  "p56_body": "WRITE EXACTLY 3600 chars: 1.Schwierige Handstückplatzierung Hautbeschaffenheit Faktoren herausfordernd. Lösung Technik variieren Handstücke richtig gewählt effektiv platziert. 2.Unzureichende Ergebnisse nach mehreren Sitzungen trotz Behandlungen gewünschte Ergebnisse nicht erreicht. Lösung Behandlungsplanung überprüfen Kombination verschiedene Techniken erneute Beratung realistische Erwartungen. 3.Hautirritationen Rötungen empfindliche Haut angewendete Techniken Irritationen. Lösung Produkte Handstücke Hauttyp geeignet Behandlungsparameter anpassen beruhigende Hautpflegeprodukte. 4.Schmerzen Unbehagen während Behandlung. Lösung Kommunikation mit Kunden fördern Behandlung anpassen Pausen einlegen gründliche Aufklärung Unannehmlichkeiten. 5.Ungleiche Ergebnisse verschiedenen Körperstellen individuelle Unterschiede Fettverteilung Hautbeschaffenheit. Lösung Behandlungsstrategie anpassen mehr Aufmerksamkeit bestimmte Bereiche. 6.Allergische Reaktionen Hautprobleme Inhaltsstoffe Produkte allergisch reagieren. Lösung Kunden informieren Allergietests unerwünschte Reaktionen vermeiden. 7.Probleme mit Geräten technische Probleme reibungslosen Ablauf stören. Lösung regelmäßige Wartung Überprüfung Geräte Ausfälle minimieren Ersatzgeräte Reparaturdienste. 8.Kunden nicht für Behandlung geeignet. Lösung gründliche Anamnese vor Behandlung gesundheitlich anatomisch geeignet. Sorgfältige Kommunikation Kunden entscheidender Bedeutung Probleme frühzeitig erkennen Lösungen finden.",\n'
        f'  "p57_body_risks": "WRITE EXACTLY 3200 chars: Potenzielle Risiken Nebenwirkungen Behandlung berücksichtigt werden sollten. 1.Hautreizungen sanft dennoch empfindliche Haut vorübergehende Rötungen Reizungen leichte Schwellungen normalerweise innerhalb weniger Stunden Tage abklingen. 2.Blutergüsse Massage Vakuum zu intensiv Haut anfällig Blutergüsse Laufe Zeit verblassen. 3.Hautempfindlichkeit nach Behandlung vorübergehend empfindlicher direkte Sonneneinstrahlung intensive Hitzequellen vermeiden Hautreizungen minimieren. 4.Auslösung Hauterkrankungen Rosacea Akne vorübergehend Symptome verschlimmern auslösen Fachmann besprechen. 5.Gefäßerweiterung Massage Vakuumstimulation vorübergehende Gefäßerweiterung Rötungen Flecken normalerweise innerhalb kurzer Zeit abklingen. 6.Allergische Reaktionen Allergien Inhaltsstoffe Öle Produkte Inhaltsstoffe vor Behandlung überprüfen. 7.Individuelle Reaktionen Mensch reagiert unterschiedlich Behandlungen unerwartete Reaktionen. 8.Unzufriedenstellende Ergebnisse Möglichkeit Kundin nach Behandlung nicht zufrieden. Gründliche Beratung vor Behandlung entscheidend Kunden offen Hautzustände Allergien Gesundheitszustände individuelle sichere Behandlung gewährleisten.",\n'
        f'  "p57_quote": "Eine gesunde Haut ist die beste Grundlage für Schönheit. — Pamela Ball"\n'
        '}\nWrite ALL values as actual German text.'
    )
    try:
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt_c}],
            temperature=0.3, max_tokens=12000,
            response_format={"type": "json_object"}
        )
        data.update(json.loads(r.choices[0].message.content))
        print(f"✅")
    except Exception as e:
        print(f"❌ {e}")

    # ── Call D: Pages 58-62 (FAQ, Kundenberatung, Marketing, Preisgestaltung, Reflexion) ──
    print(f"    D p58-62...", end=" ", flush=True)
    prompt_d = (
        f'Write German beauty training content for "{topic}". ACTUAL German text only.\n'
        'Return ONLY valid JSON:\n'
        '{\n'
        f'  "p58_ch_title": "15 Häufige Fragen und Antworten zum Thema",\n'
        f'  "p58_body_L": "WRITE EXACTLY 3400 chars: F:Ist die Behandlung schmerzhaft? A:Behandlung sollte nicht schmerzhaft sein leichtes Ziehen Kribbeln Haut individuelle Toleranz. F:Wie lange dauert eine typische Behandlung? A:Behandlungsdauer behandelten Bereiche variieren 30 bis 60 Minuten. F:Wie viele Sitzungen erforderlich? A:Anzahl Sitzungen Hautzustand gewünschte Effekte variieren mehrere Sitzungen Abstand einige Wochen empfohlen. F:Kann die Behandlung bei jeder Hautfarbe und typ angewendet werden? A:Behandlung meisten Hauttypen geeignet professionelle Beratung individuelle Bedürfnisse. F:Sind die Ergebnisse langanhaltend? A:Ergebnisse Hautpflege Lebensstil genetischer Veranlagung variieren regelmäßige Auffrischungsbehandlungen aufrechterhalten. F:Sind die Ergebnisse sofort sichtbar? A:Einige leichte Effekte erhöhte Durchblutung sofort spürbar vollständige Ergebnisse einige Wochen Haut Zeit regenerieren erneuern. F:Kann die Behandlung mit anderen ästhetischen Behandlungen kombiniert werden?",\n'
        f'  "p58_body_R": "WRITE EXACTLY 3400 chars: A:In einigen Fällen Behandlung Kombination anderen Behandlungen LED-Lichttherapie Kollagenproduktion fördern Entzündungen reduzieren Hautstruktur verbessern. F:Gibt es Möglichkeiten zur Schmerzlinderung während der Behandlung? A:Intensität Behandlung individuelle Toleranz angepasst Unbehagen minimieren offene Kommunikation Kundin wichtig. F:Kann die Maderotherapie bei Narben helfen? A:Behandlung Verbesserung Erscheinungsbilds Narben Durchblutung Kollagenproduktion Haut anregen Narben Laufe Zeit verblassen glatter nicht vollständig beseitigen Erscheinungsbild minimieren. F:Kann die Maderotherapie bei Schwellungen oder Wassereinlagerungen helfen? A:Behandlung dazu beitragen Lymphfluss fördern Schwellungen reduzieren Entwässerung unterstützen. Es ist wichtig zu beachten Antworten allgemeiner Natur Konzept Behandlung beziehen spezifische Details Empfehlungen individuelle Bedürfnisse verwendete Produkte variieren.",\n'
        f'  "p59_ch_title": "16 Kundenberatung",\n'
        f'  "p59_stylish": "Customer service",\n'
        f'  "p59_body_L": "WRITE EXACTLY 1700 chars: Als Kosmetikerin entscheidend gründliche Kundenberatung zur Behandlung durchzuführen. 1.Ziel Behandlung Kunden erklären Behandlung Ergebnis erwarten individuelle Bedürfnisse entspricht. 2.Ablauf der Behandlung detailliert beschreiben Vorbereitung eigentliche Anwendung Nachsorge. 3.Vorher-Nachher-Ergebnisse Kunden Beispiele Vorher-Nachher-Fotos Fallstudien realistische Erwartungen mögliche Ergebnisse schaffen.",\n'
        f'  "p59_body_R": "WRITE EXACTLY 3200 chars: 4.Kontraindikationen etwaige Kontraindikationen Allergien Hauterkrankungen Risiken Nebenwirkungen Zusammenhang Behandlung auftreten könnten. 5.Behandlungsdauer und Intervalle wie lange dauert Sitzungen empfohlen optimale Ergebnisse. 6.Nachsorge und Pflege klare Anweisungen Produkte Verhaltensempfehlungen mögliche Einschränkungen. 7.Kosten und Finanzierung offen Kosten Behandlung etwaige Finanzierungsoptionen finanziellen Seite versteht. 8.Fragen des Kunden ermutigen Fragen stellen ehrlich umfassend beantworten Vertrauen Wohlbefinden Kunden kümmern. 9.Kundenerwartungen Erwartungen Kunden klären realistisch sind. 10.Anpassung der Behandlung individuelle Bedürfnisse Wünsche Kunden berücksichtigen Behandlung gegebenenfalls anpassen besten Ergebnisse erzielen. Gründliche Kundenberatung schafft nicht nur Vertrauen sondern ermöglicht Kunden fundierte Entscheidung treffen Behandlung bestmöglich nutzen.",\n'
        f'  "p60_ch_title": "17 Marketing und Verkauf",\n'
        f'  "p60_body": "WRITE EXACTLY 3000 chars: Marketing Verkauf wichtige Rolle Behandlung potenzielle Kunden ansprechen Vorteile Ergebnisse vermitteln. 1.Zielgruppenanalyse Zielgruppe Behandlung identifizieren Altersgruppen Geschlechter Hauttypen interessiert Marketing Verkaufsstrategien gezielt ausrichten. 2.Online-Präsenz ansprechende informative Website Social-Media-Profile Behandlung bewerben vorher-nachher-Bilder Kundenbewertungen klare Informationen Vorteile Ablauf. 3.Kundennutzen hervorheben Marketingkommunikation Vorteile Kunden strahlender Teint ebenmäßige Haut Unvollkommenheiten verbergen lang anhaltende Ergebnisse geringer Wartungsaufwand. 4.Angebotspakete erstellen attraktive Angebote Behandlungspakete andere Dienstleistungen kombinieren zusätzliche Gesichtsbehandlung Wert Kunden erhöhen zusätzliche Umsätze generieren. 5.Kundenbewertungen Empfehlungen zufriedene Kunden Bewertungen Empfehlungen hinterlassen Website Social-Media-Profile potenzielle Kunden überzeugen Vertrauen Dienstleistungen stärken. 6.Kooperationen Influencern Bloggern Beauty Hautpflegethemen Behandlung kostenlos vergünstigt Erfahrungen Followern teilen. 7.Schulungen Zertifizierungen Expertise Kompetenz Behandlung demonstrieren Vertrauen Kunden stärken Glaubwürdigkeit professionelle Kosmetikerin erhöhen. 8.Mundpropaganda hervorragendes Kundenerlebnis Ergebnisse Erwartungen übertreffen zufriedene Kunden Dienstleistungen weiterempfehlen positive Mundpropaganda. Ethische transparente Marketing Verkaufsstrategie wichtig Kunden mögliche Risiken Ergebnisse Kontraindikationen Behandlung realistische Erwartungen schaffen.",\n'
        f'  "p61_ch_title": "18 Preisgestaltung",\n'
        f'  "p61_body": "WRITE EXACTLY 2400 chars: Festlegung Preise verschiedene Faktoren berücksichtigt werden. 1.Kosten Materialien Ausrüstung Produkte Anschaffungskosten benötigte Geräte verwendete Produkte. 2.Zeit Arbeitsaufwand Einschätzung gesamten Zeitaufwands Vorbereitungs Nachbereitungszeit Wertschätzung Zeit Fachkenntnisse reflektieren. 3.Ausbildung Erfahrung zusätzliche Qualifikationen Erfahrung Preisgestaltung Kunden oft bereit Expertise Fachwissen mehr bezahlen. 4.Konkurrenzanalyse Preise Region Preis wettbewerbsfähig Wert Dienstleistung widerspiegelt. 6.Zielgruppe Zahlungsbereitschaft Zielgruppe High-End-Kunden preisbewusste Kunden. 7.Zusatzleistungen Pakete Zusatzleistungen Behandlungspakete unterschiedliche Preiskategorien. 8.Marktsegmentierung verschiedene Behandlungen unterschiedliche Preise Behandlungsart gerechtfertigt. 9.Kosten-Nutzen-Verhältnis Vorteile Ergebnisse Behandlung betonen Wert Dienstleistung verdeutlichen. 10.Rücklagen Investitionen Teil erzielten Gewinns zukünftige Investitionen Ausrüstung Fortbildung Marketing. 11.Saisonalität Jahreszeit besondere Anlässe Sonderangebote Rabatte. 12.Feedback Kunden Kunden Wert Behandlung bestätigen Preisgestaltung unterstützen. Balance Kosten Wert Dienstleistung Zahlungsbereitschaft Kunden transparent Preise informieren Nutzen Qualität Behandlungen vermitteln.",\n'
        f'  "p62_ch_title": "19 Reflexionsseite",\n'
        f'  "p62_sub": "Hier können Sie Notizen zu dem Dokument niederschreiben."\n'
        '}\nWrite ALL values as actual German text.'
    )
    try:
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt_d}],
            temperature=0.3, max_tokens=12000,
            response_format={"type": "json_object"}
        )
        data.update(json.loads(r.choices[0].message.content))
        print(f"✅")
    except Exception as e:
        print(f"❌ {e}")

    # ── Static: Pages 63-65 quiz + Dankeschön (baked in, translated) ──
    print(f"    E p63-65 quiz+thanks (static)...", end=" ", flush=True)

    data["p63_ch_title"] = "20 Wissenstest"
    data["p63_intro"]    = ("Wir laden Sie ein, Ihr Wissen auf die Probe zu stellen. Kreuzen Sie die richtigen "
        "Antworten an und entdecken Sie, wie gut Sie in diesen Themenbereichen informiert sind. Also, "
        "schnappen Sie sich einen Stift, machen Sie sich bereit zum Kreuzen und lassen Sie die "
        "Quiz-Herausforderung beginnen! Viel Spaß und viel Erfolg!")
    # Quiz questions — 6 questions × 4 options
    quiz = [
        ("Was macht die Honigwalze besonders wirksam?",
         "Ihre Pilzform", "Die Anwendung auf der Bauchpartie", "Die Anwendung auf der Bauchpartie", "Ihre Struktur, die an Honigwaben erinnert"),
        ("Welche entzündungshemmenden Eigenschaften sind für die Haut besonders wichtig?",
         "Vitamin C und E", "Ätherische Öle", "Feuchtigkeitsspendende Eigenschaften", "Beruhigender Duft"),
        ("Was ist Mischhaut?",
         "Eine Haut ohne Trockenheit oder Öligkeit", "Kombi aus öligen / trockenen Bereichen", "Eine Haut mit vergrößerten Poren", "Eine Haut mit grobkörniger Textur"),
        ("Warum könnten Ergebnisse an verschiedenen Körperstellen ungleichmäßig sein?",
         "Zu wenig Platz im Behandlungsraum", "Individuelle Fettverteilung / Hautstruktur", "Die Haut ist von Akne betroffen", "Lichtverhältnisse im Behandlungsraum"),
        ("Für welche Hautprobleme ist die Maderotherapie besonders effektiv?",
         "Pigmentflecken", "Akne", "Cellulite", "Trockene Haut"),
        ("Wann sollte ein Peeling während der Vorbehandlung angewendet werden?",
         "Vor der Reinigung", "Nach der Reinigung", "Vor und nach der Reinigung", "Nach der kompletten Behandlung"),
    ]
    for qi, (q, a, b, c, d_opt) in enumerate(quiz, 1):
        data[f"p63_q{qi}"]  = q
        data[f"p63_a{qi}a"] = a
        data[f"p63_a{qi}b"] = b
        data[f"p63_a{qi}c"] = c
        data[f"p63_a{qi}d"] = d_opt
    # Page 64 = Lösungen — same structure, same data keys reused in build
    data["p64_title"] = "Lösungen"
    for qi, (q, a, b, c, d_opt) in enumerate(quiz, 1):
        data[f"p64_q{qi}"]  = q
        data[f"p64_a{qi}a"] = a
        data[f"p64_a{qi}b"] = b
        data[f"p64_a{qi}c"] = c
        data[f"p64_a{qi}d"] = d_opt
    # Page 65 — Dankeschön
    data["p65_ch_title"] = "Dankeschön!"
    data["p65_body"]     = ("Sie haben sich erfolgreich mit einer Vielzahl von Themen rund um die Maderotherapie, "
        "Hautpflege, Hygienevorschriften und Kundenberatung auseinandergesetzt. Ihr Interesse und Ihre "
        "Hingabe zur Perfektionierung Ihrer Fähigkeiten im Bereich der Kosmetik sind bewundernswert.\n\n"
        "Denken Sie daran, dass die erworbenen Kenntnisse nicht nur Ihre professionelle Entwicklung "
        "vorantreiben, sondern auch die Zufriedenheit Ihrer zukünftigen Kunden maßgeblich beeinflussen "
        "werden. Die sorgfältige Beachtung von Hygienestandards, die präzise Hautanalyse, "
        "professionelles Arbeiten und eine umfassende Kundenberatung werden entscheidend für den Erfolg "
        "Ihrer Karriere als engagierte/r Dienstleister/in.\n\n"
        "Nutzen Sie die erworbenen Fertigkeiten, um eine positive Wirkung auf die Hautgesundheit Ihrer "
        "Kunden zu erzielen. Sie sind auf dem Weg, nicht nur Expertin in Ihrer Spezialität zu werden, "
        "sondern auch Vertrauen und Zufriedenheit bei Ihren Kunden zu schaffen.\n\n"
        "Wir sind zuversichtlich, dass Sie die erworbenen Kompetenzen in Ihrer beruflichen Laufbahn "
        "erfolgreich einsetzen werden. Weiterhin viel Erfolg auf Ihrem Weg in die aufregende Welt der "
        "Schönheit!")

    print(f"✅")
    return data


# ============================================================
# CSV2 — STEP 2: Translate CSV2 content
# ============================================================

def translate_content_csv2(topic, lang, de_data2):
    text_fields = {k: v for k, v in de_data2.items() if isinstance(v, str)}

    def clean(s):
        return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', s) if isinstance(s, str) else s
    text_fields = {k: clean(v) for k, v in text_fields.items()}

    # Short fields: chapter titles, subtitles, quotes, stylish, one-line boxes
    short_keys = [
        "p45_ch_title","p46_ch_title","p47_ch_title","p48_ch_title",
        "p49_ch_title","p49_subtitle","p53_ch_title","p53_quote",
        "p55_ch_title","p56_ch_title","p56_sub_intro","p57_quote",
        "p58_ch_title","p59_ch_title","p59_stylish",
        "p60_ch_title","p61_ch_title","p62_ch_title","p62_sub",
        "p63_ch_title","p64_title","p65_ch_title",
        # quiz questions and options
        "p63_q1","p63_q2","p63_q3","p63_q4","p63_q5","p63_q6",
        "p63_a1a","p63_a1b","p63_a1c","p63_a1d",
        "p63_a2a","p63_a2b","p63_a2c","p63_a2d",
        "p63_a3a","p63_a3b","p63_a3c","p63_a3d",
        "p63_a4a","p63_a4b","p63_a4c","p63_a4d",
        "p63_a5a","p63_a5b","p63_a5c","p63_a5d",
        "p63_a6a","p63_a6b","p63_a6c","p63_a6d",
        "p64_q1","p64_q2","p64_q3","p64_q4","p64_q5","p64_q6",
        "p64_a1a","p64_a1b","p64_a1c","p64_a1d",
        "p64_a2a","p64_a2b","p64_a2c","p64_a2d",
        "p64_a3a","p64_a3b","p64_a3c","p64_a3d",
        "p64_a4a","p64_a4b","p64_a4c","p64_a4d",
        "p64_a5a","p64_a5b","p64_a5c","p64_a5d",
        "p64_a6a","p64_a6b","p64_a6c","p64_a6d",
    ]

    short_fields = {k: text_fields[k] for k in short_keys if k in text_fields}
    long_fields  = {k: v for k, v in text_fields.items()
                    if k not in short_keys and v.strip()}
    long_keys    = list(long_fields.keys())
    chunk_size   = 4
    chunks = [(i//chunk_size + 1, long_keys[i:i+chunk_size])
              for i in range(0, len(long_keys), chunk_size)]

    result = {k: text_fields[k] for k in text_fields}

    prompt1 = f"""Translate into {lang}. Topic: "{topic}".
RULES: Full {lang} only. Professional beauty tone.

SHORT FIELDS:
{json.dumps(short_fields, ensure_ascii=False, indent=2)}

Return ONLY valid JSON:
{{
  "topic_name": "translated topic",
  ...all short field keys translated...
}}"""

    for attempt in range(2):
        try:
            r1 = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt1}],
                temperature=0.1, max_tokens=6000,
                response_format={"type": "json_object"}
            )
            result.update(json.loads(r1.choices[0].message.content))
            break
        except Exception as e:
            if attempt == 1:
                print(f"\n    ⚠ CSV2 Call 1 failed: {e}")
                return {}

    for part, keys in chunks:
        chunk = {k: long_fields[k] for k in keys}
        prompt2 = f"""Translate these German training booklet body texts about "{topic}" into {lang}.
RULES: Full {lang} only. Keep same paragraph structure and length.
IMPORTANT: Translate ALL fields completely — do not skip or shorten any field.

{json.dumps(chunk, ensure_ascii=False, indent=2)}

Return ONLY valid JSON with same keys, translated values."""

        for attempt in range(3):
            try:
                r2 = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt2}],
                    temperature=0.1, max_tokens=8000,
                    response_format={"type": "json_object"}
                )
                partial = json.loads(r2.choices[0].message.content)
                result.update(partial)
                missing = [k for k in keys if k not in partial or not str(partial.get(k,'')).strip()]
                if missing:
                    if attempt < 2:
                        continue
                break
            except Exception as e:
                if attempt == 2:
                    print(f"\n    ⚠ CSV2 Call 2.{part} failed")

    return result


# ============================================================
# CSV2 — STEP 3: Build pages 45-65
# ============================================================

def build_pages_csv2(lang, topic, data):
    """Returns 21 rows — one per page (pages 45-65)."""
    raw_topic  = data.get("topic_name", topic) or topic
    lang_codes = {
        "Deutsch": "DE", "Englisch": "EN", "Türkisch": "TR", "Polnisch": "PL",
        "Russisch": "RU", "Italienisch": "IT", "Spanisch": "ES",
        "Französisch": "FR", "Ungarisch": "HU", "Rumänisch": "RO"
    }
    lang_code  = lang_codes.get(lang, lang[:2].upper())
    topic_name = f"{raw_topic} ({lang_code})"   # unique per language — prevents Canva merging
    base  = {"Language": lang, "TopicName": topic_name}
    pages = []
    W_WIDE = 97   # wide body ~97 chars/line
    W_HALF = 46   # half column ~46 chars/line

    def g(key, default=""):
        return data.get(key, default) or default

    # ── PAGE 45: 07 Vor der Behandlung ─────────────────────────
    pages.append({**base, "PageNum": "45",
        "P45_Ch_Title": wrap(g("p45_ch_title"), 30, max_lines=1),
        "P45_Intro":    wrap(g("p45_intro"), W_WIDE, max_lines=2),
        "P45_P1":       wrap(g("p45_p1"), W_WIDE, max_lines=3),
        "P45_P2":       wrap(g("p45_p2"), W_WIDE, max_lines=3),
        "P45_P3":       wrap(g("p45_p3"), W_WIDE, max_lines=3),
        "P45_P4":       wrap(g("p45_p4"), W_WIDE, max_lines=3),
        "P45_P5":       wrap(g("p45_p5"), W_WIDE, max_lines=3),
        "P45_P6":       wrap(g("p45_p6"), W_WIDE, max_lines=3),
        "P45_P7":       wrap(g("p45_p7"), W_WIDE, max_lines=3),
        "P45_P8":       wrap(g("p45_p8"), W_WIDE, max_lines=3),
        "P45_P9":       wrap(g("p45_p9"), W_WIDE, max_lines=3)})

    # ── PAGE 46: 08 Hautanalyse ─────────────────────────────────
    pages.append({**base, "PageNum": "46",
        "P46_Ch_Title": wrap(g("p46_ch_title"), 25, max_lines=1),
        "P46_Body":     wrap(g("p46_body"), W_WIDE, max_lines=37)})

    # ── PAGE 47: 09 Körperanalyse ───────────────────────────────
    pages.append({**base, "PageNum": "47",
        "P47_Ch_Title": wrap(g("p47_ch_title"), 25, max_lines=1),
        "P47_Body":     wrap(g("p47_body"), W_WIDE, max_lines=38)})

    # ── PAGE 48: 10 Anwendungsbereiche ─────────────────────────
    pages.append({**base, "PageNum": "48",
        "P48_Ch_Title": wrap(g("p48_ch_title"), 30, max_lines=1),
        "P48_Body":     wrap(g("p48_body"), W_WIDE, max_lines=30)})

    # ── PAGE 49: 11 Technik (title + intro + subtitle + 3 cols) ─
    pages.append({**base, "PageNum": "49",
        "P49_Ch_Title": wrap(g("p49_ch_title"), 30, max_lines=1),
        "P49_Intro":    wrap(g("p49_intro"), W_WIDE, max_lines=4),
        "P49_SubTitle": wrap(g("p49_subtitle"), 55, max_lines=1),
        "P49_Col1":     wrap(g("p49_col1"), W_HALF, max_lines=25),
        "P49_Col2":     wrap(g("p49_col2"), W_HALF, max_lines=25),
        "P49_Col3":     wrap(g("p49_col3"), W_HALF, max_lines=25)})

    # ── PAGE 50: Technik continuation (cols 4-6) ───────────────
    pages.append({**base, "PageNum": "50",
        "P50_Col4":     wrap(g("p50_col4"), W_HALF, max_lines=40),
        "P50_Col5":     wrap(g("p50_col5"), W_HALF, max_lines=40),
        "P50_Col6":     wrap(g("p50_col6"), W_HALF, max_lines=40)})

    # ── PAGE 51: Technik continuation (cols 7-9) ───────────────
    pages.append({**base, "PageNum": "51",
        "P51_Col7":     wrap(g("p51_col7"), W_HALF, max_lines=40),
        "P51_Col8":     wrap(g("p51_col8"), W_HALF, max_lines=40),
        "P51_Col9":     wrap(g("p51_col9"), W_HALF, max_lines=40)})

    # ── PAGE 52: Technik continuation (cols 10-12) ─────────────
    pages.append({**base, "PageNum": "52",
        "P52_Col10":    wrap(g("p52_col10"), W_HALF, max_lines=40),
        "P52_Col11":    wrap(g("p52_col11"), W_HALF, max_lines=40),
        "P52_Col12":    wrap(g("p52_col12"), W_HALF, max_lines=40)})

    # ── PAGE 53: 12 Nach der Behandlung ────────────────────────
    pages.append({**base, "PageNum": "53",
        "P53_Ch_Title":  wrap(g("p53_ch_title"), 35, max_lines=1),
        "P53_Body_Top":  wrap(g("p53_body_top"), W_HALF, max_lines=18),
        "P53_Body_Bot":  wrap(g("p53_body_bot"), W_HALF, max_lines=15),
        "P53_Quote":     wrap(g("p53_quote"), 25, max_lines=3)})

    # ── PAGE 54: continuation ──────────────────────────────────
    pages.append({**base, "PageNum": "54",
        "P54_Body_Mid":  wrap(g("p54_body_mid"), W_WIDE, max_lines=16),
        "P54_Body_Bot":  wrap(g("p54_body_bot"), W_WIDE, max_lines=16)})

    # ── PAGE 55: 13 Ergebnismessung ────────────────────────────
    pages.append({**base, "PageNum": "55",
        "P55_Ch_Title":  wrap(g("p55_ch_title"), 25, max_lines=1),
        "P55_Body":      wrap(g("p55_body"), W_WIDE, max_lines=34)})

    # ── PAGE 56: 14 Probleme & Lösungen ────────────────────────
    pages.append({**base, "PageNum": "56",
        "P56_Ch_Title":  wrap(g("p56_ch_title"), 50, max_lines=2),
        "P56_Sub_Intro": wrap(g("p56_sub_intro"), W_WIDE, max_lines=2),
        "P56_Body":      wrap(g("p56_body"), W_WIDE, max_lines=40)})

    # ── PAGE 57: Risiken + quote ────────────────────────────────
    pages.append({**base, "PageNum": "57",
        "P57_Body_Risks": wrap(g("p57_body_risks"), W_WIDE, max_lines=38),
        "P57_Quote":      wrap(g("p57_quote"), 25, max_lines=3)})

    # ── PAGE 58: 15 Häufige Fragen ─────────────────────────────
    pages.append({**base, "PageNum": "58",
        "P58_Ch_Title":  wrap(g("p58_ch_title"), 50, max_lines=2),
        "P58_Body_L":    wrap(g("p58_body_L"), W_HALF, max_lines=39),
        "P58_Body_R":    wrap(g("p58_body_R"), W_HALF, max_lines=39)})

    # ── PAGE 59: 16 Kundenberatung ─────────────────────────────
    pages.append({**base, "PageNum": "59",
        "P59_Ch_Title":  wrap(g("p59_ch_title"), 30, max_lines=1),
        "P59_Stylish":   g("p59_stylish"),
        "P59_Body_L":    wrap(g("p59_body_L"), W_HALF, max_lines=19),
        "P59_Body_R":    wrap(g("p59_body_R"), W_HALF, max_lines=38)})

    # ── PAGE 60: 17 Marketing und Verkauf ──────────────────────
    pages.append({**base, "PageNum": "60",
        "P60_Ch_Title":  wrap(g("p60_ch_title"), 35, max_lines=1),
        "P60_Body":      wrap(g("p60_body"), W_WIDE, max_lines=34)})

    # ── PAGE 61: 18 Preisgestaltung ────────────────────────────
    pages.append({**base, "PageNum": "61",
        "P61_Ch_Title":  wrap(g("p61_ch_title"), 30, max_lines=1),
        "P61_Body":      wrap(g("p61_body"), W_WIDE, max_lines=27)})

    # ── PAGE 62: 19 Reflexionsseite ────────────────────────────
    pages.append({**base, "PageNum": "62",
        "P62_Ch_Title":  wrap(g("p62_ch_title"), 30, max_lines=1),
        "P62_Sub":       wrap(g("p62_sub"), W_WIDE, max_lines=1)})

    # ── PAGE 63: 20 Wissenstest ─────────────────────────────────
    q63 = {**base, "PageNum": "63",
        "P63_Ch_Title":  wrap(g("p63_ch_title"), 20, max_lines=1),
        "P63_Intro":     wrap(g("p63_intro"), W_WIDE, max_lines=3)}
    for qi in range(1, 7):
        q63[f"P63_Q{qi}"]   = wrap(g(f"p63_q{qi}"), W_WIDE, max_lines=1)
        q63[f"P63_A{qi}a"]  = wrap(g(f"p63_a{qi}a"), 40, max_lines=1)
        q63[f"P63_A{qi}b"]  = wrap(g(f"p63_a{qi}b"), 40, max_lines=1)
        q63[f"P63_A{qi}c"]  = wrap(g(f"p63_a{qi}c"), 40, max_lines=1)
        q63[f"P63_A{qi}d"]  = wrap(g(f"p63_a{qi}d"), 40, max_lines=1)
    pages.append(q63)

    # ── PAGE 64: Lösungen (same structure as p63) ──────────────
    q64 = {**base, "PageNum": "64",
        "P64_Title": wrap(g("p64_title"), 20, max_lines=1)}
    for qi in range(1, 7):
        q64[f"P64_Q{qi}"]   = wrap(g(f"p64_q{qi}"), W_WIDE, max_lines=1)
        q64[f"P64_A{qi}a"]  = wrap(g(f"p64_a{qi}a"), 40, max_lines=1)
        q64[f"P64_A{qi}b"]  = wrap(g(f"p64_a{qi}b"), 40, max_lines=1)
        q64[f"P64_A{qi}c"]  = wrap(g(f"p64_a{qi}c"), 40, max_lines=1)
        q64[f"P64_A{qi}d"]  = wrap(g(f"p64_a{qi}d"), 40, max_lines=1)
    pages.append(q64)

    # ── PAGE 65: Dankeschön ─────────────────────────────────────
    pages.append({**base, "PageNum": "65",
        "P65_Ch_Title":  g("p65_ch_title"),
        "P65_Body":      wrap(g("p65_body"), W_WIDE, max_lines=15)})

    return pages  # 21 pages total

# ============================================================
# MAIN
# ============================================================

def safe_filename(text):
    return re.sub(r'[^\w\s-]', '', text).strip().replace(' ', '_')

if __name__ == "__main__":
    print("=" * 62)
    print("  Booklet Generator — Theorie & Praxis Schulung")
    print("=" * 62)
    print("  44 pages | 10 languages | GPT-generated content\n")

    topic = input("Enter topic in German (e.g. Aromatherapie): ").strip()
    while not topic:
        print("  ⚠ Topic cannot be empty. Please enter a topic name.")
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
        data = {}   # always reset per language
        if lang == "Deutsch":
            data = dict(de_data)
            data["topic_name"] = topic
            print("(source — no API call)")
        else:
            try:
                data = translate_content(topic, lang, de_data)
            except Exception as ex:
                print(f"\n    ⚠ translate exception: {ex}")
                data = {}
            if not data:
                data = dict(de_data)
                data["topic_name"] = topic
                print("⚠ fallback")
            else:
                if not data.get("topic_name", "").strip():
                    data["topic_name"] = topic
                empty = [k for k in data if any(x in k.lower() for x in ['body', 'cond_l', 'cond_r'])
                         if not str(data.get(k, '')).strip()]
                if empty:
                    print(f"⚠ {len(empty)} empty fields: {empty[:3]}...")
                else:
                    print("✅")
        rows.extend(build_pages(lang, topic, data, season, now.year))

    # Merge 44 pages per language into one row per language
    pages_per_lang = 44
    all_rows = []
    for i in range(0, len(rows), pages_per_lang):
        lang_pages = rows[i:i + pages_per_lang]
        merged = {}
        for page_row in lang_pages:
            for k, v in page_row.items():
                if k != "PageNum":
                    merged[k] = v
        all_rows.append(merged)

    df = pd.DataFrame(all_rows).fillna("")

    timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"Booklet_{safe_filename(topic)}_10Languages_{timestamp}.csv"
    df.to_csv(output_file, index=False, quoting=csv.QUOTE_ALL, encoding="utf-8-sig")

    print(f"\n✅  CSV saved: {output_file}")
    print(f"    {len(df)} rows × {len(df.columns)} columns")
    cols_ok = "✅ under limit" if len(df.columns) <= 150 else f"❌ OVER by {len(df.columns) - 150}"
    print(f"    Canva column check: {cols_ok}")
    print(f"    → Canva: 10 rows × 44-page template = 10 booklets ✅")

    # ============================================================
    # CSV 2: Pages 45-65 (21 pages, 124 cols)
    # ============================================================
    print("\n" + "="*62)
    print("  CSV 2: Pages 45-65 | 21 pages | same 10 languages")
    print("="*62)

    print(f"\nStep 3: Generating German content for CSV2 pages 45-65...")
    de_data2 = generate_german_content_csv2(topic)

    rows2 = []
    print(f"\nStep 4: Translating CSV2 into 10 languages...")
    for lang in LANGUAGES:
        print(f"  → {lang:<14}", end="", flush=True)
        data2 = {}   # always reset per language
        if lang == "Deutsch":
            data2 = dict(de_data2)
            data2["topic_name"] = topic
            print("(source — no API call)")
        else:
            try:
                data2 = translate_content_csv2(topic, lang, de_data2)
            except Exception as ex:
                print(f"\n    ⚠ translate exception: {ex}")
                data2 = {}
            if not data2:
                data2 = dict(de_data2)
                data2["topic_name"] = topic
                print("⚠ fallback to German")
            else:
                if not data2.get("topic_name", "").strip():
                    data2["topic_name"] = topic
                print("✅")
        pages_this_lang = build_pages_csv2(lang, topic, data2)
        if len(pages_this_lang) != 21:
            print(f"    ⚠ WARNING: {lang} got {len(pages_this_lang)} pages instead of 21!")
        rows2.extend(pages_this_lang)

    print(f"\n  CSV2 rows collected: {len(rows2)} (expected {len(LANGUAGES) * 21})")

    pages_per_lang2 = 21
    expected2 = len(LANGUAGES) * pages_per_lang2
    if len(rows2) != expected2:
        print(f"  ⚠ Row count mismatch: got {len(rows2)}, expected {expected2}. Proceeding anyway.")
    all_rows2 = []
    for i in range(0, len(rows2), pages_per_lang2):
        lang_pages2 = rows2[i:i + pages_per_lang2]
        merged2 = {}
        for page_row in lang_pages2:
            for k, v in page_row.items():
                if k != "PageNum":
                    merged2[k] = v
        all_rows2.append(merged2)

    df2 = pd.DataFrame(all_rows2).fillna("")
    output_file2 = f"Booklet_{safe_filename(topic)}_10Languages_{timestamp}_CSV2.csv"
    df2.to_csv(output_file2, index=False, quoting=csv.QUOTE_ALL, encoding="utf-8-sig")

    print(f"\n✅  CSV2 saved: {output_file2}")
    print(f"    {len(df2)} rows × {len(df2.columns)} columns")
    cols_ok2 = "✅ under limit" if len(df2.columns) <= 150 else f"❌ OVER by {len(df2.columns) - 150}"
    print(f"    Canva column check: {cols_ok2}")
    print(f"    → Canva: 10 rows × 21-page template = 10 booklets ✅")
    print(f"\n🎉 Both CSVs ready!")
    print(f"   Upload CSV1 to your 44-page Canva template,")
    print(f"   Upload CSV2 to your 21-page Canva template.")