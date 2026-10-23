import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

# ============================================================
# SETTINGS — EDIT THESE VALUES
# ============================================================

# Paste the full URL of your Google spreadsheet between quotes.
SHEET_URL = "https://docs.google.com/spreadsheets/d/1eNZmloz7IozVoU_1cTsKVveUca73VMnjvySR9VMvz_g/edit?gid=0#gid=0"

# Replace the example names with your club/robotics team roster.
MEMBERS = [
    "Alex Johnson",
    "Jordan Smith",
    "Taylor Lee",
]

# This file is used only when running the app on your computer.
# On Streamlit Community Cloud, credentials come from App Secrets.
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

# ============================================================
# PAGE SETUP
# ============================================================

st.set_page_config(
    page_title="Robotics Team Time Tracker",
    page_icon="🕒",
    layout="centered",
)

st.title("🕒 Robotics Team Time Tracker")
st.write("Search for your name, select it, confirm your identity, then clock in or out.")

# ============================================================
# GOOGLE SHEETS HELPERS
# ============================================================

def get_worksheet():
    """Connect to Google Sheets and return the Attendance worksheet."""
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    local_credentials_path = Path(LOCAL_SERVICE_ACCOUNT_FILE)

    if local_credentials_path.is_file():
        credentials = Credentials.from_service_account_file(
            str(local_credentials_path),
            scopes=scopes,
        )
    else:
        # In Streamlit Community Cloud, add a [gcp_service_account] section
        # in App settings > Secrets, using the fields from your service account JSON.
        if "gcp_service_account" not in st.secrets:
            raise RuntimeError(
                "Google credentials are missing. Add gcp_service_account to "
                "Streamlit Community Cloud Secrets, or place the service-account "
                "JSON file at the configured local path when testing locally."
            )

        credentials = Credentials.from_service_account_info(
            dict(st.secrets["gcp_service_account"]),
            scopes=scopes,
        )

    client = gspread.authorize(credentials)
    spreadsheet = client.open_by_url(SHEET_URL)

    try:
        worksheet = spreadsheet.worksheet(WORKSHEET_NAME)
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(
            title=WORKSHEET_NAME,
            rows=1000,
            cols=len(HEADERS),
        )

    if not worksheet.row_values(1):
