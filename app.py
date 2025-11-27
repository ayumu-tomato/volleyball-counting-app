import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from streamlit_image_coordinates import streamlit_image_coordinates
import io
from PIL import Image
import datetime


# ==========================================
# 設定 & 初期化
# ==========================================
st.set_page_config(page_title="Volleyball Scouter Pro", layout="wide")


# カスタムCSS
st.markdown("""
<style>
    .big-font { font-size: 20px; font-weight: bold; }
    .score-board { 
        font-size: 40px; font-weight: bold; text-align: center; 
        background-color: #333; color: white; padding: 10px; border-radius: 10px; margin-bottom: 10px;
    }
    .legend-box {
        border: 1px solid #ddd; padding: 10px; border-radius: 5px; background-color: #f9f9f9; font-size: 12px;
    }
    div.stButton > button { width: 100%; font-weight: bold; }
</style>
""", unsafe_allow_html=True)


# セッション状態の初期化
if 'data_log' not in st.session_state: st.session_state.data_log = []
if 'score' not in st.session_state: st.session_state.score = [0, 0] # [My, Op]
if 'phase' not in st.session_state: st.session_state.phase = 'R'
if 'rotation' not in st.session_state: st.session_state.rotation = ["1", "6", "5", "4", "3", "2"] # Default Positions
if 'points' not in st.session_state: st.session_state.points = [] # Map clicks


# ==========================================
# 関数定義
# ==========================================


# 時間変換 (MM:SS -> 秒)
def time_to_sec(time_str):
    try:
        if ':' in time_str:
            m, s = time_str.split(':')
            return int(m) * 60 + int(s)
        return int(time_str)
    except:
        return 0


# ローテーション回転 (時計回り: 得点時)
def rotate_team():
    # Pos: 1->6->5->4->3->2->1
    # List index: 0(Pos1), 1(Pos6), 2(Pos5), 3(Pos4), 4(Pos3), 5(Pos2)
    # Python List rotate: last element moves to front
    rot = st.session_state.rotation
    st.session_state.rotation = [rot[-1]] + rot[:-1]


# ゾーン判定 (画像クリック -> 1~9)
def get_zone(x, y, w, h):
    cx, cy = (x/w)*9, (1-(y/h))*18
    if 0 <= cy < 9: # 自コート
        r, c = int(cy//3), int(cx//3)
        if r==0: return [1,6,5][c]
        if r==1: return [9,8,7][c]
        if r==2: return [2,3,4][c]
    elif 9 <= cy <= 18: # 相手コート
        r, c = int((cy-9)//3), int(cx//3)
        if r==0: return [4,3,2][c]
        if r==1: return [7,8,9][c]
        if r==2: return [5,6,1][c]
    return 0


# コート画像生成
def create_court_img(points):
    fig, ax = plt.subplots(figsize=(4, 8))
    ax.add_patch(patches.Rectangle((0, 0), 9, 18, fc='#FFCC99', ec='black', lw=2))
    ax.plot([0,9], [9,9], c='red', lw=3) # Net
    ax.plot([0,9], [6,6], c='black', lw=1); ax.plot([0,9], [12,12], c='black', lw=1)
    
    for i, p in enumerate(points):
        px, py = (p[0]/200)*9, (1-(p[1]/400))*18
        col = "blue" if i==0 else "red"
        lbl = "S" if i==0 else "E"
        ax.scatter(px, py, s=150, c=col, zorder=10, edgecolors='white')
        ax.text(px, py, lbl, color='white', ha='center', va='center', fontweight='bold', fontsize=8)
        if i==1: # Arrow
            sx, sy = (points[0][0]/200)*9, (1-(points[0][1]/400))*18
            ax.arrow(sx, sy, px-sx, py-sy, width=0.1, color='gray', alpha=0.5)


    ax.set_xlim(0, 9); ax.set_ylim(0, 18); ax.axis('off')
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', pad_inches=0)
    buf.seek(0)
    return Image.open(buf)


# データ保存ロジック
def save_data(effect):
    # effect: 'my_point', 'op_point', 'continue'
    
    # マップ座標取得
    s_z, e_z = "", ""
    if len(st.session_state.points) >= 1:
        s_z = get_zone(st.session_state.points[0][0], st.session_state.points[0][1], 200, 400)
    if len(st.session_state.points) >= 2:
        e_z = get_zone(st.session_state.points[1][0], st.session_state.points[1][1], 200, 400)


    # 現在のスコア文字列
    current_score_str = f"{st.session_state.score[0]}-{st.session_state.score[1]}"


    # 新しい行の作成
    new_row = {
        "set": st.session_state.set_name,
        "score": current_score_str,
        "phase": st.session_state.phase,
        "setter": st.session_state.input_setter if st.session_state.input_skill == 'A' else "",
        "player": st.session_state.input_player,
        "skill": st.session_state.input_skill,
        "combo": st.session_state.input_combo if st.session_state.input_skill == 'A' else "",
        "quality": st.session_state.input_quality,
        "start_zone": s_z,
        "end_zone": e_z,
        "memo": "", # K列ブランク
        "video_url": st.session_state.video_url,
        "video_time": time_to_sec(st.session_state.input_time)
    }
    
    # ログに追加
    st.session_state.data_log.append(new_row)
    
    # スコア・フェーズ・ローテの更新処理
    if effect == 'my_point':
        st.session_state.score[0] += 1
        st.session_state.phase = 'S'
        rotate_team()
        st.toast(f"My Point! Score: {st.session_state.score}", icon="⭕")
        
    elif effect == 'op_point':
        st.session_state.score[1] += 1
        st.session_state.phase = 'R'
        st.toast(f"Opponent Point. Score: {st.session_state.score}", icon="❌")
        
    elif effect == 'continue':
        st.toast("Rally Continues...", icon="➡️")


    # 入力リセット (マップのみ)
    st.session_state.points = []


# ==========================================
# レイアウト構成
# ==========================================


# --- ヘッダーエリア (Step 0, 2) ---
col_h1, col_h2, col_h3 = st.columns([1, 2, 1])


# 左上: Quality凡例 (Step 0)
with col_h1:
    st.markdown("""
    <div class="legend-box">
    <b>Quality Legend</b><br>
    #: Point/Perfect<br>
    ": Good<br>
    !: OK<br>
    -: Poor<br>
    /: Rebound<br>
    ^: Error/Block
    </div>
    """, unsafe_allow_html=True)


# 中央: スコアボード
with col_h2:
    st.markdown(f'<div class="score-board">{st.session_state.score[0]} - {st.session_state.score[1]} ({st.session_state.phase})</div>', unsafe_allow_html=True)


# 右上: ローテーション (Step 2)
with col_h3:
    r = st.session_state.rotation
    st.info(f"**Rotation**\n\nFront: {r[3]} {r[4]} {r[5]}\n\nBack : {r[2]} {r[1]} **{r[0]}**")


st.divider()


# --- 入力設定エリア (Step 1, 3) ---
with st.expander("🛠️ Game Settings (Set, URL, Start Rotation, First Server)", expanded=False):
    c1, c2 = st.columns(2)
    with c1:
        st.session_state.set_name = st.text_input("1. Set Name (A列)", "1")
        st.session_state.video_url = st.text_input("1. Video URL (L列)", "https://")
        
        # Step 2: Rotation Input
        rot_input = st.text_input("2. Starting Rotation (Pos1,6,5,4,3,2)", "1,6,5,4,3,2")
        if st.button("Set Rotation"):
            st.session_state.rotation = [x.strip() for x in rot_input.split(',')]
            
    with c2:
        # Step 3: First Serve/Reception
        start_phase = st.radio("3. First Phase", ["Serve (We serve)", "Reception (They serve)"])
        if st.button("Reset Score & Phase"):
            st.session_state.score = [0, 0]
            st.session_state.phase = 'S' if "Serve" in start_phase else 'R'
            st.rerun()


# --- メイン入力エリア (Step 4-8) ---
col_main_L, col_main_C, col_main_R = st.columns([1, 1.2, 1])


# 左下: マップ (Step 7)
with col_main_L:
    st.subheader("7. Map (Start -> End)")
    court_img = create_court_img(st.session_state.points)
    val = streamlit_image_coordinates(court_img, key="court", width=200, height=400)
    
    if val:
        p = (val['x'], val['y'])
        if not st.session_state.points or st.session_state.points[-1] != p:
            if len(st.session_state.points) < 2:
                st.session_state.points.append(p)
                st.rerun()
            else:
                st.session_state.points = [p] # 3回目でリセット
                st.rerun()
    
    if len(st.session_state.points)==0: st.caption("Tap Start")
    elif len(st.session_state.points)==1: st.caption("Tap End")


# 中央: プレー詳細入力 (Step 4, 5, 6)
with col_main_C:
    st.subheader("Input Details")
    
    # Step 4: Time
    st.session_state.input_time = st.text_input("4. Time (MM:SS)", "00:00")
    
    # Step 5: Skill
    skill_opts = ["S", "R", "A", "B", "D", "E"]
    st.session_state.input_skill = st.selectbox("5. Skill", skill_opts)
    
    # Step 6: Player/Setter/Combo
    # 簡易的にテキスト入力にする（運用に合わせてリスト化推奨）
    if st.session_state.input_skill == 'A':
        c1, c2 = st.columns(2)
        st.session_state.input_setter = c1.text_input("Setter", "Sekita")
        st.session_state.input_player = c2.text_input("Player", "Ishikawa")
        st.session_state.input_combo = st.text_input("Combo", "X5")
    else:
        st.session_state.input_player = st.text_input("Player", "Ishikawa")
        # 他は空
        st.session_state.input_setter = ""
        st.session_state.input_combo = ""


# 右: Quality & Action (Step 8, 9, 10)
with col_main_R:
    st.subheader("8-10. Quality & Action")
    
    # Step 8: Quality Input
    quality_opts = ["#", "+", "!", "-", "/", "^", "T"]
    st.session_state.input_quality = st.select_slider("8. Quality", options=quality_opts, value="#")
    
    st.markdown("---")
    st.markdown("**9 & 10. Register & Next**")
    
    # 自動判定ロジックの実行ボタン (Enter相当)
    if st.button("✅ Register (Auto Logic)", type="primary"):
        s = st.session_state.input_skill
        q = st.session_state.input_quality
        
        # Step 9: 自動判定
        # 得点パターン: (A#) or (B#) or (S#) -> My Point
        if (s in ['A', 'B', 'S'] and q == '#') or (s == 'A' and q == 'T'):
            save_data('my_point')
        # 失点パターン: Error(^) -> Op Point
        elif q == '^':
            save_data('op_point')
        else:
            # それ以外 -> Step 10: ユーザー選択へ誘導
            st.warning("Manual direction required below ↓")


    st.markdown("**(Step 10: Manual Override)**")
    c_up, c_right, c_down = st.columns(3)
    
    # Step 10: Manual Buttons
    if c_up.button("↑ My Pt"):
        save_data('my_point')
    
    if c_right.button("→ Cont"):
        save_data('continue')
        
    if c_down.button("↓ Op Pt"):
        save_data('op_point')


st.divider()


# ==========================================
# 0 & 11. データテーブル & 出力
# ==========================================
st.subheader("Recorded Data (Editable)")


if len(st.session_state.data_log) > 0:
    # データをDataFrame化
    df = pd.DataFrame(st.session_state.data_log)
    
    # Step 0: Userによる変更を認める (data_editor)
    edited_df = st.data_editor(df, num_rows="dynamic", use_container_width=True)
    
    st.session_state.data_log = edited_df.to_dict('records') # 編集内容をStateに戻す
    
    # Step 11: FINISH Button
    st.markdown("### 11. FINISH")
    col_dl1, col_dl2 = st.columns(2)
    
    # Excel Download
    buffer_xlsx = io.BytesIO()
    with pd.ExcelWriter(buffer_xlsx, engine='xlsxwriter') as writer:
        edited_df.to_excel(writer, index=False, sheet_name='Sheet1')
        
    col_dl1.download_button(
        label="Download as .xlsx",
        data=buffer_xlsx.getvalue(),
        file_name="scouting_data.xlsx",
        mime="application/vnd.ms-excel"
    )
    
    # CSV Download
    csv = edited_df.to_csv(index=False).encode('utf-8')
    col_dl2.download_button(
        label="Download as .csv",
        data=csv,
        file_name="scouting_data.csv",
        mime="text/csv"
    )


else:
    st.info("No data recorded yet.")