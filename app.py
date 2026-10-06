import streamlit as st
import sqlite3
import os
import re
from datetime import datetime, date
from urllib.parse import urlsplit, parse_qs, urlencode

# ページ基本設定
st.set_page_config(page_title="スイング・チェックシート", layout="wide")

# 画面リセット用のセッション管理
if "refresh_key" not in st.session_state:
    st.session_state.refresh_key = 0
if "form_reset_key" not in st.session_state:
    st.session_state.form_reset_key = 0

# DB接続ヘルパー
def get_db_connection():
    conn = sqlite3.connect("golf_lesson.db")
    conn.row_factory = sqlite3.Row
    return conn

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

# 独自のアプリ用スキームに依存しない再生ボタン
def render_video_links(url, number):
    st.link_button(
        f"▶️ 動画{number}を開く（Googleドライブ）",
        drive_playback_url(url),
        use_container_width=True,
        type="primary",
    )
    if get_drive_file_id(url):
        st.link_button(
            "🌐 ブラウザ用プレビューを開く",
            drive_playback_url(url, preview=True),
            use_container_width=True,
        )

# データベース初期化・マイグレーション
def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            handicap TEXT,
            goal TEXT
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS coaches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS lessons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER,
            lesson_date TEXT,
            addr_posture INTEGER,
            addr_align INTEGER,
            back_path INTEGER,
            back_top INTEGER,
            down_plane INTEGER,
            down_release INTEGER,
            video1 TEXT,
            video2 TEXT,
            images TEXT,
            target_goal TEXT,
            lesson_practice TEXT,
            evaluation_note TEXT,
            v1_url TEXT,
            v2_url TEXT,
            coach_name TEXT,
            drive_images TEXT,
            FOREIGN KEY (student_id) REFERENCES students(id)
        )
    ''')
    
    c.execute("PRAGMA table_info(lessons)")
    existing_cols = [col["name"] for col in c.fetchall()]
    if "target_goal" not in existing_cols:
        c.execute("ALTER TABLE lessons ADD COLUMN target_goal TEXT")
    if "lesson_practice" not in existing_cols:
        c.execute("ALTER TABLE lessons ADD COLUMN lesson_practice TEXT")
    if "evaluation_note" not in existing_cols:
        c.execute("ALTER TABLE lessons ADD COLUMN evaluation_note TEXT")
    if "v1_url" not in existing_cols:
        c.execute("ALTER TABLE lessons ADD COLUMN v1_url TEXT")
    if "v2_url" not in existing_cols:
        c.execute("ALTER TABLE lessons ADD COLUMN v2_url TEXT")
    if "coach_name" not in existing_cols:
        c.execute("ALTER TABLE lessons ADD COLUMN coach_name TEXT")
    if "drive_images" not in existing_cols:
        c.execute("ALTER TABLE lessons ADD COLUMN drive_images TEXT")

    for column in ("previous_issues", "previous_check_date", "previous_address", "previous_backswing", "previous_downswing", "current_address", "current_backswing", "current_downswing"):
        if column not in existing_cols:
            c.execute(f"ALTER TABLE lessons ADD COLUMN {column} TEXT")

    conn.commit()
    conn.close()

init_db()

# DB操作関数
def get_students():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id, name, handicap, goal FROM students ORDER BY name")
    rows = [dict(row) for row in c.fetchall()]
    conn.close()
    return rows

def add_student(name, handicap, goal):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO students (name, handicap, goal) VALUES (?, ?, ?)", (name, handicap, goal))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    conn.close()

def update_student(student_id, name, handicap, goal):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute('UPDATE students SET name = ?, handicap = ?, goal = ? WHERE id = ?', (name, handicap, goal, student_id))
        conn.commit()
        success = True
    except sqlite3.IntegrityError:
        success = False
    conn.close()
    return success

def delete_student(student_id):
    conn = get_db_connection()
    try:
        with conn:
            conn.execute("DELETE FROM lessons WHERE student_id = ?", (student_id,))
            conn.execute("DELETE FROM students WHERE id = ?", (student_id,))
    finally:
        conn.close()

def get_coaches():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id, name FROM coaches ORDER BY name")
    rows = [dict(row) for row in c.fetchall()]
    conn.close()
    return rows

def add_coach(name):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO coaches (name) VALUES (?)", (name,))
        conn.commit()
        success = True
    except sqlite3.IntegrityError:
        success = False
    conn.close()
    return success

def delete_coach(coach_id):
    conn = get_db_connection()
    try:
        with conn:
            conn.execute("DELETE FROM coaches WHERE id = ?", (coach_id,))
    finally:
        conn.close()

def save_lesson(student_id, lesson_date, coach_name, target_goal, lesson_practice, evaluation_note, v1_url="", v2_url="", drive_images="", previous_issues="", previous_check_date=None, previous_address="", previous_backswing="", previous_downswing="", current_address="", current_backswing="", current_downswing=""):
    conn = get_db_connection()
    try:
        with conn:
            conn.execute("""
                INSERT INTO lessons (
                    student_id, lesson_date, coach_name,
                    target_goal, lesson_practice, evaluation_note,
                    v1_url, v2_url, drive_images,
                    previous_issues, previous_check_date,
                    previous_address, previous_backswing, previous_downswing,
                    current_address, current_backswing, current_downswing
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (student_id, str(lesson_date), coach_name,
                  target_goal, lesson_practice, evaluation_note,
                  v1_url, v2_url, drive_images, previous_issues,
                  str(previous_check_date) if previous_check_date else "",
                  previous_address, previous_backswing, previous_downswing,
                  current_address, current_backswing, current_downswing))
    finally:
        conn.close()

def update_lesson(lesson_id, lesson_date, coach_name, target_goal, lesson_practice, evaluation_note, v1_url="", v2_url="", drive_images="", previous_issues="", previous_check_date=None, previous_address="", previous_backswing="", previous_downswing="", current_address="", current_backswing="", current_downswing=""):
    conn = get_db_connection()
    try:
        with conn:
            conn.execute("""
                UPDATE lessons SET lesson_date = ?, coach_name = ?,
                    target_goal = ?, lesson_practice = ?, evaluation_note = ?,
                    v1_url = ?, v2_url = ?, drive_images = ?,
                    previous_issues = ?, previous_check_date = ?,
                    previous_address = ?, previous_backswing = ?, previous_downswing = ?,
                    current_address = ?, current_backswing = ?, current_downswing = ?
                WHERE id = ?
            """, (str(lesson_date), coach_name,
                  target_goal, lesson_practice, evaluation_note,
                  v1_url, v2_url, drive_images, previous_issues,
                  str(previous_check_date) if previous_check_date else "",
                  previous_address, previous_backswing, previous_downswing,
                  current_address, current_backswing, current_downswing, lesson_id))
    finally:
        conn.close()

def delete_lesson(lesson_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM lessons WHERE id = ?", (lesson_id,))
    conn.commit()
    conn.close()

def get_student_history(student_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM lessons WHERE student_id = ? ORDER BY lesson_date DESC, id DESC", (student_id,))
    rows = [dict(row) for row in c.fetchall()]
    conn.close()
    return rows

def get_previous_lesson(student_id, lesson_date, lesson_id=None):
    # 日付順。同日では、編集中の記録より前に登録された記録だけを参照。
    for record in get_student_history(student_id):
        if record["lesson_date"] < str(lesson_date) or (
            record["lesson_date"] == str(lesson_date)
            and (lesson_id is None or record["id"] < lesson_id)
        ):
            return record
    return None

def previous_issue_value(record, phase):
    if not record:
        return ""
    value = record.get(f"current_{phase}")
    if value is not None:
        return value
    return record.get(f"previous_{phase}") or ""

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

def render_text_box(content, box_type="blue"):
    if not content or not str(content).strip():
        return '<div style="color: #888; font-style: italic; padding: 8px;">（未記入）</div>'
    
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
        color: #222;
        margin-top: 6px;
        margin-bottom: 12px;
    ">{content}</div>'''

# --- 画面構成 ---
st.title("スイング・チェックシート")
if "carry_notice" in st.session_state:
    st.info(st.session_state.pop("carry_notice"))
if "management_notice" in st.session_state:
    st.success(st.session_state.pop("management_notice"))

# サイドバー
st.sidebar.header("生徒管理")
raw_students = get_students()

with st.sidebar.expander("＋ 新規生徒を登録", expanded=False):
    new_s_name = st.text_input("生徒名", key="new_s_name")
    new_s_hdcp = st.text_input("現在のハンデ/平均スコア", key="new_s_hdcp")
    new_s_goal = st.text_input("長期目標", key="new_s_goal")
    if st.button("登録する", key="btn_add_student"):
        if new_s_name.strip():
            add_student(new_s_name.strip(), new_s_hdcp.strip(), new_s_goal.strip())
            st.success(f"{new_s_name} 様を登録しました")
            st.rerun()

st.sidebar.markdown("---")
st.sidebar.header("コーチ管理")
raw_coaches = get_coaches()
coach_list = [c["name"] for c in raw_coaches]

with st.sidebar.expander("＋ コーチを登録", expanded=False):
    new_coach_name = st.text_input("新規コーチ氏名", placeholder="例: 山田 コーチ", key="new_coach_name_input")
    if st.button("＋ コーチを登録", key="btn_add_coach"):
        if new_coach_name.strip():
            if add_coach(new_coach_name.strip()):
                st.success(f"{new_coach_name} を登録しました")
                st.rerun()
            else:
                st.error("同じ名前のコーチが既に登録されています。")

with st.sidebar.expander("🗑️ コーチを削除", expanded=True):
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
            except sqlite3.Error as e:
                st.error(f"コーチの削除に失敗しました: {e}")
    else:
        st.info("登録済みのコーチはいません。")

if not raw_students:
    st.info("サイドバーから生徒を登録してください。")
    st.stop()

student_dict = {s["name"]: s for s in raw_students}
selected_name = st.sidebar.selectbox("受講者を選択", options=list(student_dict.keys()))

curr_student = student_dict[selected_name]
selected_id = curr_student["id"]

with st.sidebar.expander("👤 生徒プロフィールを編集", expanded=False):
    edit_s_name = st.text_input("氏名", value=selected_name, key=f"s_name_{selected_id}")
    edit_s_hdcp = st.text_input("ハンデ / 平均スコア", value=curr_student.get("handicap") or "", key=f"s_hdcp_{selected_id}")
    edit_s_goal = st.text_input("長期目標", value=curr_student.get("goal") or "", key=f"s_goal_{selected_id}")
    
    if st.button("💾 プロフィールを更新", type="primary", key=f"btn_up_s_{selected_id}"):
        if edit_s_name.strip():
            if update_student(selected_id, edit_s_name.strip(), edit_s_hdcp.strip(), edit_s_goal.strip()):
                st.session_state.refresh_key += 1
                st.toast("✅ プロフィールを更新しました！")
                st.rerun()
            else:
                st.error("同姓同名の生徒が既に存在します。別の名前を指定してください。")
                
with st.sidebar.expander("🗑️ 生徒を削除", expanded=True):
    st.write(f"削除対象：{selected_name} 様")
    st.caption("この生徒のプロフィールと全レッスン履歴を削除します。元に戻せません。")
    del_s_chk = st.checkbox("この生徒と全レッスン履歴を削除することを確認", key=f"del_s_chk_{selected_id}")
    if st.button("🗑️ 選択した生徒を削除", key=f"btn_del_s_{selected_id}", disabled=not del_s_chk):
        try:
            delete_student(selected_id)
            st.session_state.refresh_key += 1
            st.session_state.management_notice = f"{selected_name} 様と全レッスン履歴を削除しました。"
            st.rerun()
        except sqlite3.Error as e:
            st.error(f"生徒の削除に失敗しました: {e}")


st.caption(f"**受講者:** {selected_name} 様 ｜ **ハンデ/平均:** {curr_student.get('handicap') or '未設定'} ｜ **長期目標:** {curr_student.get('goal') or '未設定'}")

tab_new, tab_history = st.tabs(["📝 新規スイングチェック入力", "📂 過去カルテ・日付変更・編集"])

# ================================
# タブ1: 新規入力フォーム
# ================================
with tab_new:
    st.subheader(f"{selected_name} 様 - レッスンチェック新規入力")
    
    fk = f"{selected_id}_{st.session_state.form_reset_key}"
    
    top_col1, top_col2 = st.columns(2)
    with top_col1:
        lesson_date = st.date_input("📅 レッスン受講日", value=date.today(), key=f"new_date_{fk}")
    with top_col2:
        coach_options = ["（未選択）"] + coach_list
        selected_coach_new = st.selectbox("🏌️️‍♂️ 担当コーチ", options=coach_options, index=0, key=f"new_coach_{fk}")
        new_coach_val = "" if selected_coach_new == "（未選択）" else selected_coach_new

    previous = get_previous_lesson(selected_id, lesson_date)
    previous_key = f"{selected_id}_{fk}_{lesson_date}_{previous['id'] if previous else 0}_{st.session_state.refresh_key}"
    st.markdown("### ■ 前回の課題・問題点")
    previous_check_date = st.date_input(
        "📅 直前のレッスン（チェック日）",
        value=parse_optional_date(previous["lesson_date"]) if previous else None,
        key=f"new_previous_date_{previous_key}",
    )
    previous_issues = ""
    previous_address = st.text_area(
        "アドレス", value=previous_issue_value(previous, "address"),
        placeholder="アドレスの課題・問題点を記入",
        key=f"new_previous_address_{previous_key}",
    )
    previous_backswing = st.text_area(
        "バックスイング", value=previous_issue_value(previous, "backswing"),
        placeholder="バックスイングの課題・問題点を記入",
        key=f"new_previous_backswing_{previous_key}",
    )
    previous_downswing = st.text_area(
        "ダウンスイング", value=previous_issue_value(previous, "downswing"),
        placeholder="ダウンスイングの課題・問題点を記入",
        key=f"new_previous_downswing_{previous_key}",
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
    current_address_key = f"new_current_address_{previous_key}"
    issue_col, carry_col = st.columns([4, 1])
    with issue_col:
        current_address = st.text_area(
            "アドレス", placeholder="今回のアドレスの課題・問題点を記入",
            key=current_address_key,
        )
    with carry_col:
        st.button(
            "前回の内容を引き継ぐ", key=f"carry_address_{previous_key}",
            type="primary",
            on_click=carry_previous_issue,
            args=(current_address_key, f"new_previous_address_{previous_key}"),
        )
    current_backswing_key = f"new_current_backswing_{previous_key}"
    issue_col, carry_col = st.columns([4, 1])
    with issue_col:
        current_backswing = st.text_area(
            "バックスイング", placeholder="今回のバックスイングの課題・問題点を記入",
            key=current_backswing_key,
        )
    with carry_col:
        st.button(
            "前回の内容を引き継ぐ", key=f"carry_backswing_{previous_key}",
            type="primary",
            on_click=carry_previous_issue,
            args=(current_backswing_key, f"new_previous_backswing_{previous_key}"),
        )
    current_downswing_key = f"new_current_downswing_{previous_key}"
    issue_col, carry_col = st.columns([4, 1])
    with issue_col:
        current_downswing = st.text_area(
            "ダウンスイング", placeholder="今回のダウンスイングの課題・問題点を記入",
            key=current_downswing_key,
        )
    with carry_col:
        st.button(
            "前回の内容を引き継ぐ", key=f"carry_downswing_{previous_key}",
            type="primary",
            on_click=carry_previous_issue,
            args=(current_downswing_key, f"new_previous_downswing_{previous_key}"),
        )

    st.markdown("---")
    st.markdown("### ■ Google ドライブ共有リンク登録")
    st.caption("※共有設定を「リンクを知っている全員（閲覧者）」にしたリンクを貼り付けてください。")
    
    u_col1, u_col2 = st.columns(2)
    with u_col1:
        v1_url = st.text_input("🎥 動画 1 共有リンク（後方など）", value="", placeholder="https://drive.google.com/file/d/.../view", key=f"new_v1_url_{fk}")
    with u_col2:
        v2_url = st.text_input("🎥 動画 2 共有リンク（正面など）", value="", placeholder="https://drive.google.com/file/d/.../view", key=f"new_v2_url_{fk}")

    drive_imgs_input = st.text_area(
        "📷 静止画 共有リンク（複数ある場合は改行して入力）",
        placeholder="https://drive.google.com/file/d/xxxxxxx/view?usp=sharing\nhttps://drive.google.com/file/d/yyyyyyy/view?usp=sharing",
        key=f"new_drive_imgs_{fk}"
    )

    save_clicked = st.button("💾 このレッスンカルテを保存する", type="primary", use_container_width=True)

    if save_clicked:
        try:
            clean_v1 = clean_drive_url(v1_url)
            clean_v2 = clean_drive_url(v2_url)
            drive_imgs_clean = ",".join([clean_drive_url(line) for line in drive_imgs_input.splitlines() if line.strip()])
            
            save_lesson(
                selected_id, lesson_date, new_coach_val,
                target_goal, lesson_practice, evaluation_note,
                clean_v1, clean_v2, drive_imgs_clean, previous_issues, previous_check_date,
                previous_address, previous_backswing, previous_downswing,
                current_address, current_backswing, current_downswing
            )
            
            st.session_state.form_reset_key += 1
            st.session_state.refresh_key += 1
            st.success("✅ レッスンカルテを保存しました！")
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
            r_v1_url = rec.get("v1_url") or ""
            r_v2_url = rec.get("v2_url") or ""
            r_drive_images = rec.get("drive_images") or ""
            
            coach_badge_title = f" ｜ 担当: {r_coach_name}" if r_coach_name else ""
            expander_title = f"📅 レッスン日: {r_date}{coach_badge_title} (ID: {r_id})" + ("\u200b" * rf_k)
            edit_expander_title = f"✏️ このレッスン記録の日付・コーチ・内容・メディアを修正する" + ("\u200b" * rf_k)
            
            with st.expander(expander_title, expanded=False):
                if r_coach_name:
                    st.markdown(f'<div style="background-color:#eef2ff; border-left:4px solid #4f46e5; padding:8px 12px; border-radius:4px; font-weight:bold; color:#312e81; margin-bottom:12px;">🏌️‍♂️ 担当コーチ: {r_coach_name}</div>', unsafe_allow_html=True)
                else:
                    st.markdown('<div style="color:#888; font-size:13px; margin-bottom:8px;">🏌️‍♂️ 担当コーチ: （未指定）</div>', unsafe_allow_html=True)

                previous = get_previous_lesson(selected_id, r_date, r_id)
                r_previous_issues = rec.get("previous_issues")
                r_previous_date = rec.get("previous_check_date")
                # 変更前の記録では、直前のレッスンから初期値を補う。
                if r_previous_issues is None:
                    r_previous_issues = (previous.get("target_goal") or "") if previous else ""
                if r_previous_date is None:
                    r_previous_date = previous["lesson_date"] if previous else ""
                st.markdown("**📌 前回の課題・問題点:**")
                st.caption(f"直前のレッスン（チェック日）：{r_previous_date or '未記入'}")
                for label, field in (
                    ("アドレス", "previous_address"),
                    ("バックスイング", "previous_backswing"),
                    ("ダウンスイング", "previous_downswing"),
                ):
                    st.markdown(f"**{label}**")
                    st.markdown(render_text_box(rec.get(field) or "", "blue"), unsafe_allow_html=True)

                st.markdown("### ■ 今回の練習内容")
                st.markdown(render_text_box(r_lesson_practice, "blue"), unsafe_allow_html=True)
                st.markdown("### ■ 今回の課題・問題点")
                for label, field in (
                    ("アドレス", "current_address"),
                    ("バックスイング", "current_backswing"),
                    ("ダウンスイング", "current_downswing"),
                ):
                    st.markdown(f"**{label}**")
                    st.markdown(render_text_box(rec.get(field) or "", "blue"), unsafe_allow_html=True)

                # --- Android / iPhone / PC共通 動画・静止画 再生カード ---
                has_v1 = bool(r_v1_url and r_v1_url.startswith("http"))
                has_v2 = bool(r_v2_url and r_v2_url.startswith("http"))
                drive_imgs_list = [u.strip() for u in r_drive_images.split(",") if u.strip() and u.strip().startswith("http")]

                if has_v1 or has_v2 or drive_imgs_list:
                    st.markdown("---")
                    st.markdown("### 🎬 スイング動画・静止画")
                    
                    if has_v1 or has_v2:
                        v_col1, v_col2 = st.columns(2)
                        
                        # 動画1
                        with v_col1:
                            if has_v1:
                                st.markdown("""
                                <div style="background:#f1f5f9; border:1px solid #cbd5e1; border-radius:10px; padding:12px; text-align:center; margin-bottom:6px;">
                                    <div style="font-size:22px; margin-bottom:2px;">🎥</div>
                                    <div style="font-weight:bold; font-size:14px; color:#1e293b;">スイング動画 1 </div>
                                </div>
                                """, unsafe_allow_html=True)
                                
                                render_video_links(r_v1_url, 1)

                        # 動画2
                        with v_col2:
                            if has_v2:
                                st.markdown("""
                                <div style="background:#f1f5f9; border:1px solid #cbd5e1; border-radius:10px; padding:12px; text-align:center; margin-bottom:6px;">
                                    <div style="font-size:22px; margin-bottom:2px;">🎥</div>
                                    <div style="font-weight:bold; font-size:14px; color:#1e293b;">スイング動画 2 </div>
                                </div>
                                """, unsafe_allow_html=True)
                                
                                render_video_links(r_v2_url, 2)

                    if has_v1 or has_v2:
                        st.caption("動画が開かない場合は、共有権限とGoogleドライブ側の動画処理状況を確認してください。")

                    # 静止画
                    if drive_imgs_list:
                        st.markdown("<div style='margin-top:10px;'></div>", unsafe_allow_html=True)
                        st.caption("📷 静止画・解析データ:")
                        num_img_cols = min(len(drive_imgs_list), 4)
                        img_cols = st.columns(num_img_cols)
                        for idx, img_url in enumerate(drive_imgs_list):
                            with img_cols[idx % num_img_cols]:
                                st.markdown(f"""
                                <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:10px; text-align:center; margin-bottom:6px;">
                                    <div style="font-size:18px;">🖼️</div>
                                    <div style="font-weight:bold; font-size:13px; color:#334155;">静止画 {idx+1}</div>
                                </div>
                                """, unsafe_allow_html=True)
                                img_fid = get_drive_file_id(img_url)
                                if img_fid:
                                    clean_img_url = clean_drive_url(img_url)
                                    st.link_button("🔍 拡大表示", clean_img_url, use_container_width=True)
                                else:
                                    st.link_button("🔍 拡大表示", img_url, use_container_width=True)

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
                    edit_previous_issues = r_previous_issues
                    edit_previous_address = st.text_area(
                        "アドレス", value=rec.get("previous_address") or "",
                        key=f"ed_previous_address_{r_id}_{rf_k}",
                    )
                    edit_previous_backswing = st.text_area(
                        "バックスイング", value=rec.get("previous_backswing") or "",
                        key=f"ed_previous_backswing_{r_id}_{rf_k}",
                    )
                    edit_previous_downswing = st.text_area(
                        "ダウンスイング", value=rec.get("previous_downswing") or "",
                        key=f"ed_previous_downswing_{r_id}_{rf_k}",
                    )
                    st.markdown("### ■ 今回の練習内容")
                    edit_lesson_practice = st.text_area(
                        "今回の練習内容", value=r_lesson_practice,
                        key=f"ed_practice_{r_id}_{rf_k}",
                    )
                    edit_target_goal = r_target_goal
                    edit_eval_note = r_eval_note
                    st.markdown("### ■ 今回の課題・問題点")
                    edit_current_address_key = f"ed_current_address_{r_id}_{rf_k}"
                    issue_col, carry_col = st.columns([4, 1])
                    with issue_col:
                        edit_current_address = st.text_area(
                            "アドレス", value=rec.get("current_address") or "",
                            key=edit_current_address_key,
                        )
                    with carry_col:
                        st.button(
                            "前回の内容を引き継ぐ", key=f"ed_carry_address_{r_id}_{rf_k}",
                            type="primary",
                            on_click=carry_previous_issue,
                            args=(edit_current_address_key, f"ed_previous_address_{r_id}_{rf_k}"),
                        )
                    edit_current_backswing_key = f"ed_current_backswing_{r_id}_{rf_k}"
                    issue_col, carry_col = st.columns([4, 1])
                    with issue_col:
                        edit_current_backswing = st.text_area(
                            "バックスイング", value=rec.get("current_backswing") or "",
                            key=edit_current_backswing_key,
                        )
                    with carry_col:
                        st.button(
                            "前回の内容を引き継ぐ", key=f"ed_carry_backswing_{r_id}_{rf_k}",
                            type="primary",
                            on_click=carry_previous_issue,
                            args=(edit_current_backswing_key, f"ed_previous_backswing_{r_id}_{rf_k}"),
                        )
                    edit_current_downswing_key = f"ed_current_downswing_{r_id}_{rf_k}"
                    issue_col, carry_col = st.columns([4, 1])
                    with issue_col:
                        edit_current_downswing = st.text_area(
                            "ダウンスイング", value=rec.get("current_downswing") or "",
                            key=edit_current_downswing_key,
                        )
                    with carry_col:
                        st.button(
                            "前回の内容を引き継ぐ", key=f"ed_carry_downswing_{r_id}_{rf_k}",
                            type="primary",
                            on_click=carry_previous_issue,
                            args=(edit_current_downswing_key, f"ed_previous_downswing_{r_id}_{rf_k}"),
                        )

                    st.markdown("---")
                    st.markdown("**🎬 Google ドライブ共有リンクの変更・追加:**")
                    ed_u1, ed_u2 = st.columns(2)
                    with ed_u1:
                        edit_v1_url = st.text_input("動画 1 リンク", value=r_v1_url, key=f"ed_v1_url_{r_id}_{rf_k}")
                    with ed_u2:
                        edit_v2_url = st.text_input("動画 2 リンク", value=r_v2_url, key=f"ed_v2_url_{r_id}_{rf_k}")

                    existing_drive_imgs_text = "\n".join(r_drive_images.split(",")) if r_drive_images else ""
                    edit_drive_imgs_input = st.text_area(
                        "📷 静止画リンク（改行で区切って入力）",
                        value=existing_drive_imgs_text,
                        key=f"ed_drive_imgs_{r_id}_{rf_k}"
                    )

                    btn_c1, btn_c2 = st.columns([3, 1])
                    with btn_c1:
                        if st.button("💾 日付・修正内容を保存する", key=f"btn_update_{r_id}_{rf_k}", type="primary"):
                            try:
                                clean_ed_v1 = clean_drive_url(edit_v1_url)
                                clean_ed_v2 = clean_drive_url(edit_v2_url)
                                clean_ed_imgs = ",".join([clean_drive_url(line) for line in edit_drive_imgs_input.splitlines() if line.strip()])

                                update_lesson(
                                    r_id, edit_date, edit_coach_val, 
                                    edit_target_goal, edit_lesson_practice, edit_eval_note, 
                                    clean_ed_v1, clean_ed_v2, clean_ed_imgs, edit_previous_issues, edit_previous_date,
                                    edit_previous_address, edit_previous_backswing, edit_previous_downswing,
                                    edit_current_address, edit_current_backswing, edit_current_downswing
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