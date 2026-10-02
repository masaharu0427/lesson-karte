import streamlit as st
import sqlite3
import os
import re
from datetime import datetime, date

# ページ基本設定
st.set_page_config(page_title="ゴルフ スイングチェックカルテ", layout="wide")

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

# GoogleドライブURLの整形（クリーンなURLで保存）
def clean_drive_url(url):
    if not url:
        return ""
    fid = get_drive_file_id(url)
    if fid:
        return f"https://drive.google.com/file/d/{fid}/view?usp=sharing"
    return url.strip()

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
    c = conn.cursor()
    c.execute("DELETE FROM lessons WHERE student_id = ?", (student_id,))
    c.execute("DELETE FROM students WHERE id = ?", (student_id,))
    conn.commit()
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
    c = conn.cursor()
    c.execute("DELETE FROM coaches WHERE id = ?", (coach_id,))
    conn.commit()
    conn.close()

def save_lesson(student_id, lesson_date, coach_name, scores, target_goal, lesson_practice, evaluation_note, v1_url="", v2_url="", drive_images=""):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''
        INSERT INTO lessons (
            student_id, lesson_date, coach_name,
            addr_posture, addr_align, 
            back_path, back_top, 
            down_plane, down_release, 
            video1, video2, images, 
            target_goal, lesson_practice, evaluation_note,
            v1_url, v2_url, drive_images
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '', '', '', ?, ?, ?, ?, ?, ?)
    ''', (
        student_id, str(lesson_date), coach_name,
        scores["addr_posture"], scores["addr_align"],
        scores["back_path"], scores["back_top"],
        scores["down_plane"], scores["down_release"],
        target_goal, lesson_practice, evaluation_note,
        v1_url, v2_url, drive_images
    ))
    conn.commit()
    conn.close()

def update_lesson(lesson_id, lesson_date, coach_name, scores, target_goal, lesson_practice, evaluation_note, v1_url="", v2_url="", drive_images=""):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''
        UPDATE lessons 
        SET lesson_date = ?,
            coach_name = ?,
            addr_posture = ?,
            addr_align = ?,
            back_path = ?,
            back_top = ?,
            down_plane = ?,
            down_release = ?,
            target_goal = ?,
            lesson_practice = ?,
            evaluation_note = ?,
            v1_url = ?,
            v2_url = ?,
            drive_images = ?
        WHERE id = ?
    ''', (
        str(lesson_date), coach_name,
        scores["addr_posture"], scores["addr_align"],
        scores["back_path"], scores["back_top"],
        scores["down_plane"], scores["down_release"],
        target_goal, lesson_practice, evaluation_note,
        v1_url, v2_url, drive_images, lesson_id
    ))
    conn.commit()
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

def render_score_badge(score):
    if score is None or score == "":
        return '<span style="color:#aaa; font-size:16px;">-</span>'
    if score == 1:
        color = "#0066cc"
        bg = "#e6f0fa"
    elif score == 2:
        color = "#d9822b"
        bg = "#fdf6e2"
    elif score == 3:
        color = "#cc0000"
        bg = "#fae6e6"
    else:
        return '<span style="color:#aaa; font-size:16px;">-</span>'
    return f'<span style="background-color:{bg}; color:{color}; font-weight:bold; font-size:18px; padding:3px 12px; border-radius:6px; border:1px solid {color};">{score}</span>'

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
st.title("⛳ ゴルフレッスン スイングチェックカルテ")

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

if not raw_students:
    st.info("サイドバーから生徒を登録してください。")
    st.stop()

student_dict = {s["name"]: s for s in raw_students}
selected_name = st.sidebar.selectbox("受講者を選択", options=list(student_dict.keys()))

curr_student = student_dict[selected_name]
selected_id = curr_student["id"]

with st.sidebar.expander("👤 生徒プロフィールを編集・削除", expanded=False):
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
                
    st.markdown("---")
    del_s_chk = st.checkbox("この生徒と全レッスン履歴を削除する", key=f"del_s_chk_{selected_id}")
    if st.button("🗑️ 生徒を完全削除", key=f"btn_del_s_{selected_id}", disabled=not del_s_chk):
        delete_student(selected_id)
        st.session_state.refresh_key += 1
        st.warning(f"{selected_name} 様を削除しました。")
        st.rerun()

st.sidebar.markdown("---")
st.sidebar.header("コーチ管理")
raw_coaches = get_coaches()
coach_list = [c["name"] for c in raw_coaches]

with st.sidebar.expander("🏌️‍♂️ コーチの追加・削除", expanded=False):
    new_coach_name = st.text_input("新規コーチ氏名", placeholder="例: 山田 コーチ", key="new_coach_name_input")
    if st.button("＋ コーチを登録", key="btn_add_coach"):
        if new_coach_name.strip():
            if add_coach(new_coach_name.strip()):
                st.success(f"{new_coach_name} を登録しました")
                st.rerun()
            else:
                st.error("同じ名前のコーチが既に登録されています。")
    
    if raw_coaches:
        st.markdown("---")
        st.caption("登録済みコーチの削除:")
        coach_to_del = st.selectbox("削除するコーチを選択", options=[c["name"] for c in raw_coaches], key="coach_to_del_select")
        del_coach_id = [c["id"] for c in raw_coaches if c["name"] == coach_to_del][0]
        if st.button(f"🗑️ {coach_to_del} を削除", key="btn_del_coach"):
            delete_coach(del_coach_id)
            st.warning(f"{coach_to_del} を削除しました。")
            st.rerun()

st.caption(f"**受講者:** {selected_name} 様 ｜ **ハンデ/平均:** {curr_student.get('handicap') or '未設定'} ｜ **長期目標:** {curr_student.get('goal') or '未設定'}")

tab_new, tab_history = st.tabs(["📝 新規スイングチェック入力", "📂 過去カルテ・日付変更・編集"])

# ================================
# タブ1: 新規入力フォーム
# ================================
with tab_new:
    st.subheader(f"{selected_name} 様 - レッスンチェック新規入力")
    
    fk = st.session_state.form_reset_key
    
    top_col1, top_col2 = st.columns(2)
    with top_col1:
        lesson_date = st.date_input("📅 レッスン受講日", value=date.today(), key=f"new_date_{fk}")
    with top_col2:
        coach_options = ["（未選択）"] + coach_list
        selected_coach_new = st.selectbox("🏌️️‍♂️ 担当コーチ", options=coach_options, index=0, key=f"new_coach_{fk}")
        new_coach_val = "" if selected_coach_new == "（未選択）" else selected_coach_new

    st.markdown("### ■ スイング3段階チェック (1: 青 / 2: 黄 / 3: 赤)")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("#### 【アドレス】")
        addr_posture = st.radio("前傾・ポスチャー", [1, 2, 3], index=None, horizontal=True, key=f"new_p1_{fk}")
        st.markdown(f"現在値: {render_score_badge(addr_posture)}", unsafe_allow_html=True)
        
        addr_align = st.radio("アライメント（肩・足の向き）", [1, 2, 3], index=None, horizontal=True, key=f"new_p2_{fk}")
        st.markdown(f"現在値: {render_score_badge(addr_align)}", unsafe_allow_html=True)

    with col2:
        st.markdown("#### 【バックスイング】")
        back_path = st.radio("テイクバック軌道", [1, 2, 3], horizontal=True, index=None, key=f"new_p3_{fk}")
        st.markdown(f"現在値: {render_score_badge(back_path)}", unsafe_allow_html=True)
        
        back_top = st.radio("トップポジション（手元・フェース）", [1, 2, 3], index=None, horizontal=True, key=f"new_p4_{fk}")
        st.markdown(f"現在値: {render_score_badge(back_top)}", unsafe_allow_html=True)

    with col3:
        st.markdown("#### 【ダウンスイング】")
        down_plane = st.radio("スイングプレーン", [1, 2, 3], index=None, horizontal=True, key=f"new_p5_{fk}")
        st.markdown(f"現在値: {render_score_badge(down_plane)}", unsafe_allow_html=True)
        
        down_release = st.radio("インパクト・リリース", [1, 2, 3], index=None, horizontal=True, key=f"new_p6_{fk}")
        st.markdown(f"現在値: {render_score_badge(down_release)}", unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("### ■ レッスン記録・カルテ詳細")
    
    in_col1, in_col2 = st.columns(2)
    with in_col1:
        target_goal = st.text_area("📌 取り組んでいる課題・目標", value="", placeholder="例:\n・スライス改善\n・トップでのフェース開き防止", key=f"new_target_goal_{fk}")
    with in_col2:
        lesson_practice = st.text_area("🏌️ 今回のレッスン・練習", value="", placeholder="例:\n・ハーフスイングドリル\n・手首のコック維持練習", key=f"new_lesson_practice_{fk}")
    
    evaluation_note = st.text_area("📝 評価", value="", placeholder="例:\n・手元の浮きが解消され始めた\n・次回はフォローの抜けを確認", key=f"new_evaluation_note_{fk}")

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
            scores = {
                "addr_posture": addr_posture,
                "addr_align": addr_align,
                "back_path": back_path,
                "back_top": back_top,
                "down_plane": down_plane,
                "down_release": down_release,
            }
            
            clean_v1 = clean_drive_url(v1_url)
            clean_v2 = clean_drive_url(v2_url)
            drive_imgs_clean = ",".join([clean_drive_url(line) for line in drive_imgs_input.splitlines() if line.strip()])
            
            save_lesson(
                selected_id, lesson_date, new_coach_val, scores,
                target_goal, lesson_practice, evaluation_note,
                clean_v1, clean_v2, drive_imgs_clean
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

                st.markdown(f"""
                | アドレス: 姿勢 | アドレス: 向き | バック: 軌道 | バック: トップ | ダウン: プレーン | ダウン: リリース |
                | :---: | :---: | :---: | :---: | :---: | :---: |
                | {render_score_badge(rec.get("addr_posture"))} | {render_score_badge(rec.get("addr_align"))} | {render_score_badge(rec.get("back_path"))} | {render_score_badge(rec.get("back_top"))} | {render_score_badge(rec.get("down_plane"))} | {render_score_badge(rec.get("down_release"))} |
                """, unsafe_allow_html=True)
                
                t_col1, t_col2 = st.columns(2)
                with t_col1:
                    st.markdown("**📌 取り組んでいる課題・目標:**")
                    st.markdown(render_text_box(r_target_goal, "blue"), unsafe_allow_html=True)
                with t_col2:
                    st.markdown("**🏌️ 今回のレッスン・練習:**")
                    st.markdown(render_text_box(r_lesson_practice, "blue"), unsafe_allow_html=True)
                
                st.markdown("**📝 評価:**")
                st.markdown(render_text_box(r_eval_note, "green"), unsafe_allow_html=True)
                
                # --- iPhone対応 動画・静止画 再生カード ---
                fid1 = get_drive_file_id(r_v1_url)
                fid2 = get_drive_file_id(r_v2_url)
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
                                    <div style="font-weight:bold; font-size:14px; color:#1e293b;">スイング動画 1 (後方)</div>
                                </div>
                                """, unsafe_allow_html=True)
                                
                                # iPhoneアプリ直通URL（Googleドライブアプリが入っていれば最優先）
                                if fid1:
                                    app_url = f"googledrive://drive.google.com/file/d/{fid1}/view"
                                    web_url = f"https://drive.google.com/file/d/{fid1}/preview"
                                    st.link_button("📲 ドライブアプリで再生 (推奨)", app_url, use_container_width=True, type="primary")
                                    st.link_button("🌐 Safari / ブラウザで再生", web_url, use_container_width=True)
                                else:
                                    st.link_button("▶️ 動画1を開く", r_v1_url, use_container_width=True, type="primary")
                                    
                        # 動画2
                        with v_col2:
                            if has_v2:
                                st.markdown("""
                                <div style="background:#f1f5f9; border:1px solid #cbd5e1; border-radius:10px; padding:12px; text-align:center; margin-bottom:6px;">
                                    <div style="font-size:22px; margin-bottom:2px;">🎥</div>
                                    <div style="font-weight:bold; font-size:14px; color:#1e293b;">スイング動画 2 (正面)</div>
                                </div>
                                """, unsafe_allow_html=True)
                                
                                if fid2:
                                    app_url2 = f"googledrive://drive.google.com/file/d/{fid2}/view"
                                    web_url2 = f"https://drive.google.com/file/d/{fid2}/preview"
                                    st.link_button("📲 ドライブアプリで再生 (推奨)", app_url2, use_container_width=True, type="primary")
                                    st.link_button("🌐 Safari / ブラウザで再生", web_url2, use_container_width=True)
                                else:
                                    st.link_button("▶️ 動画2を開く", r_v2_url, use_container_width=True, type="primary")

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
                                    clean_img_url = f"https://drive.google.com/file/d/{img_fid}/view?usp=sharing"
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
                    
                    st.markdown("**評価スコアの修正:**")
                    ec1, ec2, ec3 = st.columns(3)
                    with ec1:
                        e_p = st.radio("アドレス: 姿勢", [1, 2, 3], index=[1, 2, 3].index(rec.get("addr_posture")) if rec.get("addr_posture") in [1, 2, 3] else None, horizontal=True, key=f"e_p_{r_id}_{rf_k}")
                        e_a = st.radio("アドレス: 向き", [1, 2, 3], index=[1, 2, 3].index(rec.get("addr_align")) if rec.get("addr_align") in [1, 2, 3] else None, horizontal=True, key=f"e_a_{r_id}_{rf_k}")
                    with ec2:
                        e_bp = st.radio("バック: 軌道", [1, 2, 3], index=[1, 2, 3].index(rec.get("back_path")) if rec.get("back_path") in [1, 2, 3] else None, horizontal=True, key=f"e_bp_{r_id}_{rf_k}")
                        e_bt = st.radio("バック: トップ", [1, 2, 3], index=[1, 2, 3].index(rec.get("back_top")) if rec.get("back_top") in [1, 2, 3] else None, horizontal=True, key=f"e_bt_{r_id}_{rf_k}")
                    with ec3:
                        e_dp = st.radio("ダウン: プレーン", [1, 2, 3], index=[1, 2, 3].index(rec.get("down_plane")) if rec.get("down_plane") in [1, 2, 3] else None, horizontal=True, key=f"e_dp_{r_id}_{rf_k}")
                        e_dr = st.radio("ダウン: リリース", [1, 2, 3], index=[1, 2, 3].index(rec.get("down_release")) if rec.get("down_release") in [1, 2, 3] else None, horizontal=True, key=f"e_dr_{r_id}_{rf_k}")
                    
                    st.markdown("**レッスンカルテ内容の修正:**")
                    ed_col1, ed_col2 = st.columns(2)
                    with ed_col1:
                        edit_target_goal = st.text_area("📌 取り組んでいる課題・目標", value=r_target_goal, key=f"ed_goal_{r_id}_{rf_k}")
                    with ed_col2:
                        edit_lesson_practice = st.text_area("🏌️ 今回のレッスン・練習", value=r_lesson_practice, key=f"ed_practice_{r_id}_{rf_k}")
                    
                    edit_eval_note = st.text_area("📝 評価", value=r_eval_note, key=f"ed_eval_{r_id}_{rf_k}")
                    
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

                                updated_scores = {
                                    "addr_posture": e_p,
                                    "addr_align": e_a,
                                    "back_path": e_bp,
                                    "back_top": e_bt,
                                    "down_plane": e_dp,
                                    "down_release": e_dr,
                                }
                                
                                update_lesson(
                                    r_id, edit_date, edit_coach_val, updated_scores, 
                                    edit_target_goal, edit_lesson_practice, edit_eval_note, 
                                    clean_ed_v1, clean_ed_v2, clean_ed_imgs
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