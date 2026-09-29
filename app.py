import sqlite3
import os
from datetime import date, datetime
import streamlit as st

# -----------------------------
# 基本設定 & ディレクトリ初期化
# -----------------------------
DB_FILE = "lesson_karte.db"
UPLOAD_DIR = "uploads"

os.makedirs(UPLOAD_DIR, exist_ok=True)

def get_connection():
    return sqlite3.connect(DB_FILE)

def init_db():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS lessons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                lesson_date TEXT NOT NULL,
                content TEXT,
                video_url TEXT,
                image_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (student_id) REFERENCES students(id)
            )
        """)
        conn.commit()

init_db()

# -----------------------------
# 画面レイアウト
# -----------------------------
st.set_page_config(page_title="レッスンカルテ管理システム", layout="wide")
st.title("📋 レッスンカルテ管理ダッシュボード")

# サイドバーメニュー
menu = st.sidebar.radio(
    "メニュー", 
    ["新規カルテ登録", "生徒・カルテ検索 & 編集・削除", "📈 成長と趨勢（トレンド）", "新規生徒の登録"]
)

# -----------------------------
# 1. 新規カルテ登録
# -----------------------------
if menu == "新規カルテ登録":
    st.subheader("✍️ 新規カルテ入力")

    with get_connection() as conn:
        cursor = conn.cursor()
        students = cursor.execute("SELECT id, name FROM students ORDER BY name").fetchall()

    if not students:
        st.warning("先に「新規生徒の登録」メニューから生徒を登録してください。")
    else:
        student_dict = {name: s_id for s_id, name in students}
        
        with st.form("karte_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                selected_student = st.selectbox("生徒名", options=list(student_dict.keys()))
            with col2:
                lesson_date = st.date_input("レッスン日", value=date.today())

            content = st.text_area("レッスン内容・課題・指導ポイント", height=120)
            
            st.markdown("---")
            col_v_file, col_v_url = st.columns(2)
            with col_v_file:
                uploaded_video = st.file_uploader("スイング動画をドロップ", type=["mp4", "mov", "avi", "mkv"])
            with col_v_url:
                video_url_text = st.text_input("または動画URL（YouTube等）", placeholder="https://...")

            col_i_file, col_i_url = st.columns(2)
            with col_i_file:
                uploaded_image = st.file_uploader("分析画像をドロップ", type=["png", "jpg", "jpeg", "webp"])
            with col_i_url:
                image_url_text = st.text_input("または画像URL", placeholder="https://...")

            submitted = st.form_submit_button("カルテを保存する", use_container_width=True)

            if submitted:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                final_video_path = video_url_text.strip()
                final_image_path = image_url_text.strip()

                if uploaded_video is not None:
                    ext = os.path.splitext(uploaded_video.name)[1]
                    save_path = os.path.join(UPLOAD_DIR, f"video_{timestamp}{ext}")
                    with open(save_path, "wb") as f:
                        f.write(uploaded_video.getbuffer())
                    final_video_path = save_path

                if uploaded_image is not None:
                    ext = os.path.splitext(uploaded_image.name)[1]
                    save_path = os.path.join(UPLOAD_DIR, f"image_{timestamp}{ext}")
                    with open(save_path, "wb") as f:
                        f.write(uploaded_image.getbuffer())
                    final_image_path = save_path

                with get_connection() as conn:
                    cur = conn.cursor()
                    cur.execute("""
                        INSERT INTO lessons (student_id, lesson_date, content, video_url, image_url)
                        VALUES (?, ?, ?, ?, ?)
                    """, (student_dict[selected_student], str(lesson_date), content, final_video_path, final_image_path))
                    conn.commit()

                st.success(f"{selected_student} さんのカルテを保存しました！")

# -----------------------------
# 2. カルテ検索 & 編集・削除
# -----------------------------
elif menu == "生徒・カルテ検索 & 編集・削除":
    st.subheader("🔍 カルテの検索・閲覧・編集・削除")

    with get_connection() as conn:
        cursor = conn.cursor()
        students = cursor.execute("SELECT id, name FROM students ORDER BY name").fetchall()

    if not students:
        st.info("登録されている生徒データがありません。")
    else:
        student_dict = {name: s_id for s_id, name in students}
        search_target = st.selectbox("生徒を選択", options=list(student_dict.keys()))

        if search_target:
            target_id = student_dict[search_target]

            with get_connection() as conn:
                cur = conn.cursor()
                records = cur.execute("""
                    SELECT id, lesson_date, content, video_url, image_url 
                    FROM lessons 
                    WHERE student_id = ? 
                    ORDER BY lesson_date DESC, id DESC
                """, (target_id,)).fetchall()

            if not records:
                st.info("この生徒のカルテ記録はまだありません。")
            else:
                st.write(f"### {search_target} さんの受講履歴（全 {len(records)} 件）")

                for r_id, r_date, r_content, r_video, r_image in records:
                    with st.expander(f"📅 {r_date} のカルテ（ID: {r_id}）", expanded=False):
                        tab_view, tab_edit, tab_delete = st.tabs(["👁️ 閲覧", "✏️ 編集", "🗑️ 削除"])

                        # --- タブ1: 閲覧 ---
                        with tab_view:
                            st.markdown(f"**【レッスン日】**: `{r_date}`")
                            st.markdown("**【レッスン内容・課題】**")
                            st.write(r_content if r_content else "（記載なし）")

                            col_m1, col_m2 = st.columns(2)
                            with col_m1:
                                if r_video:
                                    st.markdown("🎥 **【スイング動画】**")
                                    v_path = r_video.strip('"\'')
                                    if v_path.startswith("http://") or v_path.startswith("https://"):
                                        st.video(v_path)
                                    elif os.path.exists(v_path):
                                        st.video(v_path)
                                    else:
                                        st.warning("動画ファイルが見つかりません。")
                            with col_m2:
                                if r_image:
                                    st.markdown("🖼️ **【分析画像】**")
                                    i_path = r_image.strip('"\'')
                                    if i_path.startswith("http://") or i_path.startswith("https://"):
                                        st.image(i_path, use_container_width=True)
                                    elif os.path.exists(i_path):
                                        st.image(i_path, use_container_width=True)
                                    else:
                                        st.warning("画像ファイルが見つかりません。")

                        # --- タブ2: 編集（日付・内容・ファイルの再指定） ---
                        with tab_edit:
                            with st.form(f"edit_form_{r_id}"):
                                # 登録済みの日付を読み込んで初期値に設定
                                try:
                                    parsed_date = datetime.strptime(r_date, "%Y-%m-%d").date()
                                except ValueError:
                                    parsed_date = date.today()

                                # 日付の修正カレンダー入力
                                edit_date = st.date_input("レッスン日を修正", value=parsed_date, key=f"date_{r_id}")
                                edit_content = st.text_area("レッスン内容・課題", value=r_content or "", height=120, key=f"content_{r_id}")
                                
                                st.markdown("##### 添付ファイル／URLの修正")
                                edit_video = st.text_input("動画パス / YouTube URL", value=r_video or "", key=f"video_{r_id}")
                                edit_image = st.text_input("画像パス / URL", value=r_image or "", key=f"image_{r_id}")
                                
                                save_edit_btn = st.form_submit_button("変更内容を保存する", use_container_width=True)
                                if save_edit_btn:
                                    with get_connection() as conn:
                                        c = conn.cursor()
                                        c.execute("""
                                            UPDATE lessons 
                                            SET lesson_date = ?, content = ?, video_url = ?, image_url = ? 
                                            WHERE id = ?
                                        """, (str(edit_date), edit_content, edit_video.strip(), edit_image.strip(), r_id))
                                        conn.commit()
                                    st.success(f"カルテを更新しました！（日付: {edit_date}）")
                                    st.rerun()

                        # --- タブ3: 削除 ---
                        with tab_delete:
                            st.warning("⚠️ この操作は取り消せません。")
                            confirm_del = st.checkbox("本当にこのカルテを削除しますか？", key=f"del_chk_{r_id}")
                            if st.button("カルテを完全に削除する", type="primary", key=f"del_btn_{r_id}", disabled=not confirm_del):
                                with get_connection() as conn:
                                    c = conn.cursor()
                                    c.execute("DELETE FROM lessons WHERE id = ?", (r_id,))
                                    conn.commit()
                                st.success("カルテを削除しました。")
                                st.rerun()

# -----------------------------
# 3. 成長と趨勢（トレンド）
# -----------------------------
elif menu == "📈 成長と趨勢（トレンド）":
    st.subheader("📈 生徒の成長プロセス・課題の変遷")

    with get_connection() as conn:
        cursor = conn.cursor()
        students = cursor.execute("SELECT id, name FROM students ORDER BY name").fetchall()

    if not students:
        st.info("登録されている生徒データがありません。")
    else:
        student_dict = {name: s_id for s_id, name in students}
        target_student = st.selectbox("分析する生徒を選択", options=list(student_dict.keys()), key="trend_student")

        if target_student:
            target_id = student_dict[target_student]

            with get_connection() as conn:
                cur = conn.cursor()
                records = cur.execute("""
                    SELECT id, lesson_date, content, video_url, image_url 
                    FROM lessons 
                    WHERE student_id = ? 
                    ORDER BY lesson_date ASC, id ASC
                """, (target_id,)).fetchall()

            if len(records) < 1:
                st.info("表示できるカルテ記録がまだありません。")
            else:
                st.markdown(f"### 🏌️‍♂️ {target_student} さんの取り組み趨勢（累計受講回数: {len(records)} 回）")

                if len(records) >= 2:
                    st.markdown("#### 🔄 ビフォー & アフター比較")
                    first_record = records[0]
                    latest_record = records[-1]

                    col_before, col_after = st.columns(2)
                    with col_before:
                        st.info(f"**【初受講時】 {first_record[1]}**")
                        st.write(first_record[2] if first_record[2] else "（記載なし）")
                        if first_record[3] and os.path.exists(first_record[3]):
                            st.video(first_record[3])
                        elif first_record[4] and os.path.exists(first_record[4]):
                            st.image(first_record[4], use_container_width=True)

                    with col_after:
                        st.success(f"**【最新】 {latest_record[1]}**")
                        st.write(latest_record[2] if latest_record[2] else "（記載なし）")
                        if latest_record[3] and os.path.exists(latest_record[3]):
                            st.video(latest_record[3])
                        elif latest_record[4] and os.path.exists(latest_record[4]):
                            st.image(latest_record[4], use_container_width=True)

                    st.divider()

                st.markdown("#### ⏳ 課題・指導内容のタイムライン（初回 ➔ 最新）")
                for idx, (l_id, l_date, l_content, l_vid, l_img) in enumerate(records, start=1):
                    with st.container():
                        st.markdown(f"**第 {idx} 回目 ｜ 実施日: `{l_date}`**")
                        st.text_area(
                            f"記録内容（回: {idx}）", 
                            value=l_content or "記載なし", 
                            height=80, 
                            disabled=True, 
                            key=f"trend_view_{l_id}"
                        )
                        st.markdown("---")

# -----------------------------
# 4. 新規生徒の登録
# -----------------------------
elif menu == "新規生徒の登録":
    st.subheader("👤 生徒の新規追加")
    with st.form("new_student_form", clear_on_submit=True):
        new_name = st.text_input("生徒のお名前")
        btn = st.form_submit_button("登録")
        if btn and new_name.strip():
            try:
                with get_connection() as conn:
                    cur = conn.cursor()
                    cur.execute("INSERT INTO students (name) VALUES (?)", (new_name.strip(),))
                    conn.commit()
                st.success(f"「{new_name.strip()}」さんを登録しました！")
            except sqlite3.IntegrityError:
                st.error("その生徒名はすでに登録されています。")