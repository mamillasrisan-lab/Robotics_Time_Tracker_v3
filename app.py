import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

# ==========================================================
# EDIT THESE SETTINGS
# ==========================================================

# Paste your Google Sheet URL between the quotation marks:
SHEET_URL = "SHEET_URL = https://docs.google.com/spreadsheets/d/1eNZmloz7IozVoU_1cTsKVveUca73VMnjvySR9VMvz_g/edit?gid=0#gid=0"

# Put your club members' names in this list:
MEMBERS = [
    "Alex Johnson",
    "Jordan Smith",
    "Taylor Lee",
]

# Optional: local service-account JSON path for testing on your PC.
# On Streamlit Cloud, credentials are read securely from Streamlit Secrets.
LOCAL_SERVICE_ACCOUNT_FILE = r"C:\Users\Srithan\service_account.json"

WORKSHEET_NAME = "Attendance"
TIMEZONE = "America/Los_Angeles"

# ==========================================================
# APP
# ==========================================================

st.set_page_config(page_title="Club Check-In", page_icon="📋")
st.title("📋 Club Check-In / Check-Out")
st.caption("Search for your name, select it, and choose an action.")

def get_worksheet():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    if Path(LOCAL_SERVICE_ACCOUNT_FILE).exists():
        credentials = Credentials.from_service_account_file(
            LOCAL_SERVICE_ACCOUNT_FILE, scopes=scopes
        )
    else:
        # On Streamlit Cloud, add [gcp_service_account] in App settings → Secrets.
        credentials = Credentials.from_service_account_info(
            dict(st.secrets["gcp_service_account"]), scopes=scopes
        )

    client = gspread.authorize(credentials)
    spreadsheet = client.open_by_url(SHEET_URL)

    try:
        worksheet = spreadsheet.worksheet(WORKSHEET_NAME)
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(
            title=WORKSHEET_NAME, rows=1000, cols=6
        )

    headers = [
        "Name",
        "Check In Date",
        "Check In Time",
        "Check Out Date",
        "Check Out Time",
        "Status",
    ]
    if not worksheet.get_all_values():
        worksheet.append_row(headers)

    return worksheet

if not MEMBERS:
    st.error("Add member names to the MEMBERS list near the top of app.py.")
    st.stop()

search = st.text_input("Search your name", placeholder="Start typing your name...")
matches = [
    name for name in MEMBERS
    if search.strip().casefold() in name.casefold()
] if search.strip() else MEMBERS

if not matches:
    st.warning("No matching names. Check the spelling or ask the club organizer.")
    st.stop()

selected_name = st.selectbox("Select your full name", [""] + matches)

if not selected_name:
    st.info("Select your name to continue.")
    st.stop()

confirmed = st.checkbox(f"I confirm I am {selected_name}")
