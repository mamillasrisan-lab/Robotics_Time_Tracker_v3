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
SHEET_URL = "PASTE_YOUR_GOOGLE_SHEET_URL_HERE"

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
        worksheet.update(
            range_name="A1:F1",
            values=[HEADERS],
        )

    return worksheet


def get_active_row(rows, member_name):
    """Find the most recent row where this member is still clocked in."""
    active_row_number = None

    # Google Sheets row numbers start at 1. Row 1 is the header.
    for row_number, row in enumerate(rows[1:], start=2):
        padded_row = (row + [""] * len(HEADERS))[:len(HEADERS)]
        name = padded_row[0].strip()
        status = padded_row[5].strip().casefold()

        if name.casefold() == member_name.casefold() and status == "clocked in":
            active_row_number = row_number

    return active_row_number


def get_now():
    """Return the current date/time in California."""
    return datetime.now(ZoneInfo(TIMEZONE))


# ============================================================
# CHECK SETTINGS BEFORE SHOWING THE APP
# ============================================================

if not SHEET_URL.startswith("https://"):
    st.error(
        "Setup needed: replace PASTE_YOUR_GOOGLE_SHEET_URL_HERE near the top "
        "of app.py with your actual Google Sheet URL."
    )
    st.stop()

if not MEMBERS or any(not name.strip() for name in MEMBERS):
    st.error("Setup needed: add valid member names to the MEMBERS list near the top of app.py.")
    st.stop()

# ============================================================
# MEMBER SEARCH AND CONFIRMATION
# ============================================================

search_text = st.text_input(
    "Search for your name",
    placeholder="Start typing your name...",
)

if search_text.strip():
    matches = [
        member
        for member in MEMBERS
        if search_text.strip().casefold() in member.casefold()
    ]
else:
    matches = sorted(set(MEMBERS), key=str.casefold)

if not matches:
    st.warning("No matching names found. Check the spelling and try again.")
    st.stop()

selected_name = st.selectbox(
    "Select your full name",
    [""] + matches,
    format_func=lambda value: "Choose your name..." if value == "" else value,
)

if not selected_name:
    st.info("Select your name to continue.")
    st.stop()

confirmed = st.checkbox(f"I confirm that I am {selected_name}")

if not confirmed:
    st.warning("Please confirm your name before clocking in or out.")
    st.stop()

# ============================================================
# CONNECT TO GOOGLE SHEETS AND SHOW CURRENT STATUS
# ============================================================

try:
    worksheet = get_worksheet()
    current_rows = worksheet.get_all_values()
except Exception as error:
    st.error(
        "Could not connect to Google Sheets. Check that the Sheet URL is correct, "
        "the credentials are configured, and the spreadsheet is shared with the "
        "service-account email as an Editor."
    )
    st.caption(f"Technical detail: {error}")
    st.stop()

active_row_number = get_active_row(current_rows, selected_name)

if active_row_number is not None:
    st.success(f"{selected_name} is currently clocked in.")
else:
    st.info(f"{selected_name} is currently clocked out.")

# ============================================================
# CLOCK IN / CLOCK OUT
# ============================================================

clock_in_col, clock_out_col = st.columns(2)

with clock_in_col:
    clock_in_clicked = st.button(
        "Clock In",
        type="primary",
        use_container_width=True,
        disabled=active_row_number is not None,
    )

with clock_out_col:
    clock_out_clicked = st.button(
        "Clock Out",
        use_container_width=True,
        disabled=active_row_number is None,
    )

if clock_in_clicked:
    try:
        # Re-read the sheet to avoid creating a second open visit.
        latest_rows = worksheet.get_all_values()

        if get_active_row(latest_rows, selected_name) is not None:
            st.warning(f"{selected_name} is already clocked in.")
        else:
            now = get_now()

            # Each new visit gets a new row; prior visits are preserved.
            worksheet.append_row(
                [
                    selected_name,
                    now.strftime("%Y-%m-%d"),
                    now.strftime("%I:%M:%S %p"),
                    "",
                    "",
                    "Clocked In",
                ],
                value_input_option="RAW",
                insert_data_option="INSERT_ROWS",
            )

            st.success(
                f"{selected_name} clocked in at "
                f"{now.strftime('%I:%M:%S %p')} on {now.strftime('%Y-%m-%d')}."
            )
            st.rerun()

    except Exception as error:
        st.error("Clock-in failed. Check the Google Sheets connection and try again.")
        st.caption(f"Technical detail: {error}")

if clock_out_clicked:
    try:
        # Re-read the sheet and close the currently open visit.
        latest_rows = worksheet.get_all_values()
        latest_active_row = get_active_row(latest_rows, selected_name)

        if latest_active_row is None:
            st.warning(f"No active clock-in was found for {selected_name}.")
        else:
            now = get_now()

            # Update only the end date, end time, and status on that same row.
            worksheet.update(
                range_name=f"D{latest_active_row}:F{latest_active_row}",
                values=[[
                    now.strftime("%Y-%m-%d"),
                    now.strftime("%I:%M:%S %p"),
                    "Clocked Out",
                ]],
            )

            st.success(
                f"{selected_name} clocked out at "
                f"{now.strftime('%I:%M:%S %p')} on {now.strftime('%Y-%m-%d')}."
            )
            st.rerun()

    except Exception as error:
        st.error("Clock-out failed. Check the Google Sheets connection and try again.")
        st.caption(f"Technical detail: {error}")

# ============================================================
# CURRENTLY CLOCKED-IN MEMBERS
# ============================================================

st.divider()
st.subheader("Currently Clocked In")

try:
    refreshed_rows = worksheet.get_all_values()
    current_members = []

    for row in refreshed_rows[1:]:
        padded_row = (row + [""] * len(HEADERS))[:len(HEADERS)]

        if padded_row[5].strip().casefold() == "clocked in":
            current_members.append({
                "Name": padded_row[0],
                "Start Date": padded_row[1],
                "Start Time": padded_row[2],
            })

    if current_members:
        st.dataframe(
            current_members,
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.write("Nobody is currently clocked in.")

except Exception:
    st.warning("Could not load the current clock-in list.")
