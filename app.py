import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from gspread.exceptions import WorksheetNotFound, APIError
from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
from streamlit_js_eval import streamlit_js_eval

# ========================= SETTINGS =========================
SHEET_URL = "https://docs.google.com/spreadsheets/d/1eNZmloz7IozVoU_1cTsKVveUca73VMnjvySR9VMvz_g/edit"

# Team Names
MEMBERS = ["Alex Johnson", "Jordan Smith", "Taylor Lee"]

LOCAL_SERVICE_ACCOUNT_FILE = r"C:\Users\Srithan\service_account.json"
WORKSHEET_NAME = "Attendance"
TIMEZONE = "America/Los_Angeles"
HEADERS = [
    "Name", "Start Date", "Start Time", "End Date", "End Time", "Status",
    "Clock In Device ID", "Clock In Browser", "Clock In IP",
    "Clock Out Device ID", "Clock Out Browser", "Clock Out IP",
    "Device Mismatch", "Total Time Spent",
]


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

    # Ensure the sheet has enough columns and current audit headers.
    if worksheet.col_count < len(HEADERS):
        worksheet.resize(cols=len(HEADERS))
    worksheet.update(range_name="A1:N1", values=[HEADERS])
    backfill_missing_visit_totals(worksheet)

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
        except ValueError:
            continue

    if parsed_time is None:
        return None

    return datetime.combine(parsed_date, parsed_time, tzinfo=ZoneInfo(TIMEZONE))


def get_active_row(rows, member_name):
    """Return the most recent active visit row for a member, or None."""
    active_row = None

    for row_number, row in enumerate(rows[1:], start=2):
        values = (row + [""] * len(HEADERS))[:len(HEADERS)]
        if (
            values[0].strip().casefold() == member_name.casefold()
            and values[5].strip().casefold() == "clocked in"
        ):
            active_row = row_number

    return active_row


def format_duration(total_seconds):
    total_minutes = max(0, int(total_seconds // 60))
    hours, minutes = divmod(total_minutes, 60)
    return f"{hours} hr {minutes} min"


def visit_end_datetime(values, now):
    """Get the end time for a visit, using now for a currently active visit."""
    status = values[5].strip().casefold()
    if status == "clocked in" or not values[3].strip() or not values[4].strip():
        return now, True

    end_dt = parse_sheet_datetime(values[3], values[4])
    return end_dt, False


def total_time_for_member(rows, member_name, period_start, period_end, now):
    """Sum only the part of each visit overlapping the requested period."""
    total_seconds = 0

    for row in rows[1:]:
        values = (row + [""] * len(HEADERS))[:len(HEADERS)]
        if values[0].strip().casefold() != member_name.casefold():
            continue

        start_dt = parse_sheet_datetime(values[1], values[2])
        if start_dt is None:
            continue

        end_dt, _ = visit_end_datetime(values, now)
        if end_dt is None or end_dt < start_dt:
            continue

        overlap_start = max(start_dt, period_start)
        overlap_end = min(end_dt, period_end, now)
        if overlap_end > overlap_start:
            total_seconds += (overlap_end - overlap_start).total_seconds()

    return total_seconds


def backfill_missing_visit_totals(worksheet):
    """Fill totals for previously completed visits where the total column is blank."""
    try:
        rows = worksheet.get_all_values()
        updates = []
        for row_number, row in enumerate(rows[1:], start=2):
            values = (row + [""] * len(HEADERS))[:len(HEADERS)]
            if values[13].strip():
                continue
            if values[5].strip().casefold() != "clocked out":
                continue

            start_dt = parse_sheet_datetime(values[1], values[2])
            end_dt = parse_sheet_datetime(values[3], values[4])
            if start_dt is None or end_dt is None or end_dt < start_dt:
                continue

            duration_text = format_duration((end_dt - start_dt).total_seconds())
            updates.append({"range": f"N{row_number}", "values": [[duration_text]]})

        if updates:
            worksheet.batch_update(updates, value_input_option="RAW")
    except Exception:
        # Do not prevent attendance use if historical backfilling fails.
        pass


def reset_person_selection():
    """Reset widget values from a callback, before Streamlit recreates the widgets."""
    st.session_state["member_search"] = ""
    st.session_state["selected_member"] = ""
    st.session_state["confirm_member"] = False


def get_client_ip():
    """Read the visitor IP forwarded by the hosting proxy, when available."""
    try:
        headers = st.context.headers
        forwarded = headers.get("X-Forwarded-For", "")
        if forwarded:
            # Hosting proxies commonly append a comma-separated forwarding chain.
            return forwarded.split(",")[0].strip()
        return (
            headers.get("X-Real-IP", "").strip()
            or headers.get("CF-Connecting-IP", "").strip()
            or "Unavailable"
        )
    except Exception:
        return "Unavailable"


def get_device_metadata():
    """Read a persistent browser ID and browser user-agent from the visitor's browser."""
    try:
        device_id = streamlit_js_eval(
            js_expressions="""(() => {
                const key = 'robotics_time_tracker_device_id';
                let id = localStorage.getItem(key);
                if (!id) {
                    id = (crypto.randomUUID)
                        ? crypto.randomUUID()
                        : ('dev-' + Date.now() + '-' + Math.random().toString(16).slice(2));
                    localStorage.setItem(key, id);
                }
                return id;
            })()""",
            key="persistent_device_id_component",
        )
    except Exception:
        device_id = None

    try:
        browser = streamlit_js_eval(
            js_expressions="navigator.userAgent",
            key="browser_user_agent_component",
        )
    except Exception:
        browser = None

    device_id = str(device_id).strip() if device_id else ""
    browser = str(browser).strip() if browser else ""

    # Keep values available to the clock-action callbacks.
    st.session_state["audit_device_id"] = device_id or "Unavailable"
    st.session_state["audit_browser"] = browser or "Unavailable"
    st.session_state["audit_ip"] = get_client_ip()
    return device_id, browser


def clock_in_callback():
    """Save a clock-in and reset the member widgets safely."""
    member_name = st.session_state.get("selected_member", "")
    if not member_name:
        return

    try:
        worksheet = get_worksheet()
        latest_rows = worksheet.get_all_values()
        if get_active_row(latest_rows, member_name) is not None:
            st.session_state["last_action_message"] = (
                f"{member_name} is already clocked in."
            )
            return

        action_time = california_now()
        worksheet.append_row(
            [
                member_name,
                action_time.strftime("%Y-%m-%d"),
                action_time.strftime("%I:%M:%S %p"),
                "",
                "",
                "Clocked In",
                st.session_state.get("audit_device_id", "Unavailable"),
                st.session_state.get("audit_browser", "Unavailable"),
                st.session_state.get("audit_ip", "Unavailable"),
                "", "", "", "", "",
            ],
            value_input_option="RAW",
            insert_data_option="INSERT_ROWS",
        )
        st.session_state["last_action_message"] = (
            f"{member_name} clocked in at {action_time.strftime('%I:%M:%S %p')} "
            f"on {action_time.strftime('%Y-%m-%d')}."
        )
        reset_person_selection()
    except Exception as exc:
        st.session_state["last_action_message"] = f"Clock-in failed: {exc}"


def clock_out_callback():
    """Save a clock-out and reset the member widgets safely."""
    member_name = st.session_state.get("selected_member", "")
    if not member_name:
        return

    try:
        worksheet = get_worksheet()
        latest_rows = worksheet.get_all_values()
        active_row = get_active_row(latest_rows, member_name)

        if active_row is None:
            st.session_state["last_action_message"] = (
                f"No active clock-in was found for {member_name}."
            )
            return

        action_time = california_now()
        worksheet.update(
            range_name=f"D{active_row}:F{active_row}",
            values=[[
                action_time.strftime("%Y-%m-%d"),
                action_time.strftime("%I:%M:%S %p"),
                "Clocked Out",
            ]],
        )
        clock_in_device_id = (
            latest_rows[active_row - 1][6]
            if len(latest_rows[active_row - 1]) > 6 else ""
        )
        clock_out_device_id = st.session_state.get("audit_device_id", "Unavailable")
        mismatch = (
            "Yes"
            if clock_in_device_id and clock_out_device_id
            and clock_in_device_id != "Unavailable"
            and clock_out_device_id != "Unavailable"
            and clock_in_device_id != clock_out_device_id
            else "No" if clock_in_device_id and clock_out_device_id
            and clock_in_device_id != "Unavailable"
            and clock_out_device_id != "Unavailable"
            else "Unknown"
        )
        start_values = (latest_rows[active_row - 1] + [""] * len(HEADERS))[:len(HEADERS)]
        start_dt = parse_sheet_datetime(start_values[1], start_values[2])
        if start_dt is not None and action_time >= start_dt:
            total_time_text = format_duration((action_time - start_dt).total_seconds())
        else:
            total_time_text = "Unavailable"

        worksheet.update(
            range_name=f"J{active_row}:N{active_row}",
            values=[[
                clock_out_device_id,
                st.session_state.get("audit_browser", "Unavailable"),
                st.session_state.get("audit_ip", "Unavailable"),
                mismatch,
                total_time_text,
            ]],
        )
        st.session_state["last_action_message"] = (
            f"{member_name} clocked out at {action_time.strftime('%I:%M:%S %p')} "
            f"on {action_time.strftime('%Y-%m-%d')}."
        )
        reset_person_selection()
    except Exception as exc:
        st.session_state["last_action_message"] = f"Clock-out failed: {exc}"


# ========================= APP UI =========================
st.set_page_config(page_title="Robotics Team Time Tracker", page_icon="🕒")
st.title("Robotics Team Time Tracker")
st.write(
    "The home page shows everyone's time for today. Members can clock in or out "
    "below, and the app resets for the next person after each action."
)

device_id, browser_user_agent = get_device_metadata()
if not device_id:
    st.info(
        "Loading browser device information… If this message remains, reload the page "
        "and make sure browser storage is enabled."
    )

if not SHEET_URL.startswith("https://docs.google.com/spreadsheets/d/"):
    st.error("The Google Sheet URL in app.py is not valid.")
    st.stop()

if not MEMBERS or any(not name.strip() for name in MEMBERS):
    st.error("Add valid names to the MEMBERS list near the top of app.py.")
    st.stop()

# Home / Next Person resets the selection fields.
if st.button(
    "Home / Next Person",
    use_container_width=True,
    on_click=reset_person_selection,
):
    st.rerun()

if st.session_state.get("last_action_message"):
    st.success(st.session_state.pop("last_action_message"))

try:
    worksheet = get_worksheet()
    rows = worksheet.get_all_values()
except Exception as exc:
    st.error(
        "Could not connect to Google Sheets. Check the Sheet URL, Streamlit Secrets, "
        "and make sure the spreadsheet is shared with the service-account email as Editor."
    )
    st.caption(f"Technical detail: {exc}")
    st.stop()

now = california_now()

# ========================= HOME DASHBOARD =========================
st.divider()
st.subheader("Today's Team Time Tracker")
st.caption(
    f"Everyone is listed below. Time is calculated using California time for "
    f"{now.strftime('%B %d, %Y')}."
)

today_start = datetime.combine(now.date(), time.min, tzinfo=ZoneInfo(TIMEZONE))
tomorrow_start = today_start + timedelta(days=1)
today_summary = []

for member in sorted(set(MEMBERS), key=str.casefold):
    total_seconds = total_time_for_member(
        rows, member, today_start, tomorrow_start, now
    )
    active_row = get_active_row(rows, member)

    active_start_text = "—"
    if active_row is not None:
        active_values = (rows[active_row - 1] + [""] * len(HEADERS))[:len(HEADERS)]
        active_start = parse_sheet_datetime(active_values[1], active_values[2])
        if active_start:
            active_start_text = active_start.strftime("%I:%M:%S %p")

    today_summary.append(
        {
            "Team Member": member,
            "Time Today": format_duration(total_seconds),
            "Status": "Clocked In" if active_row is not None else "Clocked Out",
            "Current Visit Started": active_start_text,
        }
    )

st.dataframe(today_summary, use_container_width=True, hide_index=True)

# ========================= CLOCK IN / CLOCK OUT =========================
st.divider()
st.subheader("Clock In or Clock Out")

search_text = st.text_input(
    "Search for a team member",
    placeholder="Start typing their name...",
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
else:
    selected_name = st.selectbox(
        "Select the full name",
        [""] + matches,
        format_func=lambda name: "Choose a name..." if name == "" else name,
        key="selected_member",
    )

    if selected_name:
        confirmed = st.checkbox(
            f"I confirm that I am {selected_name}",
            key="confirm_member",
        )

        if confirmed:
            # Refresh the rows before deciding which button is available.
            rows = worksheet.get_all_values()
            active_row = get_active_row(rows, selected_name)

            if active_row is not None:
                st.success(f"{selected_name} is currently clocked in.")
            else:
                st.info(f"{selected_name} is currently clocked out.")

            col_in, col_out = st.columns(2)

            with col_in:
                st.button(
                    "Clock In",
                    type="primary",
                    use_container_width=True,
                    disabled=active_row is not None or not device_id,
                    on_click=clock_in_callback,
                )

            with col_out:
                st.button(
                    "Clock Out",
                    use_container_width=True,
                    disabled=active_row is None or not device_id,
                    on_click=clock_out_callback,
                )
        else:
            st.info("Confirm the selected name to enable Clock In / Clock Out.")
    else:
        st.info("Search for a name and select the correct person.")

# ========================= CUSTOM DATE-RANGE REPORT =========================
st.divider()
st.subheader("Time Spent Report")
st.write(
    "Choose a team member and a date range to see their total recorded time. "
    "Only the part of each visit that overlaps the selected dates is counted."
)

report_col1, report_col2 = st.columns(2)

with report_col1:
    report_member = st.selectbox(
        "Team member for report",
        options=sorted(set(MEMBERS), key=str.casefold),
        key="report_member",
    )

with report_col2:
    today_date = california_now().date()
    first_day_of_month = today_date.replace(day=1)
    report_dates = st.date_input(
        "Date range (inclusive)",
        value=(first_day_of_month, today_date),
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
        report_now = california_now()

        try:
            report_rows = worksheet.get_all_values()
        except Exception:
            report_rows = rows

        report_seconds = total_time_for_member(
            report_rows,
            report_member,
            range_start_dt,
            range_end_dt,
            report_now,
        )

        st.metric(
            f"Total time for {report_member}",
            format_duration(report_seconds),
        )
        st.caption(
            f"Dates included: {range_start.strftime('%b %d, %Y')} – "
            f"{range_end.strftime('%b %d, %Y')} (California time)."
        )

        visit_details = []
        for row in report_rows[1:]:
            values = (row + [""] * len(HEADERS))[:len(HEADERS)]
            if values[0].strip().casefold() != report_member.casefold():
                continue

            start_dt = parse_sheet_datetime(values[1], values[2])
            if start_dt is None:
                continue

            end_dt, currently_active = visit_end_datetime(values, report_now)
            if end_dt is None or end_dt < start_dt:
                continue

            overlap_start = max(start_dt, range_start_dt)
            overlap_end = min(end_dt, range_end_dt, report_now)
            seconds = max(0, (overlap_end - overlap_start).total_seconds())

            if seconds > 0:
                visit_details.append(
                    {
                        "Start": start_dt.strftime("%Y-%m-%d %I:%M:%S %p"),
                        "End": (
                            "Currently clocked in"
                            if currently_active
                            else end_dt.strftime("%Y-%m-%d %I:%M:%S %p")
                        ),
                        "Time in Selected Range": format_duration(seconds),
                    }
                )

        if visit_details:
            st.dataframe(visit_details, use_container_width=True, hide_index=True)
        else:
            st.info("No recorded time for this person in the selected date range.")
