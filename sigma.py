import os
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

import gspread
import pandas as pd
import streamlit as st
from google.oauth2.service_account import Credentials
from gspread.exceptions import WorksheetNotFound

# ========================= SETTINGS =========================

SHEET_URL = "https://docs.google.com/spreadsheets/d/1PUB0qcTfH9qPxSdldpfeQdDR0GKCrz5QLDoDn4TgWJI/edit"

TEAMS_WORKSHEET = "Teams"
NOTES_WORKSHEET = "Notes"

TEAM_HEADERS = [
    "Team ID",
    "Team Number",
    "Team Name",
    "Event",
    "Chassis",
    "Lift",
    "Claw",
    "Strengths",
    "Weaknesses",
    "Updated At",
    "Rated By",
]

NOTE_HEADERS = [
    "Note ID",
    "Team ID",
    "Team Number",
    "Note",
    "Created At",
]

LOCAL_SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", r"C:\Users\Srithan\service_account.json")
SCOPES = ["https://spreadsheets.google.com/feeds"]

TIMEZONE = "America/Los_Angeles"

COMPONENTS = [
    ("chassis", "Chassis"),
    ("lift", "Lift"),
    ("claw", "Claw"),
]

RATING_OPTIONS = ["Good", "OK", "Bad"]
RATING_POINTS = {"Good": 100, "OK": 60, "Bad": 20}
RATING_COLORS = {"Good": "#22c55e", "OK": "#f5c542", "Bad": "#ef4444"}

st.set_page_config(
    page_title="Robot Scouting Board",
    page_icon="🤖",
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
            padding-bottom: 3rem;
            max-width: 1150px;
        }

        div[data-testid="stTextInput"],
        div[data-testid="stTextArea"],
        div[data-testid="stSelectbox"],
        div[data-testid="stNumberInput"],
        div[data-testid="stDateInput"],
        div[data-testid="stCheckbox"],
        div[data-testid="stForm"],
        div[data-testid="stExpander"],
        div[data-baseweb="select"],
        div[data-baseweb="input"],
        textarea,
        input,
        select {
            background: transparent !important;
            color: #edf6ff !important;
            border-radius: 10px !important;
            box-shadow: none !important;
        }

        textarea::placeholder,
        input::placeholder {
            color: rgba(237, 246, 255, 0.7) !important;
            opacity: 1 !important;
        }

        .stButton > button {
            background: rgba(255, 255, 255, 0.12) !important;
            color: #edf6ff !important;
            border: 1px solid rgba(255, 255, 255, 0.35) !important;
            border-radius: 12px !important;
            font-weight: 700 !important;
        }

        .stButton > button:hover {
            background: rgba(255, 255, 255, 0.24) !important;
            color: #ffffff !important;
        }

        h1, h2, h3, h4, h5, h6,
        .stMarkdown p,
        .stMarkdown li,
        label,
        .stCaptionContainer,
        [data-testid="stCaptionContainer"] {
            color: #edf6ff !important;
        }

        .stMetric {
            background: transparent !important;
            color: #edf6ff !important;
        }

        .scout-card {
            background: rgba(10, 26, 64, 0.55);
            border: 1px solid rgba(255, 255, 255, 0.22);
            border-radius: 16px;
            padding: 1.1rem 1.25rem;
            height: 100%;
        }

        .scout-card-title {
            font-size: 0.78rem;
            letter-spacing: 0.12em;
            text-transform: uppercase;
            opacity: 0.75;
            margin-bottom: 0.35rem;
        }

        .scout-score {
            font-size: 2.6rem;
            font-weight: 800;
            line-height: 1;
            margin: 0.2rem 0 0.35rem 0;
        }

        .scout-verdict {
            font-size: 1.05rem;
            font-weight: 700;
        }

        .rating-pill {
            display: inline-block;
            padding: 0.18rem 0.7rem;
            border-radius: 999px;
            font-size: 0.85rem;
            font-weight: 700;
            color: #0b1c3d;
        }

        .rating-name {
            font-size: 0.8rem;
            letter-spacing: 0.1em;
            text-transform: uppercase;
            opacity: 0.8;
            margin-bottom: 0.3rem;
        }

        .scout-note {
            background: rgba(10, 26, 64, 0.45);
            border-left: 3px solid #f7d64a;
            border-radius: 10px;
            padding: 0.7rem 0.9rem;
            margin-bottom: 0.55rem;
        }

        .scout-note-time {
            font-size: 0.75rem;
            opacity: 0.7;
            margin-bottom: 0.2rem;
        }

        .bullet-good, .bullet-bad, .bullet-empty {
            border-radius: 10px;
            padding: 0.45rem 0.65rem;
            margin-bottom: 0.35rem;
            font-size: 0.95rem;
        }

        .bullet-good { background: rgba(34, 197, 94, 0.18); border-left: 3px solid #22c55e; }
        .bullet-bad { background: rgba(239, 68, 68, 0.18); border-left: 3px solid #ef4444; }
        .bullet-empty { background: rgba(255, 255, 255, 0.08); border-left: 3px solid rgba(255,255,255,0.35); }
    </style>
    """,
    unsafe_allow_html=True,
)


# ========================= GOOGLE SHEETS ACCESS =========================


def timestamp():
    return datetime.now(ZoneInfo(TIMEZONE)).strftime("%b %d, %Y %I:%M %p")


def get_credentials():
    try:
        service_account_info = st.secrets["google_service_account"]
        return Credentials.from_service_account_info(service_account_info, scopes=SCOPES)
    except Exception:
        pass

    env_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
    if env_path and Path(env_path).exists():
        return Credentials.from_service_account_file(env_path, scopes=SCOPES)

    service_account_path = Path(LOCAL_SERVICE_ACCOUNT_FILE)
    if service_account_path.exists():
        return Credentials.from_service_account_file(str(service_account_path), scopes=SCOPES)

    raise FileNotFoundError(
        "Google service account file not found. Set GOOGLE_SERVICE_ACCOUNT_FILE or add a `google_service_account` entry in Streamlit secrets."
    )


@st.cache_resource(show_spinner=False)
def get_workbook():
    if not SHEET_URL.startswith("https://docs.google.com/spreadsheets/d/"):
        raise ValueError("The Google Sheet URL in scout_app.py is not valid.")

    client = gspread.authorize(get_credentials())
    return client.open_by_url(SHEET_URL)


def get_or_create_worksheet(workbook, title, headers):
    try:
        worksheet = workbook.worksheet(title)
    except WorksheetNotFound:
        worksheet = workbook.add_worksheet(title=title, rows=200, cols=max(len(headers), 10))
        worksheet.append_row(headers, value_input_option="RAW")
        return worksheet

    rows = worksheet.get_all_values()
    if not rows or not any(cell.strip() for cell in rows[0]):
        worksheet.append_row(headers, value_input_option="RAW")
    return worksheet


def get_teams_worksheet(workbook):
    worksheet = get_or_create_worksheet(workbook, TEAMS_WORKSHEET, TEAM_HEADERS)
    headers = worksheet.row_values(1)
    if "Rated By" not in headers:
        worksheet.update_cell(1, len(headers) + 1, "Rated By")
    return worksheet


def get_notes_worksheet(workbook):
    return get_or_create_worksheet(workbook, NOTES_WORKSHEET, NOTE_HEADERS)


@st.cache_data(ttl=20, show_spinner=False)
def load_sheet_rows():
    workbook = get_workbook()
    return (
        get_teams_worksheet(workbook).get_all_values(),
        get_notes_worksheet(workbook).get_all_values(),
    )


def build_data():
    team_rows, note_rows = load_sheet_rows()

    notes_by_team = {}
    for sheet_row, raw_row in enumerate(note_rows[1:], start=2):
        values = (raw_row + [""] * len(NOTE_HEADERS))[: len(NOTE_HEADERS)]
        note_id, team_id, _number, text, created_at = values
        team_id = team_id.strip()
        if not team_id or not text.strip():
            continue
        notes_by_team.setdefault(team_id, []).append(
            {
                "id": note_id.strip() or str(uuid4()),
                "created_at": created_at.strip(),
                "text": text.strip(),
                "row": sheet_row,
            }
        )

    teams = []
    for sheet_row, raw_row in enumerate(team_rows[1:], start=2):
        values = (raw_row + [""] * len(TEAM_HEADERS))[: len(TEAM_HEADERS)]
        team_id = values[0].strip()
        if not team_id:
            continue

        ratings = {
            key: values[4 + index].strip() if values[4 + index].strip() in RATING_OPTIONS else "OK"
            for index, (key, _label) in enumerate(COMPONENTS)
        }
        team_notes = sorted(notes_by_team.get(team_id, []), key=lambda note: note["row"], reverse=True)
        teams.append(
            {
                "id": team_id,
                "number": values[1].strip(),
                "name": values[2].strip() or "Unnamed team",
                "event": values[3].strip(),
                "ratings": ratings,
                "strengths": values[7],
                "weaknesses": values[8],
                "updated_at": values[9].strip(),
                "rated_by": values[10].strip(),
                "notes": team_notes,
                "row": sheet_row,
            }
        )

    return {"teams": teams}


def add_team_to_sheet(number, name, event):
    workbook = get_workbook()
    worksheet = get_teams_worksheet(workbook)
    team_id = str(uuid4())
    worksheet.append_row(
        [
            team_id,
            number.strip(),
            name.strip(),
            event.strip(),
            "OK",
            "OK",
            "OK",
            "",
            "",
            timestamp(),
            "",
        ],
        value_input_option="RAW",
        insert_data_option="INSERT_ROWS",
    )
    st.cache_data.clear()
    return team_id


def save_evaluation_to_sheet(team, ratings, strengths, weaknesses, rated_by):
    workbook = get_workbook()
    worksheet = get_teams_worksheet(workbook)
    row = team["row"]
    worksheet.update(
        range_name=f"E{row}:K{row}",
        values=[
            [
                ratings.get("chassis", "OK"),
                ratings.get("lift", "OK"),
                ratings.get("claw", "OK"),
                strengths,
                weaknesses,
                timestamp(),
                rated_by.strip(),
            ]
        ],
        value_input_option="RAW",
    )
    st.cache_data.clear()


def add_note_to_sheet(team, text):
    workbook = get_workbook()
    get_notes_worksheet(workbook).append_row(
        [str(uuid4()), team["id"], team["number"], text.strip(), timestamp()],
        value_input_option="RAW",
        insert_data_option="INSERT_ROWS",
    )
    get_teams_worksheet(workbook).update(
        range_name=f"J{team['row']}",
        values=[[timestamp()]],
        value_input_option="RAW",
    )
    st.cache_data.clear()


def delete_note_from_sheet(note):
    workbook = get_workbook()
    get_notes_worksheet(workbook).delete_rows(note["row"])
    st.cache_data.clear()


def delete_team_from_sheet(team):
    workbook = get_workbook()
    notes_worksheet = get_notes_worksheet(workbook)
    for note in sorted(team["notes"], key=lambda item: item["row"], reverse=True):
        notes_worksheet.delete_rows(note["row"])
    get_teams_worksheet(workbook).delete_rows(team["row"])
    st.cache_data.clear()


# ========================= HELPERS =========================


def find_team(data, team_id):
    return next((team for team in data["teams"] if team["id"] == team_id), None)


def team_label(team):
    if team is None:
        return ""
    if team["number"]:
        return f"#{team['number']} — {team['name']}"
    return team["name"]


def scout_score(ratings):
    scores = [RATING_POINTS.get(ratings.get(key, "OK"), RATING_POINTS["OK"]) for key, _ in COMPONENTS]
    return round(sum(scores) / len(scores))


def verdict_label(score):
    if score >= 85:
        return "Strong team — a real threat"
    if score >= 60:
        return "Solid team — competitive"
    return "Needs work — vulnerable"


def auto_strengths(ratings):
    return [label for key, label in COMPONENTS if ratings.get(key) == "Good"]


def auto_weaknesses(ratings):
    return [label for key, label in COMPONENTS if ratings.get(key) == "Bad"]


def split_lines(text):
    return [line.strip(" -•\t") for line in text.splitlines() if line.strip(" -•\t")]


def sheet_error(exc, action):
    st.error(f"Could not {action} in Google Sheets. Check the Sheet URL, the service account, and that the sheet is shared with it as Editor.")
    st.caption(f"Technical detail: {exc}")


# ========================= SECTIONS =========================


def render_header(team):
    st.title(f"🤖 {team_label(team)}")
    subtitle = team["event"] if team["event"] else "No event recorded"
    st.caption(f"{subtitle} · Last updated {team['updated_at'] or 'never'}")


def render_overview(team):
    score = scout_score(team["ratings"])
    verdict = verdict_label(score)

    left, right = st.columns([1.1, 2])

    with left:
        st.markdown(
            f"""
            <div class="scout-card">
                <div class="scout-card-title">Is this team good?</div>
                <div class="scout-score">{score}<span style="font-size:1.1rem;opacity:0.7;">/100</span></div>
                <div class="scout-verdict">{verdict}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with right:
        pills = '<div class="scout-card" style="display:flex;gap:1.4rem;flex-wrap:wrap;align-items:center;">'
        for key, label in COMPONENTS:
            rating = team["ratings"].get(key, "OK")
            pills += (
                '<div style="min-width:110px;">'
                f'<div class="rating-name">{label}</div>'
                f'<span class="rating-pill" style="background:{RATING_COLORS[rating]};">{rating}</span>'
                "</div>"
            )
        pills += "</div>"
        st.markdown(pills, unsafe_allow_html=True)

    st.caption(
        "The score is the average of the chassis, lift and claw ratings (Good = 100, OK = 60, Bad = 20)."
    )
    if team["rated_by"]:
        st.caption(f"Rating entered by {team['rated_by']}.")


def render_evaluation_form(team):
    st.divider()
    st.subheader("Rate the robot")
    st.caption("Update Chassis, Lift and Claw, then save. The score and verdict above refresh immediately.")

    with st.form(f"evaluate_{team['id']}"):
        rated_by = st.text_input(
            "Your name (scout)",
            value=team["rated_by"],
            placeholder="Enter the name of the person rating this robot",
            key=f"rated_by_{team['id']}",
        )
        columns = st.columns(3)
        chosen = {}
        for column, (key, label) in zip(columns, COMPONENTS):
            with column:
                current = team["ratings"].get(key, "OK")
                chosen[key] = st.selectbox(
                    label,
                    RATING_OPTIONS,
                    index=RATING_OPTIONS.index(current),
                    key=f"rating_{key}_{team['id']}",
                )

        strengths_col, weaknesses_col = st.columns(2)
        with strengths_col:
            strengths = st.text_area(
                "Strengths",
                value=team["strengths"],
                height=140,
                placeholder="One strength per line, e.g. Fast, stable drivetrain",
                key=f"strengths_{team['id']}",
            )
        with weaknesses_col:
            weaknesses = st.text_area(
                "Weaknesses",
                value=team["weaknesses"],
                height=140,
                placeholder="One weakness per line, e.g. Claw jams on tall stacks",
                key=f"weaknesses_{team['id']}",
            )

        submitted = st.form_submit_button("Save evaluation", use_container_width=True)

    if submitted:
        try:
            save_evaluation_to_sheet(team, chosen, strengths, weaknesses, rated_by)
        except Exception as exc:
            sheet_error(exc, "save the evaluation")
        else:
            st.session_state["flash_message"] = f"Evaluation saved for {team_label(team)}."
            st.rerun()


def render_strengths_weaknesses(team):
    st.divider()
    st.subheader("Strengths and weaknesses")

    strengths = split_lines(team["strengths"])
    weaknesses = split_lines(team["weaknesses"])

    if not strengths:
        strengths = [f"{name} rated Good" for name in auto_strengths(team["ratings"])]
    if not weaknesses:
        weaknesses = [f"{name} rated Bad" for name in auto_weaknesses(team["ratings"])]

    good_col, bad_col = st.columns(2)

    with good_col:
        st.markdown("**Strengths**")
        if strengths:
            for item in strengths:
                st.markdown(
                    f'<div class="bullet-good">✅ {item}</div>',
                    unsafe_allow_html=True,
                )
        else:
            st.markdown(
                '<div class="bullet-empty">No strengths recorded yet.</div>',
                unsafe_allow_html=True,
            )

    with bad_col:
        st.markdown("**Weaknesses**")
        if weaknesses:
            for item in weaknesses:
                st.markdown(
                    f'<div class="bullet-bad">⚠️ {item}</div>',
                    unsafe_allow_html=True,
                )
        else:
            st.markdown(
                '<div class="bullet-empty">No weaknesses flagged by the current ratings.</div>',
                unsafe_allow_html=True,
            )


def render_notes(team):
    st.divider()
    st.subheader("Scouting notes")
    st.caption("Match observations, strategy ideas and pit reports. Newest notes appear first.")

    with st.form(f"note_form_{team['id']}", clear_on_submit=True):
        note_text = st.text_area(
            "Add a note",
            height=110,
            placeholder="e.g. Auton scores 2 cones, then blocks the far lane.",
            key=f"note_text_{team['id']}",
        )
        add_note = st.form_submit_button("Add note", use_container_width=True)

    if add_note:
        if not note_text.strip():
            st.warning("Write something before adding the note.")
        else:
            try:
                add_note_to_sheet(team, note_text)
            except Exception as exc:
                sheet_error(exc, "add the note")
            else:
                st.rerun()

    if not team["notes"]:
        st.info("No notes for this team yet.")
        return

    for note in team["notes"]:
        note_col, action_col = st.columns([6, 1])
        with note_col:
            st.markdown(
                f"""
                <div class="scout-note">
                    <div class="scout-note-time">{note["created_at"] or "Unknown time"}</div>
                    <div>{note["text"]}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with action_col:
            if st.button("Delete", key=f"delete_note_{note['id']}", use_container_width=True):
                try:
                    delete_note_from_sheet(note)
                except Exception as exc:
                    sheet_error(exc, "delete the note")
                else:
                    st.rerun()


def render_comparison(data):
    if len(data["teams"]) < 2:
        return

    st.divider()
    st.subheader("Compare all scouted teams")

    rows = []
    for team in data["teams"]:
        score = scout_score(team["ratings"])
        rows.append(
            {
                "Team": f"#{team['number']} {team['name']}".strip(),
                "Event": team["event"] or "—",
                "Chassis": team["ratings"].get("chassis", "OK"),
                "Lift": team["ratings"].get("lift", "OK"),
                "Claw": team["ratings"].get("claw", "OK"),
                "Score": score,
                "Verdict": verdict_label(score).split(" — ")[0],
                "Notes": len(team["notes"]),
                "Last updated": team["updated_at"] or "—",
            }
        )

    st.dataframe(
        pd.DataFrame(rows).sort_values("Score", ascending=False),
        use_container_width=True,
        hide_index=True,
    )


def render_sidebar(data):
    st.sidebar.title("Scouting HQ")

    teams = data["teams"]
    team_ids = [team["id"] for team in teams]

    selected_id = st.session_state.get("selected_team_id")
    if selected_id not in team_ids:
        selected_id = team_ids[0] if team_ids else None

    if teams:
        selected_id = st.sidebar.selectbox(
            "Active team",
            team_ids,
            index=team_ids.index(selected_id),
            format_func=lambda team_id: team_label(find_team(data, team_id)),
        )
    else:
        st.sidebar.info("No teams scouted yet. Add one below.")
    st.session_state["selected_team_id"] = selected_id

    with st.sidebar.expander("➕ Add a team", expanded=not teams):
        with st.form("add_team_form", clear_on_submit=True):
            number = st.text_input("Team number")
            name = st.text_input("Team name")
            event = st.text_input("Event / competition")
            add_submitted = st.form_submit_button("Add team", use_container_width=True)

        if add_submitted:
            if not number.strip() or not name.strip():
                st.warning("A team number and team name are required.")
            elif any(team["number"].casefold() == number.strip().casefold() for team in teams):
                st.warning(f"Team #{number.strip()} is already on the board.")
            else:
                try:
                    new_id = add_team_to_sheet(number, name, event)
                except Exception as exc:
                    sheet_error(exc, "add the team")
                else:
                    st.session_state["selected_team_id"] = new_id
                    st.rerun()

    current = find_team(data, selected_id)
    if current is not None:
        with st.sidebar.expander("🗑 Delete this team"):
            confirm = st.checkbox(f"I want to delete {team_label(current)}")
            if st.button("Delete team", disabled=not confirm, use_container_width=True):
                try:
                    delete_team_from_sheet(current)
                except Exception as exc:
                    sheet_error(exc, "delete the team")
                else:
                    st.session_state.pop("selected_team_id", None)
                    st.rerun()

    st.sidebar.divider()
    st.sidebar.caption(f"Saved to [this Google Sheet]({SHEET_URL}) — tabs `{TEAMS_WORKSHEET}` and `{NOTES_WORKSHEET}`.")


def app():
    st.title("Robot Scouting Board")
    st.write(
        "Scout every team at an event in one place: rate the chassis, lift and claw as Good, OK or Bad, "
        "and get an instant read on how strong the team is, what they do well and where they break down. "
        "Notes capture the match-by-match detail."
    )

    try:
        data = build_data()
    except Exception as exc:
        st.error(
            "Could not connect to the scouting Google Sheet. Check the Sheet URL in `scout_app.py`, the service-account "
            "credentials (`google_service_account` in Streamlit secrets or `GOOGLE_SERVICE_ACCOUNT_FILE`), and make sure "
            "the spreadsheet is shared with the service-account email as Editor."
        )
        st.caption(f"Technical detail: {exc}")
        st.stop()

    if st.session_state.get("flash_message"):
        st.success(st.session_state.pop("flash_message"))

    render_sidebar(data)

    team = find_team(data, st.session_state.get("selected_team_id"))
    if team is None:
        st.divider()
        st.info("Add your first team from **➕ Add a team** in the sidebar to start scouting.")
        return

    render_header(team)
    render_overview(team)
    render_evaluation_form(team)
    render_strengths_weaknesses(team)
    render_notes(team)
    render_comparison(data)


if __name__ == "__main__":
    app()
