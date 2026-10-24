import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from gspread.exceptions import WorksheetNotFound, APIError
from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path

# ========================= SETTINGS =========================
SHEET_URL = "https://docs.google.com/spreadsheets/d/1eNZmloz7IozVoU_1cTsKVveUca73VMnjvySR9VMvz_g/edit"

# Replace the sample names with your real team roster.
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

    # Fix JSON-style escaped newlines if they were pasted literally into Secrets.
    key = info.get("private_key", "")
    if "\\n" in key and "\n" not in key:
        info["private_key"] = key.replace("\\n", "\n")
    return Credentials.from_service_account_info(info, scopes=scopes)


def get_worksheet():
    spreadsheet = gspread.authorize(get_credentials()).open_by_url(SHEET_URL)
    try:
        worksheet = spreadsheet.worksheet(WORKSHEET_NAME)
    except WorksheetNotFound:
        try:
            worksheet = spreadsheet.add_worksheet(
                title=WORKSHEET_NAME, rows=1000, cols=len(HEADERS)
            )
        except APIError:
            # Another app session may have created it at the same time.
            worksheet = spreadsheet.worksheet(WORKSHEET_NAME)

    if not worksheet.row_values(1):
        worksheet.update(range_name="A1:F1", values=[HEADERS])
    return worksheet


def get_active_row(rows, member_name):
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


def parse_sheet_datetime(date_text, time_text):
    """Parse the date and time format used by this app's Google Sheet."""
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
        except ValueError:
            continue
    if parsed_time is None:
        return None

    return datetime.combine(parsed_date, parsed_time, tzinfo=ZoneInfo(TIMEZONE))


def format_duration(total_seconds):
    total_minutes = max(0, int(total_seconds // 60))
    hours, minutes = divmod(total_minutes, 60)
    return f"{hours} hr {minutes} min"


# ========================= APP UI =========================
st.set_page_config(page_title="Robotics Team Time Tracker", page_icon="🕒")
st.title("🕒 Robotics Team Time Tracker")
st.write("Search for your name, confirm it, and clock in or out. After each action, the app resets for the next person.")

if not SHEET_URL.startswith("https://docs.google.com/spreadsheets/d/"):
    st.error("The Google Sheet URL in app.py is not valid.")
    st.stop()
if not MEMBERS or any(not name.strip() for name in MEMBERS):
    st.error("Add valid names to the MEMBERS list near the top of app.py.")
    st.stop()

# The home button can be used at any time to reset for the next person.
if st.button("🏠 Home / Next Person", use_container_width=True):
    st.session_state["member_search"] = ""
    st.session_state["selected_member"] = ""
    st.session_state["confirm_member"] = False
    st.rerun()

search_text = st.text_input(
    "Search for your name",
    placeholder="Start typing your name...",
    key="member_search",
)
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
    key="selected_member",
)
if not selected_name:
    st.info("Select your name to continue.")
    st.stop()

confirmed = st.checkbox(f"I confirm that I am {selected_name}", key="confirm_member")
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
    clock_in_clicked = st.button(
        "Clock In", type="primary", use_container_width=True,
        disabled=active_row is not None,
    )
with col_out:
    clock_out_clicked = st.button(
        "Clock Out", use_container_width=True,
        disabled=active_row is None,
    )

if clock_in_clicked:
    try:
        latest_rows = worksheet.get_all_values()
        if get_active_row(latest_rows, selected_name) is not None:
            st.warning(f"{selected_name} is already clocked in.")
        else:
            now = california_now()
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
            st.session_state["last_action_message"] = (
                f"{selected_name} clocked in at {now.strftime('%I:%M:%S %p')} "
                f"on {now.strftime('%Y-%m-%d')}."
            )
            st.session_state["member_search"] = ""
            st.session_state["selected_member"] = ""
            st.session_state["confirm_member"] = False
            st.rerun()
    except Exception as exc:
        st.error("Clock-in failed.")
        st.caption(f"Technical detail: {exc}")

if clock_out_clicked:
    try:
        latest_rows = worksheet.get_all_values()
        active_row_latest = get_active_row(latest_rows, selected_name)
        if active_row_latest is None:
            st.warning(f"No active clock-in was found for {selected_name}.")
        else:
            now = california_now()
            worksheet.update(
                range_name=f"D{active_row_latest}:F{active_row_latest}",
                values=[[
                    now.strftime("%Y-%m-%d"),
                    now.strftime("%I:%M:%S %p"),
                    "Clocked Out",
                ]],
            )
            st.session_state["last_action_message"] = (
                f"{selected_name} clocked out at {now.strftime('%I:%M:%S %p')} "
                f"on {now.strftime('%Y-%m-%d')}."
            )
            st.session_state["member_search"] = ""
            st.session_state["selected_member"] = ""
            st.session_state["confirm_member"] = False
            st.rerun()
    except Exception as exc:
        st.error("Clock-out failed.")
        st.caption(f"Technical detail: {exc}")

if st.session_state.get("last_action_message"):
    st.success(st.session_state["last_action_message"])

st.divider()
st.subheader("Currently Clocked In")
try:
    current_rows = worksheet.get_all_values()
    active_members = []
    for row in current_rows[1:]:
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

# ========================= TIME REPORT =========================
st.divider()
st.subheader("Time Spent Report")
st.write(
    "Choose a team member and date range to see the total time recorded. "
    "Visits are counted only for the part that overlaps the selected dates. "
    "A visit that is still clocked in is counted through the current time."
)

report_col1, report_col2 = st.columns(2)
with report_col1:
    report_member = st.selectbox(
        "Team member",
        options=sorted(set(MEMBERS), key=str.casefold),
        key="report_member",
    )
with report_col2:
    today_local = california_now().date()
    default_start = today_local.replace(day=1)
    report_dates = st.date_input(
        "Date range (inclusive)",
        value=(default_start, today_local),
        key="report_dates",
    )

if isinstance(report_dates, (tuple, list)) and len(report_dates) == 2:
    range_start, range_end = report_dates
elif isinstance(report_dates, date):
    range_start = report_dates
    range_end = report_dates
else:
    range_start = None
    range_end = None

if range_start and range_end:
    if range_start > range_end:
        st.error("The start date must be on or before the end date.")
    else:
        range_start_dt = datetime.combine(
            range_start, time.min, tzinfo=ZoneInfo(TIMEZONE)
        )
        range_end_dt = datetime.combine(
            range_end + timedelta(days=1), time.min, tzinfo=ZoneInfo(TIMEZONE)
        )
        now = california_now()
        report_seconds = 0
        visit_details = []
        unparsed_rows = 0

        # Refresh the sheet so the report includes the latest clock-in/out.
        try:
            report_rows = worksheet.get_all_values()
        except Exception:
            report_rows = rows

        for row_number, row in enumerate(report_rows[1:], start=2):
            values = (row + [""] * len(HEADERS))[:len(HEADERS)]
            if values[0].strip().casefold() != report_member.casefold():
                continue

            start_dt = parse_sheet_datetime(values[1], values[2])
            if start_dt is None:
                # Ignore completely empty rows, but flag rows for this person
                # that have data yet cannot be interpreted.
                if any(value.strip() for value in values):
                    unparsed_rows += 1
                continue

            status = values[5].strip().casefold()
            if status == "clocked in" or not values[3].strip() or not values[4].strip():
                end_dt = now
                currently_active = True
            else:
                end_dt = parse_sheet_datetime(values[3], values[4])
                currently_active = False
                if end_dt is None:
                    unparsed_rows += 1
                    continue

            if end_dt < start_dt:
                unparsed_rows += 1
                continue

            overlap_start = max(start_dt, range_start_dt)
            overlap_end = min(end_dt, range_end_dt, now)
            seconds = max(0, (overlap_end - overlap_start).total_seconds())
            if seconds <= 0:
                continue

            report_seconds += seconds
            visit_details.append({
                "Start": start_dt.strftime("%Y-%m-%d %I:%M:%S %p"),
                "End": "Currently clocked in" if currently_active else end_dt.strftime("%Y-%m-%d %I:%M:%S %p"),
                "Time in selected range": format_duration(seconds),
            })

        st.metric(
            f"Total time for {report_member}",
            format_duration(report_seconds),
        )
        st.caption(
            f"Dates included: {range_start.strftime('%b %d, %Y')} – "
            f"{range_end.strftime('%b %d, %Y')} (California time)."
        )
        if visit_details:
            st.dataframe(visit_details, use_container_width=True, hide_index=True)
        else:
            st.info("No recorded time for this person in the selected date range.")
        if unparsed_rows:
            st.warning(
                f"{unparsed_rows} row(s) for this person could not be included "
                "because their date or time values were missing or in an unrecognized format."
            )
