import os
import json
import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI
import csv

# Load environment variables (OPENAI_API_KEY from .env)
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# === CONFIG ===
LANGUAGES = [
    "Deutsch",
    "Englisch",
    "Türkisch",
    "Polnisch",
    "Russisch",
    "Italienisch",
    "Spanisch",
    "Französisch",
    "Ungarisch",
    "Rumänisch"
]

# Define Canva placeholder names per category
# → Customize these exactly to match your Canva template field names!
PLACEHOLDERS = {
    "Einverständniserklärung": [
        "Title",
        "Intro",
        "Purpose",
        "Procedure",
        "Risks",
        "Contraindications",
        "Declaration",
        "SignatureLine",
        "DatePlace"
    ],
    "Schulung": [
        "Title",
        "Introduction",
        "LearningObjectives",
        "Section1_Title",
        "Section1_Text",
        "Section2_Title",
        "Section2_Text",
        "Section3_Title",
        "Section3_Text",
        "Conclusion",
        "CertificateText"
    ]
    # Add more categories here later, e.g. "Pflegehinweis": [...]
}

# Optional: path to your main product CSV (not used yet, but good for future checks)
MAIN_SHEET_PATH = "Produktbestand - Produkte (1).csv"

def generate_structured_content(treatment, category):
    """
    Ask GPT-4o-mini to generate structured JSON content in German.
    """
    placeholders = PLACEHOLDERS.get(category, [])
    if not placeholders:
        raise ValueError(f"Keine Platzhalter für Kategorie '{category}' definiert!")

    prompt = f"""
    Erstelle einen professionellen, rechtssicheren Text auf Deutsch für ein Kosmetik-/Wellness-Studio.
    Kategorie: {category}
    Behandlung/Thema: {treatment}

    Der Text muss klar, formell, kundenfreundlich und rechtlich sinnvoll sein (ähnlich bestehender Vorlagen).
    Gib **ausschließlich gültiges JSON** zurück – keine Einleitung, kein Markdown, nichts anderes.

    Die JSON-Keys müssen **exakt** diese sein (keine anderen!):
    {', '.join(placeholders)}

    Beispiel für Einverständniserklärung:
    {{
      "Title": "Einverständniserklärung zur Manuellen Lymphdrainage",
      "Intro": "Sehr geehrte Kundin, sehr geehrter Kunde,\\nmit meiner Unterschrift bestätige ich...",
      "Purpose": "Zweck der Behandlung: Förderung des Lymphflusses, Entstauung...",
      ...
    }}
    """
    
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.25,
        max_tokens=2000,
        response_format={"type": "json_object"}
    )
    
    try:
        content = json.loads(response.choices[0].message.content)
        # Basic validation
        missing = [p for p in placeholders if p not in content]
        if missing:
            print(f"Warnung: Fehlende Felder im JSON: {missing}")
        return content
    except json.JSONDecodeError:
        raise ValueError("GPT hat kein gültiges JSON zurückgegeben. Antwort war:\n" + response.choices[0].message.content)


def translate_text(text, target_lang):
    """
    Translate one field to the target language, keeping tone and formatting.
    """
    if not text.strip():
        return ""
    
    prompt = f"""
    Übersetze den folgenden Text **exakt, natürlich und fachlich korrekt** ins {target_lang}.
    Behalte Absätze, Aufzählungen, Fachbegriffe und den formellen Ton bei.
    Gib nur die reine Übersetzung zurück – keine Einleitung.

    Text:
    {text}
    """
    
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
        max_tokens=1000
    )
    
    return response.choices[0].message.content.strip()


# === MAIN PROGRAM ===
if __name__ == "__main__":
    print("=== Canva Bulk Create Generator (Option 1 – Semi-Automatic) ===\n")
    
    treatment = input("Behandlung (z.B. Lymphdrainage, Aromatherapie): ").strip()
    category = input("Kategorie (Einverständniserklärung oder Schulung): ").strip()
    
    if category not in PLACEHOLDERS:
        print(f"Fehler: Unbekannte Kategorie '{category}'. Verfügbar: {list(PLACEHOLDERS.keys())}")
        exit(1)
    
    print(f"\nGeneriere strukturierten deutschen Basis-Inhalt für '{treatment}' – {category} ...")
    try:
        german_data = generate_structured_content(treatment, category)
        print("Deutsch (JSON) fertig:")
        print(json.dumps(german_data, indent=2, ensure_ascii=False))
        print()
    except Exception as e:
        print(f"Fehler beim Generieren des deutschen Inhalts:\n{e}")
        exit(1)
    
    # Build CSV rows
    rows = []
    for lang in LANGUAGES:
        print(f"Übersetze nach {lang}...")
        row = {
            "Language": lang,
            "Treatment": treatment,
            "Category": category
        }
        
        if lang == "Deutsch":
            translated_dict = german_data
        else:
            translated_dict = {}
            for key, value in german_data.items():
                translated_dict[key] = translate_text(value, lang)
        
        row.update(translated_dict)
        rows.append(row)
    
    # Create DataFrame and save CSV
    df = pd.DataFrame(rows)
    output_filename = f"canva_bulk_{category.replace(' ', '_')}_{treatment.replace(' ', '_')}.csv"
    df.to_csv(output_filename, index=False, quoting=csv.QUOTE_ALL, encoding='utf-8')
    
    print(f"\n✅ Erfolg! CSV-Datei erstellt: {output_filename}")
    print(f"→ Öffne Canva → Bulk Create → CSV hochladen → Felder verbinden (einmalig) → Designs generieren")
    print(f"→ Exportiere PDFs + Hauptbild pro Sprache → in Google Drive Ordner ziehen → Make.com übernimmt Rest")
    print("\nFertig für Canva! Viel Erfolg beim Test mit Angela.")