import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from gspread.exceptions import WorksheetNotFound, APIError
from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path

# ========================= SETTINGS =========================
SHEET_URL = "https://docs.google.com/spreadsheets/d/1eNZmloz7IozVoU_1cTsKVveUca73VMnjvySR9VMvz_g/edit"

# Replace these sample names with your real team roster.
MEMBERS = ["Alex Johnson", "Jordan Smith", "Taylor Lee"]

LOCAL_SERVICE_ACCOUNT_FILE = r"C:\Users\Srithan\service_account.json"
WORKSHEET_NAME = "Attendance"
TIMEZONE = "America/Los_Angeles"
HEADERS = ["Name", "Start Date", "Start Time", "End Date", "End Time", "Status"]


# ========================= GOOGLE SHEETS =========================
def get_credentials():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    local_path = Path(LOCAL_SERVICE_ACCOUNT_FILE)
    if local_path.is_file():
        return Credentials.from_service_account_file(str(local_path), scopes=scopes)

    try:
        info = dict(st.secrets["gcp_service_account"])
    except Exception as exc:
        raise RuntimeError(
            "Google credentials are missing. Add gcp_service_account in "
            "Streamlit Community Cloud → App settings → Secrets."
        ) from exc

    # Convert literal backslash-n sequences to newlines if needed.
    private_key = info.get("private_key", "")
    if "\\n" in private_key and "\n" not in private_key:
        info["private_key"] = private_key.replace("\\n", "\n")

    return Credentials.from_service_account_info(info, scopes=scopes)


def get_worksheet():
    spreadsheet = gspread.authorize(get_credentials()).open_by_url(SHEET_URL)

    try:
        worksheet = spreadsheet.worksheet(WORKSHEET_NAME)
    except WorksheetNotFound:
        try:
            worksheet = spreadsheet.add_worksheet(
                title=WORKSHEET_NAME,
                rows=1000,
                cols=len(HEADERS),
            )
        except APIError:
            # Another session may have created the tab at the same time.
            worksheet = spreadsheet.worksheet(WORKSHEET_NAME)

    if not worksheet.row_values(1):
        worksheet.update(range_name="A1:F1", values=[HEADERS])

    return worksheet


def california_now():
    return datetime.now(ZoneInfo(TIMEZONE))


def parse_sheet_datetime(date_text, time_text):
    """Read date/time values written by this app and common Sheets formats."""
    date_text = (date_text or "").strip()
    time_text = (time_text or "").strip()
    if not date_text or not time_text:
        return None

    parsed_date = None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            parsed_date = datetime.strptime(date_text, fmt).date()
            break
        except ValueError:
            continue

    if parsed_date is None:
        return None

    parsed_time = None
    for fmt in ("%I:%M:%S %p", "%I:%M %p", "%H:%M:%S", "%H:%M"):
        try:
            parsed_time = datetime.strptime(time_text, fmt).time()
            break
