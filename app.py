import streamlit as st
import streamlit.components.v1 as components
from html import escape
import gspread
import threading
from uuid import uuid4
from datetime import timezone
import os
import re
from datetime import datetime, date
from urllib.parse import urlsplit, parse_qs, urlencode

# ページ基本設定
st.set_page_config(page_title="スイング・チェックシート", layout="wide")

# 課題・問題点は赤、練習内容は紺（新規入力・履歴編集共通）。
st.markdown("""
<style>
textarea[aria-label="前回の課題・問題点"],
textarea[aria-label="今回の課題・問題点"] {
    color: #cc0000 !important;
    -webkit-text-fill-color: #cc0000 !important;
}
textarea[aria-label="今回の練習内容"] {
    color: #000080 !important;
    -webkit-text-fill-color: #000080 !important;
}
[class*="st-key-image_zoom_"] a {
    background-color: #0066cc !important;
    border: 1px solid #0066cc !important;
    color: #ffffff !important;
}
[class*="st-key-image_zoom_"] a p {
    color: #ffffff !important;
}
[class*="st-key-image_zoom_"] a:hover {
    background-color: #0052a3 !important;
    border-color: #0052a3 !important;
}
</style>
""", unsafe_allow_html=True)


# 画面リセット用のセッション管理
if "refresh_key" not in st.session_state:
    st.session_state.refresh_key = 0
if "form_reset_key" not in st.session_state:
    st.session_state.form_reset_key = 0

# Googleスプレッドシートのみを保存先にする。ローカルDBへの代替保存は禁止。
class StorageError(Exception):
    pass

SCHEMAS = {
    "students": ["id", "name", "handicap", "goal", "revision", "deleted"],
    "coaches": ["id", "name", "revision", "deleted"],
    "lessons": [
        "id", "student_id", "lesson_date", "coach_name", "target_goal",
        "lesson_practice", "evaluation_note", "v1_url", "v2_url", "v3_url", "v4_url",
        "drive_images", "previous_issues", "previous_check_date", "current_issues",
        "previous_address", "previous_backswing", "previous_downswing",
        "current_address", "current_backswing", "current_downswing", "revision", "deleted",
    ],
}

@st.cache_resource
def storage_lock():
    # 同一アプリプロセス内で、複数コーチの保存処理を直列化。
    return threading.RLock()


def new_record_id():
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f") + "_" + uuid4().hex


def normalized_headers(row):
    # Sheets APIが返す右端の空セルと、見出しの前後の空白を許容する。
    result = [str(value).strip() for value in row]
    while result and not result[-1]:
        result.pop()
    return result


def header_error(name, row):
    actual = normalized_headers(row)
    expected = SCHEMAS[name]
    shown = " / ".join(actual[:len(expected) + 2]) or "（空欄）"
    return (f"{name} シートの見出しを確認してください。"
            f"\n期待する見出し：{' / '.join(expected)}"
            f"\n読み込んだ見出し：{shown}")


class SheetsStore:
    def __init__(self, workbook):
        self.book = workbook
        self.sheets = {}
        self.cache = {}

    def initialize(self):
        with storage_lock():
            worksheets = {sheet.title: sheet for sheet in self.book.worksheets()}
            for name, headers in SCHEMAS.items():
                sheet = worksheets.get(name)
                if sheet is None:
                    sheet = self.book.add_worksheet(title=name, rows=1000, cols=len(headers))
                values = sheet.get_all_values()
                if not any(str(cell).strip() for row in values for cell in row):
                    # 空セルだけの配列が返っても、空シートとして初期化する。
                    sheet.update(range_name="A1", values=[headers], raw=True)
                else:
                    actual = normalized_headers(values[0])
                    if len(actual) == 1 and actual[0].split() == headers:
                        # タブ区切りの見出しがA1の1セルに入った場合だけ安全に展開。
                        sheet.update(range_name="A1", values=[headers], raw=True)
                    elif actual != headers:
                        raise StorageError(header_error(name, values[0]))
                self.sheets[name] = sheet

    def records(self, name, fresh=False):
        if fresh or name not in self.cache:
            values = self.sheets[name].get_all_values()
            headers = SCHEMAS[name]
            if not values or normalized_headers(values[0]) != headers:
                raise StorageError(header_error(name, values[0] if values else []))
            records = []
            for row_number, row in enumerate(values[1:], 2):
                row = row + [""] * (len(headers) - len(row))
                record = dict(zip(headers, row))
                if not record["id"] or record["deleted"]:
                    continue
                record["_row"] = row_number
                records.append(record)
            self.cache[name] = records
        # 画面で初めて表示した時点の版を保存。再実行で勝手に更新しない。
        versions = st.session_state.setdefault("loaded_versions", {})
        for record in self.cache[name]:
            versions.setdefault((name, record["id"]), record["revision"])
        return [dict(record) for record in self.cache[name]]

    def append(self, name, data):
        record = dict(data, id=new_record_id(), revision=uuid4().hex, deleted="")
        values = [str(record.get(field) or "") for field in SCHEMAS[name]]
        # append APIで追記する。読み込んだ表全体を上書きしない。
        self.sheets[name].append_row(values, value_input_option="RAW", insert_data_option="INSERT_ROWS", table_range="A1")
        self.cache.pop(name, None)
        return record["id"]

    def update(self, name, record_id, changes, expected=None):
        with storage_lock():
            record = next((r for r in self.records(name, fresh=True) if r["id"] == str(record_id)), None)
            if record is None:
                raise StorageError("この記録は削除されています。画面を再読み込みしてください。")
            if expected is None:
                expected = st.session_state.get("loaded_versions", {}).get((name, str(record_id)))
            if expected is None or record["revision"] != expected:
                raise StorageError("他のコーチがこの記録を変更しました。入力内容を控え、左側の「最新データを読み込む」を押して確認してください。")
            record.update(changes)
            record["revision"] = uuid4().hex
            # 書き込み直前に、行が移動していないことを確認する。
            current = self.sheets[name].row_values(record["_row"])
            rev_index = SCHEMAS[name].index("revision")
            if not current or current[0] != str(record_id) or len(current) <= rev_index or current[rev_index] != expected:
                raise StorageError("保存中にデータが変わりました。入力内容を控え、最新データを読み込んでください。")
            values = [str(record.get(field) or "") for field in SCHEMAS[name]]
            self.sheets[name].update(range_name=f"A{record['_row']}", values=[values], raw=True)
            st.session_state["loaded_versions"][(name, str(record_id))] = record["revision"]
            self.cache.pop(name, None)

    def delete(self, name, record_id, expected=None):
        # 行を詰めず、削除フラグを付ける。別の記録の行番号を変えない。
        self.update(name, record_id, {"deleted": datetime.now(timezone.utc).isoformat()}, expected=expected)


def connect_sheets():
    try:
        spreadsheet_id = st.secrets["google_sheets"]["spreadsheet_id"].strip()
        credentials = dict(st.secrets["gcp_service_account"])
        if not spreadsheet_id or not credentials.get("private_key"):
            raise ValueError("missing settings")
    except Exception:
        st.error("Googleスプレッドシートへの接続設定が未完了です。設定手順のSecretsを登録してください。データの登録はまだできません。")
        st.stop()
    try:
        client = gspread.service_account_from_dict(
            credentials, scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
        workbook = client.open_by_key(spreadsheet_id)
        store = SheetsStore(workbook)
        store.initialize()
        return store
    except StorageError as error:
        st.error(str(error))
        st.caption(f"現在の接続先：{workbook.title}")
        st.link_button("現在の保存先スプレッドシートを開く", f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit")
        st.stop()
    except Exception:
        st.error("Googleスプレッドシートに接続できません。シートID・APIの有効化・サービスアカウントの編集権限を確認してください。接続が直るまで保存はできません。")
        st.stop()

store = connect_sheets()

# GoogleドライブのファイルID抽出
def get_drive_file_id(url):
    if not url:
        return None
    url = url.strip()
    match = re.search(r"/d/([a-zA-Z0-9_-]{15,})", url)
    if not match:
        match = re.search(r"[?&]id=([a-zA-Z0-9_-]{15,})", url)
    return match.group(1) if match else None

# Googleドライブの閲覧・プレビューURL（Android / iPhone / PC共通）
def drive_playback_url(url, preview=False):
    fid = get_drive_file_id(url)
    if not fid:
        return (url or "").strip()
    mode = "preview" if preview else "view"
    params = {} if preview else {"usp": "sharing"}
    # アクセスに必要なresourcekeyがある共有リンクでは削除しない。
    resource_key = parse_qs(urlsplit(url.strip()).query).get("resourcekey", [""])[0]
    if resource_key:
        params["resourcekey"] = resource_key
    query = urlencode(params)
    return f"https://drive.google.com/file/d/{fid}/{mode}" + (f"?{query}" if query else "")

# GoogleドライブURLの整形
def clean_drive_url(url):
    if not url:
        return ""
    return drive_playback_url(url)

def render_fullscreen_preview(url, title, height=380):
    if not get_drive_file_id(url):
        return
    preview_url = escape(drive_playback_url(url, preview=True), quote=True)
    safe_title = escape(title, quote=True)
    # Streamlitのコンポーネント内で、ユーザーのクリックから全画面表示を要求する。
    markup = """
    <style>
    * { box-sizing: border-box; }
    body { margin: 0; font-family: sans-serif; }
    #viewer { background: #111; width: 100%; height: __HEIGHT__px; }
    #viewer:fullscreen { width: 100vw; height: 100vh; }
    #viewer:-webkit-full-screen { width: 100vw; height: 100vh; }
    #toolbar { height: 46px; display: flex; align-items: center; padding: 5px 8px; gap: 8px; }
    button { background: #0066cc; color: white; border: 1px solid #0066cc;
             border-radius: 6px; padding: 8px 12px; cursor: pointer; font-size: 14px; }
    #message { color: white; font-size: 12px; }
    iframe { width: 100%; height: calc(100% - 46px); border: 0; display: block; background: white; }
    </style>
    <div id="viewer">
      <div id="toolbar">
        <button id="full" type="button">⛶ 全画面で見る</button>
        <span id="message" role="status"></span>
      </div>
      <iframe src="__URL__" title="__TITLE__"
        allow="fullscreen; autoplay; encrypted-media; picture-in-picture"
        allowfullscreen webkitallowfullscreen></iframe>
    </div>
    <script>
    const viewer = document.getElementById('viewer');
    const button = document.getElementById('full');
    const message = document.getElementById('message');
    function syncButton() {
      button.textContent = (document.fullscreenElement || document.webkitFullscreenElement)
        ? '⛶ 全画面を終了' : '⛶ 全画面で見る';
    }
    button.addEventListener('click', async () => {
      message.textContent = '';
      try {
        if (document.fullscreenElement || document.webkitFullscreenElement) {
          const exit = document.exitFullscreen || document.webkitExitFullscreen;
          if (!exit) throw new Error('unsupported');
          await exit.call(document);
        } else {
          const enter = viewer.requestFullscreen || viewer.webkitRequestFullscreen;
          if (!enter) throw new Error('unsupported');
          await enter.call(viewer);
        }
        syncButton();
      } catch (error) {
        message.textContent = 'このブラウザでは全画面にできません。ドライブを直接開いてください。';
      }
    });
    document.addEventListener('fullscreenchange', syncButton);
    document.addEventListener('webkitfullscreenchange', syncButton);
    </script>
    """
    markup = markup.replace("__HEIGHT__", str(height))
    markup = markup.replace("__TITLE__", safe_title).replace("__URL__", preview_url)
    components.html(markup, height=height + 4, scrolling=False)

# 独自のアプリ用スキームに依存しない再生ボタン
def render_video_links(url, number):
    # iPhoneでは埋め込み枠の全画面化を使わず、再生ページを直接開く。
    st.link_button(
        f"▶️ 動画{number}を再生（ブラウザ）",
        drive_playback_url(url, preview=True),
        use_container_width=True,
        type="primary",
    )
    if get_drive_file_id(url):
        st.link_button(
            "Googleドライブで開く",
            drive_playback_url(url),
            use_container_width=True,
        )

# データ操作（すべてGoogleスプレッドシートに保存）
def get_students():
    return sorted(store.records("students"), key=lambda record: record["name"])


def add_student(name, handicap, goal):
    with storage_lock():
        if any(record["name"] == name for record in store.records("students", fresh=True)):
            return False
        store.append("students", {"name": name, "handicap": handicap, "goal": goal})
        return True

def register_student_from_form():
    name = st.session_state.get("new_s_name", "").strip()
    if not name:
        st.session_state["student_registration_error"] = "生徒名を入力してください。"
        return
    try:
        success = add_student(
            name,
            st.session_state.get("new_s_hdcp", "").strip(),
            st.session_state.get("new_s_goal", "").strip(),
        )
    except Exception as error:
        st.session_state["student_registration_error"] = f"登録に失敗しました: {error}"
        return
    if not success:
        st.session_state["student_registration_error"] = "同じ名前の生徒が既に登録されています。"
        return
    for key in ("new_s_name", "new_s_hdcp", "new_s_goal"):
        st.session_state[key] = ""
    st.session_state.pop("student_registration_error", None)
    st.session_state["management_notice"] = f"{name} 様を登録しました。"

def update_student(student_id, name, handicap, goal):
    with storage_lock():
        if any(record["name"] == name and record["id"] != str(student_id)
               for record in store.records("students", fresh=True)):
            return False
        store.update("students", student_id, {"name": name, "handicap": handicap, "goal": goal})
        return True

def update_student_from_form(student_id):
    keys = (f"s_name_{student_id}", f"s_hdcp_{student_id}", f"s_goal_{student_id}")
    name, handicap, goal = (st.session_state.get(key, "").strip() for key in keys)
    if not name:
        st.session_state["profile_update_error"] = "氏名を入力してください。"
        return
    try:
        success = update_student(student_id, name, handicap, goal)
    except Exception as error:
        st.session_state["profile_update_error"] = f"更新に失敗しました: {error}"
        return
    if not success:
        st.session_state["profile_update_error"] = "同姓同名の生徒が既に存在します。別の名前を指定してください。"
        return
    for key in keys:
        st.session_state[key] = ""
    st.session_state["selected_student_name_blank"] = name
    st.session_state["refresh_key"] += 1
    st.session_state.pop("profile_update_error", None)
    st.session_state["management_notice"] = "プロフィールを更新しました。"

def delete_student(student_id):
    with storage_lock():
        # まず生徒を非表示にする。途中で通信が切れても履歴だけ失う順序にはしない。
        store.delete("students", student_id)
        for record in store.records("lessons", fresh=True):
            if record["student_id"] == str(student_id):
                store.delete("lessons", record["id"], expected=record["revision"])


def get_coaches():
    return sorted(store.records("coaches"), key=lambda record: record["name"])


def add_coach(name):
    with storage_lock():
        if any(record["name"] == name for record in store.records("coaches", fresh=True)):
            return False
        store.append("coaches", {"name": name})
        return True


def delete_coach(coach_id):
    store.delete("coaches", coach_id)


def lesson_data(lesson_date, coach_name, target_goal, lesson_practice, evaluation_note,
                v1_url, v2_url, drive_images, previous_issues, previous_check_date,
                previous_address, previous_backswing, previous_downswing,
                current_address, current_backswing, current_downswing,
                current_issues, v3_url, v4_url):
    return {
        "lesson_date": str(lesson_date), "coach_name": coach_name,
        "target_goal": target_goal, "lesson_practice": lesson_practice,
        "evaluation_note": evaluation_note, "v1_url": v1_url, "v2_url": v2_url,
        "v3_url": v3_url, "v4_url": v4_url, "drive_images": drive_images,
        "previous_issues": previous_issues,
        "previous_check_date": str(previous_check_date) if previous_check_date else "",
        "current_issues": current_issues if current_issues is not None else "",
    }


def save_lesson(student_id, lesson_date, coach_name, target_goal, lesson_practice, evaluation_note, v1_url="", v2_url="", drive_images="", previous_issues="", previous_check_date=None, previous_address="", previous_backswing="", previous_downswing="", current_address="", current_backswing="", current_downswing="", current_issues=None, v3_url="", v4_url=""):
    with storage_lock():
        if not any(record["id"] == str(student_id) for record in store.records("students", fresh=True)):
            raise StorageError("この生徒は削除されています。最新データを読み込んでください。")
        data = lesson_data(lesson_date, coach_name, target_goal, lesson_practice, evaluation_note,
            v1_url, v2_url, drive_images, previous_issues, previous_check_date,
            previous_address, previous_backswing, previous_downswing,
            current_address, current_backswing, current_downswing, current_issues, v3_url, v4_url)
        data["student_id"] = str(student_id)
        store.append("lessons", data)


def update_lesson(lesson_id, lesson_date, coach_name, target_goal, lesson_practice, evaluation_note, v1_url="", v2_url="", drive_images="", previous_issues="", previous_check_date=None, previous_address="", previous_backswing="", previous_downswing="", current_address="", current_backswing="", current_downswing="", current_issues=None, v3_url="", v4_url=""):
    data = lesson_data(lesson_date, coach_name, target_goal, lesson_practice, evaluation_note,
        v1_url, v2_url, drive_images, previous_issues, previous_check_date,
        previous_address, previous_backswing, previous_downswing,
        current_address, current_backswing, current_downswing, current_issues, v3_url, v4_url)
    store.update("lessons", lesson_id, data)


def delete_lesson(lesson_id):
    store.delete("lessons", lesson_id)


def get_student_history(student_id):
    return sorted(
        [record for record in store.records("lessons") if record["student_id"] == str(student_id)],
        key=lambda record: (record["lesson_date"], record["id"]), reverse=True,
    )

def get_previous_lesson(student_id, lesson_date, lesson_id=None):
    # 日付順。同日では、編集中の記録より前に登録された記録だけを参照。
    for record in get_student_history(student_id):
        if record["lesson_date"] < str(lesson_date) or (
            record["lesson_date"] == str(lesson_date)
            and (lesson_id is None or record["id"] < lesson_id)
        ):
            return record
    return None

def combined_issues(record, kind):
    # 新しい統合欄を優先。旧記録の3区分も内容を失わずに表示する。
    if not record:
        return ""
    value = record.get(f"{kind}_issues")
    if value is not None and (kind == "current" or value.strip()):
        return value
    parts = []
    for label, phase in (("アドレス", "address"), ("バックスイング", "backswing"), ("ダウンスイング", "downswing")):
        content = record.get(f"{kind}_{phase}") or ""
        if content.strip():
            parts.append(f"【{label}】\n{content}")
    if parts:
        return "\n\n".join(parts)
    if value is not None:
        return value
    return (record.get("target_goal") or "") if kind == "current" else ""


def previous_issue_value(record):
    if not record:
        return ""
    # 今回欄が空欄として保存されている場合も、その内容をそのまま引き継ぐ。
    if record.get("current_issues") is not None or any(
        record.get(f"current_{phase}") is not None
        for phase in ("address", "backswing", "downswing")
    ):
        return combined_issues(record, "current")
    return combined_issues(record, "previous") or combined_issues(record, "current")


def clean_image_links(text):
    links = [clean_drive_url(line) for line in text.splitlines() if line.strip()]
    if len(links) > 6:
        raise ValueError("静止画は6個まで登録できます。共有リンクを6個以内にしてください。")
    return ",".join(links)

def carry_previous_issue(widget_key, source_key):
    # クリック時点の前回欄を読む。保存前の編集内容もそのまま引き継ぐ。
    content = st.session_state.get(source_key, "")
    if not content.strip():
        st.session_state["carry_notice"] = "引き継ぐ前回の内容がありません。前回の課題・問題点の欄に記入してから押してください。"
        return
    st.session_state[widget_key] = content

def parse_optional_date(value):
    try:
        return date.fromisoformat(value) if value else None
    except (TypeError, ValueError):
        return None

def render_text_box(content, box_type="blue", text_color="#222", empty_label="（未記入）"):
    if not content or not str(content).strip():
        if empty_label:
            return f'<div style="color: #888; font-style: italic; padding: 8px;">{empty_label}</div>'
        content = ""
    
    if box_type == "blue":
        bg_color = "#f0f7ff"
        border_color = "#0066cc"
    else:
        bg_color = "#f0fdf4"
        border_color = "#16a34a"
        
    return f'''<div style="
        background-color: {bg_color};
        border-left: 4px solid {border_color};
        padding: 12px 14px;
        border-radius: 4px;
        white-space: pre-wrap;
        line-height: 1.6;
        font-size: 15px;
        min-height: 24px;
        color: {text_color};
        margin-top: 6px;
        margin-bottom: 12px;
    ">{escape(str(content))}</div>'''

# --- 画面構成 ---
st.title("スイング・チェックシート")
if "carry_notice" in st.session_state:
    st.info(st.session_state.pop("carry_notice"))
if "management_notice" in st.session_state:
    st.success(st.session_state.pop("management_notice"))

# サイドバー
st.sidebar.caption("保存先：Googleスプレッドシート")
if st.sidebar.button("最新データを読み込む", key="reload_sheet_data"):
    st.session_state.pop("loaded_versions", None)
    for key in list(st.session_state):
        if key.startswith(("s_name_", "s_hdcp_", "s_goal_", "ed_")):
            del st.session_state[key]
    st.session_state.refresh_key += 1
    st.rerun()
try:
    raw_students = get_students()
    raw_coaches = get_coaches()
except Exception:
    st.error("保存データを読み込めません。時間をおいて再読み込みしてください。")
    st.stop()
name_counts = {}
for student in raw_students:
    name_counts[student["name"]] = name_counts.get(student["name"], 0) + 1
student_dict = {
    (student["name"] if name_counts[student["name"]] == 1 else f"{student['name']} (ID: {student['id']})"): student
    for student in raw_students
}
student_options = [""] + list(student_dict.keys())
if st.session_state.get("selected_student_name_blank", "") not in student_options:
    st.session_state["selected_student_name_blank"] = ""
selected_name = st.sidebar.selectbox(
    "受講者を選択", options=student_options, index=0,
    key="selected_student_name_blank", disabled=not raw_students,
)

st.sidebar.markdown("---")
st.sidebar.header("生徒管理")

with st.sidebar.expander("＋ 新規生徒を登録", expanded=False):
    new_s_name = st.text_input("生徒名", key="new_s_name")
    new_s_hdcp = st.text_input("現在のハンデ/平均スコア", key="new_s_hdcp")
    new_s_goal = st.text_input("長期目標", key="new_s_goal")
    st.button("登録する", key="btn_add_student", on_click=register_student_from_form)
    if "student_registration_error" in st.session_state:
        st.error(st.session_state.pop("student_registration_error"))

if selected_name:
    curr_student = student_dict[selected_name]
    selected_id = curr_student["id"]

    with st.sidebar.expander("👤 生徒プロフィールを編集", expanded=False):
        for key, initial in (
            (f"s_name_{selected_id}", selected_name),
            (f"s_hdcp_{selected_id}", curr_student.get("handicap") or ""),
            (f"s_goal_{selected_id}", curr_student.get("goal") or ""),
        ):
            if key not in st.session_state:
                st.session_state[key] = initial
        edit_s_name = st.text_input("氏名", key=f"s_name_{selected_id}")
        edit_s_hdcp = st.text_input("ハンデ / 平均スコア", key=f"s_hdcp_{selected_id}")
        edit_s_goal = st.text_input("長期目標", key=f"s_goal_{selected_id}")
        st.button(
            "💾 プロフィールを更新", type="primary", key=f"btn_up_s_{selected_id}",
            on_click=update_student_from_form, args=(selected_id,),
        )
        if "profile_update_error" in st.session_state:
            st.error(st.session_state.pop("profile_update_error"))

        st.markdown("---")
        st.markdown("### 🗑️ 生徒を削除")
        st.write(f"削除対象：{selected_name} 様")
        st.caption("この生徒のプロフィールと全レッスン履歴を一覧から削除します。")
        del_s_chk = st.checkbox("この生徒と全レッスン履歴を削除することを確認", key=f"del_s_chk_{selected_id}")
        if st.button("🗑️ 選択した生徒を削除", key=f"btn_del_s_{selected_id}", disabled=not del_s_chk):
            try:
                delete_student(selected_id)
                st.session_state.refresh_key += 1
                st.session_state.management_notice = f"{selected_name} 様と全レッスン履歴を削除しました。"
                st.rerun()
            except Exception as e:
                st.error(f"生徒の削除に失敗しました: {e}")

st.sidebar.markdown("---")
coach_list = [c["name"] for c in raw_coaches]

with st.sidebar.expander("コーチ管理", expanded=False):
    st.markdown("### ＋ コーチを登録")
    new_coach_name = st.text_input("新規コーチ氏名", placeholder="例: 山田 コーチ", key="new_coach_name_input")
    if st.button("＋ コーチを登録", key="btn_add_coach"):
        if new_coach_name.strip():
            try:
                if add_coach(new_coach_name.strip()):
                    st.success(f"{new_coach_name} を登録しました")
                    st.rerun()
                else:
                    st.error("同じ名前のコーチが既に登録されています。")
            except Exception as error:
                st.error(f"コーチの登録に失敗しました: {error}")

    st.markdown("---")
    st.markdown("### 🗑️ コーチを削除")
    if raw_coaches:
        coach_to_del = st.selectbox("削除するコーチを選択", options=coach_list, key="coach_to_del_select")
        del_coach_id = next(c["id"] for c in raw_coaches if c["name"] == coach_to_del)
        st.caption("コーチを削除しても、過去のレッスン記録と担当コーチ名は残ります。")
        confirm_coach_delete = st.checkbox(f"{coach_to_del} を削除することを確認", key=f"confirm_coach_delete_{del_coach_id}")
        if st.button("🗑️ 選択したコーチを削除", key=f"btn_del_coach_{del_coach_id}", disabled=not confirm_coach_delete):
            try:
                delete_coach(del_coach_id)
                st.session_state.refresh_key += 1
                st.session_state.management_notice = f"{coach_to_del} を削除しました。"
                st.rerun()
            except Exception as e:
                st.error(f"コーチの削除に失敗しました: {e}")
    else:
        st.info("登録済みのコーチはいません。")

if not selected_name:
    st.tabs(["📝 新規スイングチェック入力", "📂 過去カルテ・日付変更・編集"])
    st.stop()

st.caption(f"**受講者:** {selected_name} 様 ｜ **ハンデ/平均:** {curr_student.get('handicap') or '未設定'} ｜ **長期目標:** {curr_student.get('goal') or '未設定'}")

tab_new, tab_history = st.tabs(["📝 新規スイングチェック入力", "📂 過去カルテ・日付変更・編集"])

# ================================
# タブ1: 新規入力フォーム
# ================================
with tab_new:
    st.subheader(f"{selected_name} 様 - レッスンチェック新規入力")
    
    fk = f"{selected_id}_{st.session_state.form_reset_key}_blank"
    
    top_col1, top_col2 = st.columns(2)
    with top_col1:
        lesson_date = st.date_input("📅 レッスン受講日", value=None, key=f"new_date_{fk}")
    with top_col2:
        coach_options = [""] + coach_list
        selected_coach_new = st.selectbox("🏌️️‍♂️ 担当コーチ", options=coach_options, index=0, key=f"new_coach_{fk}")
        new_coach_val = selected_coach_new

    if lesson_date:
        previous = get_previous_lesson(selected_id, lesson_date)
    else:
        student_history = get_student_history(selected_id)
        previous = student_history[0] if student_history else None
    previous_key = f"{selected_id}_{fk}_{lesson_date}_{previous['id'] if previous else 0}_{st.session_state.refresh_key}"
    st.markdown("### ■ 前回の課題・問題点")
    previous_check_date = st.date_input(
        "📅 直前のレッスン（チェック日）",
        value=parse_optional_date(previous["lesson_date"]) if previous else None,
        key=f"new_previous_date_{previous_key}",
    )
    previous_issues = st.text_area(
        "前回の課題・問題点", value=previous_issue_value(previous),
        key=f"new_previous_issues_{previous_key}", height=180,
    )
    if previous:
        st.caption("直前のレッスンで記入した問題点を表示しています。必要に応じて書き直せます。")

    if not previous:
        st.caption("直前のレッスン記録がないため、空欄から記入できます。")

    st.markdown("---")
    st.markdown("### ■ 今回の練習内容")
    lesson_practice = st.text_area(
        "今回の練習内容", placeholder="今回行った練習やドリルを記入してください。",
        key=f"new_lesson_practice_{fk}",
    )
    target_goal = ""
    evaluation_note = ""
    st.markdown("### ■ 今回の課題・問題点")
    current_issues_key = f"new_current_issues_{previous_key}"
    issue_col, carry_col = st.columns([4, 1])
    with issue_col:
        current_issues = st.text_area(
            "今回の課題・問題点", key=current_issues_key, height=180,
        )
    with carry_col:
        st.button(
            "前回の内容を引き継ぐ", key=f"carry_issues_{previous_key}",
            type="primary", on_click=carry_previous_issue,
            args=(current_issues_key, f"new_previous_issues_{previous_key}"),
        )

    st.markdown("---")
    st.markdown("### ■ Google ドライブ共有リンク登録")
    st.caption("※共有設定を「リンクを知っている全員（閲覧者）」にしたリンクを貼り付けてください。")
    
    video_urls = []
    video_cols = st.columns(2)
    for number in range(1, 5):
        with video_cols[(number - 1) % 2]:
            video_urls.append(st.text_input(
                f"🎥 動画 {number} 共有リンク", value="",
                placeholder="https://drive.google.com/file/d/.../view",
                key=f"new_v{number}_url_{fk}",
            ))

    drive_imgs_input = st.text_area(
        "📷 静止画 共有リンク（6個まで・改行して入力）",
        placeholder="https://drive.google.com/file/d/xxxxxxx/view?usp=sharing\nhttps://drive.google.com/file/d/yyyyyyy/view?usp=sharing",
        key=f"new_drive_imgs_{fk}"
    )

    save_clicked = st.button("💾 このレッスンカルテを保存する", type="primary", use_container_width=True)

    # 保存後の再描画でも、保存ボタンの直下に完了メッセージを表示する。
    save_message_key = f"new_lesson_saved_{selected_id}"
    if st.session_state.pop(save_message_key, False):
        st.success("保存しました")

    if save_clicked:
        try:
            if lesson_date is None:
                raise ValueError("レッスン受講日を選択してください。")
            clean_videos = [clean_drive_url(url) for url in video_urls]
            drive_imgs_clean = clean_image_links(drive_imgs_input)
            
            save_lesson(
                selected_id, lesson_date, new_coach_val,
                target_goal, lesson_practice, evaluation_note,
                clean_videos[0], clean_videos[1], drive_imgs_clean, previous_issues, previous_check_date,
                current_issues=current_issues, v3_url=clean_videos[2], v4_url=clean_videos[3]
            )
            
            st.session_state.form_reset_key += 1
            st.session_state.refresh_key += 1
            st.session_state[save_message_key] = True
            st.rerun()

        except Exception as e:
            st.error(f"❌ 保存に失敗しました: {e}")

# ================================
# タブ2: 履歴閲覧・日付変更・編集・削除
# ================================
with tab_history:
    st.subheader(f"{selected_name} 様の過去レッスン一覧")
    records = get_student_history(selected_id)
    
    rf_k = st.session_state.refresh_key
    
    if not records:
        st.info("まだ保存されたレッスン記録がありません。")
    else:
        for rec in records:
            r_id = rec["id"]
            r_date = rec["lesson_date"]
            r_coach_name = rec.get("coach_name") or ""
            r_target_goal = rec.get("target_goal") or ""
            r_lesson_practice = rec.get("lesson_practice") or ""
            r_eval_note = rec.get("evaluation_note") or ""
            r_video_urls = [rec.get(f"v{number}_url") or "" for number in range(1, 5)]
            r_drive_images = rec.get("drive_images") or ""
            
            coach_badge_title = f" ｜ 担当: {r_coach_name}" if r_coach_name else ""
            expander_title = f"📅 レッスン日: {r_date}{coach_badge_title} (ID: {r_id})" + ("\u200b" * rf_k)
            edit_expander_title = f"✏️ この練習記録の内容を編集する" + ("\u200b" * rf_k)
            
            with st.expander(expander_title, expanded=False):
                if r_coach_name:
                    st.markdown(f'<div style="background-color:#eef2ff; border-left:4px solid #4f46e5; padding:8px 12px; border-radius:4px; font-weight:bold; color:#312e81; margin-bottom:12px;">🏌️‍♂️ 担当コーチ: {r_coach_name}</div>', unsafe_allow_html=True)
                else:
                    st.markdown('<div style="color:#888; font-size:13px; margin-bottom:8px;">🏌️‍♂️ 担当コーチ: （未指定）</div>', unsafe_allow_html=True)

                previous = get_previous_lesson(selected_id, r_date, r_id)
                r_previous_issues = combined_issues(rec, "previous")
                r_previous_date = rec.get("previous_check_date")
                if rec.get("previous_issues") is None and not r_previous_issues:
                    r_previous_issues = previous_issue_value(previous)
                if r_previous_date is None:
                    r_previous_date = previous["lesson_date"] if previous else ""
                st.markdown("**📌 前回の課題・問題点:**")
                st.caption(f"直前のレッスン（チェック日）：{r_previous_date or '未記入'}")
                st.markdown(render_text_box(r_previous_issues, "blue", text_color="#cc0000", empty_label=""), unsafe_allow_html=True)

                st.markdown("### ■ 今回の練習内容")
                st.markdown(render_text_box(r_lesson_practice, "blue", text_color="#000080"), unsafe_allow_html=True)
                st.markdown("### ■ 今回の課題・問題点")
                st.markdown(render_text_box(combined_issues(rec, "current"), "blue", text_color="#cc0000", empty_label=""), unsafe_allow_html=True)

                # --- Android / iPhone / PC共通 動画・静止画 再生カード ---
                available_videos = [(number, url) for number, url in enumerate(r_video_urls, 1) if url.startswith("http")]
                drive_imgs_list = [u.strip() for u in r_drive_images.split(",") if u.strip() and u.strip().startswith("http")]

                if available_videos or drive_imgs_list:
                    st.markdown("---")
                    st.markdown("### 🎬 スイング動画・静止画")
                    if available_videos:
                        video_cols = st.columns(2)
                        for idx, (number, url) in enumerate(available_videos):
                            with video_cols[idx % 2]:
                                st.markdown(f"""
                                <div style="background:#f1f5f9; border:1px solid #cbd5e1; border-radius:10px; padding:12px; text-align:center; margin-bottom:6px;">
                                    <div style="font-size:22px; margin-bottom:2px;">🎥</div>
                                    <div style="font-weight:bold; font-size:14px; color:#1e293b;">スイング動画 {number}</div>
                                </div>
                                """, unsafe_allow_html=True)
                                render_video_links(url, number)
                        st.caption("動画が開かない場合は、共有権限とGoogleドライブ側の動画処理状況を確認してください。")

                    # 静止画
                    if drive_imgs_list:
                        st.markdown("<div style='margin-top:10px;'></div>", unsafe_allow_html=True)
                        st.caption("📷 静止画・解析データ:")
                        num_img_cols = min(len(drive_imgs_list), 3)
                        img_cols = st.columns(num_img_cols)
                        for idx, img_url in enumerate(drive_imgs_list):
                            with img_cols[idx % num_img_cols]:
                                st.markdown(f"""
                                <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:10px; text-align:center; margin-bottom:6px;">
                                    <div style="font-size:18px;">🖼️</div>
                                    <div style="font-weight:bold; font-size:13px; color:#334155;">画像 {idx+1}</div>
                                </div>
                                """, unsafe_allow_html=True)
                                img_fid = get_drive_file_id(img_url)
                                zoom_url = clean_drive_url(img_url) if img_fid else img_url
                                with st.container(key=f"image_zoom_{r_id}_{idx}"):
                                    st.link_button("🔍 拡大表示", zoom_url, use_container_width=True, type="primary")
                                render_fullscreen_preview(img_url, f"画像 {idx + 1}", height=300)

                st.markdown("---")
                
                # 編集エリア
                with st.expander(edit_expander_title, expanded=False):
                    try:
                        parsed_date = datetime.strptime(r_date, "%Y-%m-%d").date()
                    except ValueError:
                        parsed_date = date.today()
                    
                    e_top_c1, e_top_c2 = st.columns(2)
                    with e_top_c1:
                        edit_date = st.date_input("📅 レッスン受講日を変更", value=parsed_date, key=f"ed_date_{r_id}_{rf_k}")
                    with e_top_c2:
                        edit_coach_options = ["（未選択）"] + coach_list
                        default_coach_idx = edit_coach_options.index(r_coach_name) if r_coach_name in edit_coach_options else 0
                        chosen_coach_edit = st.selectbox("🏌️‍♂️ 担当コーチを変更", options=edit_coach_options, index=default_coach_idx, key=f"ed_coach_{r_id}_{rf_k}")
                        edit_coach_val = "" if chosen_coach_edit == "（未選択）" else chosen_coach_edit
                    
                    edit_previous_date = st.date_input(
                        "📅 直前のレッスン（チェック日）",
                        value=parse_optional_date(r_previous_date),
                        key=f"ed_previous_date_{r_id}_{rf_k}",
                    )
                    edit_previous_issues = st.text_area(
                        "前回の課題・問題点", value=r_previous_issues,
                        key=f"ed_previous_issues_{r_id}_{rf_k}", height=180,
                    )
                    st.markdown("### ■ 今回の練習内容")
                    edit_lesson_practice = st.text_area(
                        "今回の練習内容", value=r_lesson_practice,
                        key=f"ed_practice_{r_id}_{rf_k}",
                    )
                    edit_target_goal = r_target_goal
                    edit_eval_note = r_eval_note
                    st.markdown("### ■ 今回の課題・問題点")
                    edit_current_issues_key = f"ed_current_issues_{r_id}_{rf_k}"
                    issue_col, carry_col = st.columns([4, 1])
                    with issue_col:
                        edit_current_issues = st.text_area(
                            "今回の課題・問題点", value=combined_issues(rec, "current"),
                            key=edit_current_issues_key, height=180,
                        )
                    with carry_col:
                        st.button(
                            "前回の内容を引き継ぐ", key=f"ed_carry_issues_{r_id}_{rf_k}",
                            type="primary", on_click=carry_previous_issue,
                            args=(edit_current_issues_key, f"ed_previous_issues_{r_id}_{rf_k}"),
                        )

                    st.markdown("---")
                    st.markdown("**🎬 Google ドライブ共有リンクの変更・追加:**")
                    edit_video_urls = []
                    edit_video_cols = st.columns(2)
                    for number in range(1, 5):
                        with edit_video_cols[(number - 1) % 2]:
                            edit_video_urls.append(st.text_input(
                                f"動画 {number} リンク", value=r_video_urls[number - 1],
                                key=f"ed_v{number}_url_{r_id}_{rf_k}",
                            ))

                    existing_drive_imgs_text = "\n".join(r_drive_images.split(",")) if r_drive_images else ""
                    edit_drive_imgs_input = st.text_area(
                        "📷 静止画リンク（6個まで・改行で区切って入力）",
                        value=existing_drive_imgs_text,
                        key=f"ed_drive_imgs_{r_id}_{rf_k}"
                    )

                    btn_c1, btn_c2 = st.columns([3, 1])
                    with btn_c1:
                        if st.button("💾 日付・修正内容を保存する", key=f"btn_update_{r_id}_{rf_k}", type="primary"):
                            try:
                                clean_ed_videos = [clean_drive_url(url) for url in edit_video_urls]
                                clean_ed_imgs = clean_image_links(edit_drive_imgs_input)

                                update_lesson(
                                    r_id, edit_date, edit_coach_val, 
                                    edit_target_goal, edit_lesson_practice, edit_eval_note, 
                                    clean_ed_videos[0], clean_ed_videos[1], clean_ed_imgs, edit_previous_issues, edit_previous_date,
                                    current_issues=edit_current_issues, v3_url=clean_ed_videos[2], v4_url=clean_ed_videos[3]
                                )
                                
                                st.session_state.refresh_key += 1
                                st.toast("✅ レッスン内容を更新しました！")
                                st.rerun()
                            except Exception as e:
                                st.error(f"❌ 更新に失敗しました: {e}")
                    with btn_c2:
                        confirm_delete = st.checkbox("削除確認", key=f"chk_del_{r_id}_{rf_k}")
                        if st.button("🗑️ レッスンを完全削除", key=f"btn_del_{r_id}_{rf_k}", disabled=not confirm_delete):
                            try:
                                delete_lesson(r_id)
                                st.session_state.refresh_key += 1
                                st.toast("🗑️ レッスン記録を削除しました。")
                                st.rerun()
                            except Exception as e:
                                st.error(f"❌ 削除に失敗しました: {e}")
