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
# 1. 設定 & CSS
# ==========================================
st.set_page_config(page_title="Volleyball Scouter Ver.2.1", layout="wide")

st.markdown("""
<style>
    .big-font { font-size: 18px; font-weight: bold; }
    .score-board { 
        font-size: 45px; font-weight: 900; text-align: center; 
        background-color: #222; color: #fff; 
        padding: 5px; border-radius: 10px; margin-bottom: 5px;
    }
    .score-btn { width: 100%; margin-top: 0px; }
    .legend-box {
        border: 1px solid #ccc; padding: 10px; border-radius: 5px; 
        background-color: #f8f9fa; font-size: 13px; line-height: 1.4;
        height: 200px; overflow-y: auto;
    }
    .legend-title { font-weight: bold; border-bottom: 1px solid #ddd; margin-bottom: 5px;}
    .rot-container {
        display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 5px;
        background-color: #eef; padding: 5px; border-radius: 5px;
        text-align: center; font-weight: bold; font-size: 14px;
    }
    .rot-player {
        background-color: white; border: 2px solid #333; border-radius: 5px; padding: 8px 2px;
    }
    .rot-front { background-color: #ffcccc; }
    .rot-server { border: 3px solid red; color: red; }
    div.stButton > button { width: 100%; font-weight: bold; height: 50px; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. セッション状態の初期化
# ==========================================
if 'data_log' not in st.session_state: st.session_state.data_log = []
if 'score' not in st.session_state: st.session_state.score = [0, 0]
if 'phase' not in st.session_state: st.session_state.phase = 'R'
if 'rotation' not in st.session_state: 
    st.session_state.rotation = ["Sekita(#8)", "Nishida(#1)", "Onodera(#2)", "Ishikawa(#14)", "Yamauchi(#6)", "R.Takahashi(#12)"]
if 'liberos' not in st.session_state:
    st.session_state.liberos = ["Yamamoto(#20)", "Ogawa(#24)"] 
if 'setter_counts' not in st.session_state: st.session_state.setter_counts = {}
if 'points' not in st.session_state: st.session_state.points = []
if 'time_key' not in st.session_state: st.session_state.time_key = 0
if 'combo_key' not in st.session_state: st.session_state.combo_key = 0

# ==========================================
# 3. 関数ロジック
# ==========================================

def format_time_input(val):
    if not val: return ""
    val = str(val).strip()
    if ":" in val: return val
    if len(val) == 4 and val.isdigit(): return f"{val[:2]}:{val[2:]}"
    if len(val) == 3 and val.isdigit(): return f"0{val[:1]}:{val[1:]}"
    return val

def time_to_sec(time_str):
    try:
        t = format_time_input(time_str)
        if ':' in t:
            m, s = t.split(':')
            return int(m) * 60 + int(s)
        return int(t)
    except:
        return 0

def rotate_team():
    rot = st.session_state.rotation
    st.session_state.rotation = [rot[-1]] + rot[:-1]

def get_sorted_setters():
    candidates = st.session_state.rotation + [l for l in st.session_state.liberos if l]
    def sort_key(name): return st.session_state.setter_counts.get(name, 0)
    sorted_list = sorted(candidates, key=sort_key, reverse=True)
    sorted_list.append("Direct/Two")
    return sorted_list

def count_setter_usage(name):
    if name and name != "Direct/Two":
        current = st.session_state.setter_counts.get(name, 0)
        st.session_state.setter_counts[name] = current + 1

def substitute_player(out_player, in_player_name):
    if out_player in st.session_state.rotation:
        idx = st.session_state.rotation.index(out_player)
        st.session_state.rotation[idx] = in_player_name
        st.toast(f"🔄 Sub: {out_player} ➡️ {in_player_name}", icon="✅")
    else:
        st.error("OUT選手がローテーションに見つかりません")

def get_zone(x, y, w, h):
    cx, cy = (x / w) * 9, (1 - (y / h)) * 18 
    if 0 <= cy < 9: # 自コート
        r, c = int(cy//3), int(cx//3)
        if r==0: return [1,6,5][c]
        if r==1: return [9,8,7][c]
        if r==2: return [2,3,4][c]
    elif 9 <= cy <= 18: # 相手コート
        is_front = (cy < 13.5)
        col_img = int(cx // 3)
        if is_front:
            if col_img == 0: return 2
            if col_img == 1: return 3
            if col_img == 2: return 4
        else:
            if col_img == 0: return 1
            if col_img == 1: return 6
            if col_img == 2: return 5
    return 0

def create_court_img(points):
    fig, ax = plt.subplots(figsize=(4, 8))
    ax.add_patch(patches.Rectangle((0, 0), 9, 18, fc='#FFCC99', ec='black', lw=2))
    ax.plot([0,9], [9,9], c='red', lw=3)
    ax.plot([0,9], [6,6], c='black', lw=1); ax.plot([0,9], [12,12], c='black', lw=1)
    ax.plot([0,9], [13.5, 13.5], c='gray', ls=':', lw=0.5)
    ax.plot([3,3], [9,18], c='gray', ls=':', lw=0.5)
    ax.plot([6,6], [9,18], c='gray', ls=':', lw=0.5)

    for i, p in enumerate(points):
        px, py = (p[0]/200)*9, (1-(p[1]/400))*18
        col = "blue" if i==0 else "red"
        lbl = "S" if i==0 else "E"
        ax.scatter(px, py, s=150, c=col, zorder=10, edgecolors='white')
        ax.text(px, py, lbl, color='white', ha='center', va='center', fontweight='bold', fontsize=8)
        if i==1: 
            sx, sy = (points[0][0]/200)*9, (1-(points[0][1]/400))*18
            ax.arrow(sx, sy, px-sx, py-sy, width=0.1, color='gray', alpha=0.5)

    ax.set_xlim(0, 9); ax.set_ylim(0, 18); ax.axis('off')
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', pad_inches=0)
    buf.seek(0)
    return Image.open(buf)

def manual_score_update(team):
    if team == 'my':
        st.session_state.score[0] += 1
        st.session_state.phase = 'S'
        rotate_team()
        st.toast(f"Point Added (My). Rotated.", icon="⬆️")
    else:
        st.session_state.score[1] += 1
        st.session_state.phase = 'R'
        st.toast(f"Point Added (Op).", icon="⬇️")

def register_data(quality):
    s_z, e_z = "", ""
    if len(st.session_state.points) >= 1:
        s_z = get_zone(st.session_state.points[0][0], st.session_state.points[0][1], 200, 400)
    if len(st.session_state.points) >= 2:
        e_z = get_zone(st.session_state.points[1][0], st.session_state.points[1][1], 200, 400)

    current_score = f"{st.session_state.score[0]}-{st.session_state.score[1]}"
    time_val = format_time_input(st.session_state.input_time)
    
    skill = st.session_state.input_skill
    setter = st.session_state.input_setter if skill == 'A' else ""
    combo = st.session_state.input_combo if skill == 'A' else ""

    if skill == 'A': count_setter_usage(setter)

    # ログ保存 (内部用キー名で保存)
    new_row = {
        "set": st.session_state.set_name,
        "score": current_score,
        "phase": st.session_state.phase,
        "setter": setter,
        "player": st.session_state.input_player,
        "skill": skill,
        "combo": combo,
        "quality": quality,
        "start_zone": s_z,
        "end_zone": e_z,
        "memo": "", 
        "video_url": st.session_state.video_url, # L列 (Video_URL)
        "video_time": time_to_sec(time_val)      # M列 (Time_Sec)
    }
    st.session_state.data_log.append(new_row)
    
    # 自動更新ロジック
    is_my_point = False
    is_op_point = False
    
    if (skill in ['A', 'B', 'S'] and quality == '#') or (skill == 'A' and quality == 'T'):
        is_my_point = True
    elif quality == '^':
        is_op_point = True
    
    if is_my_point:
        st.session_state.score[0] += 1
        st.session_state.phase = 'S'
        rotate_team()
        st.toast("My Point! Rotated.", icon="⭕")
    elif is_op_point:
        st.session_state.score[1] += 1
        st.session_state.phase = 'R'
        st.toast("Op Point.", icon="❌")
    else:
        st.toast("Registered.", icon="✅")

    st.session_state.points = []
    st.session_state.time_key += 1
    st.session_state.combo_key += 1
    st.rerun()

# ==========================================
# レイアウト構成
# ==========================================

c_legend, c_score, c_rot = st.columns([1.2, 1.5, 1.3])

with c_legend:
    st.markdown("""
    <div class="legend-box">
    <div class="legend-title">判例 (Quality)</div>
    <b>Reception (R)</b><br>
    #: Aパス (セッター定位置)<br>
    ": Bパス (速攻可)<br>
    !: Cパス (オープンのみ)<br>
    -: 乱れ/チャンス献上<br>
    ^: エース被弾(失点)<br><br>
    <b>Attack (A) / Serve (S)</b><br>
    #: 得点/エース<br>
    ": 効果/崩した<br>
    !: 拾われた/普通<br>
    ^: 失点/ミス<br>
    T: ブロックアウト(得点)
    </div>
    """, unsafe_allow_html=True)

with c_score:
    st.markdown(f'<div class="score-board">{st.session_state.score[0]} - {st.session_state.score[1]}</div>', unsafe_allow_html=True)
    st.markdown(f"<div style='text-align:center; font-weight:bold;'>Phase: {st.session_state.phase}</div>", unsafe_allow_html=True)
    
    sc1, sc2 = st.columns(2)
    if sc1.button("↑ My Pt (+1/Rot)", key="btn_up"): manual_score_update('my')
    if sc2.button("↓ Op Pt (+1)", key="btn_down"): manual_score_update('op')

with c_rot:
    r = st.session_state.rotation
    rot_html = f"""
    <div class="rot-container">
        <div class="rot-player rot-front">4: {r[3]}</div>
        <div class="rot-player rot-front">3: {r[4]}</div>
        <div class="rot-player rot-front">2: {r[5]}</div>
        <div class="rot-player">5: {r[2]}</div>
        <div class="rot-player">6: {r[1]}</div>
        <div class="rot-player rot-server">1: {r[0]}</div>
    </div>
    """
    st.markdown(rot_html, unsafe_allow_html=True)
    
    with st.expander("詳細設定"):
        st.session_state.set_name = st.text_input("Set (A列)", "1")
        st.session_state.video_url = st.text_input("URL (L列)", "https://")
        rot_csv = st.text_input("Start Rot (comma sep)", ",".join(st.session_state.rotation))
        if st.button("Set Rotation"):
            st.session_state.rotation = [x.strip() for x in rot_csv.split(',')]
        
        start_ph = st.radio("Start Phase", ["Serve (My)", "Reception (Op)"])
        if st.button("Reset Game"):
            st.session_state.score = [0, 0]
            st.session_state.phase = 'S' if "Serve" in start_ph else 'R'
            st.rerun()

st.divider()

col_map, col_input, col_qual = st.columns([1, 1.2, 1.5])

with col_map:
    st.markdown("##### 7. Map")
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

with col_input:
    st.markdown("##### Input")
    st.session_state.input_time = st.text_input("4. Time (XXXX)", key=f"time_{st.session_state.time_key}")
    
    skill_opts = ["R", "A", "S", "B", "D", "E"]
    st.session_state.input_skill = st.selectbox("5. Skill", skill_opts)
    
    active_players = st.session_state.rotation + [l for l in st.session_state.liberos if l]
    st.session_state.input_player = st.selectbox("6. Player", active_players)
    
    if st.session_state.input_skill == 'A':
        sorted_setters = get_sorted_setters()
        st.session_state.input_setter = st.selectbox("Setter", sorted_setters)
        st.session_state.input_combo = st.text_input("Combo", key=f"combo_{st.session_state.combo_key}")
    else:
        st.session_state.input_setter = ""
        st.session_state.input_combo = ""

with col_qual:
    st.markdown("##### 8. Quality (Register)")
    q1, q2 = st.columns(2)
    with q1:
        if st.button("# Perfect / Point", type="primary"): register_data("#")
        if st.button("! OK / Continue"): register_data("!")
        if st.button("/ Rebound (Soft)"): register_data("/")
    with q2:
        if st.button('" Good / Effect'): register_data('"')
        if st.button("- Poor / Chance"): register_data("-")
        if st.button("^ Error / Blocked"): register_data("^")
    
    if st.button("T BlockOut (Point)"): register_data("T")

st.divider()

c_sub, c_table = st.columns([1, 2])

with c_sub:
    st.markdown("#### 🔄 選手交代")
    with st.container():
        out_p = st.selectbox("OUT", st.session_state.rotation)
        in_p = st.text_input("IN (Name)", "")
        if st.button("Change"):
            if in_p: substitute_player(out_p, in_p)
            else: st.error("Name required")
            
    st.markdown("#### リベロ登録")
    lib_val = st.text_input("Liberos (max 2)", ",".join(st.session_state.liberos))
    if st.button("Update Lib"):
        st.session_state.liberos = [x.strip() for x in lib_val.split(',')]
        st.toast("Updated")

with c_table:
    st.markdown("#### Recorded Data")
    if len(st.session_state.data_log) > 0:
        df = pd.DataFrame(st.session_state.data_log)
        edited_df = st.data_editor(df, num_rows="dynamic", height=250, use_container_width=True)
        st.session_state.data_log = edited_df.to_dict('records')
        
        st.markdown("### 11. FINISH")
        cd1, cd2 = st.columns(2)
        
        # 出力前に列名を指定のものに変更
        # A:set, B:score, C:phase, D:setter, E:player, F:skill, G:combo, H:quality, I:start_zone, J:end_zone, 
        # K:ブランク(memo), L:Video_URL, M:Time_Sec
        
        export_df = df.copy()
        export_df.rename(columns={
            "video_url": "Video_URL",
            "video_time": "Time_Sec"
        }, inplace=True)
        
        # Excel
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
            export_df.to_excel(writer, index=False, sheet_name='Sheet1')
        cd1.download_button("Download .xlsx", buf.getvalue(), "scouting.xlsx", "application/vnd.ms-excel")
        
        # CSV
        csv = export_df.to_csv(index=False).encode('utf-8')
        cd2.download_button("Download .csv", csv, "scouting.csv", "text/csv")
    else:
        st.info("No data yet.")
