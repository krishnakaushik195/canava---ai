"""
Booklet PDF Merger + Google Drive + WooCommerce
================================================
Phase 1 — Merge 10 Part-1 PDFs (44p) + 4 Part-2 PDFs (21p blocks)
           into 10 complete 65-page booklets. Language via GPT-4o-mini.
Phase 2 — Upload all 10 PDFs to Google Drive, get shareable links.
Phase 3 — Create WooCommerce product:
           • Simple downloadable  → all 10 languages, one price (standard products)
           • Variable product     → "Sprachen" attribute, one variation per language
                                    each with its own price + download link
                                    (for Komplettpaket-style products)
           Yoast SEO fields set via wp-json/yoast/v1/... REST endpoint.

Requirements:
    pip install streamlit pypdf openai python-dotenv pdf2image pytesseract
    pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib requests

.env file (same folder):
    OPENAI_API_KEY=sk-your-openai-key
    GOOGLE_CREDENTIALS_FILE=credentials.json
    GOOGLE_TOKEN_FILE=token.json
    GOOGLE_DRIVE_PARENT_FOLDER_ID=1uZJHM_hMWYkRv0wACLBcbLDUyFRguDy4
    WP_URL=https://beautymediashop.de
    WC_CONSUMER_KEY=ck_xxxxxxxxxxxx
    WC_CONSUMER_SECRET=cs_xxxxxxxxxxxx
    WP_USERNAME=your-wp-username
    WP_APP_PASSWORD=your-wp-app-password
"""

import re
import streamlit as st
import zipfile
import io
import os
import json
import socket
import requests as _requests
import base64 as _base64
from datetime import datetime
from pypdf import PdfReader, PdfWriter
from dotenv import load_dotenv

load_dotenv()

# ── DNS Override ─────────────────────────────────────────────────────────────
# Patches socket.getaddrinfo so Python's requests library resolves hosts that
# the system DNS fails on (e.g. when hosts file is ignored by Anaconda/conda).
# Maps hostname → IP. Extend this dict if other hosts fail to resolve.
_DNS_OVERRIDES: dict = {
    "beautymediashop.de": "85.13.153.187",
}
_orig_getaddrinfo = socket.getaddrinfo
def _patched_getaddrinfo(host, port, *args, **kwargs):
    resolved = _DNS_OVERRIDES.get(host, host)
    return _orig_getaddrinfo(resolved, port, *args, **kwargs)
socket.getaddrinfo = _patched_getaddrinfo
# ─────────────────────────────────────────────────────────────────────────────

# ── OCR ────────────────────────────────────────────────────────────────────
try:
    from pdf2image import convert_from_bytes
    import pytesseract
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

# ── OpenAI ─────────────────────────────────────────────────────────────────
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

# ── Google Drive ───────────────────────────────────────────────────────────
try:
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseUpload
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    GDRIVE_AVAILABLE = True
except ImportError:
    GDRIVE_AVAILABLE = False

# ══════════════════════════════════════════════════════════════════════════════
# Page config
# ══════════════════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="Booklet Merger · Drive · WooCommerce",
    page_icon="📚", layout="wide"
)
st.title("📚 Booklet Merger · ☁️ Drive · 🛒 WooCommerce")
st.markdown("""
**Full workflow in one app:**
1. Upload PDFs → language auto-detected → merge into 10 × 65-page booklets
2. Upload all to Google Drive → get public shareable links
3. GPT writes product description → create WooCommerce draft product
   - **Simple product** (all languages, one price) for standard documents
   - **Variable product** (one variation per language, own price) for Komplettpaket
""")

caps = []
caps.append(f"{'✅' if OPENAI_AVAILABLE  else '❌'} GPT-4o-mini")
caps.append(f"{'✅' if OCR_AVAILABLE     else '❌'} OCR")
caps.append(f"{'✅' if GDRIVE_AVAILABLE  else '❌'} Google Drive")
st.caption("Engines: " + "  |  ".join(caps))

# ══════════════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════════════
LANGUAGES = [
    "Deutsch", "Englisch", "Türkisch", "Polnisch", "Russisch",
    "Italienisch", "Spanisch", "Französisch", "Ungarisch", "Rumänisch"
]
LANGUAGES_WITH_UNKNOWN = ["⚠️ Unknown — select manually"] + LANGUAGES

FLAGS = {
    "Deutsch": "🇩🇪", "Englisch": "🇬🇧", "Türkisch": "🇹🇷", "Polnisch": "🇵🇱",
    "Russisch": "🇷🇺", "Italienisch": "🇮🇹", "Spanisch": "🇪🇸",
    "Französisch": "🇫🇷", "Ungarisch": "🇭🇺", "Rumänisch": "🇷🇴"
}
CODES = {
    "Deutsch": "DE", "Englisch": "EN", "Türkisch": "TR", "Polnisch": "PL",
    "Russisch": "RU", "Italienisch": "IT", "Spanisch": "ES",
    "Französisch": "FR", "Ungarisch": "HU", "Rumänisch": "RO"
}
CODES_INV = {v: k for k, v in CODES.items()}

# Language name in its own language (for variation labels)
LANG_NATIVE = {
    "Deutsch":     "Deutsch",
    "Englisch":    "English",
    "Türkisch":    "Türkçe",
    "Polnisch":    "Polski",
    "Russisch":    "Русский",
    "Italienisch": "Italiano",
    "Spanisch":    "Español",
    "Französisch": "Français",
    "Ungarisch":   "Magyar",
    "Rumänisch":   "Română",
}

TESS_LANGS     = "deu+eng+tur+pol+rus+ita+spa+fra+hun+ron"
MIN_TEXT_CHARS = 300

GDRIVE_SCOPES           = ["https://www.googleapis.com/auth/drive"]
GDRIVE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
GDRIVE_TOKEN_FILE       = os.getenv("GOOGLE_TOKEN_FILE",        "token.json")
GDRIVE_PARENT_FOLDER_ID = os.getenv("GOOGLE_DRIVE_PARENT_FOLDER_ID", "root")

env_api_key     = os.getenv("OPENAI_API_KEY", "").strip()
env_etsy_key    = os.getenv("ETSY_API_KEY", "").strip()
env_etsy_token  = os.getenv("ETSY_ACCESS_TOKEN", "").strip()
env_etsy_shop   = os.getenv("ETSY_SHOP_ID", "").strip()

# ══════════════════════════════════════════════════════════════════════════════
# URL Sanitizer
# ══════════════════════════════════════════════════════════════════════════════

def _clean_url(url: str) -> str:
    if not url:
        return url
    url = url.strip()
    md_match = re.match(r'\[.*?\]\((https?://[^\)]+)\)', url)
    if md_match:
        url = md_match.group(1)
    url = re.sub(r'[\[\]\(\)]', '', url)
    url = re.sub(r'[\u200b\u200c\u200d\ufeff\u00ad]', '', url)
    return url.strip()


# ══════════════════════════════════════════════════════════════════════════════
# Sidebar
# ══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.header("🔑 OpenAI API Key")
    if env_api_key:
        st.success("✅ Loaded from `.env`")
        api_key_input = env_api_key
    else:
        st.warning("No OPENAI_API_KEY in `.env`")
        api_key_input = st.text_input(
            "Paste OpenAI key", type="password", placeholder="sk-..."
        )

    st.markdown("---")
    st.subheader("☁️ Google Drive")
    drive_creds_file  = st.text_input("credentials.json path", value=GDRIVE_CREDENTIALS_FILE)
    drive_parent_id   = st.text_input("Parent folder ID",       value=GDRIVE_PARENT_FOLDER_ID)
    drive_folder_name = st.text_input(
        "New folder name",
        value=f"Booklets_{datetime.now().strftime('%Y-%m-%d')}"
    )

    st.markdown("---")
    st.subheader("🛒 WooCommerce")

    _raw_wp_url = os.getenv("WP_URL", "https://beautymediashop.de")
    wc_site_url = st.text_input(
        "Site URL", value=_clean_url(_raw_wp_url)
    )
    wc_site_url = _clean_url(wc_site_url).rstrip("/").strip()
    st.caption(f"URL in use: `{repr(wc_site_url)}`")

    # DNS override UI
    with st.expander("🔧 DNS Override (if host can\'t be resolved)"):
        st.caption(
            "If Python\'s requests can\'t resolve your domain, enter its IP here. "
            "Find it with: `nslookup beautymediashop.de 8.8.8.8`"
        )
        override_host = st.text_input("Hostname", value="beautymediashop.de", key="dns_host")
        override_ip   = st.text_input("IP address", value="85.13.153.187",   key="dns_ip")
        if override_host.strip() and override_ip.strip():
            _DNS_OVERRIDES[override_host.strip()] = override_ip.strip()
            st.caption(f"✅ `{override_host.strip()}` → `{override_ip.strip()}`")

    wc_ck = st.text_input(
        "Consumer Key", type="password",
        value=os.getenv("WC_CONSUMER_KEY", ""), placeholder="ck_..."
    )
    wc_cs = st.text_input(
        "Consumer Secret", type="password",
        value=os.getenv("WC_CONSUMER_SECRET", ""), placeholder="cs_..."
    )

    st.markdown("---")
    st.subheader("🔐 WordPress Auth (for Yoast SEO)")
    st.caption("Required to set Fokus-Keyphrase, SEO-Titel, Meta-Beschreibung via Yoast REST API.")
    wp_username = st.text_input(
        "WP Username", value=os.getenv("WP_USERNAME", ""), placeholder="admin"
    )
    wp_app_password = st.text_input(
        "WP App Password", type="password",
        value=os.getenv("WP_APP_PASSWORD", ""),
        placeholder="xxxx xxxx xxxx xxxx xxxx xxxx"
    )

    wc_status = st.selectbox(
        "Product status", ["draft", "publish", "pending"], index=0
    )

    st.markdown("---")
    st.subheader("🛍️ Etsy")
    st.caption("Etsy API v3 — create digital download listings.")
    etsy_api_key = st.text_input(
        "Etsy API Key (Keystring)", type="password",
        value=env_etsy_key, placeholder="your-etsy-api-key"
    )
    etsy_access_token = st.text_input(
        "Etsy Access Token (OAuth)", type="password",
        value=env_etsy_token, placeholder="your-oauth-access-token"
    )
    etsy_shop_id = st.text_input(
        "Etsy Shop ID", value=env_etsy_shop, placeholder="12345678"
    )
    st.caption(
        "Get OAuth token: Etsy Developer Portal → Your App → Generate OAuth Token\n\n"
        "Add to .env:\n"
        "```\nETSY_API_KEY=your-keystring\n"
        "ETSY_ACCESS_TOKEN=your-oauth-token\n"
        "ETSY_SHOP_ID=your-shop-id\n```"
    )

    st.markdown("---")
    st.caption(
        "`.env` keys:\n"
        "```\nOPENAI_API_KEY=sk-...\n"
        "GOOGLE_CREDENTIALS_FILE=credentials.json\n"
        "GOOGLE_TOKEN_FILE=token.json\n"
        "GOOGLE_DRIVE_PARENT_FOLDER_ID=...\n"
        "WP_URL=https://beautymediashop.de\n"
        "WC_CONSUMER_KEY=ck_...\n"
        "WC_CONSUMER_SECRET=cs_...\n"
        "WP_USERNAME=admin\n"
        "WP_APP_PASSWORD=xxxx xxxx xxxx xxxx\n```"
    )

API_KEY = api_key_input.strip() if api_key_input else ""


# ══════════════════════════════════════════════════════════════════════════════
# Helper — PDF
# ══════════════════════════════════════════════════════════════════════════════

def read_file_bytes(file_obj):
    file_obj.seek(0)
    data = file_obj.read()
    file_obj.seek(0)
    return data

def get_page_count(file_obj):
    return len(PdfReader(io.BytesIO(read_file_bytes(file_obj))).pages)

def extract_text_pypdf(file_obj, page_indices):
    reader = PdfReader(io.BytesIO(read_file_bytes(file_obj)))
    text = ""
    for i in page_indices:
        if i < len(reader.pages):
            try: text += (reader.pages[i].extract_text() or "")
            except: pass
    return text

def extract_text_from_page_objects(page_objects):
    targets = page_objects[9:12] if len(page_objects) >= 12 else page_objects[-3:]
    text = ""
    for page in targets:
        try: text += (page.extract_text() or "")
        except: pass
    return text

def ocr_from_pdf_bytes(pdf_bytes, dpi=150):
    if not OCR_AVAILABLE: return ""
    try:
        imgs = convert_from_bytes(pdf_bytes, dpi=dpi, first_page=10, last_page=12)
        return "".join(
            pytesseract.image_to_string(img, lang=TESS_LANGS, config="--oem 1 --psm 3")
            for img in imgs
        )
    except: return ""

def ocr_from_page_objects(page_objects, dpi=150):
    if not OCR_AVAILABLE: return ""
    try:
        writer = PdfWriter()
        for p in (page_objects[9:12] if len(page_objects) >= 12 else page_objects[-3:]):
            writer.add_page(p)
        buf = io.BytesIO()
        writer.write(buf)
        return ocr_from_pdf_bytes(buf.getvalue(), dpi=dpi)
    except: return ""


# ══════════════════════════════════════════════════════════════════════════════
# Helper — Language detection
# ══════════════════════════════════════════════════════════════════════════════

ALIAS_MAP = {
    "deutsch":"Deutsch","german":"Deutsch","de":"Deutsch",
    "englisch":"Englisch","english":"Englisch","en":"Englisch",
    "türkisch":"Türkisch","turkisch":"Türkisch","turkish":"Türkisch",
    "türkçe":"Türkisch","turkce":"Türkisch","tr":"Türkisch",
    "polnisch":"Polnisch","polish":"Polnisch","polski":"Polnisch","pl":"Polnisch",
    "russisch":"Russisch","russian":"Russisch","русский":"Russisch","ru":"Russisch",
    "italienisch":"Italienisch","italian":"Italienisch","italiano":"Italienisch","it":"Italienisch",
    "spanisch":"Spanisch","spanish":"Spanisch","español":"Spanisch","espanol":"Spanisch","es":"Spanisch",
    "französisch":"Französisch","franzosisch":"Französisch","french":"Französisch",
    "français":"Französisch","francais":"Französisch","fr":"Französisch",
    "ungarisch":"Ungarisch","hungarian":"Ungarisch","magyar":"Ungarisch","hu":"Ungarisch",
    "rumänisch":"Rumänisch","rumanisch":"Rumänisch","romanian":"Rumänisch",
    "română":"Rumänisch","romana":"Rumänisch","ro":"Rumänisch",
}

def gpt_detect_language(text, api_key):
    if not OPENAI_AVAILABLE: return None, "openai not installed"
    if not api_key:          return None, "no API key"
    try:
        client = OpenAI(api_key=api_key)
        sample = text[:1000].strip()
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role":"system","content":"Language detection tool. Reply with only the language name from the list. No other text."},
                {"role":"user","content":(
                    "Identify the language. Reply with ONLY one from:\n"
                    "Deutsch\nEnglisch\nTürkisch\nPolnisch\nRussisch\n"
                    "Italienisch\nSpanisch\nFranzösisch\nUngarisch\nRumänisch\n\n"
                    f"Text:\n{sample}"
                )}
            ],
            max_tokens=15, temperature=0,
        )
        result = response.choices[0].message.content.strip()
        if result in LANGUAGES: return result, None
        norm = result.lower().strip().strip(".'\"")
        mapped = ALIAS_MAP.get(norm)
        if mapped: return mapped, None
        for alias, lang in ALIAS_MAP.items():
            if norm.startswith(alias) or alias.startswith(norm):
                return lang, None
        return None, f"GPT returned: '{result}'"
    except Exception as e:
        return None, str(e)

def detect_language_full(raw_text, pdf_bytes=None, page_objects=None):
    def call_gpt(text, label):
        lang, err = gpt_detect_language(text, API_KEY)
        if lang: return lang, label, 5, None
        return "Unknown", label + " (GPT failed)", 0, err

    if len(raw_text.strip()) >= MIN_TEXT_CHARS:
        return call_gpt(raw_text, "gpt-4o-mini")

    ocr = ""
    if pdf_bytes:      ocr = ocr_from_pdf_bytes(pdf_bytes)
    elif page_objects: ocr = ocr_from_page_objects(page_objects)

    if len(ocr.strip()) >= MIN_TEXT_CHARS:
        return call_gpt(ocr, "ocr+gpt-4o-mini")

    combined = (raw_text + " " + ocr).strip()
    if combined and API_KEY:
        return call_gpt(combined, "ocr+gpt-4o-mini (low text)")

    msg = "No API key" if not API_KEY else "Could not extract text"
    return "Unknown", "no-text", 0, msg

def confidence_label(score, method):
    icons = {
        "gpt-4o-mini":                  "🤖 GPT-4o-mini",
        "ocr+gpt-4o-mini":              "🔬🤖 OCR+GPT",
        "ocr+gpt-4o-mini (low text)":   "🔬🤖 OCR+GPT (low text)",
        "gpt-4o-mini (GPT failed)":     "⚠️ GPT failed",
        "ocr+gpt-4o-mini (GPT failed)": "⚠️ OCR+GPT failed",
        "no-text":                      "⚠️ no text",
    }
    label = icons.get(method, f"🤖 {method}")
    if "failed" in method or method == "no-text": return f"🔴 Fix manually ({label})"
    if "low text" in method: return f"🟡 Low text — verify ({label})"
    return f"🟢 High ({label})"


# ══════════════════════════════════════════════════════════════════════════════
# Helper — Google Drive
# ══════════════════════════════════════════════════════════════════════════════

def get_drive_service(creds_file, token_file):
    creds = None
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, GDRIVE_SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(creds_file):
                raise FileNotFoundError(
                    f"credentials.json not found at '{creds_file}'.\n"
                    "Download from Google Cloud Console → APIs & Services → Credentials."
                )
            flow  = InstalledAppFlow.from_client_secrets_file(creds_file, GDRIVE_SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_file, "w") as f:
            f.write(creds.to_json())
    return build("drive", "v3", credentials=creds)

def create_drive_folder(service, name, parent):
    meta   = {"name": name, "mimeType": "application/vnd.google-apps.folder", "parents": [parent]}
    folder = service.files().create(body=meta, fields="id,name,webViewLink").execute()
    return folder["id"], folder["webViewLink"]

def set_public(service, file_id):
    service.permissions().create(
        fileId=file_id, body={"type":"anyone","role":"reader"}
    ).execute()

def upload_pdf_to_drive(service, pdf_bytes, filename, folder_id):
    media = MediaIoBaseUpload(io.BytesIO(pdf_bytes), mimetype="application/pdf", resumable=True)
    meta  = {"name": filename, "parents": [folder_id]}
    return service.files().create(body=meta, media_body=media, fields="id,name,size,webViewLink").execute()

def drive_view_link(fid):     return f"https://drive.google.com/file/d/{fid}/view?usp=sharing"
def drive_download_link(fid): return f"https://drive.google.com/uc?export=download&id={fid}"


# ══════════════════════════════════════════════════════════════════════════════
# Helper — WooCommerce REST
# ══════════════════════════════════════════════════════════════════════════════

def wc_get(endpoint, ck, cs, site):
    site = _clean_url(site)
    url  = f"{site.rstrip('/')}/wp-json/wc/v3/{endpoint.lstrip('/')}"
    r    = _requests.get(url, auth=(ck, cs), timeout=15)
    r.raise_for_status()
    return r.json()

def wc_post(endpoint, ck, cs, site, payload):
    site = _clean_url(site)
    url  = f"{site.rstrip('/')}/wp-json/wc/v3/{endpoint.lstrip('/')}"
    r    = _requests.post(url, auth=(ck, cs), json=payload, timeout=30)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"WC {r.status_code}: {r.text[:500]}")
    return r.json()

def wc_test(site, ck, cs):
    try:
        d   = wc_get("system_status", ck, cs, site)
        env = d.get("environment", {})
        return True, f"WooCommerce {env.get('version','?')} on {env.get('site_url','?')}"
    except Exception as e:
        return False, str(e)

def wc_get_categories(site, ck, cs):
    cats, page = [], 1
    while True:
        batch = wc_get(f"products/categories?per_page=100&page={page}", ck, cs, site)
        if not batch: break
        cats.extend(batch)
        if len(batch) < 100: break
        page += 1
    return cats


# ══════════════════════════════════════════════════════════════════════════════
# Helper — Yoast SEO via WordPress REST API
# Uses WP Application Password authentication
# ══════════════════════════════════════════════════════════════════════════════

def set_yoast_seo(site, wp_username, wp_app_password, post_id,
                  focus_keyphrase, seo_title, meta_description):
    """
    Sets Yoast SEO fields on a post/product via the WordPress REST API.
    Requires Application Password (Settings → Users → Application Passwords).
    Returns (success: bool, message: str)
    """
    if not wp_username or not wp_app_password:
        return False, "No WP credentials provided"

    site = _clean_url(site).rstrip("/")
    url  = f"{site}/wp-json/wp/v2/product/{post_id}"

    payload = {
        "meta": {
            "_yoast_wpseo_focuskw":        focus_keyphrase,
            "_yoast_wpseo_title":          seo_title,
            "_yoast_wpseo_metadesc":       meta_description,
        }
    }

    try:
        r = _requests.post(
            url,
            auth=(wp_username, wp_app_password),
            json=payload,
            timeout=20,
        )
        if r.status_code in (200, 201):
            return True, "✅ Yoast SEO fields updated successfully"
        else:
            # Try PATCH if POST doesn't work
            r2 = _requests.patch(
                url,
                auth=(wp_username, wp_app_password),
                json=payload,
                timeout=20,
            )
            if r2.status_code in (200, 201):
                return True, "✅ Yoast SEO fields updated (PATCH)"
            return False, f"HTTP {r2.status_code}: {r2.text[:300]}"
    except Exception as e:
        return False, str(e)


# ══════════════════════════════════════════════════════════════════════════════
# Helper — GPT product content generation
# ══════════════════════════════════════════════════════════════════════════════

def gpt_generate_product_content(product_name, language_list, num_pages, file_type,
                                  product_format, canva_link, api_key,
                                  related_products=None, is_variable=False,
                                  product_type_hint=""):
    if not OPENAI_AVAILABLE or not api_key:
        return None, "OpenAI not available or no API key"

    client    = OpenAI(api_key=api_key)
    langs_str = ", ".join(language_list)
    num_langs = len(language_list)

    # Pre-compute for f-string safety
    _short_desc_langs = "Mehrsprachig* (Sprache wählbar)" if is_variable else langs_str
    _short_desc_note  = "<p>* <em>Bitte wählen Sie Ihre gewünschte Sprache aus dem Dropdown-Menü.</em></p>" if is_variable else ""
    _var_note         = f"Der Kunde wählt beim Kauf eine Sprache aus: {langs_str}" if is_variable else ""

    # Hard-coded recommendation links (always correct)
    if related_products:
        rec_html = "".join(
            f'– <a href="{r["url"]}">{r["name"]}:</a> {r["desc"]}<br>'
            for r in related_products
        )
    else:
        rec_html = (
            '– <a href="https://beautymediashop.de/produkt/einverstaendnis-fuer-die-behandlung/">Einverständniserklärung:</a> ' 
            'Bietet Ihnen rechtliche Sicherheit und informiert Ihre Kundinnen umfassend.<br>' 
            '– <a href="https://beautymediashop.de/produkt/pflegehinweis-fuer-die-behandlung/">Pflegehinweise:</a> ' 
            'Vermitteln klare Anweisungen für die richtige Nachsorge.<br>' 
            '– <a href="https://beautymediashop.de/produkt/vorabinformationen-behandlung/">Vorabinformation:</a> ' 
            'Schaffen Sie Vertrauen vor der Behandlung.<br>'
        )

    # ── CALL 1: description_html only ────────────────────────────────────
    # Fixed HTML sections built 100% in Python — GPT never touches these links
    _section_recommendations = (
        f"<br><br><strong>Unsere Empfehlung für Sie</strong><br>"
        f"{rec_html}"
    )
    _section_devices = (
        "<br><br><strong>Maximale Flexibilität auf allen Geräten</strong><br>"
        "Kompatibel mit Windows, MacOS, Android und iOS – digital nutzbar oder ausdruckbar."
    )
    _section_contact = (
        "<br><br><strong>Noch Fragen? Kontaktieren Sie uns!</strong><br>"
        "Schauen Sie in unsere <a href=\"https://beautymediashop.de/faq/\">FAQ</a> "
        "oder schreiben Sie uns über das <a href=\"https://beautymediashop.de/faq/#kontakt\">Kontaktformular</a>. "
        "Per WhatsApp erreichbar.<br><br>"
        "Jetzt herunterladen und professionell durchstarten. "
        "Weitere Vorlagen in unserem <a href=\"https://beautymediashop.de/shop/\">Onlineshop</a>."
    )

    desc_prompt = f"""Schreibe NUR den HTML-Text für 3 Abschnitte eines Produkttextes.
Kein JSON, kein Markdown — nur HTML direkt. Sprache: Deutsch. Umlaute: ä ö ü Ä Ö Ü ß

PRODUKT: {product_name}
Seiten: {num_pages} | Sprachen ({num_langs}): {langs_str}
{'VARIANTES PRODUKT: Kunde wählt Sprache beim Kauf' if is_variable else 'Einfaches Produkt: alle Sprachen enthalten'}

Schreibe GENAU diese 3 Abschnitte:

ABSCHNITT A — Einleitung:
<strong>{product_name} – jetzt downloaden und direkt anwenden!</strong> [Schreibe hier 2 konkrete Sätze über das Produkt]

ABSCHNITT B — Vorteile (direkt danach, mit <br><br> davor):
<br><br><strong>Ihre Vorteile auf einen Blick</strong><br>– [Vorteil 1 konkret zu diesem Produkt]<br>– [Vorteil 2 konkret]<br>– [Vorteil 3 konkret]<br>– [Vorteil 4 konkret]<br>

ABSCHNITT C — Zielgruppe (direkt danach, mit <br><br> davor):
<br><br><strong>Für wen ist dieses Produkt geeignet?</strong><br>[Schreibe 2 konkrete Sätze zur Zielgruppe]

ABSCHNITT D — Zitate (direkt danach, mit <br><br> davor):
<br><br><strong>Erfahrungen unserer Anwenderinnen</strong><br>„[Zitat 1 vollständig mit Punkt am Ende.]" – [Vorname Nachname], [Beruf]<br>„[Zitat 2 vollständig.]" – [Vorname Nachname], [Beruf]<br>„[Zitat 3 vollständig.]" – [Vorname Nachname], [Beruf]<br>„[Zitat 4 vollständig.]" – [Vorname Nachname], [Beruf]<br>

PFLICHT: Alle 4 Zitate vollständig — niemals abschneiden!"""

    # ── CALL 2: SEO + short_description only ─────────────────────────────
    seo_prompt = f"""Schreibe NUR valides JSON mit diesen 3 Feldern für ein WooCommerce-Produkt.
Kein Markdown, keine Backticks, nur JSON.
Sprache: Deutsch. Umlaute direkt: ä ö ü Ä Ö Ü ß

PRODUKT: {product_name}
Sprachen: {langs_str}
Seiten: {num_pages}
Dateityp: {file_type}

short_description EXAKT so (eine Zeile, nichts ändern):
<strong>Produktdetails:</strong><ul><li>Dateityp: {file_type}</li><li>Format: {product_format}</li><li>Seitenanzahl: {num_pages} Seiten</li><li>Sprachen: {_short_desc_langs}</li></ul>{_short_desc_note}

{{
  "seo_title": "[Produktname max 60 Zeichen]",
  "focus_keyphrase": "[4-6 deutsche Suchwörter]",
  "meta_description": "Mehr Sicherheit, mehr Professionalität: [Rest max 155 Zeichen total]",
  "short_description": "[exakt wie oben]"
}}"""

    try:
        # Call 1 — description
        r1 = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Du schreibst HTML-Produkttexte auf Deutsch für beautymediashop.de. Antworte nur mit dem HTML-Text. Schreibe NUR die Abschnitte A, B, C und D. Schreibe KEINE Empfehlungen, KEINE Geräte-Abschnitte, KEINE Kontakt-Abschnitte, KEINE Links."},
                {"role": "user",   "content": desc_prompt}
            ],
            max_tokens=2500,
            temperature=0.5,
        )
        gpt_parts = r1.choices[0].message.content.strip()
        # Strip any accidental markdown fences
        if gpt_parts.startswith("```"):
            gpt_parts = gpt_parts.split("```")[1]
            if gpt_parts.startswith("html"): gpt_parts = gpt_parts[4:]
        gpt_parts = gpt_parts.strip()

        # Strip ANY sections GPT wrote that contain links — Python injects correct versions
        for _marker in ["<strong>Unsere Empfehlung", "<strong>Maximale Flexibilität", "<strong>Noch Fragen"]:
            if _marker in gpt_parts:
                gpt_parts = gpt_parts[:gpt_parts.find(_marker)]

        # Final assembly — GPT: intro+benefits+target+quotes | Python: all 3 link sections
        desc_html = (
            gpt_parts.rstrip().rstrip("<br>").rstrip()
            + _section_recommendations
            + _section_devices
            + _section_contact
        )

        # Call 2 — SEO + short desc
        r2 = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Du schreibst WooCommerce SEO-Felder auf Deutsch. Antworte nur mit validem JSON, nichts sonst."},
                {"role": "user",   "content": seo_prompt}
            ],
            max_tokens=600,
            temperature=0.3,
        )
        raw2 = r2.choices[0].message.content.strip()
        if raw2.startswith("```"):
            raw2 = raw2.split("```")[1]
            if raw2.startswith("json"): raw2 = raw2[4:]
        raw2 = raw2.strip()
        seo_data = json.loads(raw2)

        return {
            "seo_title":         seo_data.get("seo_title", product_name[:60]),
            "focus_keyphrase":   seo_data.get("focus_keyphrase", ""),
            "meta_description":  seo_data.get("meta_description", ""),
            "short_description": seo_data.get("short_description", ""),
            "description_html":  desc_html,
            "_desc_locked":      desc_html,  # never overwritten by text_area
        }, None

    except json.JSONDecodeError as e:
        return None, f"JSON parse error in SEO call: {e}\nRaw: {raw2[:300]}"
    except Exception as e:
        return None, str(e)


def fallback_description_html(product_name, drive_result, num_pages=65,
                               language_list=None, is_variable=False):
    if language_list is None:
        language_list = LANGUAGES
    langs_str = ", ".join(language_list)
    files = [r for r in drive_result.get("files", []) if "error" not in r]

    if is_variable:
        lang_section = (
            "<strong>Verfügbare Sprachen</strong>\n"
            f"Dieses Paket ist in {len(language_list)} Sprachen erhältlich: {langs_str}. "
            "Wählen Sie einfach Ihre gewünschte Sprache aus dem Dropdown-Menü."
        )
    else:
        rows = "".join(
            f'<li>{r["flag"]} {r["language"]}: '
            f'<a href="{r["download_link"]}">PDF herunterladen</a></li>'
            for r in files
        )
        lang_section = f"<strong>Verfügbare Sprachen</strong>\n<ul>\n{rows}\n</ul>"

    return f"""<strong>{product_name} – jetzt downloaden und direkt anwenden!</strong>
Das {product_name} bietet Ihnen professionelle Unterstützung für Ihren Arbeitsalltag als Beauty-Fachfrau.

<strong>Ihre Vorteile auf einen Blick</strong>
– Flexibel anpassbar: Stimmen Sie das Design und die Inhalte exakt auf Ihr Studio-Branding ab.
– Sofort einsetzbar: Downloaden und ohne Wartezeit direkt in Ihrer Praxis nutzen.
– Digital &amp; nachhaltig: Umweltfreundlich und papierlos arbeiten – am PC oder mobil.
– Immer aktuell: Dank Live-Link in Canva sind Ihre Vorlagen automatisch auf dem neuesten Stand.

{lang_section}

<strong>Unsere Empfehlung für Sie</strong>
– <a href="https://beautymediashop.de/produkt/einverstaendnis-fuer-die-behandlung/">Einverständniserklärung</a>
– <a href="https://beautymediashop.de/produkt/pflegehinweis-fuer-die-behandlung/">Pflegehinweise</a>
– <a href="https://beautymediashop.de/produkt/vorabinformationen-behandlung/">Vorabinformation</a>

<strong>Noch Fragen? Kontaktieren Sie uns!</strong>
Schauen Sie in unsere <a href="https://beautymediashop.de/faq/">FAQ</a> oder schreiben Sie uns über das <a href="https://beautymediashop.de/faq/#kontakt">Kontaktformular</a>.

Jetzt herunterladen und professionell durchstarten. Weitere Vorlagen im <a href="https://beautymediashop.de/shop/">Onlineshop</a>."""


def fallback_short_description(num_pages, language_list=None, is_variable=False,
                                 extra_docs=None):
    """
    Matches the microneedling product short description style.
    extra_docs: list of dicts {"label": "Schulung", "pages": 53, "langs": "Deutsch, Türkisch"}
    """
    if language_list is None:
        language_list = LANGUAGES

    if extra_docs:
        items = "".join(f"<li>{d['label']} | {d['pages']} Seiten | {d['langs']}</li>"
                        for d in extra_docs)
        lang_note = ""
    elif is_variable:
        items = (
            f"<li>Seitenanzahl: {num_pages} Seiten</li>\n"
            "<li>Sprache: Mehrsprachig* (Sprache wählbar)</li>"
        )
        lang_note = "<p>* <em>Bitte wählen Sie Ihre gewünschte Sprache aus dem Dropdown-Menü.</em></p>"
    else:
        langs_str = ", ".join(language_list)
        items = (
            f"<li>Seitenanzahl: {num_pages} Seiten</li>\n"
            f"<li>Sprachen: {langs_str}</li>"
        )
        lang_note = ""

    return (
        f"<strong>Produktdetails:</strong>\n"
        f"<ul>\n"
        f"<li>Dateityp: Canva Link &amp; PDF Dateien</li>\n"
        f"<li>Format: A4</li>\n"
        f"{items}\n"
        f"</ul>\n"
        f"{lang_note}"
    )


# ══════════════════════════════════════════════════════════════════════════════
# Helper — Etsy API v3
# ══════════════════════════════════════════════════════════════════════════════

def etsy_get(endpoint, api_key, access_token):
    """GET request to Etsy API v3."""
    url = f"https://openapi.etsy.com/v3/application/{endpoint.lstrip('/')}"
    headers = {
        "x-api-key":     api_key,
        "Authorization": f"Bearer {access_token}",
    }
    r = _requests.get(url, headers=headers, timeout=15)
    r.raise_for_status()
    return r.json()

def etsy_post(endpoint, api_key, access_token, payload):
    """POST request to Etsy API v3."""
    url = f"https://openapi.etsy.com/v3/application/{endpoint.lstrip('/')}"
    headers = {
        "x-api-key":     api_key,
        "Authorization": f"Bearer {access_token}",
        "Content-Type":  "application/json",
    }
    r = _requests.post(url, headers=headers, json=payload, timeout=30)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"Etsy {r.status_code}: {r.text[:500]}")
    return r.json()

def etsy_test(api_key, access_token, shop_id):
    """Test Etsy connection by fetching shop info."""
    try:
        data = etsy_get(f"shops/{shop_id}", api_key, access_token)
        return True, f"✅ Connected to shop: {data.get('shop_name', shop_id)}"
    except Exception as e:
        return False, str(e)

def etsy_get_shipping_profiles(api_key, access_token, shop_id):
    """Get shipping profiles for the shop."""
    try:
        data = etsy_get(f"shops/{shop_id}/shipping-profiles", api_key, access_token)
        return data.get("results", [])
    except Exception:
        return []

def etsy_get_taxonomy_id():
    """Return default taxonomy node ID for digital downloads (Art & Collectibles → Prints)."""
    return 2078  # Digital Prints taxonomy node

def gpt_generate_etsy_content(product_name, language_list, num_pages,
                               file_type, product_format, api_key,
                               related_products=None, is_variable=False):
    """
    Generate Etsy-optimised listing content via two GPT calls:
    Call 1 — description (plain text, no HTML — Etsy strips HTML)
    Call 2 — title, tags (13), materials, JSON
    """
    if not OPENAI_AVAILABLE or not api_key:
        return None, "OpenAI not available or no API key"

    client    = OpenAI(api_key=api_key)
    langs_str = ", ".join(language_list)
    num_langs = len(language_list)

    # ── Call 1: Etsy description (plain text, NO HTML) ────────────────────
    desc_prompt = f"""Du schreibst einen Etsy-Produkttext auf ENGLISCH für einen digitalen Download.
Etsy unterstützt KEIN HTML — schreibe reinen Text mit Zeilenumbrüchen.
Verwende Großbuchstaben für Abschnittsüberschriften (wie auf Etsy üblich).

PRODUKT: {product_name}
Seiten: {num_pages} | Sprachen ({num_langs}): {langs_str}
Dateityp: {file_type} | Format: {product_format}
{'VARIABLE PRODUCT: Customer chooses language at checkout' if is_variable else 'ALL LANGUAGES INCLUDED in one purchase'}

Schreibe GENAU diese Abschnitte:

★ INSTANT DIGITAL DOWNLOAD ★
[2 sentences about what this product is and its benefits]

WHAT'S INCLUDED:
• {num_pages} pages of professional documentation
• Available in {num_langs} languages: {langs_str}
• Format: {product_format}
• File type: {file_type}

YOUR BENEFITS:
• [Benefit 1 specific to this product]
• [Benefit 2]
• [Benefit 3]
• [Benefit 4]
• Compatible with Windows, MacOS, Android and iOS

HOW IT WORKS:
1. Purchase and download instantly
2. Open with Canva (free account required) or as PDF
3. Customize with your studio branding
4. Print or use digitally

PERFECT FOR:
[2 sentences describing the ideal customer]

★ CUSTOMER REVIEWS ★
"[Complete review 1]" - [Name], [Profession]
"[Complete review 2]" - [Name], [Profession]
"[Complete review 3]" - [Name], [Profession]

QUESTIONS?
Visit our FAQ or contact us via our shop message system.

IMPORTANT: Write all 4 reviews completely — never cut off mid-sentence!"""

    # ── Call 2: Title + Tags + Price suggestion ───────────────────────────
    meta_prompt = f"""Write Etsy listing metadata for a digital download product. Reply ONLY with valid JSON.

PRODUCT: {product_name}
Languages: {langs_str}
Pages: {num_pages}
Type: {'Variable — customer picks language' if is_variable else 'Simple — all languages included'}

Rules:
- title: max 140 chars, start with main keyword, include "Digital Download", no ALL CAPS
- tags: exactly 13 tags, each max 20 chars, mix of specific and broad, relevant to beauty/wellness professionals
- price_suggestion: suggested EUR price as float (based on {num_pages} pages, {num_langs} languages)
- who_made: "i_did"
- when_made: "made_to_order"
- taxonomy_id: 2078

{{
  "title": "...",
  "tags": ["tag1", "tag2", "tag3", "tag4", "tag5", "tag6", "tag7", "tag8", "tag9", "tag10", "tag11", "tag12", "tag13"],
  "price_suggestion": 0.00,
  "who_made": "i_did",
  "when_made": "made_to_order",
  "taxonomy_id": 2078
}}"""

    try:
        # Call 1 — description
        r1 = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You write Etsy product descriptions in English for beauty/wellness digital downloads. Plain text only, no HTML tags."},
                {"role": "user",   "content": desc_prompt}
            ],
            max_tokens=1500,
            temperature=0.6,
        )
        etsy_desc = r1.choices[0].message.content.strip()

        # Call 2 — metadata
        r2 = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You write Etsy listing metadata. Reply only with valid JSON, nothing else."},
                {"role": "user",   "content": meta_prompt}
            ],
            max_tokens=400,
            temperature=0.3,
        )
        raw2 = r2.choices[0].message.content.strip()
        if raw2.startswith("```"):
            raw2 = raw2.split("```")[1]
            if raw2.startswith("json"): raw2 = raw2[4:]
        meta = json.loads(raw2.strip())

        return {
            "title":           meta.get("title", product_name[:140]),
            "description":     etsy_desc,
            "tags":            meta.get("tags", [])[:13],
            "price_suggestion":meta.get("price_suggestion", 26.80),
            "who_made":        meta.get("who_made", "i_did"),
            "when_made":       meta.get("when_made", "made_to_order"),
            "taxonomy_id":     meta.get("taxonomy_id", 2078),
        }, None

    except json.JSONDecodeError as e:
        return None, f"JSON parse error: {e}\nRaw: {raw2[:200]}"
    except Exception as e:
        return None, str(e)


# ══════════════════════════════════════════════════════════════════════════════
# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — PART 1 (pages 1–44)
# ══════════════════════════════════════════════════════════════════════════════
st.divider()
st.header("📁 Phase 1 — Part 1: Pages 1–44")
st.caption("Upload all 10 PDFs. Language auto-detected via GPT-4o-mini (OCR fallback for image-based).")

p1_files = st.file_uploader(
    "Drop all 10 Part-1 PDFs here",
    type="pdf", accept_multiple_files=True, key="p1_uploader"
)

part1_map = {}
p1_rows   = []

if p1_files:
    if not API_KEY:
        st.warning("⚠️ No API key — GPT disabled. Add OPENAI_API_KEY to .env or paste in sidebar.")

    bar1 = st.progress(0, text="Detecting Part-1 languages…")
    for fi, f in enumerate(p1_files):
        bar1.progress(fi / len(p1_files), text=f"Detecting {fi+1}/{len(p1_files)}: {f.name[:40]}…")
        pdf_bytes = read_file_bytes(f)
        pages     = len(PdfReader(io.BytesIO(pdf_bytes)).pages)
        raw_text  = extract_text_pypdf(f, [9, 10, 11])
        lang, method, score, gpt_err = detect_language_full(raw_text, pdf_bytes=pdf_bytes)
        p1_rows.append({"file":f,"name":f.name,"pages":pages,
                        "auto_lang":lang,"method":method,"score":score,"gpt_err":gpt_err})
    bar1.progress(1.0, text="✅ Part-1 detection complete")

    hdr = st.columns([3,1,3,2])
    hdr[0].markdown("**File**"); hdr[1].markdown("**Pages**")
    hdr[2].markdown("**Detected language** *(change if wrong)*")
    hdr[3].markdown("**Confidence / Method**")

    for row in p1_rows:
        c0,c1,c2,c3 = st.columns([3,1,3,2])
        c0.text(row["name"][:50])
        c1.markdown(f"{'✅' if row['pages']==44 else '⚠️'} {row['pages']}")
        default_idx = LANGUAGES_WITH_UNKNOWN.index(row["auto_lang"]) \
                      if row["auto_lang"] in LANGUAGES_WITH_UNKNOWN else 0
        chosen = c2.selectbox(
            "Detected language", LANGUAGES_WITH_UNKNOWN, index=default_idx,
            key=f"p1_{row['name']}", label_visibility="collapsed"
        )
        conf = confidence_label(row["score"], row["method"])
        if row.get("gpt_err"):
            conf = conf + "  \n`" + str(row["gpt_err"]) + "`"
        c3.markdown(conf)
        row["chosen_lang"] = chosen

    valid_rows   = [r for r in p1_rows if r["chosen_lang"] in LANGUAGES]
    unknown_rows = [r for r in p1_rows if r["chosen_lang"] not in LANGUAGES]
    if unknown_rows:
        st.error(f"⚠️ {len(unknown_rows)} file(s) still Unknown — select a language above.")

    lang_count = {}
    for r in valid_rows:
        lang_count[r["chosen_lang"]] = lang_count.get(r["chosen_lang"],0) + 1
    dups = {l for l,c in lang_count.items() if c>1}
    if dups:
        st.error(f"⚠️ Duplicates: **{', '.join(dups)}** — fix dropdowns above.")
    elif not unknown_rows:
        for r in p1_rows:
            part1_map[r["chosen_lang"]] = r["file"]
        missing = [l for l in LANGUAGES if l not in part1_map]
        if missing: st.warning(f"Missing in Part 1: {', '.join(missing)}")
        else:       st.success("✅ All 10 languages mapped for Part 1!")

    chip_cols = st.columns(10)
    for idx, lang in enumerate(LANGUAGES):
        with chip_cols[idx]:
            st.markdown(f"{FLAGS[lang]} {'✅' if lang in part1_map else '❌'}")
            st.caption(CODES[lang])


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — PART 2 (pages 45–65)
# ══════════════════════════════════════════════════════════════════════════════
st.divider()
st.header("📁 Phase 1 — Part 2: Pages 45–65")
st.markdown(
    "Canva exported 10 languages × 21 pages as **4 PDFs** (63+63+63+21). "
    "Upload all 4 — split into 21-page blocks, language detected via GPT-4o-mini."
)

p2_files = st.file_uploader(
    "Drop all 4 Part-2 PDFs here",
    type="pdf", accept_multiple_files=True, key="p2_uploader"
)

part2_blocks   = {}
p2_assignments = []

if p2_files:
    p2_sorted = sorted(p2_files, key=lambda f: get_page_count(f), reverse=True)
    bad_files = []
    total_est = sum(get_page_count(f)//21 for f in p2_files if get_page_count(f)%21==0)
    processed = 0
    bar2 = st.progress(0, text="Detecting Part-2 languages…")

    for f in p2_sorted:
        pdf_bytes = read_file_bytes(f)
        reader    = PdfReader(io.BytesIO(pdf_bytes))
        total     = len(reader.pages)
        if total % 21 != 0:
            st.error(f"❌ **{f.name}** — {total} pages not divisible by 21.")
            bad_files.append(f.name); continue

        n_blocks   = total // 21
        st.markdown(f"**{f.name}** — {total} pages → {n_blocks} block(s) of 21 pages")
        bcols = st.columns(max(n_blocks,1))

        for b in range(n_blocks):
            start       = b * 21
            block_pages = list(reader.pages[start:start+21])
            raw_text    = extract_text_from_page_objects(block_pages)
            bar2.progress(processed/max(total_est,1), text=f"Detecting block {processed+1}/{total_est}…")
            lang, method, score, gpt_err = detect_language_full(raw_text, page_objects=block_pages)
            processed += 1
            block_key  = f"p2_{f.name}_b{b}"

            with bcols[b]:
                st.markdown(f"**Block {b+1}** (p{start+1}–{start+21})")
                default_idx = LANGUAGES_WITH_UNKNOWN.index(lang) \
                              if lang in LANGUAGES_WITH_UNKNOWN else 0
                chosen = st.selectbox(
                    f"Block {b+1} language", LANGUAGES_WITH_UNKNOWN,
                    index=default_idx, key=block_key, label_visibility="collapsed"
                )
                st.caption(f"{FLAGS.get(lang,'')} Auto: {lang}")
                conf = confidence_label(score, method)
                if gpt_err: conf = conf + "  \n`" + str(gpt_err) + "`"
                st.caption(conf)

            p2_assignments.append({"block_key":block_key,"pages":block_pages,
                "auto_lang":lang,"method":method,"score":score,
                "gpt_err":gpt_err,"chosen_lang":chosen})

    bar2.progress(1.0, text="✅ Part-2 detection complete")

    if not bad_files:
        valid_a   = [a for a in p2_assignments if a["chosen_lang"] in LANGUAGES]
        unknown_a = [a for a in p2_assignments if a["chosen_lang"] not in LANGUAGES]
        if unknown_a:
            st.error(f"⚠️ {len(unknown_a)} block(s) still Unknown — select above.")
        lc2 = {}
        for a in valid_a:
            lc2[a["chosen_lang"]] = lc2.get(a["chosen_lang"],0) + 1
        dup2 = {l for l,c in lc2.items() if c>1}
        if dup2:
            st.error(f"⚠️ Duplicate blocks: **{', '.join(dup2)}** — fix dropdowns.")
        elif not unknown_a:
            for a in p2_assignments:
                part2_blocks[a["chosen_lang"]] = a["pages"]
            missing2 = [l for l in LANGUAGES if l not in part2_blocks]
            if missing2: st.warning(f"Missing from Part 2: {', '.join(missing2)}")
            else:        st.success("✅ All 10 language blocks detected in Part 2!")

        chip_cols2 = st.columns(10)
        for idx, lang in enumerate(LANGUAGES):
            with chip_cols2[idx]:
                st.markdown(f"{FLAGS[lang]} {'✅' if lang in part2_blocks else '❌'}")
                st.caption(CODES[lang])


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — MERGE
# ══════════════════════════════════════════════════════════════════════════════
st.divider()
st.header("🚀 Phase 1 — Merge & Download")

p1_ready = len(part1_map)    == 10
p2_ready = len(part2_blocks) == 10

ca, cb = st.columns(2)
ca.metric("Part 1 ready", f"{len(part1_map)}/10",    "✅" if p1_ready else "⏳")
cb.metric("Part 2 ready", f"{len(part2_blocks)}/10", "✅" if p2_ready else "⏳")

if not p1_ready and not p2_files:
    st.info("Upload Part 1 and Part 2 files above to get started.")
elif not p1_ready:
    st.warning(f"Part 1 still needs: {', '.join([l for l in LANGUAGES if l not in part1_map])}")
elif not p2_ready:
    st.warning(f"Part 2 still needs: {', '.join([l for l in LANGUAGES if l not in part2_blocks])}")

if p1_ready and p2_ready:
    st.success("✅ Both parts fully mapped — ready to merge!")

    if st.button("📄 Merge All 10 Booklets", type="primary", use_container_width=True):
        mbar    = st.progress(0, text="Starting merge…")
        zip_buf = io.BytesIO()
        merge_results = []

        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for idx, lang in enumerate(LANGUAGES):
                mbar.progress(idx/10, text=f"Merging {FLAGS[lang]} {lang} ({idx+1}/10)…")
                writer = PdfWriter()
                f1 = part1_map[lang]; f1.seek(0)
                for page in PdfReader(f1).pages: writer.add_page(page)
                for page in part2_blocks[lang]:  writer.add_page(page)
                total_pages = len(writer.pages)
                pbuf = io.BytesIO(); writer.write(pbuf); pdf_bytes = pbuf.getvalue()
                filename = f"Booklet_{CODES[lang]}_{lang}.pdf"
                zf.writestr(filename, pdf_bytes)
                merge_results.append((lang, total_pages, filename, pdf_bytes))
                mbar.progress((idx+1)/10, text=f"✅ {FLAGS[lang]} {lang} — {total_pages}p")

        mbar.progress(1.0, text="✅ All 10 merged!")
        st.balloons()

        st.markdown("### ✅ Merge complete!")
        sc = st.columns(5)
        for idx, (lang, pages, fname, _) in enumerate(merge_results):
            with sc[idx%5]:
                ok = pages == 65
                st.markdown(f"{FLAGS[lang]} **{CODES[lang]}** — {lang}")
                st.markdown(f"{'✅' if ok else '⚠️'} **{pages}p**")
                if not ok: st.caption(f"Expected 65, got {pages}")

        st.markdown("---")
        zip_buf.seek(0)
        st.download_button("📦 Download All as ZIP", data=zip_buf.getvalue(),
            file_name="Booklets_10_Languages.zip", mime="application/zip",
            use_container_width=True, type="primary")

        st.markdown("**Or individually:**")
        ic = st.columns(5)
        for idx, (lang, pages, filename, pdf_bytes) in enumerate(merge_results):
            with ic[idx%5]:
                st.download_button(
                    label=f"{FLAGS[lang]} {lang} ({pages}p)",
                    data=pdf_bytes, file_name=filename,
                    mime="application/pdf", key=f"dl_{lang}"
                )

        st.session_state["merged_pdfs"] = {CODES[lang]: pdf_bytes for lang,_,_,pdf_bytes in merge_results}
        st.session_state["merge_done"]  = True


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4 — GOOGLE DRIVE UPLOAD
# ══════════════════════════════════════════════════════════════════════════════
st.divider()
st.header("☁️ Phase 2 — Upload to Google Drive")

if not st.session_state.get("merge_done"):
    st.info("Complete Phase 1 (merge) first.")
else:
    if not GDRIVE_AVAILABLE:
        st.error("❌ Google Drive library not installed.\n\n"
                 "`pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib`")
    else:
        creds_exist = os.path.exists(drive_creds_file) or os.path.exists(GDRIVE_TOKEN_FILE)
        if not creds_exist:
            st.warning(
                f"⚠️ `{drive_creds_file}` not found. "
                "Download from Google Cloud Console → APIs & Services → Credentials → OAuth 2.0 → Desktop App."
            )

        st.markdown(f"""
**What will happen:**
1. New folder **`{drive_folder_name}`** created in your Drive
2. All 10 PDFs uploaded and made **public**
3. You get 10 shareable links → used in Phase 3
        """)

        if st.button("☁️ Upload All 10 PDFs to Google Drive", type="primary", use_container_width=True):
            merged_pdfs    = st.session_state["merged_pdfs"]
            dbar           = st.progress(0, text="Connecting…")
            dstatus        = st.empty()
            log_lines      = []
            upload_results = []

            try:
                service = get_drive_service(drive_creds_file, GDRIVE_TOKEN_FILE)
                dstatus.success("✅ Connected to Google Drive")

                dbar.progress(0.05, text=f"Creating folder '{drive_folder_name}'…")
                folder_id, folder_link = create_drive_folder(service, drive_folder_name, drive_parent_id)
                dstatus.success(f"✅ Folder created — [Open in Drive]({folder_link})")

                for i, (code, pdf_bytes) in enumerate(merged_pdfs.items()):
                    lang     = CODES_INV.get(code, code)
                    flag     = FLAGS.get(lang, "")
                    filename = f"Booklet_{code}_{lang}.pdf"
                    dbar.progress((i+1)/10, text=f"Uploading {flag} {lang} ({i+1}/10)…")
                    try:
                        meta    = upload_pdf_to_drive(service, pdf_bytes, filename, folder_id)
                        file_id = meta["id"]
                        set_public(service, file_id)
                        vl   = drive_view_link(file_id)
                        dl   = drive_download_link(file_id)
                        size = round(int(meta.get("size",0))/1_048_576, 2)
                        upload_results.append({"code":code,"language":lang,"flag":flag,
                            "filename":filename,"file_id":file_id,
                            "view_link":vl,"download_link":dl,"size_mb":size})
                        log_lines.append(f"✅ {flag} **{code}** — [{filename}]({vl}) ({size} MB)")
                    except Exception as e:
                        upload_results.append({"code":code,"language":lang,"flag":flag,
                            "filename":filename,"error":str(e)})
                        log_lines.append(f"❌ {flag} **{code}** — {e}")
                    dstatus.markdown("\n\n".join(log_lines))

                dbar.progress(1.0, text="✅ All uploads complete!")
                drive_result = {
                    "folder_name": drive_folder_name, "folder_id": folder_id,
                    "folder_link": folder_link,
                    "uploaded_at": datetime.now().isoformat(),
                    "files": upload_results,
                }
                st.session_state["drive_result"] = drive_result

                ok_count = len([r for r in upload_results if "error" not in r])
                st.success(
                    f"✅ {ok_count}/10 uploaded  |  "
                    f"[📁 Open Drive folder]({folder_link})"
                )

                st.markdown("### 📋 Drive Links")
                for r in upload_results:
                    if "error" in r:
                        st.error(f"{r['flag']} **{r['code']}** — ❌ {r['error']}")
                    else:
                        c1,c2,c3,c4 = st.columns([1,3,2,2])
                        c1.markdown(f"**{r['flag']} {r['code']}**")
                        c2.markdown(f"[{r['filename']}]({r['view_link']})")
                        c3.markdown(f"[🔗 View]({r['view_link']})")
                        c4.markdown(f"[⬇️ Download]({r['download_link']})")

                summary_json = json.dumps(drive_result, indent=2, ensure_ascii=False)
                st.download_button("💾 Download drive_links.json",
                    data=summary_json, file_name="drive_links.json",
                    mime="application/json", use_container_width=True)

            except FileNotFoundError as e: st.error(str(e))
            except Exception as e:
                st.error(f"❌ Drive upload failed: {e}")
                st.exception(e)


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 5 — WOOCOMMERCE PRODUCT
# ══════════════════════════════════════════════════════════════════════════════
st.divider()
st.header("🛒 Phase 3 — Create WooCommerce Product")

drive_result_wc = st.session_state.get("drive_result")

if not drive_result_wc:
    with st.expander("📂 Load drive_links.json (if app was restarted)"):
        uploaded_json = st.file_uploader("Upload drive_links.json", type="json", key="drive_json_wc")
        if uploaded_json:
            try:
                drive_result_wc = json.loads(uploaded_json.read())
                st.session_state["drive_result"] = drive_result_wc
                st.success(f"✅ Loaded {len(drive_result_wc.get('files',[]))} files.")
            except Exception as e:
                st.error(f"❌ {e}")

if not drive_result_wc:
    st.info("Complete Phase 2 (Google Drive upload) first, or load drive_links.json above.")
else:
    ok_files = [r for r in drive_result_wc.get("files",[]) if "error" not in r]
    st.success(f"✅ {len(ok_files)} Drive links ready.")

    # ── Product Type Selection ────────────────────────────────────────────
    st.markdown("### 🎛️ Product Type")
    st.info(
        "**Simple product** — all 10 languages included in one download (one price).\n\n"
        "**Variable product (Komplettpaket)** — customer picks their language from a dropdown "
        "at checkout. Each language gets its own price and download link."
    )
    product_type = st.radio(
        "Product type",
        options=["simple", "variable"],
        format_func=lambda x: (
            "🗂️ Simple — all languages, one price (standard documents)"
            if x == "simple" else
            "📦 Variable — customer selects language (Komplettpaket)"
        ),
        horizontal=True,
        key="product_type_radio"
    )
    is_variable = (product_type == "variable")

    # ── Product Settings ──────────────────────────────────────────────────
    st.markdown("### ⚙️ Product Settings")
    col1, col2 = st.columns(2)
    with col1:
        product_name  = st.text_input("Product name",
            value="Paket - Aromatherapie Behandlung")
        product_sku = st.text_input("SKU (optional)", value="",
            placeholder="Leave empty to auto-assign, or enter unique SKU")
    with col2:
        st.markdown("**Categories** — fetch from your store:")
        if st.button("🔄 Load categories from WooCommerce"):
            if not wc_ck or not wc_cs:
                st.error("Enter Consumer Key + Secret in sidebar first.")
            else:
                with st.spinner("Loading…"):
                    try:
                        cats = wc_get_categories(wc_site_url, wc_ck, wc_cs)
                        st.session_state["wc_categories"] = cats
                        st.success(f"✅ {len(cats)} categories loaded.")
                    except Exception as e:
                        st.error(f"❌ {e}")

    # ── Price configuration ───────────────────────────────────────────────
    st.markdown("### 💶 Pricing")

    if is_variable:
        st.markdown(
            "**Variable product:** Set a price for each language variation. "
            "Each language gets its own price and download link."
        )
        variation_prices = {}
        price_cols = st.columns(5)
        for idx, lang in enumerate(LANGUAGES):
            with price_cols[idx % 5]:
                flag = FLAGS[lang]
                default_price = 26.80
                price = st.number_input(
                    f"{flag} {lang}",
                    value=default_price, step=0.10, format="%.2f",
                    key=f"var_price_{lang}",
                    min_value=0.0,
                )
                variation_prices[lang] = price
    else:
        regular_price = st.number_input(
            "Price (€)", value=26.80, step=0.10, format="%.2f"
        )

    cats_loaded = st.session_state.get("wc_categories", [])
    if cats_loaded:
        cat_options     = {f"{c['name']} (ID:{c['id']})": c["id"] for c in cats_loaded}
        selected_labels = st.multiselect(
            "Select categories",
            options=list(cat_options.keys()),
            default=[k for k in cat_options if "Komplett" in k or "Aromatherapie" in k][:2]
        )
        selected_cat_ids = [cat_options[k] for k in selected_labels]
    else:
        st.caption("Or enter IDs manually:")
        manual_ids       = st.text_input("Category IDs (comma-separated)", placeholder="42, 87")
        selected_cat_ids = [int(x.strip()) for x in manual_ids.split(",") if x.strip().isdigit()]

    # ── Product Details for GPT ───────────────────────────────────────────
    st.markdown("### 📋 Product Details")
    det_col1, det_col2 = st.columns(2)
    with det_col1:
        product_file_type   = st.text_input("Dateityp", value="Canva Link & PDF Datei")
        product_format      = st.text_input("Format", value="A4")
        product_num_pages   = st.number_input(
            "Seitenanzahl (pages per language)", value=65, min_value=1
        )
    with det_col2:
        product_canva_link  = st.text_input(
            "Canva Live-Link (optional)", placeholder="https://www.canva.com/..."
        )
        rel1_name = st.text_input("Related product 1 name", value="Einverständniserklärung")
        rel1_url  = st.text_input("Related product 1 URL",
            value="https://beautymediashop.de/produkt/einverstaendnis-fuer-die-behandlung/")
        rel1_desc = st.text_input("Related product 1 description",
            value="Bietet Ihnen rechtliche Sicherheit und informiert Ihre Kundinnen umfassend.")

    related_products = None
    if rel1_name and rel1_url:
        related_products = [
            {"name": rel1_name, "url": rel1_url, "desc": rel1_desc},
            {"name": "Pflegehinweise",
             "url": "https://beautymediashop.de/produkt/pflegehinweis-fuer-die-behandlung/",
             "desc": "Vermitteln klare Anweisungen für die richtige Nachsorge, damit die Ergebnisse optimal bleiben."},
            {"name": "Vorabinformation",
             "url": "https://beautymediashop.de/produkt/vorabinformationen-behandlung/",
             "desc": "Schaffen Sie Vertrauen, indem Sie Ihre Kundinnen schon vor der Behandlung professionell aufklären."},
        ]

    # ── Extra docs for short description (Komplettpaket style) ────────────
    if is_variable:
        st.markdown("### 📄 Short Description — Document List")
        st.caption(
            "For the Komplettpaket short description, list each document type with its page count "
            "and languages (like the Microneedling product). Add rows as needed."
        )
        num_extra_docs = st.number_input(
            "Number of document types in this package", min_value=1, max_value=20, value=4
        )
        extra_docs = []
        for i in range(int(num_extra_docs)):
            dc1, dc2, dc3 = st.columns([3, 2, 4])
            doc_label = dc1.text_input(
                f"Doc {i+1} label", value=["Schulung", "Blanko-Zertifikat", "Kundenkartei", "Einverständniserklärung"][i] if i < 4 else f"Dokument {i+1}",
                key=f"doc_label_{i}"
            )
            doc_pages = dc2.number_input(
                f"Pages", value=[53, 1, 1, 2][i] if i < 4 else 1,
                min_value=1, key=f"doc_pages_{i}"
            )
            doc_langs = dc3.text_input(
                f"Languages", value=["Deutsch, Türkisch", "Deutsch", "Mehrsprachig*", "Mehrsprachig*"][i] if i < 4 else "Mehrsprachig*",
                key=f"doc_langs_{i}"
            )
            extra_docs.append({"label": doc_label, "pages": int(doc_pages), "langs": doc_langs})
    else:
        extra_docs = None

    # ── GPT content generation ────────────────────────────────────────────
    st.markdown("### ✍️ Product Content — GPT-4o-mini")

    lang_list   = [r["language"] for r in ok_files]
    gpt_content = st.session_state.get("gpt_product_content")

    col_gen, col_regen = st.columns([2,1])
    with col_gen:
        if st.button("🤖 Generate Description with GPT-4o-mini",
                     type="primary", use_container_width=True):
            if not API_KEY:
                st.error("No API key — add OPENAI_API_KEY to .env or paste in sidebar.")
            else:
                type_hint = (
                    "Dieses Komplettpaket enthält alle wichtigen Unterlagen für die Behandlung in einer Sprache."
                    if is_variable else
                    "Dieses Produkt enthält alle Unterlagen in 10 Sprachen in einem Kauf."
                )
                with st.spinner("GPT is writing your product description…"):
                    content, err = gpt_generate_product_content(
                        product_name      = product_name,
                        language_list     = lang_list,
                        num_pages         = int(product_num_pages),
                        file_type         = product_file_type,
                        product_format    = product_format,
                        canva_link        = product_canva_link,
                        api_key           = API_KEY,
                        related_products  = related_products,
                        is_variable       = is_variable,
                        product_type_hint = type_hint,
                    )
                    if content:
                        # Only clean non-HTML fields (SEO fields) — never touch description_html
                        # description_html is protected via _desc_locked key
                        for _k in ["seo_title", "focus_keyphrase", "meta_description", "short_description"]:
                            if _k in content and isinstance(content[_k], str):
                                content[_k] = content[_k].replace("\\n", "\n").strip()
                        # description_html: only fix literal \n, never touch href attributes
                        if "description_html" in content and isinstance(content["description_html"], str):
                            content["description_html"] = content["description_html"].replace("\\n", "\n")
                        if "_desc_locked" in content and isinstance(content["_desc_locked"], str):
                            content["_desc_locked"] = content["_desc_locked"].replace("\\n", "\n")
                        st.session_state["gpt_product_content"] = content
                        gpt_content = content
                        st.success("✅ GPT description generated!")
                    else:
                        st.error(f"❌ GPT failed: {err}")
                        st.info("Fallback static description will be used.")
    with col_regen:
        if gpt_content and st.button("🔄 Regenerate", use_container_width=True):
            st.session_state.pop("gpt_product_content", None)
            st.rerun()

    if gpt_content:
        st.markdown("**📝 GPT-generated content (editable):**")

        st.markdown("#### 🔍 Yoast SEO Fields")
        yoast_col1, yoast_col2 = st.columns(2)
        with yoast_col1:
            edited_focus_kw   = st.text_input(
                "Fokus-Keyphrase",
                value=gpt_content.get("focus_keyphrase", ""),
                help="Yoast SEO → Fokus-Keyphrase"
            )
            edited_seo_title  = st.text_input(
                "SEO-Titel (max 60 Zeichen)",
                value=gpt_content.get("seo_title",""), max_chars=60,
                help="Yoast SEO → SEO-Titel"
            )
        with yoast_col2:
            edited_meta_desc  = st.text_area(
                "Meta-Beschreibung (max 155 Zeichen)",
                value=gpt_content.get("meta_description",""), max_chars=155, height=100,
                help="Yoast SEO → Meta-Beschreibung"
            )

        st.markdown("#### 📄 Product Content")
        edited_short_desc = st.text_area(
            "Produkt Kurzbeschreibung (HTML)",
            value=gpt_content.get("short_description",""), height=150,
        )
        # text_area for display/editing — but NEVER use its value for WooCommerce
        # because st.text_area corrupts href=" quotes on re-render cycles
        _locked_desc = gpt_content.get("_desc_locked") or gpt_content.get("description_html", "")
        edited_desc = st.text_area(
            "Produktbeschreibung (HTML) — zum Bearbeiten (Links werden automatisch korrekt gesetzt)",
            value=_locked_desc, height=400,
        )

        # _locked_desc always has correct Python-built links
        # If user edited the text area, use their version; otherwise keep locked
        _final_desc = edited_desc if edited_desc != _locked_desc else _locked_desc

        st.session_state["gpt_product_content"] = {
            "focus_keyphrase":   edited_focus_kw,
            "seo_title":         edited_seo_title,
            "meta_description":  edited_meta_desc,
            "short_description": edited_short_desc,
            "description_html":  _final_desc,
            "_desc_locked":      _locked_desc,  # preserve across re-renders
        }

        with st.expander("👁️ Preview description HTML"):
            st.markdown(_locked_desc, unsafe_allow_html=True)
        with st.expander("👁️ Preview short description HTML"):
            st.markdown(edited_short_desc, unsafe_allow_html=True)
        st.info("Click 'Generate Description' above, or a static fallback will be used.")

    # ── Downloadable files / Variations preview ───────────────────────────
    st.markdown("### 📎 Download Files from Google Drive")
    for r in ok_files:
        c1, c2 = st.columns([2,5])
        c1.markdown(f"**{r['flag']} {r['code']}** {r['language']}")
        c2.code(r["download_link"])

    # ── Create product ────────────────────────────────────────────────────
    st.markdown("### 🚀 Create Product in WooCommerce")

    if is_variable:
        st.info(
            "**Variable product flow:**\n"
            "1. Creates the parent variable product with a 'Sprachen' attribute\n"
            "2. Creates one variation per language, each with its own price + download\n"
            "3. Sets Yoast SEO fields if WP credentials are provided"
        )
    else:
        st.info(
            "**Simple product flow:**\n"
            "1. Creates a simple downloadable product with all 10 language files attached\n"
            "2. Sets Yoast SEO fields if WP credentials are provided"
        )

    col_test, col_create = st.columns([1,2])

    with col_test:
        if st.button("🔌 Test WC Connection", use_container_width=True):
            if not wc_ck or not wc_cs:
                st.error("Enter Consumer Key + Secret in sidebar.")
            else:
                clean = _clean_url(wc_site_url)
                st.caption(f"Testing: `{clean}`")
                ok, msg = wc_test(wc_site_url, wc_ck, wc_cs)
                if ok: st.success(f"✅ {msg}")
                else:  st.error(f"❌ {msg}")

    with col_create:
        btn_label = {
            "draft":   f"💾 Create {'Variable' if is_variable else 'Simple'} Product as Draft",
            "publish": f"🚀 Publish {'Variable' if is_variable else 'Simple'} Product",
            "pending": f"📋 Submit {'Variable' if is_variable else 'Simple'} for Review",
        }.get(wc_status, "📤 Create")

        if st.button(btn_label, type="primary", use_container_width=True):
            if not wc_ck or not wc_cs:
                st.error("Enter Consumer Key + Secret in sidebar.")
            elif not product_name.strip():
                st.error("Product name cannot be empty.")
            elif not ok_files:
                st.error("No Drive files available.")
            else:
                gc = st.session_state.get("gpt_product_content")
                if gc:
                    # Use _desc_locked which always has correct Python-built links
                    desc_html  = gc.get("_desc_locked") or gc.get("description_html","")
                    short_desc = gc.get("short_description","")
                else:
                    desc_html  = fallback_description_html(
                        product_name, drive_result_wc,
                        num_pages=int(product_num_pages),
                        language_list=lang_list,
                        is_variable=is_variable,
                    )
                    short_desc = fallback_short_description(
                        int(product_num_pages), lang_list,
                        is_variable=is_variable,
                        extra_docs=extra_docs,
                    )

                # ── BUILD lang→file lookup ────────────────────────────────
                lang_file_map = {r["language"]: r for r in ok_files}

                with st.spinner("Creating WooCommerce product…"):
                    try:
                        if not is_variable:
                            # ─── SIMPLE PRODUCT ───────────────────────────
                            download_files = [
                                {
                                    "name": f"{r['flag']} {r['language']} — {product_name}",
                                    "file": r["download_link"]
                                }
                                for r in ok_files
                            ]
                            payload = {
                                "name":              product_name,
                                "type":              "simple",
                                "status":            wc_status,
                                "downloadable":      True,
                                "virtual":           True,
                                "regular_price":     str(round(regular_price, 2)),
                                "description":       desc_html,
                                "short_description": short_desc,
                                **({"sku": product_sku} if product_sku.strip() else {}),
                                "categories":        [{"id": cid} for cid in selected_cat_ids],
                                "downloads":         download_files,
                                "download_limit":    -1,
                                "download_expiry":   -1,
                            }
                            result_wc  = wc_post("products", wc_ck, wc_cs, wc_site_url, payload)
                            product_id = result_wc["id"]

                        else:
                            # ─── VARIABLE PRODUCT ─────────────────────────
                            # Build the attribute options list (native language names)
                            attr_options = [
                                LANG_NATIVE.get(lang, lang) for lang in LANGUAGES
                                if lang in lang_file_map
                            ]

                            parent_payload = {
                                "name":              product_name,
                                "type":              "variable",
                                "status":            wc_status,
                                "downloadable":      True,
                                "virtual":           True,
                                "description":       desc_html,
                                "short_description": short_desc,
                                **({"sku": product_sku} if product_sku.strip() else {}),
                                "categories":        [{"id": cid} for cid in selected_cat_ids],
                                "attributes": [
                                    {
                                        "name":      "Sprachen",
                                        "position":  0,
                                        "visible":   True,
                                        "variation": True,
                                        "options":   attr_options,
                                    }
                                ],
                            }
                            parent_result = wc_post("products", wc_ck, wc_cs, wc_site_url, parent_payload)
                            product_id    = parent_result["id"]

                            # Create one variation per language
                            var_bar     = st.progress(0, text="Creating variations…")
                            var_errors  = []
                            var_created = []

                            for vidx, lang in enumerate(LANGUAGES):
                                if lang not in lang_file_map:
                                    continue
                                r         = lang_file_map[lang]
                                price     = variation_prices.get(lang, 26.80)
                                native    = LANG_NATIVE.get(lang, lang)

                                var_payload = {
                                    "status":        "publish",
                                    "downloadable":  True,
                                    "virtual":       True,
                                    "regular_price": str(round(price, 2)),
                                    "download_limit":  -1,
                                    "download_expiry": -1,
                                    "downloads": [
                                        {
                                            "name": f"{r['flag']} {lang} — {product_name}",
                                            "file": r["download_link"],
                                        }
                                    ],
                                    "attributes": [
                                        {
                                            "name":   "Sprachen",
                                            "option": native,
                                        }
                                    ],
                                }

                                try:
                                    var_result = wc_post(
                                        f"products/{product_id}/variations",
                                        wc_ck, wc_cs, wc_site_url, var_payload
                                    )
                                    var_created.append(
                                        f"✅ {r['flag']} {lang} ({native}) — "
                                        f"ID {var_result['id']} — €{price:.2f}"
                                    )
                                except Exception as ve:
                                    var_errors.append(f"❌ {lang}: {ve}")

                                var_bar.progress(
                                    (vidx+1) / len(LANGUAGES),
                                    text=f"Variation {vidx+1}/{len(LANGUAGES)}: {lang}…"
                                )

                            var_bar.progress(1.0, text="✅ All variations created!")
                            st.markdown("**Variations created:**")
                            for msg in var_created:
                                st.markdown(msg)
                            for msg in var_errors:
                                st.error(msg)

                        # ── Common: get product URL ───────────────────────
                        result_final = wc_get(
                            f"products/{product_id}", wc_ck, wc_cs, wc_site_url
                        )
                        product_url = result_final.get("permalink", "")
                        edit_url    = (
                            f"{_clean_url(wc_site_url).rstrip('/')}/wp-admin/post.php"
                            f"?post={product_id}&action=edit"
                        )

                        st.balloons()
                        st.success(
                            f"✅ {'Variable' if is_variable else 'Simple'} product "
                            f"{'saved as draft' if wc_status=='draft' else 'published'}!\n\n"
                            f"**ID:** `{product_id}`  \n"
                            f"**Edit:** [{edit_url}]({edit_url})  \n"
                            f"**Live:** [{product_url}]({product_url})"
                        )

                        # ── Yoast SEO ─────────────────────────────────────
                        if gc and (gc.get("focus_keyphrase") or gc.get("seo_title") or gc.get("meta_description")):
                            yoast_success = False
                            if wp_username and wp_app_password:
                                with st.spinner("Setting Yoast SEO fields…"):
                                    ok_yoast, yoast_msg = set_yoast_seo(
                                        site             = wc_site_url,
                                        wp_username      = wp_username,
                                        wp_app_password  = wp_app_password,
                                        post_id          = product_id,
                                        focus_keyphrase  = gc.get("focus_keyphrase",""),
                                        seo_title        = gc.get("seo_title",""),
                                        meta_description = gc.get("meta_description",""),
                                    )
                                    if ok_yoast:
                                        st.success(yoast_msg)
                                        yoast_success = True
                                    else:
                                        st.warning(
                                            f"⚠️ Yoast SEO auto-update failed: {yoast_msg}\n\n"
                                            "Please set these fields manually in the product editor:"
                                        )

                            if not yoast_success:
                                st.info(
                                    f"📌 **Yoast SEO — set manually in product editor:**\n\n"
                                    f"- **Fokus-Keyphrase:** `{gc.get('focus_keyphrase','')}`\n"
                                    f"- **SEO-Titel:** `{gc.get('seo_title','')}`\n"
                                    f"- **Meta-Beschreibung:** `{gc.get('meta_description','')}`\n\n"
                                    f"➡️ [Open product editor]({edit_url})"
                                )

                        st.session_state["wc_result"] = {
                            "product_id":   product_id,
                            "product_url":  product_url,
                            "edit_url":     edit_url,
                            "status":       wc_status,
                            "name":         product_name,
                            "type":         "variable" if is_variable else "simple",
                            "created_at":   datetime.now().isoformat(),
                        }

                    except RuntimeError as e:
                        st.error(f"❌ WooCommerce error: {e}")
                        st.markdown("""
**Common fixes:**
- Key must have **Read/Write** permissions
  → WooCommerce → Settings → Advanced → REST API → Edit → Permissions: Read/Write
- Consumer Key starts with `ck_`, Secret with `cs_`
- No trailing slash in site URL
                        """)
                    except Exception as e:
                        st.error(f"❌ Unexpected: {e}")
                        st.exception(e)

    if st.session_state.get("wc_result"):
        r = st.session_state["wc_result"]
        ptype = r.get("type","simple")
        st.markdown("---")
        st.markdown(f"""
**Last created product:**
- 🏷️ **{r['name']}** ({'🔀 Variable' if ptype=='variable' else '📄 Simple'})
- 🆔 ID: `{r['product_id']}`
- ✏️ [Edit in WP Admin]({r['edit_url']})
- 🌐 [View live]({r['product_url']})
- 📅 {r['created_at'][:19].replace('T',' ')}
- 📌 Status: `{r['status']}`
        """)


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 6 — ETSY LISTING
# ══════════════════════════════════════════════════════════════════════════════
st.divider()
st.header("🛍️ Phase 4 — Create Etsy Listing")
st.markdown("""
Creates a **digital download listing** on Etsy with GPT-generated English description,
13 SEO tags, and all Drive download links attached as digital files.
""")

# Check prerequisites
_etsy_drive_ok = bool(drive_result_wc and ok_files) if drive_result_wc else False
_etsy_creds_ok = bool(etsy_api_key and etsy_access_token and etsy_shop_id)

if not _etsy_drive_ok:
    st.info("Complete Phase 2 (Google Drive upload) first — Etsy needs the Drive links.")
else:
    st.success(f"✅ {len(ok_files)} Drive links ready for Etsy.")

    if not _etsy_creds_ok:
        st.warning("⚠️ Add Etsy API Key, Access Token and Shop ID in the sidebar to continue.")
    else:
        # ── Etsy product settings ─────────────────────────────────────────
        st.markdown("### ⚙️ Etsy Listing Settings")
        ecol1, ecol2 = st.columns(2)
        with ecol1:
            etsy_product_name = st.text_input(
                "Listing title base (GPT will optimise)",
                value=product_name if "product_name" in dir() else "Paket - Aromatherapie Behandlung",
                key="etsy_product_name"
            )
            etsy_price = st.number_input(
                "Price (€)", value=26.80, step=0.10, format="%.2f", key="etsy_price"
            )
            etsy_quantity = st.number_input(
                "Quantity (999 = unlimited digital)", value=999, min_value=1, key="etsy_qty"
            )
        with ecol2:
            etsy_state = st.selectbox(
                "Listing state", ["draft", "active"], index=0, key="etsy_state"
            )
            etsy_num_pages = st.number_input(
                "Pages per booklet", value=65, min_value=1, key="etsy_pages"
            )
            etsy_file_type = st.text_input(
                "File type", value="Canva Link & PDF", key="etsy_filetype"
            )

        # ── GPT content for Etsy ─────────────────────────────────────────
        st.markdown("### ✍️ Etsy Content — GPT-4o-mini (English)")
        st.caption("Etsy requires plain text descriptions — no HTML. GPT writes optimised English copy with 13 SEO tags.")

        etsy_content = st.session_state.get("etsy_content")
        ecol_gen, ecol_regen = st.columns([2, 1])

        with ecol_gen:
            if st.button("🤖 Generate Etsy Content", type="primary",
                         use_container_width=True, key="etsy_gen_btn"):
                if not API_KEY:
                    st.error("No OpenAI API key.")
                else:
                    with st.spinner("GPT writing Etsy listing…"):
                        _etsy_langs = [r["language"] for r in ok_files]
                        _etsy_is_var = (product_type == "variable") if "product_type" in dir() else False
                        ec, err = gpt_generate_etsy_content(
                            product_name   = etsy_product_name,
                            language_list  = _etsy_langs,
                            num_pages      = int(etsy_num_pages),
                            file_type      = etsy_file_type,
                            product_format = "A4",
                            api_key        = API_KEY,
                            is_variable    = _etsy_is_var,
                        )
                        if ec:
                            st.session_state["etsy_content"] = ec
                            etsy_content = ec
                            st.success("✅ Etsy content generated!")
                        else:
                            st.error(f"❌ {err}")

        with ecol_regen:
            if etsy_content and st.button("🔄 Regenerate", key="etsy_regen",
                                           use_container_width=True):
                st.session_state.pop("etsy_content", None)
                st.rerun()

        if etsy_content:
            st.markdown("**📝 Etsy content (editable):**")

            etsy_title_edited = st.text_input(
                "Listing Title (max 140 chars)",
                value=etsy_content.get("title", ""), max_chars=140, key="etsy_title_edit"
            )
            st.caption(f"{len(etsy_title_edited)}/140 characters")

            etsy_desc_edited = st.text_area(
                "Description (plain text, no HTML)",
                value=etsy_content.get("description", ""), height=350, key="etsy_desc_edit"
            )

            st.markdown("**🏷️ Tags (13 max, 20 chars each):**")
            etsy_tags_raw = st.text_input(
                "Tags (comma-separated)",
                value=", ".join(etsy_content.get("tags", [])), key="etsy_tags_edit"
            )
            etsy_tags_list = [t.strip()[:20] for t in etsy_tags_raw.split(",") if t.strip()][:13]
            st.caption(f"{len(etsy_tags_list)}/13 tags  |  "
                       + "  |  ".join(f"`{t}`" for t in etsy_tags_list))

            etsy_price_final = st.number_input(
                "Final Price (€)",
                value=float(etsy_content.get("price_suggestion", etsy_price)),
                step=0.10, format="%.2f", key="etsy_price_final"
            )

            with st.expander("👁️ Preview description"):
                st.text(etsy_desc_edited)

            # Save edits
            st.session_state["etsy_content"] = {
                **etsy_content,
                "title":       etsy_title_edited,
                "description": etsy_desc_edited,
                "tags":        etsy_tags_list,
                "price_final": etsy_price_final,
            }

        # ── Create Etsy listing ───────────────────────────────────────────
        st.markdown("### 🚀 Create Etsy Listing")

        etsy_col_test, etsy_col_create = st.columns([1, 2])

        with etsy_col_test:
            if st.button("🔌 Test Etsy Connection", use_container_width=True, key="etsy_test"):
                ok_e, msg_e = etsy_test(etsy_api_key, etsy_access_token, etsy_shop_id)
                if ok_e: st.success(msg_e)
                else:    st.error(f"❌ {msg_e}")

        with etsy_col_create:
            if st.button("🛍️ Create Etsy Listing", type="primary",
                         use_container_width=True, key="etsy_create"):
                if not etsy_content:
                    st.error("Generate Etsy content first.")
                else:
                    ec = st.session_state.get("etsy_content", etsy_content)
                    _price = ec.get("price_final", etsy_price)
                    _tags  = ec.get("tags", [])

                    # Build description with download links appended
                    _lang_links = "\n".join(
                        f"• {r['flag']} {r['language']}: {r['download_link']}"
                        for r in ok_files
                    )
                    _full_desc = (
                        ec.get("description", "") +
                        "\n\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        "DOWNLOAD LINKS:\n" + _lang_links
                    )

                    # Etsy listing payload
                    listing_payload = {
                        "quantity":       int(etsy_quantity),
                        "title":          ec.get("title", etsy_product_name)[:140],
                        "description":    _full_desc,
                        "price":          round(float(_price), 2),
                        "who_made":       ec.get("who_made", "i_did"),
                        "when_made":      ec.get("when_made", "made_to_order"),
                        "taxonomy_id":    int(ec.get("taxonomy_id", 2078)),
                        "tags":           _tags,
                        "is_digital":     True,
                        "state":          etsy_state,
                        "type":           "download",
                    }

                    with st.spinner("Creating Etsy listing…"):
                        try:
                            result_etsy = etsy_post(
                                f"shops/{etsy_shop_id}/listings",
                                etsy_api_key, etsy_access_token, listing_payload
                            )
                            listing_id  = result_etsy.get("listing_id")
                            listing_url = result_etsy.get("url", 
                                f"https://www.etsy.com/listing/{listing_id}")

                            st.balloons()
                            st.success(
                                f"✅ Etsy listing created!"
                                f"**Listing ID:** `{listing_id}`"
                                f"**URL:** [{listing_url}]({listing_url})"
                                f"**State:** `{etsy_state}`"
                            )
                            st.info(
                                "**Next steps in Etsy:**\n"
                                "1. Go to Shop Manager → Listings\n"
                                "2. Upload the PDF files as digital downloads\n"
                                "3. Add product images\n"
                                "4. Set shipping profile to 'Digital' or free\n"
                                "5. Publish when ready"
                            )

                            st.session_state["etsy_result"] = {
                                "listing_id":  listing_id,
                                "listing_url": listing_url,
                                "title":       ec.get("title",""),
                                "state":       etsy_state,
                                "created_at":  datetime.now().isoformat(),
                            }

                        except RuntimeError as e:
                            st.error(f"❌ Etsy API error: {e}")
                            st.markdown("""
**Common fixes:**
- Make sure your OAuth Access Token is valid and not expired
- Token needs scope: `listings_w` (write listings)
- Shop ID must be numeric (find it in Etsy Shop Manager URL)
- Rate limit: 5 requests/second — if hitting limits, wait and retry
                            """)
                        except Exception as e:
                            st.error(f"❌ Unexpected: {e}")
                            st.exception(e)

    if st.session_state.get("etsy_result"):
        er = st.session_state["etsy_result"]
        st.markdown("---")
        st.markdown(f"""
**Last created Etsy listing:**
- 🏷️ **{er['title'][:60]}...**
- 🆔 ID: `{er['listing_id']}`
- 🌐 [View on Etsy]({er['listing_url']})
- 📅 {er['created_at'][:19].replace('T',' ')}
- 📌 State: `{er['state']}`
        """)