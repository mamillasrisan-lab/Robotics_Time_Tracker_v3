import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

# ==========================================================
# EDIT THESE SETTINGS
# ==========================================================

# 1) Paste your Google Sheet URL between these quotation marks:
SHEET_URL = "PASTE_YOUR_GOOGLE_SHEET_URL_HERE"

# 2) Replace these examples with the names in your club roster:
MEMBERS = [
    "Alex Johnson",
    "Jordan Smith",
    "Taylor Lee",
]

# Local testing on your computer. On Streamlit Cloud, the app uses Secrets.
LOCAL_SERVICE_ACCOUNT_FILE = r"C:\Users\Srithan\service_account.json"

WORKSHEET_NAME = "Attendance"
TIMEZONE = "America/Los_Angeles"

HEADERS = [
    "Name",
    "Start Date",
    "Start Time",
    "End Date",
    "End Time",
    "Status",
]

# ==========================================================
# PAGE
# ==========================================================

st.set_page_config(page_title="Club Clock In / Clock Out", page_icon="🕒")
st.title("🕒 Club Clock In / Clock Out")
st.write("Search for your name, select it, and use the appropriate button.")

# ==========================================================
# GOOGLE SHEETS CONNECTION
# ==========================================================

def get_worksheet():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    if Path(LOCAL_SERVICE_ACCOUNT_FILE).is_file():
        credentials = Credentials.from_service_account_file(
            LOCAL_SERVICE_ACCOUNT_FILE, scopes=scopes
        )
    else:
        # In Streamlit Cloud, add your service-account fields under Secrets:
        # [gcp_service_account]
        credentials = Credentials.from_service_account_info(
            dict(st.secrets["gcp_service_account"]), scopes=scopes
        )

    client = gspread.authorize(credentials)
    spreadsheet = client.open_by_url(SHEET_URL)

    try:
        worksheet = spreadsheet.worksheet(WORKSHEET_NAME)
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(
            title=WORKSHEET_NAME, rows=1000, cols=len(HEADERS)
        )

    if not worksheet.row_values(1):
        worksheet.update(range_name="A1:F1", values=[HEADERS])

    return worksheet


if not SHEET_URL.startswith("https://"):
    st.error("Paste your Google Sheet URL into SHEET_URL near the top of app.py.")
    st.stop()

if not MEMBERS:
    st.error("Add your club members to the MEMBERS list near the top of app.py.")
    st.stop()

# ==========================================================
# MEMBER SEARCH
# ==========================================================

search = st.text_input("Search for your name", placeholder="Start typing your name...")
if search.strip():
    matches = [
