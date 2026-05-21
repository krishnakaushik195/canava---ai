# generate_canva_bulk_csv.py
# Updated for your specific sheet: https://docs.google.com/spreadsheets/d/1wUtgcEmGOoC4rfOOX1OsV4vx1qBgNgvRA4KlP4dHNyw/edit

import json
import os
from datetime import datetime

import gspread
import pandas as pd
from google.oauth2.service_account import Credentials

# ────────────────────────────────────────────────
#  CONFIGURATION – only change if needed
# ────────────────────────────────────────────────

SHEET_ID = "1wUtgcEmGOoC4rfOOX1OsV4vx1qBgNgvRA4KlP4dHNyw"   # your real sheet ID
TAB_NAME = "Queue - table (1).csv"                               # tab name (remove .csv if not part of name)

SERVICE_ACCOUNT_FILE = "service-account.json"                # must be in same folder

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# Columns to include in the final CSV (add more if needed)
CSV_COLUMNS = [
    "Treatment",
    "DocumentType",
    "GermanTitle",
    "GermanBody",
    "EnglishTitle",
    "EnglishBody",
    # Add other languages later: "TurkishTitle", "TurkishBody", ...
]

# Simple dummy translator – replace with real API later
def dummy_translate_german_to_english(text):
    if not text or pd.isna(text):
        return ""
    return "[EN] " + str(text)[:150] + "..." if len(str(text)) > 150 else "[EN] " + str(text)

# ────────────────────────────────────────────────
#  MAIN
# ────────────────────────────────────────────────

def main():
    print("Starting CSV generator for Canva Bulk Create...")

    # 1. Authenticate
    try:
        creds = Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE,
            scopes=SCOPES
        )
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(SHEET_ID)
        worksheet = spreadsheet.worksheet(TAB_NAME)
        print(f"Opened sheet ID: {SHEET_ID} → tab: {TAB_NAME}")
    except gspread.exceptions.WorksheetNotFound:
        print(f"Error: Tab '{TAB_NAME}' not found. Check the exact tab name (case-sensitive).")
        return
    except Exception as e:
        print("Error connecting to Google Sheet:", str(e))
        print("Possible fixes:")
        print("1. Enable Google Drive API: https://console.cloud.google.com/apis/api/drive.googleapis.com/overview?project=414771868151")
        print("2. Share sheet with service account email (from JSON file)")
        print("3. Re-download service-account.json if needed")
        return

    # 2. Read data
    try:
        data = worksheet.get_all_records()
        if not data:
            print("No data found in the sheet.")
            return
        df = pd.DataFrame(data)
        print(f"Read {len(df)} rows from sheet.")
    except Exception as e:
        print("Error reading data:", str(e))
        return

    # 3. Filter YES rows
    if "NeedsAction" not in df.columns:
        print("Column 'NeedsAction' not found. Check headers.")
        return

    df_yes = df[df["NeedsAction"].astype(str).str.strip().str.upper() == "YES"].copy()

    if df_yes.empty:
        print("No rows with NeedsAction = YES found.")
        return

    print(f"Found {len(df_yes)} rows to export.")

    # 4. Build output DataFrame
    output_df = pd.DataFrame(columns=CSV_COLUMNS)

    for _, row in df_yes.iterrows():
        new_row = {
            "Treatment": row.get("Treatment", ""),
            "DocumentType": row.get("DocumentType", ""),
            "GermanTitle": row.get("GermanTitle", ""),
            "GermanBody": row.get("GermanBody", ""),
            "EnglishTitle": row.get("EnglishTitle", ""),
            "EnglishBody": row.get("EnglishBody", ""),
        }

        # Auto-fill English if missing (dummy translation)
        if not new_row["EnglishTitle"]:
            new_row["EnglishTitle"] = dummy_translate_german_to_english(row.get("GermanTitle", ""))
        if not new_row["EnglishBody"]:
            new_row["EnglishBody"] = dummy_translate_german_to_english(row.get("GermanBody", ""))

        output_df = pd.concat([output_df, pd.DataFrame([new_row])], ignore_index=True)

    # 5. Save CSV
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"canva_bulk_create_{timestamp}.csv"

    output_df.to_csv(filename, index=False, encoding="utf-8-sig")  # utf-8-sig for Excel compatibility
    print(f"\nCSV file created: {os.path.abspath(filename)}")
    print(f"Rows exported: {len(output_df)}")
    print("\nPreview of CSV (first few rows):")
    print(output_df.head().to_string(index=False))

    print("\nDone! Now upload this CSV to Canva Bulk Create.")

if __name__ == "__main__":
    main()