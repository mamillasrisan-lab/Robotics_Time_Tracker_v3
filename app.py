import html
import os
from datetime import date, datetime, time, timedelta
from pathlib import Path
from time import sleep
from uuid import uuid4
from zoneinfo import ZoneInfo

import gspread
import pandas as pd
import streamlit as st
from google.oauth2.service_account import Credentials
from gspread.exceptions import APIError, WorksheetNotFound

# ========================= SETTINGS =========================

SHEET_URL = "https://docs.google.com/spreadsheets/d/1eNZmloz7IozVoU_1cTsKVveUca73VMnjvySR9VMvz_g/edit"

MEMBERS = [
    "Alex Johnson",
    "Jordan Smith",
    "Taylor Lee",
    "Test User 1",
    "Test User 2",
]

LOCAL_SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", r"C:\Users\Srithan\service_account.json")
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
    "Clock Out Device ID",
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
    page_title="HOSA Team Time Tracker",
    page_icon="🕒",
    layout="wide",
)

st.markdown(
    """
    <style>
        .stApp {
            background: linear-gradient(180deg, #0e2d6b 0%, #183f90 35%, #f7d64a 100%);
            color: #edf6ff;
        }

        .block-container {
            padding-top: 2rem;
            padding-bottom: 2rem;
        }

        .centered-section {
            max-width: 60%;
            margin: 0 auto;
        }

        @media (max-width: 1100px) {
            .centered-section {
                max-width: 100%;
            }
        }

        div[data-testid="stDataFrame"],
        div[data-testid="stVerticalBlock"],
        div[data-testid="stForm"],
        div[data-testid="stExpander"],
        div[data-testid="stAlert"],
        [data-testid="stVerticalBlock"] > div,
        [data-testid="stDataFrame"] > div,
        div[data-testid="stTextInput"],
        div[data-testid="stTextArea"],
        div[data-testid="stSelectbox"],
        div[data-testid="stDateInput"],
        div[data-testid="stCheckbox"],
        div[data-baseweb="select"],
        div[data-baseweb="input"],
        div[role="button"],
        div[role="combobox"],
        div[role="textbox"],
        textarea,
        input,
        select {
            background: transparent !important;
            border-radius: 10px !important;
            box-shadow: none !important;
            color: #edf6ff !important;
        }

        div[data-testid="stTextInput"] > div > div > input,
        div[data-testid="stTextArea"] > div > div > textarea,
        div[data-testid="stSelectbox"] > div > div > div,
        div[data-testid="stDateInput"] input,
        div[data-testid="stCheckbox"] input,
        div[data-baseweb="select"] > div,
        div[data-baseweb="input"] > div,
        textarea,
        input,
        select {
            background: transparent !important;
            color: #edf6ff !important;
            border: none !important;
            box-shadow: none !important;
        }

        .stTextInput > div > div > input::placeholder,
        .stTextArea > div > div > textarea::placeholder {
            color: rgba(237, 246, 255, 0.76) !important;
            opacity: 1 !important;
        }

        .stButton > button {
            background: transparent !important;
            color: #edf6ff !important;
            border-radius: 12px !important;
            font-weight: 700 !important;
        }

        .stButton > button:hover {
            background: transparent !important;
            color: #ffffff !important;
        }

        h1, h2, h3, h4, h5, h6,
        .stMarkdown p,
        .stMarkdown li,
        label,
        .stSelectbox > label,
        .stTextInput > label,
        .stTextArea > label,
        .stDateInput > label {
            color: #edf6ff !important;
        }

        .stDataFrame, .stTable {
            background: transparent !important;
            border-radius: 12px;
        }

        .stMetric {
            background: transparent !important;
            border-radius: 12px;
            padding: 0.8rem;
            color: #edf6ff !important;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


# ========================= DATA ACCESS =========================


def california_now():
    return datetime.now(ZoneInfo(TIMEZONE))


def get_sheet_client():
    if not SHEET_URL.startswith("https://docs.google.com/spreadsheets/d/"):
        raise ValueError("The Google Sheet URL in app.py is not valid.")

    scopes = ["https://spreadsheets.google.com/feeds"]

    try:
        service_account_info = st.secrets["google_service_account"]
        creds = Credentials.from_service_account_info(service_account_info, scopes=scopes)
        client = gspread.authorize(creds)
        return client.open_by_url(SHEET_URL)
    except Exception:
        pass

    env_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
    if env_path:
        creds = Credentials.from_service_account_file(env_path, scopes=scopes)
        client = gspread.authorize(creds)
        return client.open_by_url(SHEET_URL)

    service_account_path = Path(LOCAL_SERVICE_ACCOUNT_FILE)
    if service_account_path.exists():
        creds = Credentials.from_service_account_file(str(service_account_path), scopes=scopes)
        client = gspread.authorize(creds)
        return client.open_by_url(SHEET_URL)

    raise FileNotFoundError(
        "Google service account file not found. Set GOOGLE_SERVICE_ACCOUNT_FILE or add a `google_service_account` entry in Streamlit secrets."
    )


def get_attendance_worksheet():
    workbook = get_sheet_client()
    try:
        return workbook.worksheet(ATTENDANCE_WORKSHEET)
    except WorksheetNotFound:
        raise ValueError(f"Worksheet '{ATTENDANCE_WORKSHEET}' not found in the Google Sheet.")


def get_tasks_worksheet():
    workbook = get_sheet_client()
    try:
        return workbook.worksheet(TASKS_WORKSHEET)
    except WorksheetNotFound:
        raise ValueError(f"Worksheet '{TASKS_WORKSHEET}' not found in the Google Sheet.")


@st.cache_data
def get_cached_attendance_rows():
    sheet = get_attendance_worksheet()
    return sheet.get_all_values()


@st.cache_data
def get_cached_task_rows():
    sheet = get_tasks_worksheet()
    return sheet.get_all_values()


def parse_sheet_datetime(date_value, time_value):
    if not date_value or not time_value:
        return None
    try:
        naive_dt = datetime.strptime(f"{date_value} {time_value}", "%Y-%m-%d %H:%M:%S")
    except ValueError:
        try:
            naive_dt = datetime.strptime(f"{date_value} {time_value}", "%m/%d/%Y %H:%M:%S")
        except ValueError:
            return None
    return naive_dt.replace(tzinfo=ZoneInfo(TIMEZONE))


def get_device_metadata():
    try:
        return st.context.device_id
    except Exception:
        return None


def build_status_dataframe(rows):
    status_rows = []
    for member in sorted(set(MEMBERS), key=str.casefold):
        active = False
        for row in rows[1:]:
            values = (row + [""] * len(ATTENDANCE_HEADERS))[: len(ATTENDANCE_HEADERS)]
            if values[0].strip().casefold() != member.casefold():
                continue
            if values[5].strip().lower() == "active":
                active = True
                break
        status_rows.append({"Name": member, "Status": "Clocked In" if active else "Clocked Out"})
    return pd.DataFrame(status_rows)


def get_active_row(rows, selected_name):
    for row in rows[1:]:
        values = (row + [""] * len(ATTENDANCE_HEADERS))[: len(ATTENDANCE_HEADERS)]
        if values[0].strip().casefold() != selected_name.casefold():
            continue
        status = values[5].strip()
        if status.lower() == "active":
            return row
    return None


def visit_end_datetime(values, report_now):
    end_date = values[3].strip()
    end_time = values[4].strip()
    if end_date and end_time:
        end_dt = parse_sheet_datetime(end_date, end_time)
        if end_dt is not None:
            return end_dt, False

    status = values[5].strip().lower()
    if status == "active":
        return report_now, True
    return None, False


def format_duration(seconds):
    total_seconds = max(0, int(seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def total_time_for_member(rows, member, range_start_dt, range_end_dt, report_now):
    total = 0.0
    for row in rows[1:]:
        values = (row + [""] * len(ATTENDANCE_HEADERS))[: len(ATTENDANCE_HEADERS)]
        if values[0].strip().casefold() != member.casefold():
            continue

        start_dt = parse_sheet_datetime(values[1], values[2])
        if start_dt is None:
            continue

        end_dt, _ = visit_end_datetime(values, report_now)
        if end_dt is None or end_dt < start_dt:
            continue

        overlap_start = max(start_dt, range_start_dt)
        overlap_end = min(end_dt, range_end_dt, report_now)
        total += max(0.0, (overlap_end - overlap_start).total_seconds())
    return total


def reset_person_selection():
    st.session_state.pop("selected_member", None)
    st.session_state.pop("confirm_member", None)


def clock_in_callback():
    selected_name = st.session_state.get("selected_member")
    if not selected_name:
        st.session_state["last_action_message"] = "Select a member before clocking in."
        return

    try:
        now = california_now()
        worksheet = get_attendance_worksheet()
        worksheet.append_row(
            [
                selected_name,
                now.strftime("%Y-%m-%d"),
                now.strftime("%H:%M:%S"),
                "",
                "",
                "Active",
                "",
                "",
                "",
                "",
                "",
                "",
            ],
            value_input_option="RAW",
        )
        st.cache_data.clear()
        st.session_state["last_action_message"] = f"{selected_name} clocked in."
    except Exception as exc:
        st.session_state["last_action_message"] = f"Clock in failed: {exc}"


def clock_out_callback():
    selected_name = st.session_state.get("selected_member")
    if not selected_name:
        st.session_state["last_action_message"] = "Select a member before clocking out."
        return

    try:
        rows = get_cached_attendance_rows()
        worksheet = get_attendance_worksheet()
        now = california_now()
        target_row = None

        for idx, row in enumerate(rows[1:], start=2):
            values = (row + [""] * len(ATTENDANCE_HEADERS))[: len(ATTENDANCE_HEADERS)]
            if values[0].strip().casefold() == selected_name.casefold() and values[5].strip().lower() == "active":
                target_row = idx
                break

        if target_row is None:
            st.session_state["last_action_message"] = f"{selected_name} is not currently clocked in."
            return

        worksheet.update(
            f"D{target_row}:F{target_row}",
            [[now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"), "Completed"]],
        )
        st.cache_data.clear()
        st.session_state["last_action_message"] = f"{selected_name} clocked out."
    except Exception as exc:
        st.session_state["last_action_message"] = f"Clock out failed: {exc}"


def centered_section():
    return st.container()


def show_task_tracker():
    st.divider()
    st.subheader("Team Task Board")

    member_options = sorted(set(MEMBERS), key=str.casefold)

    with st.form("create_task_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            task_name = st.text_input("Task name")
            task_description = st.text_area("Description")
        with col2:
            task_creator = st.selectbox("Created by", member_options, index=0)
            task_assignee = st.selectbox("Assigned to", member_options, index=0)
            task_priority = st.selectbox("Priority", TASK_PRIORITIES, index=1)
            has_due_date = st.checkbox("Set a due date")
            if has_due_date:
                task_due_date = st.date_input("Due date", value=california_now().date())
            else:
                task_due_date = ""

        create_task = st.form_submit_button("Create Task", use_container_width=True)

    if create_task:
        try:
            if not task_name.strip():
                st.warning("Enter a task name before creating the task.")
                return

            created_at = california_now()
            task_due_value = task_due_date.strftime("%Y-%m-%d") if has_due_date and task_due_date else ""
            tasks_worksheet = get_tasks_worksheet()
            tasks_worksheet.append_row(
                [
                    str(uuid4()),
                    task_name,
                    task_description,
                    task_creator,
                    task_assignee,
                    task_priority,
                    task_due_value,
                    "To Do",
                    created_at.strftime("%Y-%m-%d %I:%M:%S %p"),
                ],
                value_input_option="RAW",
                insert_data_option="INSERT_ROWS",
            )
            st.cache_data.clear()
            st.success(f"Task created and assigned to {task_assignee}.")
            st.rerun()
        except Exception as exc:
            st.error("Could not save the task to Google Sheets.")
            st.caption(f"Technical detail: {exc}")

    try:
        task_rows = get_cached_task_rows()
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
            tasks_worksheet = get_tasks_worksheet()
            tasks_worksheet.update(range_name=f"H{target_row}", values=[[selected_task_status]])
            st.cache_data.clear()
            st.success("Task status updated.")
            st.rerun()
        except Exception as exc:
            st.error("Could not update the task status.")
            st.caption(f"Technical detail: {exc}")


# ========================= APP UI =========================


def app():
    st.title("HOSA Tracker")
    st.write(
        "The home page shows everyone's time for today. Members can clock in or out below. "
        "Attendance will be tracked, and you can review the total amount of time members spent. "
        "and manage shared team tasks."
    )

    device_id = get_device_metadata()
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

    if not SHEET_URL.startswith("https://docs.google.com/spreadsheets/d/"):
        st.error("The Google Sheet URL in app.py is not valid.")
        st.stop()

    if not MEMBERS or any(not name.strip() for name in MEMBERS):
        st.error("Add valid names to the MEMBERS list near the top of app.py.")
        st.stop()

   # if st.button("Home / Next Person", use_container_width=True, on_click=reset_person_selection):
      #  st.rerun()

    if st.session_state.get("last_action_message"):
        st.success(st.session_state.pop("last_action_message"))

    try:
        rows = get_cached_attendance_rows()
    except Exception as exc:
        st.error(
            "Could not connect to Google Sheets. Check the Sheet URL, Streamlit Secrets, and make sure the spreadsheet is shared with the service-account email as Editor."
        )
        st.caption(f"Technical detail: {exc}")
        st.stop()

    now = california_now()
    today_start = datetime.combine(now.date(), time.min, tzinfo=ZoneInfo(TIMEZONE))
    tomorrow_start = today_start + timedelta(days=1)

    clock_col = centered_section()
    with clock_col:
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
                            disabled=active_row is not None,
                            on_click=clock_in_callback,
                        )
                    with col_out:
                        st.button(
                            "Clock Out",
                            use_container_width=True,
                            disabled=active_row is None,
                            on_click=clock_out_callback,
                        )
                else:
                    st.info("Confirm the selected name to enable Clock In / Clock Out.")
            else:
                st.info("Search for a name and select the correct person.")

    show_task_tracker()

    status_col = centered_section()
    with status_col:
        st.divider()
        st.subheader("Team Attendance Status")
        status_df = build_status_dataframe(rows)
        st.dataframe(status_df, use_container_width=True, hide_index=True)

    report_col = centered_section()
    with report_col:
        st.divider()
        st.subheader("Time Spent Report")
        st.write(
            "Choose a team member and a date range to see their total recorded time. "
            "Only the part of each visit that overlaps the selected dates is counted."
        )

        report_member_col, report_date_col = st.columns(2)
        with report_member_col:
            report_member = st.selectbox(
                "Team member for report",
                options=sorted(set(MEMBERS), key=str.casefold),
                key="report_member",
            )
        with report_date_col:
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


if __name__ == "__main__":
    app()
