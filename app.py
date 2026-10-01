import streamlit as st
import sqlite3
import os
from datetime import datetime, date
from PIL import Image

# ページ基本設定
st.set_page_config(page_title="ゴルフ スイングチェックカルテ", layout="wide")

# 保存先フォルダの作成
UPLOAD_DIR = "uploaded_media"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# 画面リセット用のセッション管理
if "refresh_key" not in st.session_state:
    st.session_state.refresh_key = 0
if "form_reset_key" not in st.session_state:
    st.session_state.form_reset_key = 0

# データベース初期化・マイグレーション
def init_db():
    conn = sqlite3.connect("golf_lesson.db")
    c = conn.cursor()
    # 生徒テーブル
    c.execute('''
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            handicap TEXT,
            goal TEXT
        )
    ''')
    # レッスン記録テーブル
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
            FOREIGN KEY (student_id) REFERENCES students(id)
        )
    ''')
    
    # 既存DBへの新カラム追加対応（自動移行）
    c.execute("PRAGMA table_info(lessons)")
    existing_cols = [col[1] for col in c.fetchall()]
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

    conn.commit()
    conn.close()

init_db()

# DB操作関数
def get_students():
    conn = sqlite3.connect("golf_lesson.db")
    c = conn.cursor()
    c.execute("SELECT id, name, handicap, goal FROM students ORDER BY name")
    data = c.fetchall()
    conn.close()
    return data

def add_student(name, handicap, goal):
    conn = sqlite3.connect("golf_lesson.db")
    c = conn.cursor()
    try:
        c.execute("INSERT INTO students (name, handicap, goal) VALUES (?, ?, ?)", (name, handicap, goal))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    conn.close()

def update_student(student_id, name, handicap, goal):
    conn = sqlite3.connect("golf_lesson.db")
    c = conn.cursor()
    try:
        c.execute('''
            UPDATE students 
            SET name = ?, handicap = ?, goal = ? 
            WHERE id = ?
        ''', (name, handicap, goal, student_id))
        conn.commit()
        success = True
    except sqlite3.IntegrityError:
        success = False
    conn.close()
    return success

def delete_student(student_id):
    conn = sqlite3.connect("golf_lesson.db")
    c = conn.cursor()
    c.execute("DELETE FROM lessons WHERE student_id = ?", (student_id,))
    c.execute("DELETE FROM students WHERE id = ?", (student_id,))
    conn.commit()
    conn.close()

def save_lesson(student_id, lesson_date, scores, v1_path, v2_path, img_paths, target_goal, lesson_practice, evaluation_note, v1_url="", v2_url=""):
    conn = sqlite3.connect("golf_lesson.db")
    c = conn.cursor()
    c.execute('''
        INSERT INTO lessons (
            student_id, lesson_date, 
            addr_posture, addr_align, 
            back_path, back_top, 
            down_plane, down_release, 
            video1, video2, images, 
            target_goal, lesson_practice, evaluation_note,
            v1_url, v2_url
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        student_id, str(lesson_date),
        scores["addr_posture"], scores["addr_align"],
        scores["back_path"], scores["back_top"],
        scores["down_plane"], scores["down_release"],
        v1_path, v2_path, ",".join(img_paths), 
        target_goal, lesson_practice, evaluation_note,
        v1_url, v2_url
    ))
    conn.commit()
    conn.close()

def update_lesson(lesson_id, lesson_date, scores, target_goal, lesson_practice, evaluation_note, v1_path, v2_path, img_paths_str, v1_url="", v2_url=""):
    conn = sqlite3.connect("golf_lesson.db")
    c = conn.cursor()
    c.execute('''
        UPDATE lessons 
        SET lesson_date = ?,
            addr_posture = ?,
            addr_align = ?,
            back_path = ?,
            back_top = ?,
            down_plane = ?,
            down_release = ?,
            target_goal = ?,
            lesson_practice = ?,
            evaluation_note = ?,
            video1 = ?,
            video2 = ?,
            images = ?,
            v1_url = ?,
            v2_url = ?
        WHERE id = ?
    ''', (
        str(lesson_date),
        scores["addr_posture"], scores["addr_align"],
        scores["back_path"], scores["back_top"],
        scores["down_plane"], scores["down_release"],
        target_goal, lesson_practice, evaluation_note,
        v1_path, v2_path, img_paths_str,
        v1_url, v2_url, lesson_id
    ))
    conn.commit()
    conn.close()

def delete_lesson(lesson_id):
    conn = sqlite3.connect("golf_lesson.db")
    c = conn.cursor()
    c.execute("DELETE FROM lessons WHERE id = ?", (lesson_id,))
    conn.commit()
    conn.close()

def get_student_history(student_id):
    conn = sqlite3.connect("golf_lesson.db")
    c = conn.cursor()
    c.execute('''
        SELECT id, lesson_date, addr_posture, addr_align, back_path, back_top, 
               down_plane, down_release, video1, video2, images, 
               target_goal, lesson_practice, evaluation_note,
               v1_url, v2_url
        FROM lessons 
        WHERE student_id = ? 
        ORDER BY lesson_date DESC, id DESC
    ''', (student_id,))
    rows = c.fetchall()
    conn.close()
    return rows

# 1:青, 2:黄, 3:赤 のバッジHTMLを生成する関数（未選択はハイフン）
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

# 改行を崩さず綺麗に表示するためのHTML装飾ボックス
def render_text_box(content, box_type="blue"):
    if not content or not content.strip():
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

# サイドバー：生徒管理と選択
st.sidebar.header("生徒管理")
raw_students = get_students()

with st.sidebar.expander("＋ 新規生徒を登録", expanded=False):
    new_s_name = st.text_input("生徒名", key="new_s_name")
    new_s_hdcp = st.text_input("現在のハンデ/平均スコア", key="new_s_hdcp")
    new_s_goal = st.text_input("長期目標", key="new_s_goal")
    if st.button("登録する", key="btn_add_student"):
        if new_s_name:
            add_student(new_s_name, new_s_hdcp, new_s_goal)
            st.success(f"{new_s_name} 様を登録しました")
            st.rerun()

if not raw_students:
    st.info("サイドバーから生徒を登録してください。")
    st.stop()

student_dict = {s[1]: {"id": s[0], "hdcp": s[2], "goal": s[3]} for s in raw_students}
selected_name = st.sidebar.selectbox("受講者を選択", options=list(student_dict.keys()))

curr_student = student_dict[selected_name]
selected_id = curr_student["id"]

with st.sidebar.expander("👤 生徒プロフィールを編集・削除", expanded=False):
    edit_s_name = st.text_input("氏名", value=selected_name, key=f"s_name_{selected_id}")
    edit_s_hdcp = st.text_input("ハンデ / 平均スコア", value=curr_student["hdcp"] or "", key=f"s_hdcp_{selected_id}")
    edit_s_goal = st.text_input("長期目標", value=curr_student["goal"] or "", key=f"s_goal_{selected_id}")
    
    if st.button("💾 プロフィールを更新", type="primary", key=f"btn_up_s_{selected_id}"):
        if edit_s_name:
            if update_student(selected_id, edit_s_name, edit_s_hdcp, edit_s_goal):
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

st.caption(f"**受講者:** {selected_name} 様 ｜ **ハンデ/平均:** {curr_student['hdcp'] or '未設定'} ｜ **長期目標:** {curr_student['goal'] or '未設定'}")

tab_new, tab_history = st.tabs(["📝 新規スイングチェック入力", "📂 過去カルテ・日付変更・編集"])

# ================================
# タブ1: 新規入力フォーム
# ================================
with tab_new:
    st.subheader(f"{selected_name} 様 - レッスンチェック新規入力")
    
    fk = st.session_state.form_reset_key
    lesson_date = st.date_input("レッスン受講日", value=date.today(), key=f"new_date_{fk}")
    
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
    st.markdown("### ■ メディア登録（Googleフォト共有リンク または 直接ファイル）")
    
    # Googleフォト リンク入力枠
    st.markdown("##### 🔗 Googleフォト 共有リンク（推奨: 容量無制限・高速）")
    u_col1, u_col2 = st.columns(2)
    with u_col1:
        v1_url = st.text_input("動画 1 のGoogleフォトリンク (例: https://photos.app.goo.gl/...)", value="", key=f"new_v1_url_{fk}")
    with u_col2:
        v2_url = st.text_input("動画 2 のGoogleフォトリンク (例: https://photos.app.goo.gl/...)", value="", key=f"new_v2_url_{fk}")

    st.markdown("##### 📁 または動画ファイルを直接アップロード（mp4 / mov）")
    m_col1, m_col2 = st.columns(2)
    with m_col1:
        v1_file = st.file_uploader("スイング動画 1（後方など）", type=["mp4", "mov"], key=f"v1_{fk}")
    with m_col2:
        v2_file = st.file_uploader("スイング動画 2（正面など）", type=["mp4", "mov"], key=f"v2_{fk}")

    st.markdown("##### 📷 スイング静止画（最大5枚まで）")
    img_files = st.file_uploader("静止画（jpg, png）", type=["jpg", "jpeg", "png"], accept_multiple_files=True, key=f"imgs_{fk}")

    save_clicked = st.button("💾 このレッスンカルテを保存する", type="primary", use_container_width=True)

    if save_clicked:
        if img_files and len(img_files) > 5:
            st.error("❌ 保存に失敗しました: 画像は最大5枚までにしてください。")
        else:
            try:
                v1_path = ""
                if v1_file:
                    v1_path = os.path.join(UPLOAD_DIR, f"{selected_id}_{lesson_date}_v1_{v1_file.name}")
                    with open(v1_path, "wb") as f:
                        f.write(v1_file.getbuffer())
                        
                v2_path = ""
                if v2_file:
                    v2_path = os.path.join(UPLOAD_DIR, f"{selected_id}_{lesson_date}_v2_{v2_file.name}")
                    with open(v2_path, "wb") as f:
                        f.write(v2_file.getbuffer())

                img_paths = []
                if img_files:
                    for idx, img_f in enumerate(img_files[:5]):
                        i_path = os.path.join(UPLOAD_DIR, f"{selected_id}_{lesson_date}_img{idx}_{img_f.name}")
                        with open(i_path, "wb") as f:
                            f.write(img_f.getbuffer())
                        img_paths.append(i_path)

                scores = {
                    "addr_posture": addr_posture,
                    "addr_align": addr_align,
                    "back_path": back_path,
                    "back_top": back_top,
                    "down_plane": down_plane,
                    "down_release": down_release,
                }
                
                save_lesson(selected_id, lesson_date, scores, v1_path, v2_path, img_paths, target_goal, lesson_practice, evaluation_note, v1_url.strip(), v2_url.strip())
                
                st.session_state.form_reset_key += 1
                st.session_state.refresh_key += 1
                st.success("✅ 保存しました")
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
            r_id, r_date, r_p, r_a, r_bp, r_bt, r_dp, r_dr, r_v1, r_v2, r_imgs, r_target_goal, r_lesson_practice, r_eval_note, r_v1_url, r_v2_url = rec
            
            expander_title = f"📅 レッスン日: {r_date} (ID: {r_id})" + ("\u200b" * rf_k)
            edit_expander_title = f"✏️ このレッスン記録の日付・内容・メディアを修正する" + ("\u200b" * rf_k)
            
            with st.expander(expander_title, expanded=False):
                st.markdown(f"""
                | アドレス: 姿勢 | アドレス: 向き | バック: 軌道 | バック: トップ | ダウン: プレーン | ダウン: リリース |
                | :---: | :---: | :---: | :---: | :---: | :---: |
                | {render_score_badge(r_p)} | {render_score_badge(r_a)} | {render_score_badge(r_bp)} | {render_score_badge(r_bt)} | {render_score_badge(r_dp)} | {render_score_badge(r_dr)} |
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
                
                # Googleフォト リンクボタン表示
                if r_v1_url or r_v2_url:
                    st.markdown("##### 🔗 Googleフォト クラウド動画")
                    link_col1, link_col2 = st.columns(2)
                    with link_col1:
                        if r_v1_url:
                            st.link_button("▶️ Googleフォトで動画1を再生", r_v1_url, use_container_width=True)
                    with link_col2:
                        if r_v2_url:
                            st.link_button("▶️ Googleフォトで動画2を再生", r_v2_url, use_container_width=True)

                # アップロード動画の再生
                if (r_v1 and os.path.exists(r_v1)) or (r_v2 and os.path.exists(r_v2)):
                    v_col1, v_col2 = st.columns(2)
                    with v_col1:
                        if r_v1 and os.path.exists(r_v1):
                            st.caption("🎥 スイング動画 1")
                            st.video(r_v1)
                    with v_col2:
                        if r_v2 and os.path.exists(r_v2):
                            st.caption("🎥 スイング動画 2")
                            st.video(r_v2)
                
                # 静止画ギャラリー（最大5枚）
                if r_imgs:
                    img_list = [p for p in r_imgs.split(",") if p and os.path.exists(p)]
                    if img_list:
                        img_cols = st.columns(min(len(img_list), 5))
                        for idx, img_p in enumerate(img_list):
                            with img_cols[idx]:
                                img = Image.open(img_p)
                                st.image(img, use_container_width=True, caption=f"画像 {idx+1}")

                st.markdown("---")
                
                # 編集・日付変更・削除・メディア追加エリア
                with st.expander(edit_expander_title, expanded=False):
                    try:
                        parsed_date = datetime.strptime(r_date, "%Y-%m-%d").date()
                    except ValueError:
                        parsed_date = date.today()
                    
                    edit_date = st.date_input("📅 レッスン受講日を変更", value=parsed_date, key=f"ed_date_{r_id}_{rf_k}")
                    
                    st.markdown("**評価スコアの修正:**")
                    ec1, ec2, ec3 = st.columns(3)
                    with ec1:
                        e_p = st.radio("アドレス: 姿勢", [1, 2, 3], index=[1, 2, 3].index(r_p) if r_p in [1, 2, 3] else None, horizontal=True, key=f"e_p_{r_id}_{rf_k}")
                        e_a = st.radio("アドレス: 向き", [1, 2, 3], index=[1, 2, 3].index(r_a) if r_a in [1, 2, 3] else None, horizontal=True, key=f"e_a_{r_id}_{rf_k}")
                    with ec2:
                        e_bp = st.radio("バック: 軌道", [1, 2, 3], index=[1, 2, 3].index(r_bp) if r_bp in [1, 2, 3] else None, horizontal=True, key=f"e_bp_{r_id}_{rf_k}")
                        e_bt = st.radio("バック: トップ", [1, 2, 3], index=[1, 2, 3].index(r_bt) if r_bt in [1, 2, 3] else None, horizontal=True, key=f"e_bt_{r_id}_{rf_k}")
                    with ec3:
                        e_dp = st.radio("ダウン: プレーン", [1, 2, 3], index=[1, 2, 3].index(r_dp) if r_dp in [1, 2, 3] else None, horizontal=True, key=f"e_dp_{r_id}_{rf_k}")
                        e_dr = st.radio("ダウン: リリース", [1, 2, 3], index=[1, 2, 3].index(r_dr) if r_dr in [1, 2, 3] else None, horizontal=True, key=f"e_dr_{r_id}_{rf_k}")
                    
                    st.markdown("**レッスンカルテ内容の修正:**")
                    ed_col1, ed_col2 = st.columns(2)
                    with ed_col1:
                        edit_target_goal = st.text_area("📌 取り組んでいる課題・目標", value=r_target_goal or "", key=f"ed_goal_{r_id}_{rf_k}")
                    with ed_col2:
                        edit_lesson_practice = st.text_area("🏌️ 今回のレッスン・練習", value=r_lesson_practice or "", key=f"ed_practice_{r_id}_{rf_k}")
                    
                    edit_eval_note = st.text_area("📝 評価", value=r_eval_note or "", key=f"ed_eval_{r_id}_{rf_k}")
                    
                    st.markdown("---")
                    st.markdown("**🔗 Googleフォト共有リンクの変更・追加:**")
                    ed_u1, ed_u2 = st.columns(2)
                    with ed_u1:
                        edit_v1_url = st.text_input("動画 1 リンク", value=r_v1_url or "", key=f"ed_v1_url_{r_id}_{rf_k}")
                    with ed_u2:
                        edit_v2_url = st.text_input("動画 2 リンク", value=r_v2_url or "", key=f"ed_v2_url_{r_id}_{rf_k}")

                    st.markdown("**📁 直接動画ファイルの追加・変更 (未選択時は維持):**")
                    ed_m1, ed_m2 = st.columns(2)
                    with ed_m1:
                        ed_v1_file = st.file_uploader(f"動画 1 ファイル (現在: {'登録済' if r_v1 else '未登録'})", type=["mp4", "mov"], key=f"ed_v1_{r_id}_{rf_k}")
                    with ed_m2:
                        ed_v2_file = st.file_uploader(f"動画 2 ファイル (現在: {'登録済' if r_v2 else '未登録'})", type=["mp4", "mov"], key=f"ed_v2_{r_id}_{rf_k}")
                    
                    current_img_count = len([p for p in (r_imgs or "").split(",") if p])
                    ed_img_files = st.file_uploader(f"静止画を追加・差し替え (現在: {current_img_count}枚 / 最大5枚)", type=["jpg", "jpeg", "png"], accept_multiple_files=True, key=f"ed_imgs_{r_id}_{rf_k}")

                    btn_c1, btn_c2 = st.columns([3, 1])
                    with btn_c1:
                        if st.button("💾 日付・修正内容を保存する", key=f"btn_update_{r_id}_{rf_k}", type="primary"):
                            if ed_img_files and len(ed_img_files) > 5:
                                st.error("❌ 画像は最大5枚までにしてください。")
                            else:
                                try:
                                    new_v1_path = r_v1 or ""
                                    if ed_v1_file:
                                        new_v1_path = os.path.join(UPLOAD_DIR, f"{selected_id}_{edit_date}_v1_edit_{ed_v1_file.name}")
                                        with open(new_v1_path, "wb") as f:
                                            f.write(ed_v1_file.getbuffer())

                                    new_v2_path = r_v2 or ""
                                    if ed_v2_file:
                                        new_v2_path = os.path.join(UPLOAD_DIR, f"{selected_id}_{edit_date}_v2_edit_{ed_v2_file.name}")
                                        with open(new_v2_path, "wb") as f:
                                            f.write(ed_v2_file.getbuffer())

                                    new_img_paths_str = r_imgs or ""
                                    if ed_img_files:
                                        new_imgs = []
                                        for idx, img_f in enumerate(ed_img_files[:5]):
                                            i_path = os.path.join(UPLOAD_DIR, f"{selected_id}_{edit_date}_img{idx}_edit_{img_f.name}")
                                            with open(i_path, "wb") as f:
                                                f.write(img_f.getbuffer())
                                            new_imgs.append(i_path)
                                        new_img_paths_str = ",".join(new_imgs)

                                    updated_scores = {
                                        "addr_posture": e_p,
                                        "addr_align": e_a,
                                        "back_path": e_bp,
                                        "back_top": e_bt,
                                        "down_plane": e_dp,
                                        "down_release": e_dr,
                                    }
                                    update_lesson(
                                        r_id, edit_date, updated_scores, 
                                        edit_target_goal, edit_lesson_practice, edit_eval_note, 
                                        new_v1_path, new_v2_path, new_img_paths_str,
                                        edit_v1_url.strip(), edit_v2_url.strip()
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