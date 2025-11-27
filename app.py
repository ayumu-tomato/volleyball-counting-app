import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from streamlit_image_coordinates import streamlit_image_coordinates
import io
from PIL import Image
import datetime
import xlsxwriter

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
    div.stButton > button { width: 100%; font-weight: bold; min-height: 45px; }
    .sub-box { border: 2px dashed #ff4b4b; padding: 15px; border-radius: 10px; background-color: #fff0f0; }
</style>
""", unsafe_allow_html=True)

# セッション状態の初期化
if 'data_log' not in st.session_state: st.session_state.data_log = []
if 'score' not in st.session_state: st.session_state.score = [0, 0] # [My, Op]
if 'phase' not in st.session_state: st.session_state.phase = 'R'
# ローテーション (6人)
if 'rotation' not in st.session_state: 
    st.session_state.rotation = ["Sekita(#8)", "Nishida(#1)", "Onodera(#2)", "Ishikawa(#14)", "Yamauchi(#6)", "R.Takahashi(#12)"]
# リベロ (最大2名)
if 'liberos' not in st.session_state:
    st.session_state.liberos = ["Yamamoto(#20)", "Ogawa(#24)"] 

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

# ローテーション回転 (時計回り)
def rotate_team():
    rot = st.session_state.rotation
    st.session_state.rotation = [rot[-1]] + rot[:-1]

# 選手交代処理
def substitute_player(out_player, in_player_name):
    if out_player in st.session_state.rotation:
        idx = st.session_state.rotation.index(out_player)
        st.session_state.rotation[idx] = in_player_name
        st.toast(f"🔄 Sub: {out_player} ➡️ {in_player_name}", icon="✅")
    else:
        st.error("OUT選手がローテーションに見つかりません")

# ゾーン判定
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
    s_z, e_z = "", ""
    if len(st.session_state.points) >= 1:
        s_z = get_zone(st.session_state.points[0][0], st.session_state.points[0][1], 200, 400)
    if len(st.session_state.points) >= 2:
        e_z = get_zone(st.session_state.points[1][0], st.session_state.points[1][1], 200, 400)

    current_score_str = f"{st.session_state.score[0]}-{st.session_state.score[1]}"

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
        "memo": "", 
        "video_url": st.session_state.video_url,
        "video_time": time_to_sec(st.session_state.input_time)
    }
    
    st.session_state.data_log.append(new_row)
    
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

    st.session_state.points = []

# ==========================================
# レイアウト構成
# ==========================================

# --- ヘッダーエリア ---
col_h1, col_h2, col_h3 = st.columns([1, 2, 1])

with col_h1:
    st.markdown("""
    <div class="legend-box">
    <b>Legend</b><br>#:Point, ":Good, !:OK<br>-:Poor, /:Rebound, ^:Err
    </div>
    """, unsafe_allow_html=True)

with col_h2:
    st.markdown(f'<div class="score-board">{st.session_state.score[0]} - {st.session_state.score[1]} ({st.session_state.phase})</div>', unsafe_allow_html=True)

with col_h3:
    r = st.session_state.rotation
    st.info(f"**Rotation**\n\nF: {r[3]} {r[4]} {r[5]}\n\nB: {r[2]} {r[1]} **{r[0]}**")

st.divider()

# --- 入力設定エリア ---
with st.expander("🛠️ Game & Member Settings", expanded=False):
    c1, c2 = st.columns(2)
    with c1:
        st.session_state.set_name = st.text_input("1. Set Name", "1")
        st.session_state.video_url = st.text_input("1. Video URL", "https://")
        
        # スタメン設定
        rot_input = st.text_area("Starting Rotation (Pos1..6)", ",".join(st.session_state.rotation))
        if st.button("Update Rotation"):
            st.session_state.rotation = [x.strip() for x in rot_input.split(',')]
            st.toast("Rotation Updated")
            
    with c2:
        start_phase = st.radio("Start Phase", ["Serve (My)", "Reception (Op)"])
        if st.button("Reset Score"):
            st.session_state.score = [0, 0]
            st.session_state.phase = 'S' if "Serve" in start_phase else 'R'
            st.rerun()
            
        # ★リベロ設定 (最大2名)
        lib_input = st.text_input("Liberos (Max 2, comma separated)", ",".join(st.session_state.liberos))
        if st.button("Update Liberos"):
            st.session_state.liberos = [x.strip() for x in lib_input.split(',')]
            st.toast("Liberos Updated")

# --- メイン入力エリア ---
col_main_L, col_main_C, col_main_R = st.columns([1, 1.2, 1])

# 左: マップ
with col_main_L:
    st.subheader("Map")
    court_img = create_court_img(st.session_state.points)
    val = streamlit_image_coordinates(court_img, key="court", width=200, height=400)
    
    if val:
        p = (val['x'], val['y'])
        if not st.session_state.points or st.session_state.points[-1] != p:
            if len(st.session_state.points) < 2:
                st.session_state.points.append(p)
                st.rerun()
            else:
                st.session_state.points = [p]
                st.rerun()
    
    if len(st.session_state.points)==0: st.caption("Tap Start")
    elif len(st.session_state.points)==1: st.caption("Tap End")

# 中央: プレー詳細
with col_main_C:
    st.subheader("Input")
    
    st.session_state.input_time = st.text_input("Time (MM:SS)", "00:00")
    
    # ★Player選択 (ローテーション + リベロ)
    # 現在のローテメンバーにリベロを加えたリストを作成
    active_players = st.session_state.rotation + [l for l in st.session_state.liberos if l]
    st.session_state.input_player = st.selectbox("Player", active_players)
    
    skill_opts = ["S", "R", "A", "B", "D", "E"]
    st.session_state.input_skill = st.selectbox("Skill", skill_opts)
    
    if st.session_state.input_skill == 'A':
        c1, c2 = st.columns(2)
        st.session_state.input_setter = c1.text_input("Setter", "Sekita")
        st.session_state.input_combo = c2.text_input("Combo", "X5")
    else:
        st.session_state.input_setter = ""
        st.session_state.input_combo = ""

# 右: Quality & Action
with col_main_R:
    st.subheader("Quality & Save")
    
    quality_opts = ["#", "+", "!", "-", "/", "^", "T"]
    st.session_state.input_quality = st.select_slider("Quality", options=quality_opts, value="#")
    
    st.markdown("---")
    
    # 自動判定登録
    if st.button("✅ Register (Auto)", type="primary"):
        s = st.session_state.input_skill
        q = st.session_state.input_quality
        
        if (s in ['A', 'B', 'S'] and q == '#') or (s == 'A' and q == 'T'):
            save_data('my_point')
        elif q == '^':
            save_data('op_point')
        else:
            st.warning("Select result below ↓")

    c_up, c_mid, c_down = st.columns(3)
    if c_up.button("↑ My Pt"): save_data('my_point')
    if c_mid.button("→ Cont"): save_data('continue')
    if c_down.button("↓ Op Pt"): save_data('op_point')

st.divider()

# ==========================================
# ★ 選手交代エリア (Substitution)
# ==========================================
st.markdown("### 🔄 選手交代 (Substitution)")
with st.container():
    st.markdown('<div class="sub-box">', unsafe_allow_html=True)
    sc1, sc2, sc3 = st.columns([2, 2, 1])
    
    # OUT: 現在のローテーションメンバーから選択
    out_player = sc1.selectbox("OUT (Leaving Court)", st.session_state.rotation)
    
    # IN: 名前を入力
    in_player = sc2.text_input("IN (Entering Court)", "")
    
    # 実行ボタン
    if sc3.button("Change!", type="secondary"):
        if in_player:
            substitute_player(out_player, in_player)
            st.rerun()
        else:
            st.error("Enter IN player name")
    st.markdown('</div>', unsafe_allow_html=True)

st.divider()

# ==========================================
# データ管理
# ==========================================
st.subheader("Recorded Data")

if len(st.session_state.data_log) > 0:
    df = pd.DataFrame(st.session_state.data_log)
    edited_df = st.data_editor(df, num_rows="dynamic", use_container_width=True)
    st.session_state.data_log = edited_df.to_dict('records')
    
    st.markdown("#### Download")
    col_dl1, col_dl2 = st.columns(2)
    
    buffer_xlsx = io.BytesIO()
    with pd.ExcelWriter(buffer_xlsx, engine='xlsxwriter') as writer:
        edited_df.to_excel(writer, index=False, sheet_name='Sheet1')
        
    col_dl1.download_button("Download .xlsx", data=buffer_xlsx.getvalue(), file_name="scouting.xlsx", mime="application/vnd.ms-excel")
    
    csv = edited_df.to_csv(index=False).encode('utf-8')
    col_dl2.download_button("Download .csv", data=csv, file_name="scouting.csv", mime="text/csv")
