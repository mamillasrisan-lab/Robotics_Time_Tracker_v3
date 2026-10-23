import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from gspread.exceptions import WorksheetNotFound, APIError
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

# ============================================================
# SETTINGS
# ============================================================

# Google Sheet URL supplied by you:
SHEET_URL = "https://docs.google.com/spreadsheets/d/1eNZmloz7IozVoU_1cTsKVveUca73VMnjvySR9VMvz_g/edit"

# Replace these sample names with the real robotics team roster.
MEMBERS = [
    "Alex Johnson",
    "Jordan Smith",
    "Taylor Lee",
]

# Local-only fallback. Do not upload this JSON file to GitHub.
LOCAL_SERVICE_ACCOUNT_FILE = r"C:\Users\Srithan\service_account.json"

WORKSHEET_NAME = "Attendance"
TIMEZONE = "America/Los_Angeles"

HEADERS = ["Name", "Start Date", "Start Time", "End Date", "End Time", "Status"]


# ============================================================
# GOOGLE SHEETS
# ============================================================

def get_credentials():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    local_path = Path(LOCAL_SERVICE_ACCOUNT_FILE)
    if local_path.is_file():
        return Credentials.from_service_account_file(str(local_path), scopes=scopes)

    try:
        secret_info = dict(st.secrets["gcp_service_account"])
    except Exception as exc:
        raise RuntimeError(
            "Google credentials are missing. Add the gcp_service_account section "
            "in Streamlit Community Cloud → App settings → Secrets."
        ) from exc

    # Streamlit TOML multiline strings can preserve the PEM formatting.
    # If the key was pasted as a JSON-style string with literal \\n sequences,
    # convert those sequences to actual newlines before loading credentials.
    private_key = secret_info.get("private_key", "")
    if "\\n" in private_key and "\n" not in private_key:
        secret_info["private_key"] = private_key.replace("\\n", "\n")

    return Credentials.from_service_account_info(secret_info, scopes=scopes)


def get_worksheet():
    credentials = get_credentials()
    client = gspread.authorize(credentials)
    spreadsheet = client.open_by_url(SHEET_URL)

    try:
        worksheet = spreadsheet.worksheet(WORKSHEET_NAME)
    except WorksheetNotFound:
        # Another app session may create the worksheet at the same time.
        try:
            worksheet = spreadsheet.add_worksheet(
                title=WORKSHEET_NAME,
                rows=1000,
                cols=len(HEADERS),
            )
        except APIError:
            # If the add failed because another session created it, retrieve it.
            worksheet = spreadsheet.worksheet(WORKSHEET_NAME)

    if not worksheet.row_values(1):
        worksheet.update(range_name="A1:F1", values=[HEADERS])

    return worksheet


def get_active_row(rows, member_name):
    """Return the latest open visit row number for a member, or None."""
    active_row = None
    for row_number, row in enumerate(rows[1:], start=2):
        values = (row + [""] * len(HEADERS))[:len(HEADERS)]
        if (
            values[0].strip().casefold() == member_name.casefold()
            and values[5].strip().casefold() == "clocked in"
        ):
            active_row = row_number
    return active_row


def california_now():
    return datetime.now(ZoneInfo(TIMEZONE))


# ============================================================
# APP UI
# ============================================================

st.set_page_config(page_title="Robotics Team Time Tracker", page_icon="🕒")
st.title("🕒 Robotics Team Time Tracker")
st.write("Search for your name, select it, confirm it, and then clock in or out.")

if not SHEET_URL.startswith("https://docs.google.com/spreadsheets/d/"):
    st.error("The Google Sheet URL in app.py is not valid. Check SHEET_URL near the top.")
    st.stop()

if not MEMBERS or any(not member.strip() for member in MEMBERS):
    st.error("Add your team members to the MEMBERS list near the top of app.py.")
    st.stop()

search_text = st.text_input("Search for your name", placeholder="Start typing your name")

if search_text.strip():
    matches = [
        member for member in MEMBERS
        if search_text.strip().casefold() in member.casefold()
    ]
else:
    matches = sorted(set(MEMBERS), key=str.casefold)

if not matches:
    st.warning("No matching names found. Check the spelling.")
    st.stop()

selected_name = st.selectbox(
    "Select your full name",
    [""] + matches,
    format_func=lambda name: "Choose your name..." if name == "" else name,
)

if not selected_name:
    st.info("Select your name to continue.")
    st.stop()

confirmed = st.checkbox(f"I confirm that I am {selected_name}")
if not confirmed:
    st.warning("Please confirm your name before continuing.")
    st.stop()

try:
    worksheet = get_worksheet()
    rows = worksheet.get_all_values()
except Exception as exc:
    st.error(
        "Could not connect to Google Sheets. Check the Sheet URL, Streamlit Secrets, "
        "and that the spreadsheet is shared with the service-account email as Editor."
    )
    st.caption(f"Technical detail: {exc}")
    st.stop()

active_row = get_active_row(rows, selected_name)
if active_row is not None:
    st.success(f"{selected_name} is currently clocked in.")
else:
    st.info(f"{selected_name} is currently clocked out.")

col_in, col_out = st.columns(2)
with col_in:
    clock_in = st.button(
        "Clock In",
        type="primary",
        use_container_width=True,
        disabled=active_row is not None,
    )
with col_out:
    clock_out = st.button(
        "Clock Out",
        use_container_width=True,
        disabled=active_row is None,
    )

if clock_in:
    try:
        # Recheck the sheet before appending, to avoid duplicate active visits.
        latest_rows = worksheet.get_all_values()
        if get_active_row(latest_rows, selected_name) is not None:
            st.warning(f"{selected_name} is already clocked in.")
        else:
            now = california_now()
            # Each clock-in creates a fresh row; earlier visits are preserved.
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
            st.success(f"Clocked in at {now.strftime('%I:%M:%S %p')} on {now.strftime('%Y-%m-%d')}.")
            st.rerun()
    except Exception as exc:
        st.error("Clock-in failed.")
        st.caption(f"Technical detail: {exc}")

if clock_out:
    try:
        # Find the latest open visit again, then close that same row.
        latest_rows = worksheet.get_all_values()
        latest_active_row = get_active_row(latest_rows, selected_name)
        if latest_active_row is None:
            st.warning(f"No active clock-in was found for {selected_name}.")
        else:
            now = california_now()
            worksheet.update(
                range_name=f"D{latest_active_row}:F{latest_active_row}",
                values=[[
                    now.strftime("%Y-%m-%d"),
                    now.strftime("%I:%M:%S %p"),
                    "Clocked Out",
                ]],
            )
            st.success(f"Clocked out at {now.strftime('%I:%M:%S %p')} on {now.strftime('%Y-%m-%d')}.")
            st.rerun()
    except Exception as exc:
        st.error("Clock-out failed.")
        st.caption(f"Technical detail: {exc}")

st.divider()
st.subheader("Currently Clocked In")

try:
    latest_rows = worksheet.get_all_values()
    active_members = []
    for row in latest_rows[1:]:
        values = (row + [""] * len(HEADERS))[:len(HEADERS)]
        if values[5].strip().casefold() == "clocked in":
            active_members.append({
                "Name": values[0],
                "Start Date": values[1],
                "Start Time": values[2],
            })

    if active_members:
        st.dataframe(active_members, use_container_width=True, hide_index=True)
    else:
        st.write("Nobody is currently clocked in.")
except Exception:
    st.warning("Could not load the current clock-in list.")
