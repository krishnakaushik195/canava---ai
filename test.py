"""
Google Drive Connection Tester
================================
Tests your Drive access and shows:
  1. Which Google account is connected
  2. Whether the parent folder in .env is accessible
  3. Lists your top-level Drive folders so you can pick a valid one
  4. Creates a small test folder + test file, then cleans up

Run:
    streamlit run drive_test.py
"""

import os
import io
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

try:
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseUpload
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    GDRIVE_AVAILABLE = True
except ImportError:
    GDRIVE_AVAILABLE = False

SCOPES               = ["https://www.googleapis.com/auth/drive"]
CREDENTIALS_FILE     = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
TOKEN_FILE           = os.getenv("GOOGLE_TOKEN_FILE",       "token.json")
PARENT_FOLDER_ID     = os.getenv("GOOGLE_DRIVE_PARENT_FOLDER_ID", "root")

st.set_page_config(page_title="Drive Connection Tester", page_icon="☁️", layout="centered")
st.title("☁️ Google Drive Connection Tester")

if not GDRIVE_AVAILABLE:
    st.error("❌ Google Drive library not installed.\n\n"
             "Run: `pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib`")
    st.stop()

# ── Auth ──────────────────────────────────────────────────────────────────────

def get_drive_service():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                raise FileNotFoundError(
                    f"credentials.json not found at '{CREDENTIALS_FILE}'. "
                    "Download from Google Cloud Console → APIs & Services → Credentials."
                )
            flow  = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return build("drive", "v3", credentials=creds)

# ── Helpers ───────────────────────────────────────────────────────────────────

def get_account_info(service):
    about = service.about().get(fields="user").execute()
    return about["user"]


def check_folder_access(service, folder_id):
    """Try to fetch the folder metadata. Returns (ok, name_or_error)."""
    if folder_id == "root":
        return True, "My Drive (root)"
    try:
        meta = service.files().get(
            fileId=folder_id,
            fields="id,name,mimeType,webViewLink"
        ).execute()
        if meta.get("mimeType") == "application/vnd.google-apps.folder":
            return True, meta
        return False, f"'{meta.get('name')}' is not a folder (it's a file)"
    except Exception as e:
        return False, str(e)


def list_drive_folders(service, parent="root", max_results=30):
    """List folders inside a given parent (default = root of Drive)."""
    query  = f"'{parent}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
    result = service.files().list(
        q=query,
        fields="files(id, name, webViewLink)",
        pageSize=max_results,
        orderBy="name"
    ).execute()
    return result.get("files", [])


def create_test_folder(service, parent_id):
    meta   = {"name": "_drive_test_folder", "mimeType": "application/vnd.google-apps.folder", "parents": [parent_id]}
    folder = service.files().create(body=meta, fields="id,name,webViewLink").execute()
    return folder


def upload_test_file(service, folder_id):
    content = b"This is a Drive upload test file. Safe to delete."
    media   = MediaIoBaseUpload(io.BytesIO(content), mimetype="text/plain")
    meta    = {"name": "_drive_test_file.txt", "parents": [folder_id]}
    f       = service.files().create(body=meta, media_body=media, fields="id,name,webViewLink").execute()
    return f


def delete_item(service, file_id):
    service.files().delete(fileId=file_id).execute()


# ══════════════════════════════════════════════════════════════════════════════
# UI
# ══════════════════════════════════════════════════════════════════════════════

st.markdown(f"""
**Current `.env` settings:**
- `GOOGLE_CREDENTIALS_FILE` = `{CREDENTIALS_FILE}`
- `GOOGLE_TOKEN_FILE`       = `{TOKEN_FILE}`
- `GOOGLE_DRIVE_PARENT_FOLDER_ID` = `{PARENT_FOLDER_ID}`
""")

st.divider()

if st.button("🔌 Connect & Run All Tests", type="primary", use_container_width=True):

    # ── Step 1: Connect ───────────────────────────────────────────────────
    st.markdown("### Step 1 — Connect to Google Drive")
    try:
        with st.spinner("Authenticating…"):
            service = get_drive_service()
        st.success("✅ Connected to Google Drive")
    except FileNotFoundError as e:
        st.error(str(e))
        st.stop()
    except Exception as e:
        st.error(f"❌ Auth failed: {e}")
        st.stop()

    # ── Step 2: Account info ──────────────────────────────────────────────
    st.markdown("### Step 2 — Logged-in Google Account")
    try:
        user = get_account_info(service)
        st.success(
            f"✅ **{user.get('displayName', 'Unknown')}**  \n"
            f"📧 `{user.get('emailAddress', 'unknown')}`  \n"
            f"🖼️ Photo: {user.get('photoLink', 'N/A')}"
        )
    except Exception as e:
        st.warning(f"⚠️ Could not fetch account info: {e}")

    st.divider()

    # ── Step 3: Check parent folder from .env ─────────────────────────────
    st.markdown("### Step 3 — Parent Folder Access Check")
    st.caption(f"Checking folder ID: `{PARENT_FOLDER_ID}`")

    ok, result = check_folder_access(service, PARENT_FOLDER_ID)
    if ok:
        if isinstance(result, dict):
            st.success(
                f"✅ Folder accessible!\n\n"
                f"**Name:** {result['name']}  \n"
                f"**ID:** `{result['id']}`  \n"
                f"**Link:** [{result['webViewLink']}]({result['webViewLink']})"
            )
        else:
            st.success(f"✅ {result}")
    else:
        st.error(
            f"❌ Cannot access folder `{PARENT_FOLDER_ID}`\n\n"
            f"**Reason:** {result}\n\n"
            "👇 See Step 4 below — pick a folder you DO have access to."
        )

    st.divider()

    # ── Step 4: List available folders ────────────────────────────────────
    st.markdown("### Step 4 — Your Drive Folders (pick one to use)")
    st.caption("These are the top-level folders in the connected Google account's Drive.")

    try:
        folders = list_drive_folders(service, parent="root")
        if folders:
            st.info(f"Found {len(folders)} folder(s). Copy the ID of the one you want into `.env`.")
            for folder in folders:
                c1, c2, c3 = st.columns([3, 4, 2])
                c1.markdown(f"📁 **{folder['name']}**")
                c2.code(folder['id'])
                c3.markdown(f"[Open]({folder['webViewLink']})")
        else:
            st.warning("No folders found in the root of this Drive. The Drive may be empty.")
    except Exception as e:
        st.error(f"❌ Could not list folders: {e}")

    st.divider()

    # ── Step 5: Upload test ───────────────────────────────────────────────
    st.markdown("### Step 5 — Upload Test (creates then deletes a test folder + file)")

    # Use parent folder if accessible, otherwise root
    test_parent = PARENT_FOLDER_ID if ok else "root"
    st.caption(f"Testing upload into: `{test_parent}`")

    try:
        with st.spinner("Creating test folder…"):
            test_folder = create_test_folder(service, test_parent)
        st.success(f"✅ Test folder created: **{test_folder['name']}** → [Open]({test_folder['webViewLink']})")

        with st.spinner("Uploading test file…"):
            test_file = upload_test_file(service, test_folder["id"])
        st.success(f"✅ Test file uploaded: **{test_file['name']}** → [Open]({test_file['webViewLink']})")

        with st.spinner("Cleaning up…"):
            delete_item(service, test_file["id"])
            delete_item(service, test_folder["id"])
        st.success("✅ Cleanup done — test folder and file deleted")

        st.balloons()
        st.success("🎉 **All tests passed! Your Drive connection is working perfectly.**")

    except Exception as e:
        st.error(f"❌ Upload test failed: {e}")
        st.exception(e)

    st.divider()
    st.markdown("### ✅ Summary — copy the correct folder ID into your `.env`")
    st.code(
        f"GOOGLE_CREDENTIALS_FILE={CREDENTIALS_FILE}\n"
        f"GOOGLE_TOKEN_FILE={TOKEN_FILE}\n"
        f"GOOGLE_DRIVE_PARENT_FOLDER_ID=<paste folder ID from Step 4 above>",
        language="ini"
    )