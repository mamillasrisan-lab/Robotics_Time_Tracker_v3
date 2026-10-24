import html
from pathlib import Path
from datetime import datetime, date, time, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from gspread.exceptions import WorksheetNotFound, APIError
from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
from streamlit_js_eval import streamlit_js_eval
import html

# ========================= SETTINGS =========================

SHEET_URL = "https://docs.google.com/spreadsheets/d/1eNZmloz7IozVoU_1cTsKVveUca73VMnjvySR9VMvz_g/edit"

MEMBERS = [
    "Alex Johnson",
    "Jordan Smith",
    "Taylor Lee",
]

MEMBERS = ["Alex Johnson", "Jordan Smith", "Taylor Lee"]  # Replace with your team's names.
LOCAL_SERVICE_ACCOUNT_FILE = r"C:\Users\Srithan\service_account.json"
WORKSHEET_NAME = "Attendance"
TIMEZONE = "America/Los_Angeles"

# Keep the existing 14-column structure so existing reports still work.
# Columns I and L are retained but are no longer used for IP addresses.
HEADERS = [
    "Name",
    "Start Date",
    "Start Time",
    "End Date",
    "End Time",
    "Status",
    "Clock In Device ID",
    "Clock In Browser",
    "Unused",
    "Clock Out Device ID",
    "Clock Out Browser",
    "Unused",
    "Device Mismatch",
    "Total Time Spent",
ATTENDANCE_WORKSHEET = "Attendance"
TASKS_WORKSHEET = "Tasks"

# Keep the original 14-column attendance layout for compatibility with existing data.
# IP columns are deliberately renamed and never collected or written to.
ATTENDANCE_HEADERS = [
    "Name", "Start Date", "Start Time", "End Date", "End Time", "Status",
    "Clock In Device ID", "Clock In Browser", "Reserved (No IP Tracking)",
    "Clock Out Device ID", "Clock Out Browser", "Reserved (No IP Tracking)",
    "Device Mismatch", "Total Time Spent",
]
TASK_HEADERS = [
    "Task ID", "Task", "Description", "Created By", "Assigned To",
    "Priority", "Due Date", "Status", "Created At",
]
TASK_STATUSES = ["To Do", "In Progress", "Blocked", "Completed"]
TASK_PRIORITIES = ["Low", "Medium", "High", "Urgent"]

st.set_page_config(
    page_title="Robotics Team Time Tracker",
    page_icon="🕒",
    layout="wide",
)

# ========================= GOOGLE SHEETS =========================

def get_credentials():
scopes = [
"https://www.googleapis.com/auth/spreadsheets",
"https://www.googleapis.com/auth/drive",
]

local_path = Path(LOCAL_SERVICE_ACCOUNT_FILE)

if local_path.is_file():
        return Credentials.from_service_account_file(
            str(local_path),
            scopes=scopes,
        )
        return Credentials.from_service_account_file(str(local_path), scopes=scopes)

try:
info = dict(st.secrets["gcp_service_account"])
except Exception as exc:
raise RuntimeError(
            "Google credentials are missing. Add gcp_service_account "
            "in Streamlit Community Cloud > App settings > Secrets."
            "Google credentials are missing. Add gcp_service_account in "
            "Streamlit Community Cloud → App settings → Secrets."
) from exc

private_key = info.get("private_key", "")

if "\\n" in private_key and "\n" not in private_key:
info["private_key"] = private_key.replace("\\n", "\n")
    return Credentials.from_service_account_info(info, scopes=scopes)

    return Credentials.from_service_account_info(
        info,
        scopes=scopes,
    )

def get_spreadsheet():
    if not SHEET_URL.startswith("https://docs.google.com/spreadsheets/d/"):
        raise RuntimeError("The Google Sheet URL in app.py is not valid.")
    return gspread.authorize(get_credentials()).open_by_url(SHEET_URL)

def get_worksheet():
    spreadsheet = gspread.authorize(
        get_credentials()
    ).open_by_url(SHEET_URL)

def get_or_create_worksheet(title, headers):
    spreadsheet = get_spreadsheet()
try:
        worksheet = spreadsheet.worksheet(WORKSHEET_NAME)
        worksheet = spreadsheet.worksheet(title)
except WorksheetNotFound:
try:
worksheet = spreadsheet.add_worksheet(
                title=WORKSHEET_NAME,
                rows=1000,
                cols=len(HEADERS),
                title=title, rows=1000, cols=len(headers)
)
except APIError:
            worksheet = spreadsheet.worksheet(WORKSHEET_NAME)
            # Another session may have created the tab at the same time.
            worksheet = spreadsheet.worksheet(title)

    if worksheet.col_count < len(HEADERS):
        worksheet.resize(cols=len(HEADERS))
    if worksheet.col_count < len(headers):
        worksheet.resize(cols=len(headers))
    worksheet.update(range_name=f"A1:{column_letter(len(headers))}1", values=[headers])
    return worksheet

    worksheet.update(
        range_name="A1:N1",
        values=[HEADERS],
    )

    backfill_missing_visit_totals(worksheet)
def column_letter(number):
    result = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        result = chr(65 + remainder) + result
    return result


def get_attendance_worksheet():
    worksheet = get_or_create_worksheet(ATTENDANCE_WORKSHEET, ATTENDANCE_HEADERS)
    backfill_missing_visit_totals(worksheet)
return worksheet


# ========================= TIME HELPERS =========================
def get_tasks_worksheet():
    return get_or_create_worksheet(TASKS_WORKSHEET, TASK_HEADERS)


# ========================= TIME / ATTENDANCE HELPERS =========================
def california_now():
return datetime.now(ZoneInfo(TIMEZONE))


def parse_sheet_datetime(date_text, time_text):
date_text = (date_text or "").strip()
time_text = (time_text or "").strip()

if not date_text or not time_text:
return None

parsed_date = None

for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
try:
            parsed_date = datetime.strptime(
                date_text,
                fmt,
            ).date()
            parsed_date = datetime.strptime(date_text, fmt).date()
break
except ValueError:
            continue

            pass
if parsed_date is None:
return None

parsed_time = None

    for fmt in (
        "%I:%M:%S %p",
        "%I:%M %p",
        "%H:%M:%S",
        "%H:%M",
    ):
    for fmt in ("%I:%M:%S %p", "%I:%M %p", "%H:%M:%S", "%H:%M"):
try:
            parsed_time = datetime.strptime(
                time_text,
                fmt,
            ).time()
            parsed_time = datetime.strptime(time_text, fmt).time()
break
except ValueError:
            continue

            pass
if parsed_time is None:
return None

    return datetime.combine(
        parsed_date,
        parsed_time,
        tzinfo=ZoneInfo(TIMEZONE),
    )
    return datetime.combine(parsed_date, parsed_time, tzinfo=ZoneInfo(TIMEZONE))


def format_duration(total_seconds):
@@ -175,154 +142,88 @@ def format_duration(total_seconds):


def get_active_row(rows, member_name):
    """Return the latest active visit row for this member."""
active_row = None

for row_number, row in enumerate(rows[1:], start=2):
        values = (row + [""] * len(HEADERS))[:len(HEADERS)]

        values = (row + [""] * len(ATTENDANCE_HEADERS))[:len(ATTENDANCE_HEADERS)]
if (
values[0].strip().casefold() == member_name.casefold()
and values[5].strip().casefold() == "clocked in"
):
active_row = row_number

return active_row


def visit_end_datetime(values, now):
    status = values[5].strip().casefold()

if (
        status == "clocked in"
        values[5].strip().casefold() == "clocked in"
or not values[3].strip()
or not values[4].strip()
):
return now, True
    return parse_sheet_datetime(values[3], values[4]), False

    end_dt = parse_sheet_datetime(values[3], values[4])

    return end_dt, False


def total_time_for_member(
    rows,
    member_name,
    period_start,
    period_end,
    now,
):
def total_time_for_member(rows, member_name, period_start, period_end, now):
total_seconds = 0

for row in rows[1:]:
        values = (row + [""] * len(HEADERS))[:len(HEADERS)]

        values = (row + [""] * len(ATTENDANCE_HEADERS))[:len(ATTENDANCE_HEADERS)]
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
            total_seconds += (
                overlap_end - overlap_start
            ).total_seconds()

            total_seconds += (overlap_end - overlap_start).total_seconds()
return total_seconds


def backfill_missing_visit_totals(worksheet):
    """Fill missing totals for completed visits."""
try:
rows = worksheet.get_all_values()
updates = []

for row_number, row in enumerate(rows[1:], start=2):
            values = (row + [""] * len(HEADERS))[:len(HEADERS)]

            if values[13].strip():
                continue

            if values[5].strip().casefold() != "clocked out":
            values = (row + [""] * len(ATTENDANCE_HEADERS))[:len(ATTENDANCE_HEADERS)]
            if values[13].strip() or values[5].strip().casefold() != "clocked out":
continue

start_dt = parse_sheet_datetime(values[1], values[2])
end_dt = parse_sheet_datetime(values[3], values[4])

            if (
                start_dt is None
                or end_dt is None
                or end_dt < start_dt
            ):
                continue

            duration_text = format_duration(
                (end_dt - start_dt).total_seconds()
            )

            updates.append({
                "range": f"N{row_number}",
                "values": [[duration_text]],
            })

            if start_dt and end_dt and end_dt >= start_dt:
                updates.append({
                    "range": f"N{row_number}",
                    "values": [[format_duration((end_dt - start_dt).total_seconds())]],
                })
if updates:
            worksheet.batch_update(
                updates,
                value_input_option="RAW",
            )

            worksheet.batch_update(updates, value_input_option="RAW")
except Exception:
        # Attendance should still work if historical backfilling fails.
        # Historical backfilling must not stop the app from loading.
pass


# ========================= SELECTION HELPERS =========================

def reset_person_selection():
st.session_state["member_search"] = ""
st.session_state["selected_member"] = ""
st.session_state["confirm_member"] = False


# ========================= DEVICE REGISTRATION =========================

# ========================= DEVICE ID (NO IP TRACKING) =========================
def get_device_metadata():
    """
    Create/read a persistent browser registration ID.

    The ID stays in browser localStorage. It is not a hardware fingerprint.
    Clearing browser storage may generate a new ID.
    """
    """Read a persistent browser ID and browser user-agent. No IP address is accessed."""
try:
device_id = streamlit_js_eval(
js_expressions="""(() => {
               const key = 'robotics_time_tracker_device_id';

               let id = localStorage.getItem(key);

               if (!id) {
                    id = crypto.randomUUID
                    id = (crypto.randomUUID)
                       ? crypto.randomUUID()
                        : (
                            'dev-' +
                            Date.now() +
                            '-' +
                            Math.random().toString(16).slice(2)
                        );

                        : ('dev-' + Date.now() + '-' + Math.random().toString(16).slice(2));
                   localStorage.setItem(key, id);
               }

               return id;
           })()""",
key="persistent_device_id_component",
@@ -340,96 +241,60 @@ def get_device_metadata():

device_id = str(device_id).strip() if device_id else ""
browser = str(browser).strip() if browser else ""

st.session_state["audit_device_id"] = device_id or "Unavailable"
st.session_state["audit_browser"] = browser or "Unavailable"

return device_id, browser


# ========================= CLOCK IN =========================

# ========================= ATTENDANCE ACTIONS =========================
def clock_in_callback():
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
        worksheet = get_attendance_worksheet()
        rows = worksheet.get_all_values()
        if get_active_row(rows, member_name) is not None:
            st.session_state["last_action_message"] = f"{member_name} is already clocked in."
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
                st.session_state.get(
                    "audit_device_id",
                    "Unavailable",
                ),
                st.session_state.get(
                    "audit_browser",
                    "Unavailable",
                ),
                "",  # Former IP column is unused
                "",  # Clock Out Device ID
                "",  # Clock Out Browser
                "",  # Former IP column is unused
                "",  # Device Mismatch
                "",  # Total Time Spent
                "", "", "Clocked In",
                st.session_state.get("audit_device_id", "Unavailable"),
                st.session_state.get("audit_browser", "Unavailable"),
                "",  # Reserved column; no IP tracking.
                "", "", "", "", "",
],
value_input_option="RAW",
insert_data_option="INSERT_ROWS",
)

st.session_state["last_action_message"] = (
            f"{member_name} clocked in at "
            f"{action_time.strftime('%I:%M:%S %p')} "
            f"{member_name} clocked in at {action_time.strftime('%I:%M:%S %p')} "
f"on {action_time.strftime('%Y-%m-%d')}."
)

reset_person_selection()

except Exception as exc:
        st.session_state["last_action_message"] = (
            f"Clock-in failed: {exc}"
        )

        st.session_state["last_action_message"] = f"Clock-in failed: {exc}"

# ========================= CLOCK OUT =========================

def clock_out_callback():
member_name = st.session_state.get("selected_member", "")

if not member_name:
return

try:
        worksheet = get_worksheet()
        latest_rows = worksheet.get_all_values()

        active_row = get_active_row(latest_rows, member_name)

        worksheet = get_attendance_worksheet()
        rows = worksheet.get_all_values()
        active_row = get_active_row(rows, member_name)
if active_row is None:
            st.session_state["last_action_message"] = (
                f"No active clock-in was found for {member_name}."
            )
            st.session_state["last_action_message"] = f"No active clock-in was found for {member_name}."
return

action_time = california_now()

        old_row = (rows[active_row - 1] + [""] * len(ATTENDANCE_HEADERS))[:len(ATTENDANCE_HEADERS)]
worksheet.update(
range_name=f"D{active_row}:F{active_row}",
values=[[
@@ -438,423 +303,375 @@ def clock_out_callback():
"Clocked Out",
]],
)

        start_values = (
            latest_rows[active_row - 1] + [""] * len(HEADERS)
        )[:len(HEADERS)]

        clock_in_device_id = start_values[6]
        clock_out_device_id = st.session_state.get(
            "audit_device_id",
            "Unavailable",
        )

        clock_in_device_id = old_row[6]
        clock_out_device_id = st.session_state.get("audit_device_id", "Unavailable")
if (
            clock_in_device_id
            and clock_out_device_id
            clock_in_device_id and clock_out_device_id
and clock_in_device_id != "Unavailable"
and clock_out_device_id != "Unavailable"
):
            mismatch = (
                "Yes"
                if clock_in_device_id != clock_out_device_id
                else "No"
            )
            mismatch = "Yes" if clock_in_device_id != clock_out_device_id else "No"
else:
mismatch = "Unknown"

        start_dt = parse_sheet_datetime(
            start_values[1],
            start_values[2],
        start_dt = parse_sheet_datetime(old_row[1], old_row[2])
        total_text = (
            format_duration((action_time - start_dt).total_seconds())
            if start_dt and action_time >= start_dt else "Unavailable"
)

        if start_dt is not None and action_time >= start_dt:
            total_time_text = format_duration(
                (action_time - start_dt).total_seconds()
            )
        else:
            total_time_text = "Unavailable"

worksheet.update(
range_name=f"J{active_row}:N{active_row}",
values=[[
clock_out_device_id,
                st.session_state.get(
                    "audit_browser",
                    "Unavailable",
                ),
                "",  # Former IP column is unused
                st.session_state.get("audit_browser", "Unavailable"),
                "",  # Reserved column; no IP tracking.
mismatch,
                total_time_text,
                total_text,
]],
)

st.session_state["last_action_message"] = (
            f"{member_name} clocked out at "
            f"{action_time.strftime('%I:%M:%S %p')} "
            f"{member_name} clocked out at {action_time.strftime('%I:%M:%S %p')} "
f"on {action_time.strftime('%Y-%m-%d')}."
)

reset_person_selection()
    except Exception as exc:
        st.session_state["last_action_message"] = f"Clock-out failed: {exc}"


# ========================= TASK TRACKER =========================
def show_task_tracker():
    st.divider()
    st.header("Task Tracker")
    st.write("Create shared tasks, assign them to team members, and track their progress.")

    default_creator = st.session_state.get("selected_member", "")
    with st.form("create_task_form", clear_on_submit=True):
        st.subheader("Create a task")
        task_title = st.text_input("Task name")
        task_description = st.text_area("Description (optional)")
        col1, col2 = st.columns(2)
        with col1:
            task_creator = st.selectbox(
                "Created by", options=sorted(set(MEMBERS), key=str.casefold),
                index=(sorted(set(MEMBERS), key=str.casefold).index(default_creator)
                       if default_creator in sorted(set(MEMBERS), key=str.casefold) else 0),
            )
            task_assignee = st.selectbox(
                "Assign to", options=sorted(set(MEMBERS), key=str.casefold)
            )
        with col2:
            task_priority = st.selectbox("Priority", TASK_PRIORITIES, index=1)
            has_due_date = st.checkbox("Set a due date")
            task_due_date = st.date_input("Due date", value=california_now().date(),
                                          disabled=not has_due_date)
        create_task = st.form_submit_button("Create Task", use_container_width=True)

    if create_task:
        if not task_title.strip():
            st.error("Enter a task name before creating the task.")
        else:
            try:
                tasks_worksheet = get_tasks_worksheet()
                created_at = california_now()
                tasks_worksheet.append_row(
                    [
                        str(uuid4()),
                        task_title.strip(),
                        task_description.strip(),
                        task_creator,
                        task_assignee,
                        task_priority,
                        task_due_date.strftime("%Y-%m-%d") if has_due_date else "",
                        "To Do",
                        created_at.strftime("%Y-%m-%d %I:%M:%S %p"),
                    ],
                    value_input_option="RAW",
                    insert_data_option="INSERT_ROWS",
                )
                st.success(f"Task created and assigned to {task_assignee}.")
                st.rerun()
            except Exception as exc:
                st.error("Could not save the task to Google Sheets.")
                st.caption(f"Technical detail: {exc}")

    try:
        tasks_worksheet = get_tasks_worksheet()
        task_rows = tasks_worksheet.get_all_values()
except Exception as exc:
        st.session_state["last_action_message"] = (
            f"Clock-out failed: {exc}"
        st.error("Could not load the task board from Google Sheets.")
        st.caption(f"Technical detail: {exc}")
        task_rows = [TASK_HEADERS]

    task_records = []
    task_row_lookup = {}
    for sheet_row_number, raw_row in enumerate(task_rows[1:], start=2):
        values = (raw_row + [""] * len(TASK_HEADERS))[:len(TASK_HEADERS)]
        task_id = values[0].strip()
        if not task_id:
            continue
        task_row_lookup[task_id] = sheet_row_number
        task_records.append({
            "Task ID": task_id,
            "Task": values[1],
            "Description": values[2],
            "Created By": values[3],
            "Assigned To": values[4],
            "Priority": values[5],
            "Due Date": values[6] or "—",
            "Status": values[7] or "To Do",
            "Created At": values[8],
        })

    if not task_records:
        st.info("No tasks yet. Create a task above to get started.")
        return

    filter_col1, filter_col2 = st.columns(2)
    with filter_col1:
        status_filter = st.selectbox(
            "Filter tasks by status", ["All statuses"] + TASK_STATUSES,
            key="task_status_filter",
        )
    with filter_col2:
        assignee_filter = st.selectbox(
            "Filter tasks by assignee",
            ["All members"] + sorted(set(MEMBERS), key=str.casefold),
            key="task_assignee_filter",
)

    visible_tasks = [
        task for task in task_records
        if (status_filter == "All statuses" or task["Status"] == status_filter)
        and (assignee_filter == "All members" or task["Assigned To"] == assignee_filter)
    ]
    display_tasks = [
        {key: value for key, value in task.items() if key != "Task ID"}
        for task in visible_tasks
    ]
    st.dataframe(display_tasks, use_container_width=True, hide_index=True)

    st.subheader("Update a task's status")
    task_options = {
        f'{task["Task"]} — {task["Assigned To"]} [{task["Priority"]}] ({task["Task ID"][:8]})':
            task["Task ID"]
        for task in task_records
    }
    update_col1, update_col2 = st.columns(2)
    with update_col1:
        selected_task_label = st.selectbox(
            "Choose a task", options=list(task_options.keys()),
            key="selected_task_to_update",
        )
    with update_col2:
        selected_task_id = task_options[selected_task_label]
        current_status = next(
            (task["Status"] for task in task_records if task["Task ID"] == selected_task_id),
            "To Do",
        )
        status_index = TASK_STATUSES.index(current_status) if current_status in TASK_STATUSES else 0
        selected_task_status = st.selectbox(
            "New status", options=TASK_STATUSES, index=status_index,
            key="selected_task_new_status",
        )

# ========================= APP UI =========================
    if st.button("Save Task Status", use_container_width=True):
        selected_task_id = task_options[selected_task_label]
        target_row = task_row_lookup[selected_task_id]
        try:
            tasks_worksheet.update(
                range_name=f"H{target_row}", values=[[selected_task_status]]
            )
            st.success("Task status updated.")
            st.rerun()
        except Exception as exc:
            st.error("Could not update the task status.")
            st.caption(f"Technical detail: {exc}")

st.title("Robotics Team Time Tracker")

# ========================= APP UI =========================
st.set_page_config(page_title="Robotics Team Time Tracker", page_icon="🕒", layout="wide")
st.title("Robotics Team Time Tracker")
st.write(
    "The home page shows everyone's time for today. "
    "Members can clock in or out below. Each new visit is saved "
    "as a separate row."
    "Track attendance, review time reports, and manage shared team tasks. "
    "Time is recorded in California time. This app does not collect IP addresses."
)

device_id, browser_user_agent = get_device_metadata()

# Registered device ID displayed in the top-right corner.
if device_id:
    safe_device_id = html.escape(device_id)

st.markdown(
f"""
       <div style="
            position: fixed;
            top: 0.8rem;
            right: 1.2rem;
            z-index: 999999;
            text-align: right;
            font-size: 0.78rem;
            line-height: 1.25;
            background: rgba(255,255,255,0.94);
            color: #222;
            padding: 0.4rem 0.65rem;
            border-radius: 0.45rem;
            border: 1px solid rgba(128,128,128,0.30);
            box-shadow: 0 1px 4px rgba(0,0,0,0.08);
            max-width: 45%;
            overflow-wrap: anywhere;
        ">
            <b>Registered Device</b><br>
            <span style="font-family: monospace;">
                {safe_device_id}
            </span>
            position: fixed; top: 0.8rem; right: 1.2rem; z-index: 999999;
            text-align: right; font-size: 0.78rem; line-height: 1.2;
            background: rgba(255,255,255,0.92); color: #222;
            padding: 0.35rem 0.55rem; border-radius: 0.4rem;
            border: 1px solid rgba(128,128,128,0.3); max-width: 45vw;
            overflow-wrap: anywhere;">
            <b>Registered Device</b><br>{html.escape(device_id)}
       </div>
       """,
unsafe_allow_html=True,
)
else:
    st.info(
        "Loading browser device information. If it remains unavailable, "
        "reload the page and check that browser storage is enabled."
    )

if not SHEET_URL.startswith(
    "https://docs.google.com/spreadsheets/d/"
):
    st.error("The Google Sheet URL in app.py is not valid.")
    st.stop()
    st.info("Loading browser device information… If this remains, reload the page and enable browser storage.")

if not MEMBERS or any(not name.strip() for name in MEMBERS):
st.error("Add valid names to the MEMBERS list near the top of app.py.")
st.stop()

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
    worksheet = get_attendance_worksheet()
rows = worksheet.get_all_values()

except Exception as exc:
st.error(
        "Could not connect to Google Sheets. Check the Sheet URL, "
        "Streamlit Secrets, and make sure the spreadsheet is shared "
        "with the service-account email as Editor."
        "Could not connect to Google Sheets. Check the Sheet URL and credentials, "
        "and share the spreadsheet with the service-account email as Editor."
)
st.caption(f"Technical detail: {exc}")
st.stop()

now = california_now()
home_col1, home_col2 = st.columns([1, 5])
with home_col1:
    if st.button("Home / Next Person", use_container_width=True, on_click=reset_person_selection):
        st.rerun()
if st.session_state.get("last_action_message"):
    st.success(st.session_state.pop("last_action_message"))

# ========================= DAILY DASHBOARD =========================

# ========================= HOME DASHBOARD =========================
st.divider()
st.subheader("Today's Team Time Tracker")

st.caption(
    "Time is calculated using California time for "
    f"{now.strftime('%B %d, %Y')}."
)

today_start = datetime.combine(
    now.date(),
    time.min,
    tzinfo=ZoneInfo(TIMEZONE),
)

st.caption(f"Daily totals for {now.strftime('%B %d, %Y')} (California time).")
today_start = datetime.combine(now.date(), time.min, tzinfo=ZoneInfo(TIMEZONE))
tomorrow_start = today_start + timedelta(days=1)
today_summary = []

for member in sorted(set(MEMBERS), key=str.casefold):
    total_seconds = total_time_for_member(
        rows,
        member,
        today_start,
        tomorrow_start,
        now,
    )

    seconds = total_time_for_member(rows, member, today_start, tomorrow_start, now)
active_row = get_active_row(rows, member)
active_start_text = "—"

if active_row is not None:
        active_values = (
            rows[active_row - 1] + [""] * len(HEADERS)
        )[:len(HEADERS)]

        active_start = parse_sheet_datetime(
            active_values[1],
            active_values[2],
        )

        active_values = (rows[active_row - 1] + [""] * len(ATTENDANCE_HEADERS))[:len(ATTENDANCE_HEADERS)]
        active_start = parse_sheet_datetime(active_values[1], active_values[2])
if active_start:
active_start_text = active_start.strftime("%I:%M:%S %p")

today_summary.append({
"Team Member": member,
        "Time Today": format_duration(total_seconds),
        "Status": (
            "Clocked In"
            if active_row is not None
            else "Clocked Out"
        ),
        "Time Today": format_duration(seconds),
        "Status": "Clocked In" if active_row is not None else "Clocked Out",
"Current Visit Started": active_start_text,
})

st.dataframe(
    today_summary,
    use_container_width=True,
    hide_index=True,
)
st.dataframe(today_summary, use_container_width=True, hide_index=True)

# ========================= CLOCK IN / CLOCK OUT =========================

st.divider()
st.subheader("Clock In or Clock Out")

search_text = st.text_input(
    "Search for a team member",
    placeholder="Start typing their name...",
    "Search for a team member", placeholder="Start typing their name...",
key="member_search",
)

if search_text.strip():
    matches = [
        member
        for member in MEMBERS
        if search_text.strip().casefold() in member.casefold()
    ]
else:
    matches = sorted(set(MEMBERS), key=str.casefold)

matches = (
    [member for member in MEMBERS if search_text.strip().casefold() in member.casefold()]
    if search_text.strip()
    else sorted(set(MEMBERS), key=str.casefold)
)
if not matches:
st.warning("No matching names found. Check the spelling.")

else:
selected_name = st.selectbox(
        "Select the full name",
        [""] + matches,
        format_func=lambda name: (
            "Choose a name..." if name == "" else name
        ),
        "Select the full name", [""] + matches,
        format_func=lambda name: "Choose a name..." if name == "" else name,
key="selected_member",
)

if selected_name:
        confirmed = st.checkbox(
            f"I confirm that I am {selected_name}",
            key="confirm_member",
        )

        confirmed = st.checkbox(f"I confirm that I am {selected_name}", key="confirm_member")
if confirmed:
rows = worksheet.get_all_values()
active_row = get_active_row(rows, selected_name)

            if active_row is not None:
                st.success(f"{selected_name} is currently clocked in.")
            else:
                st.info(f"{selected_name} is currently clocked out.")

            st.success(f"{selected_name} is currently clocked in.") if active_row else st.info(
                f"{selected_name} is currently clocked out."
            )
col_in, col_out = st.columns(2)

with col_in:
st.button(
                    "Clock In",
                    type="primary",
                    use_container_width=True,
                    "Clock In", type="primary", use_container_width=True,
disabled=active_row is not None or not device_id,
on_click=clock_in_callback,
)

with col_out:
st.button(
                    "Clock Out",
                    use_container_width=True,
                    "Clock Out", use_container_width=True,
disabled=active_row is None or not device_id,
on_click=clock_out_callback,
)

else:
            st.info(
                "Confirm the selected name to enable Clock In / Clock Out."
            )

            st.info("Confirm the selected name to enable Clock In / Clock Out.")
else:
st.info("Search for a name and select the correct person.")

# ========================= CUSTOM DATE-RANGE REPORT =========================

st.divider()
st.subheader("Time Spent Report")

st.write(
    "Choose a team member and a date range to see their total recorded "
    "time. Only the part of each visit that overlaps the selected dates "
    "is counted."
)

st.write("Choose a team member and date range. Only time overlapping the selected dates is counted.")
report_col1, report_col2 = st.columns(2)

with report_col1:
report_member = st.selectbox(
        "Team member for report",
        options=sorted(set(MEMBERS), key=str.casefold),
        "Team member for report", sorted(set(MEMBERS), key=str.casefold),
key="report_member",
)

with report_col2:
today_date = california_now().date()
    first_day_of_month = today_date.replace(day=1)

    first_day = today_date.replace(day=1)
report_dates = st.date_input(
        "Date range (inclusive)",
        value=(first_day_of_month, today_date),
        key="report_dates",
        "Date range (inclusive)", value=(first_day, today_date), key="report_dates"
)

if isinstance(report_dates, (tuple, list)) and len(report_dates) == 2:
range_start, range_end = report_dates
elif isinstance(report_dates, date):
    range_start = report_dates
    range_end = report_dates
    range_start = range_end = report_dates
else:
    range_start = None
    range_end = None
    range_start = range_end = None

if range_start and range_end:
if range_start > range_end:
st.error("The start date must be on or before the end date.")

else:
        range_start_dt = datetime.combine(
            range_start,
            time.min,
            tzinfo=ZoneInfo(TIMEZONE),
        )

        range_end_dt = datetime.combine(
            range_end + timedelta(days=1),
            time.min,
            tzinfo=ZoneInfo(TIMEZONE),
        )

        start_bound = datetime.combine(range_start, time.min, tzinfo=ZoneInfo(TIMEZONE))
        end_bound = datetime.combine(range_end + timedelta(days=1), time.min, tzinfo=ZoneInfo(TIMEZONE))
report_now = california_now()

        try:
            report_rows = worksheet.get_all_values()
        except Exception:
            report_rows = rows

        report_rows = worksheet.get_all_values()
report_seconds = total_time_for_member(
            report_rows,
            report_member,
            range_start_dt,
            range_end_dt,
            report_now,
            report_rows, report_member, start_bound, end_bound, report_now
)

        st.metric(
            f"Total time for {report_member}",
            format_duration(report_seconds),
        )

        st.metric(f"Total time for {report_member}", format_duration(report_seconds))
st.caption(
f"Dates included: {range_start.strftime('%b %d, %Y')} – "
f"{range_end.strftime('%b %d, %Y')} (California time)."
)

visit_details = []

for row in report_rows[1:]:
            values = (row + [""] * len(HEADERS))[:len(HEADERS)]

            values = (row + [""] * len(ATTENDANCE_HEADERS))[:len(ATTENDANCE_HEADERS)]
if values[0].strip().casefold() != report_member.casefold():
continue

start_dt = parse_sheet_datetime(values[1], values[2])

if start_dt is None:
continue

            end_dt, currently_active = visit_end_datetime(
                values,
                report_now,
            )

            end_dt, active = visit_end_datetime(values, report_now)
if end_dt is None or end_dt < start_dt:
continue

            overlap_start = max(start_dt, range_start_dt)
            overlap_end = min(end_dt, range_end_dt, report_now)

            seconds = max(
                0,
                (overlap_end - overlap_start).total_seconds(),
            )

            overlap_start = max(start_dt, start_bound)
            overlap_end = min(end_dt, end_bound, report_now)
            seconds = max(0, (overlap_end - overlap_start).total_seconds())
if seconds > 0:
visit_details.append({
                    "Start": start_dt.strftime(
                        "%Y-%m-%d %I:%M:%S %p"
                    ),
                    "End": (
                        "Currently clocked in"
                        if currently_active
                        else end_dt.strftime(
                            "%Y-%m-%d %I:%M:%S %p"
                        )
                    ),
                    "Start": start_dt.strftime("%Y-%m-%d %I:%M:%S %p"),
                    "End": "Currently clocked in" if active else end_dt.strftime("%Y-%m-%d %I:%M:%S %p"),
"Time in Selected Range": format_duration(seconds),
})

if visit_details:
            st.dataframe(
                visit_details,
                use_container_width=True,
                hide_index=True,
            )
            st.dataframe(visit_details, use_container_width=True, hide_index=True)
else:
            st.info(
                "No recorded time for this person in the selected date range."
            )
            st.info("No recorded time for this person in the selected date range.")

# ========================= TASK TRACKER =========================
show_task_tracker()
