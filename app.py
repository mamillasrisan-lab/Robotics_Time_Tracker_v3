import html
from datetime import date, datetime, time, timedelta
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

import gspread
import streamlit as st
from google.oauth2.service_account import Credentials
from gspread.exceptions import APIError, WorksheetNotFound
from streamlit_js_eval import streamlit_js_eval

# ========================= SETTINGS =========================

SHEET_URL = "https://docs.google.com/spreadsheets/d/1eNZmloz7IozVoU_1cTsKVveUca73VMnjvySR9VMvz_g/edit"

MEMBERS = [
    "Alex Johnson",
    "Jordan Smith",
    "Taylor Lee",
]

LOCAL_SERVICE_ACCOUNT_FILE = r"C:\Users\Srithan\service_account.json"
WORKSHEET_NAME = "Attendance"
ATTENDANCE_WORKSHEET = "Attendance"
TASKS_WORKSHEET = "Tasks"
TIMEZONE = "America/Los_Angeles"

ATTENDANCE_HEADERS = [
    "Name",
    "Start Date",
    "Start Time",
    "End Date",
    "End Time",
    "Status",
    "Clock In Device ID",
    "Clock In Browser",
    "Reserved (No IP Tracking)",
    "Clock Out Device ID",
    "Clock Out Browser",
    "Reserved (No IP Tracking)",
    "Device Mismatch",
    "Total Time Spent",
]

TASK_HEADERS = [
    "Task ID",
    "Task",
    "Description",
    "Created By",
    "Assigned To",
    "Priority",
    "Due Date",
    "Status",
    "Created At",
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
        return Credentials.from_service_account_file(str(local_path), scopes=scopes)

    try:
        info = dict(st.secrets["gcp_service_account"])
    except Exception as exc:
        raise RuntimeError(
            "Google credentials are missing. Add gcp_service_account in "
            "Streamlit Community Cloud > App settings > Secrets."
        ) from exc

    private_key = info.get("private_key", "")
    if "\\n" in private_key and "\n" not in private_key:
        info["private_key"] = private_key.replace("\\n", "\n")

    return Credentials.from_service_account_info(info, scopes=scopes)


def get_spreadsheet():
    if not SHEET_URL.startswith("https://docs.google.com/spreadsheets/d/"):
        raise RuntimeError("The Google Sheet URL in app.py is not valid.")
    return gspread.authorize(get_credentials()).open_by_url(SHEET_URL)


def get_worksheet():
    spreadsheet = get_spreadsheet()
    return spreadsheet.worksheet(ATTENDANCE_WORKSHEET)


def column_letter(number):
    result = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        result = chr(65 + remainder) + result
    return result


def get_or_create_worksheet(title, headers):
    spreadsheet = get_spreadsheet()
    try:
        worksheet = spreadsheet.worksheet(title)
    except WorksheetNotFound:
        try:
            worksheet = spreadsheet.add_worksheet(title=title, rows=1000, cols=len(headers))
        except APIError:
            worksheet = spreadsheet.worksheet(title)

    if worksheet.col_count < len(headers):
        worksheet.resize(cols=len(headers))

    worksheet.update(range_name=f"A1:{column_letter(len(headers))}1", values=[headers])
    return worksheet


def get_attendance_worksheet():
    worksheet = get_or_create_worksheet(ATTENDANCE_WORKSHEET, ATTENDANCE_HEADERS)
    backfill_missing_visit_totals(worksheet)
    return worksheet


def get_tasks_worksheet():
    return get_or_create_worksheet(TASKS_WORKSHEET, TASK_HEADERS)


# ========================= TIME HELPERS =========================


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
    total_seconds = max(0, int(total_seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


# ========================= ATTENDANCE HELPERS =========================


def get_active_row(rows, member_name):
    """Return the latest active visit row for this member."""
    active_row = None
    for row_number, row in enumerate(rows[1:], start=2):
        values = (row + [""] * len(ATTENDANCE_HEADERS))[: len(ATTENDANCE_HEADERS)]
        if values[0].strip().casefold() == member_name.casefold() and values[5].strip().casefold() == "clocked in":
            active_row = row_number
    return active_row


def visit_end_datetime(values, now):
    status = (values[5].strip() if len(values) > 5 else "").casefold()
    if status == "clocked in" or not values[3].strip() or not values[4].strip():
        return now, True
    end_dt = parse_sheet_datetime(values[3], values[4])
    return end_dt, False


def total_time_for_member(rows, member_name, period_start, period_end, now):
    total_seconds = 0.0
    for row in rows[1:]:
        values = (row + [""] * len(ATTENDANCE_HEADERS))[: len(ATTENDANCE_HEADERS)]
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
    """Fill missing totals for completed visits."""
    try:
        rows = worksheet.get_all_values()
        updates = []
        for row_number, row in enumerate(rows[1:], start=2):
            values = (row + [""] * len(ATTENDANCE_HEADERS))[: len(ATTENDANCE_HEADERS)]
            if len(values) < 14:
                continue
            if values[13].strip():
                continue
            if values[5].strip().casefold() != "clocked out":
                continue

            start_dt = parse_sheet_datetime(values[1], values[2])
            end_dt = parse_sheet_datetime(values[3], values[4])
            if start_dt is None or end_dt is None or end_dt < start_dt:
                continue

            updates.append({"range": f"N{row_number}", "values": [[format_duration((end_dt - start_dt).total_seconds())]]})

        if updates:
            worksheet.batch_update(updates, value_input_option="RAW")
    except Exception:
        pass


# ========================= SELECTION HELPERS =========================


def reset_person_selection():
    st.session_state["member_search"] = ""
    st.session_state["selected_member"] = ""
    st.session_state["confirm_member"] = False


# ========================= DEVICE REGISTRATION =========================


def get_device_metadata():
    """Create/read a persistent browser registration ID."""
    try:
        device_id = streamlit_js_eval(
            js_expressions="""(() => {
                const key = 'robotics_time_tracker_device_id';
                let id = localStorage.getItem(key);
                if (!id) {
                    id = crypto.randomUUID ? crypto.randomUUID() : 'dev-' + Date.now() + '-' + Math.random().toString(16).slice(2);
                    localStorage.setItem(key, id);
                }
                return id;
            })()""",
            key="persistent_device_id_component",
        )
        browser = streamlit_js_eval(
            js_expressions="""(() => navigator.userAgent || '')()""",
            key="browser_user_agent_component",
        )
    except Exception:
        device_id = ""
        browser = ""

    device_id = str(device_id).strip() if device_id else ""
    browser = str(browser).strip() if browser else ""

    st.session_state["audit_device_id"] = device_id or "Unavailable"
    st.session_state["audit_browser"] = browser or "Unavailable"
    return device_id, browser


# ========================= CLOCK ACTIONS =========================


def clock_in_callback():
    member_name = st.session_state.get("selected_member", "")
    if not member_name:
        return

    try:
        worksheet = get_attendance_worksheet()
        rows = worksheet.get_all_values()
        if get_active_row(rows, member_name) is not None:
            st.session_state["last_action_message"] = f"{member_name} is already clocked in."
            return

        action_time = california_now()
        row = [
            member_name,
            action_time.strftime("%Y-%m-%d"),
            action_time.strftime("%I:%M:%S %p"),
            "",
            "",
            "Clocked In",
            st.session_state.get("audit_device_id", "Unavailable"),
            st.session_state.get("audit_browser", "Unavailable"),
            "",
            "",
            "",
            "",
            "",
            "",
        ]
        worksheet.append_row(row, value_input_option="RAW", insert_data_option="INSERT_ROWS")
        st.session_state["last_action_message"] = (
            f"{member_name} clocked in at {action_time.strftime('%I:%M:%S %p')} on {action_time.strftime('%Y-%m-%d')}."
        )
        reset_person_selection()
    except Exception as exc:
        st.session_state["last_action_message"] = f"Clock-in failed: {exc}"


def clock_out_callback():
    member_name = st.session_state.get("selected_member", "")
    if not member_name:
        return

    try:
        worksheet = get_attendance_worksheet()
        rows = worksheet.get_all_values()
        active_row = get_active_row(rows, member_name)
        if active_row is None:
            st.session_state["last_action_message"] = f"No active clock-in was found for {member_name}."
            return

        action_time = california_now()
        old_row = (rows[active_row - 1] + [""] * len(ATTENDANCE_HEADERS))[: len(ATTENDANCE_HEADERS)]
        start_dt = parse_sheet_datetime(old_row[1], old_row[2])

        end_date = action_time.strftime("%Y-%m-%d")
        end_time = action_time.strftime("%I:%M:%S %p")

        clock_in_device_id = old_row[6]
        clock_out_device_id = st.session_state.get("audit_device_id", "Unavailable")
        clock_in_browser = old_row[7]
        clock_out_browser = st.session_state.get("audit_browser", "Unavailable")

        mismatch = "Unknown"
        if (
            clock_in_device_id
            and clock_out_device_id
            and clock_in_device_id != "Unavailable"
            and clock_out_device_id != "Unavailable"
        ):
            mismatch = "Yes" if clock_in_device_id != clock_out_device_id else "No"

        total_time_text = "Unavailable"
        if start_dt is not None and action_time >= start_dt:
            total_time_text = format_duration((action_time - start_dt).total_seconds())

        worksheet.update(range_name=f"D{active_row}:F{active_row}", values=[[end_date, end_time, "Clocked Out"]])
        worksheet.update(
            range_name=f"J{active_row}:N{active_row}",
            values=[[clock_out_device_id, clock_out_browser, "", mismatch, total_time_text, ""]],
        )

        st.session_state["last_action_message"] = (
            f"{member_name} clocked out at {action_time.strftime('%I:%M:%S %p')} on {action_time.strftime('%Y-%m-%d')}."
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
    member_options = sorted(set(MEMBERS), key=str.casefold)

    with st.form("create_task_form", clear_on_submit=True):
        st.subheader("Create a task")
        task_title = st.text_input("Task name")
        task_description = st.text_area("Description (optional)")
        col1, col2 = st.columns(2)
        with col1:
            default_creator_index = member_options.index(default_creator) if default_creator in member_options else 0
            task_creator = st.selectbox("Created by", options=member_options, index=default_creator_index)
            task_assignee = st.selectbox("Assign to", options=member_options)
        with col2:
            task_priority = st.selectbox("Priority", TASK_PRIORITIES, index=1)
            has_due_date = st.checkbox("Set a due date")
            task_due_date = st.date_input("Due date", value=california_now().date(), disabled=not has_due_date)
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
        st.error("Could not load the task board from Google Sheets.")
        st.caption(f"Technical detail: {exc}")
        task_rows = [TASK_HEADERS]

    task_records = []
    task_row_lookup = {}
    for sheet_row_number, raw_row in enumerate(task_rows[1:], start=2):
        values = (raw_row + [""] * len(TASK_HEADERS))[: len(TASK_HEADERS)]
        task_id = values[0].strip()
        if not task_id:
            continue
        task_row_lookup[task_id] = sheet_row_number
        task_records.append(
            {
                "Task ID": task_id,
                "Task": values[1],
                "Description": values[2],
                "Created By": values[3],
                "Assigned To": values[4],
                "Priority": values[5],
                "Due Date": values[6] or "—",
                "Status": values[7] or "To Do",
                "Created At": values[8],
            }
        )

    if not task_records:
        st.info("No tasks yet. Create a task above to get started.")
        return

    filter_col1, filter_col2 = st.columns(2)
    with filter_col1:
        status_filter = st.selectbox("Filter tasks by status", ["All statuses"] + TASK_STATUSES, key="task_status_filter")
    with filter_col2:
        assignee_filter = st.selectbox("Filter tasks by assignee", ["All members"] + member_options, key="task_assignee_filter")

    visible_tasks = [
        task
        for task in task_records
        if (status_filter == "All statuses" or task["Status"] == status_filter)
        and (assignee_filter == "All members" or task["Assigned To"] == assignee_filter)
    ]
    display_tasks = [{key: value for key, value in task.items() if key != "Task ID"} for task in visible_tasks]
    st.dataframe(display_tasks, use_container_width=True, hide_index=True)

    st.subheader("Update a task's status")
    task_options = {
        f'{task["Task"]} — {task["Assigned To"]} [{task["Priority"]}] ({task["Task ID"][:8]})': task["Task ID"]
        for task in task_records
    }

    update_col1, update_col2 = st.columns(2)
    with update_col1:
        selected_task_label = st.selectbox("Choose a task", options=list(task_options.keys()), key="selected_task_to_update")
    with update_col2:
        selected_task_id = task_options[selected_task_label]
        current_status = next((task["Status"] for task in task_records if task["Task ID"] == selected_task_id), "To Do")
        status_index = TASK_STATUSES.index(current_status) if current_status in TASK_STATUSES else 0
        selected_task_status = st.selectbox("New status", options=TASK_STATUSES, index=status_index, key="selected_task_new_status")

    if st.button("Save Task Status", use_container_width=True):
        target_row = task_row_lookup[selected_task_id]
        try:
            tasks_worksheet.update(range_name=f"H{target_row}", values=[[selected_task_status]])
            st.success("Task status updated.")
            st.rerun()
        except Exception as exc:
            st.error("Could not update the task status.")
            st.caption(f"Technical detail: {exc}")


# ========================= APP UI =========================


def app():
    st.title("Robotics Team Time Tracker")
    st.write(
        "The home page shows everyone's time for today. Members can clock in or out below. "
        "Each new visit is saved as a separate row. Track attendance, review time reports, "
        "and manage shared team tasks. Time is recorded in California time. This app does not collect IP addresses."
    )

    device_id, browser_user_agent = get_device_metadata()
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
                <span style="font-family: monospace;">{safe_device_id}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.info("Loading browser device information. If it remains unavailable, reload the page and check that browser storage is enabled.")

    if not SHEET_URL.startswith("https://docs.google.com/spreadsheets/d/"):
        st.error("The Google Sheet URL in app.py is not valid.")
        st.stop()

    if not MEMBERS or any(not name.strip() for name in MEMBERS):
        st.error("Add valid names to the MEMBERS list near the top of app.py.")
        st.stop()

    if st.button("Home / Next Person", use_container_width=True, on_click=reset_person_selection):
        st.rerun()

    if st.session_state.get("last_action_message"):
        st.success(st.session_state.pop("last_action_message"))

    try:
        worksheet = get_attendance_worksheet()
        rows = worksheet.get_all_values()
    except Exception as exc:
        st.error(
            "Could not connect to Google Sheets. Check the Sheet URL, Streamlit Secrets, and make sure the spreadsheet is shared with the service-account email as Editor."
        )
        st.caption(f"Technical detail: {exc}")
        st.stop()

    now = california_now()
    today_start = datetime.combine(now.date(), time.min, tzinfo=ZoneInfo(TIMEZONE))
    tomorrow_start = today_start + timedelta(days=1)

    st.divider()
    st.subheader("Today's Team Time Tracker")
    st.caption(f"Time is calculated using California time for {now.strftime('%B %d, %Y')}.")

    today_summary = []
    for member in sorted(set(MEMBERS), key=str.casefold):
        total_seconds = total_time_for_member(rows, member, today_start, tomorrow_start, now)
        active_row = get_active_row(rows, member)
        active_start_text = "—"
        if active_row is not None:
            active_values = (rows[active_row - 1] + [""] * len(ATTENDANCE_HEADERS))[: len(ATTENDANCE_HEADERS)]
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

    st.divider()
    st.subheader("Clock In or Clock Out")

    search_text = st.text_input("Search for a team member", placeholder="Start typing their name...", key="member_search")
    if search_text.strip():
        matches = [member for member in MEMBERS if search_text.strip().casefold() in member.casefold()]
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
            confirmed = st.checkbox(f"I confirm that I am {selected_name}", key="confirm_member")
            if confirmed:
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

    st.divider()
    st.subheader("Time Spent Report")
    st.write(
        "Choose a team member and a date range to see their total recorded time. "
        "Only the part of each visit that overlaps the selected dates is counted."
    )

    report_col1, report_col2 = st.columns(2)
    with report_col1:
        report_member = st.selectbox("Team member for report", options=sorted(set(MEMBERS), key=str.casefold), key="report_member")
    with report_col2:
        today_date = california_now().date()
        first_day_of_month = today_date.replace(day=1)
        report_dates = st.date_input("Date range (inclusive)", value=(first_day_of_month, today_date), key="report_dates")

    if isinstance(report_dates, (tuple, list)) and len(report_dates) == 2:
        range_start, range_end = report_dates
    elif isinstance(report_dates, date):
        range_start = range_end = report_dates
    else:
        range_start = range_end = None

    if range_start and range_end:
        if range_start > range_end:
            st.error("The start date must be on or before the end date.")
        else:
            range_start_dt = datetime.combine(range_start, time.min, tzinfo=ZoneInfo(TIMEZONE))
            range_end_dt = datetime.combine(range_end + timedelta(days=1), time.min, tzinfo=ZoneInfo(TIMEZONE))
            report_now = california_now()
            report_seconds = total_time_for_member(rows, report_member, range_start_dt, range_end_dt, report_now)
            st.metric(f"Total time for {report_member}", format_duration(report_seconds))
            st.caption(f"Dates included: {range_start.strftime('%b %d, %Y')} – {range_end.strftime('%b %d, %Y')} (California time).")

            visit_details = []
            for row in rows[1:]:
                values = (row + [""] * len(ATTENDANCE_HEADERS))[: len(ATTENDANCE_HEADERS)]
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
                            "End": "Currently clocked in" if currently_active else end_dt.strftime("%Y-%m-%d %I:%M:%S %p"),
                            "Time in Selected Range": format_duration(seconds),
                        }
                    )

            if visit_details:
                st.dataframe(visit_details, use_container_width=True, hide_index=True)
            else:
                st.info("No recorded time for this person in the selected date range.")

    show_task_tracker()


if __name__ == "__main__":
    app()
