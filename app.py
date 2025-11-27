import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from streamlit_image_coordinates import streamlit_image_coordinates
import io
from PIL import Image
import datetime
import xlsxwriter
import time

# ==========================================
# 1. 設定 & JS制御
# ==========================================
st.set_page_config(page_title="Volleyball Scouter Ver.4.0", layout="wide")

# CSS: 省スペース化
st.markdown("""
<style>
    /* 全体の余白を詰める */
    .block-container { padding-top: 1rem; padding-bottom: 1rem; }
    
    .instruction { font-size: 20px; font-weight: bold; color: #1f77b4; margin-bottom: 5px; }
    .score-board { 
        font-size: 40px; font-weight: 900; text-align: center; 
        background: #333; color: white; padding: 0px; border-radius: 8px; 
    }
    .input-area { border: 2px solid #1f77b4; padding: 15px; border-radius: 10px; background-color: white; }
    
    /* ローテーション表をコンパクトに */
    .rot-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 2px; text-align: center; font-weight: bold; font-size: 12px; }
    .rot-cell { border: 1px solid #555; padding: 5px; background: white; border-radius: 4px; }
    .rot-front { background: #ffebeb; }
    .rot-server { border-color: red; color: red; border-width: 2px; }
    
    /* 判例を小さく */
    .legend-box { font-size: 11px; line-height: 1.2; border: 1px solid #ddd; padding: 5px; background: #f9f9f9; }
</style>
""", unsafe_allow_html=True)

# ★自動フォーカス (強力版)
def focus_input():
    ts = str(time.time())
    components.html(
        f"""
        <script>
            setTimeout(function() {{
                const doc = window.parent.document;
                const inputs = doc.querySelectorAll('input[type="text"]');
                const targetLabels = [
                    "Time", "Choice", "Skill Number", "Player Number", "Setter Number",
                    "Combo", "Press Enter", "Set Number", "YouTube URL", "Player Name", "Libero Name", "Names (comma separated)"
                ];
                let found = false;
                for (let i = 0; i < inputs.length; i++) {{
                    const label = inputs[i].getAttribute('aria-label');
                    if (label && (label === "Choice" || targetLabels.includes(label))) {{
                        inputs[i].focus();
                        found = true;
                        break; 
                    }}
                }}
                if (!found && inputs.length > 0) {{ inputs[inputs.length - 1].focus(); }}
            }}, 300);
        </script>
        """, height=0
    )

# ★ショートカット (Shift+Arrow)
def inject_shortcuts():
    components.html(
        """
        <script>
            const doc = window.parent.document;
            doc.addEventListener('keydown', function(e) {
                if (e.shiftKey) {
                    if (e.key === 'ArrowUp') {
                        const buttons = Array.from(doc.querySelectorAll('button'));
                        const target = buttons.find(el => el.innerText.includes('↑ My Pt'));
                        if (target) { target.click(); e.preventDefault(); e.stopPropagation(); }
                    } else if (e.key === 'ArrowDown') {
                        const buttons = Array.from(doc.querySelectorAll('button'));
                        const target = buttons.find(el => el.innerText.includes('↓ Op Pt'));
                        if (target) { target.click(); e.preventDefault(); e.stopPropagation(); }
                    }
                }
            });
        </script>
        """, height=0
    )

# セッション初期化
defaults = {
    'stage': 0, 'roster_cursor': 0, 'temp_roster': [], 'scout_step': 0,
    'set_name': '1', 'video_url': '', 'liberos': [], 'rotation': [], 'score': [0, 0], 'phase': 'R',
    'current_input_data': {}, 'data_log': [], 'points': [], 'setter_counts': {},
    'key_time': 0, 'key_skill': 0, 'key_player': 0, 'key_setter': 0, 'key_combo': 0, 'key_quality': 0
}
for k, v in defaults.items():
    if k not in st.session_state: st.session_state[k] = v

inject_shortcuts()

# ==========================================
# 2. ロジック関数
# ==========================================
def get_zone(x, y, w, h):
    cx, cy = (x / w) * 9, (1 - (y / h)) * 18 
    if 0 <= cy < 9: # 自コート
        r, c = int(cy//3), int(cx//3)
        if r==0: return [5,6,1][c] # Back
        if r==1: return [7,8,9][c] # Mid
        if r==2: return [4,3,2][c] # Front
    elif 9 <= cy <= 18: # 相手コート
        is_front = (cy < 13.5)
        col_img = int(cx // 3)
        if is_front: return [2,3,4][col_img]
        else: return [1,6,5][col_img]
    return 0

def create_court_img(points):
    # 画像生成サイズを小さく調整
    fig, ax = plt.subplots(figsize=(3, 6)) # figsizeを小さく
    ax.add_patch(patches.Rectangle((0, 0), 9, 18, fc='#FFCC99', ec='black', lw=2))
    ax.plot([0,9], [9,9], c='red', lw=3)
    ax.plot([0,9], [6,6], c='black', lw=1); ax.plot([0,9], [12,12], c='black', lw=1)
    
    # 相手コートガイド
    ax.plot([0,9], [13.5, 13.5], c='gray', ls=':', lw=0.5)
    ax.plot([3,3], [9,18], c='gray', ls=':', lw=0.5); ax.plot([6,6], [9,18], c='gray', ls=':', lw=0.5)

    for i, p in enumerate(points):
        # 描画用座標変換 (Click座標 -> コート座標)
        # ※ここでの分母(230, 460)は、streamlit_image_coordinatesのwidth/heightと一致させる必要がある
        px, py = (p[0]/230)*9, (1-(p[1]/460))*18
        col = "blue" if i==0 else "red"
        lbl = "S" if i==0 else "E"
        ax.scatter(px, py, s=150, c=col, zorder=10, edgecolors='white')
        ax.text(px, py, lbl, color='white', ha='center', va='center', fontweight='bold', fontsize=8)
        if i==1: 
            sx, sy = (points[0][0]/230)*9, (1-(points[0][1]/460))*18
            ax.arrow(sx, sy, px-sx, py-sy, width=0.15, color='gray', alpha=0.5)
    ax.set_xlim(0, 9); ax.set_ylim(0, 18); ax.axis('off')
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', pad_inches=0)
    buf.seek(0)
    return Image.open(buf)

def format_time(val):
    s = str(val).strip().replace(':', '')
    if not s.isdigit(): return "00:00"
    v = int(s)
    if len(str(v)) <= 2: return f"00:{v:02d}"
    sec = int(str(v)[-2:]); min_ = int(str(v)[:-2])
    return f"{min_:02d}:{sec:02d}"

def time_to_sec(t_str):
    if ':' not in t_str: return 0
    m, s = t_str.split(':')
    return int(m)*60 + int(s)

def rotate_team():
    r = st.session_state.rotation
    st.session_state.rotation = [r[-1]] + r[:-1]

def update_score(skill, quality):
    my = False; op = False
    if (skill in ['A','B','S'] and quality=='#') or (skill=='A' and quality=='T'): my = True
    elif quality == '^': op = True
    
    if my:
        st.session_state.score[0] += 1
        st.session_state.phase = 'S'
        rotate_team()
        st.toast("My Point! Rotated.", icon="⭕")
    elif op:
        st.session_state.score[1] += 1
        st.session_state.phase = 'R'
        st.toast("Opponent Point.", icon="❌")

def reset_input_keys():
    for k in ['key_time', 'key_skill', 'key_player', 'key_setter', 'key_combo', 'key_quality']:
        st.session_state[k] += 1

def commit_record(quality, winner=None):
    curr = st.session_state.current_input_data
    s_z, e_z = "", ""
    # 座標変換時のサイズ指定 (width=230, height=460)
    if len(st.session_state.points)>=1: s_z = get_zone(st.session_state.points[0][0], st.session_state.points[0][1], 230, 460)
    if len(st.session_state.points)>=2: e_z = get_zone(st.session_state.points[1][0], st.session_state.points[1][1], 230, 460)
    
    final_row = {
        "set": st.session_state.set_name,
        "score": f"{st.session_state.score[0]}-{st.session_state.score[1]}",
        "phase": st.session_state.phase,
        "setter": curr.get('setter',''), "player": curr.get('player',''),
        "skill": curr.get('skill',''), "combo": curr.get('combo',''),
        "quality": quality,
        "start_zone": s_z, "end_zone": e_z,
        "memo": "", "video_url": st.session_state.video_url,
        "video_time": time_to_sec(curr.get('time',''))
    }
    st.session_state.data_log.append(final_row)
    
    if winner: update_score(winner)
    else:
        skill = curr.get('skill','')
        if (skill in ['A','B','S'] and quality=='#') or (skill=='A' and quality=='T'): update_score('my')
        elif quality == '^': update_score('op')
        else: st.toast("Saved.", icon="✅")

    st.session_state.points = []
    st.session_state.current_input_data = {}
    st.session_state.scout_step = 0
    reset_input_keys()
    st.rerun()

# ==========================================
# 3. アプリ進行フロー
# ==========================================

# --- Stage 0: Set Input ---
if st.session_state.stage == 0:
    st.markdown('<div class="instruction">Step 1: Set Number</div>', unsafe_allow_html=True)
    def set_entered():
        val = st.session_state.input_set
        if val:
            st.session_state.set_name = val
            st.session_state.stage = 1
    st.text_input("Set Number", key="input_set", on_change=set_entered)
    focus_input()

# --- Stage 1: URL Input ---
elif st.session_state.stage == 1:
    st.markdown('<div class="instruction">Step 2: Video URL</div>', unsafe_allow_html=True)
    def url_entered():
        st.session_state.video_url = st.session_state.input_url
        st.session_state.stage = 2
        st.session_state.roster_cursor = 0
        st.session_state.temp_roster = []
    st.text_input("YouTube URL", key="input_url", on_change=url_entered)
    focus_input()

# --- Stage 2: Roster ---
elif st.session_state.stage == 2:
    idx = st.session_state.roster_cursor
    pos_name = ["1 (Back-R)", "6 (Back-C)", "5 (Back-L)", "4 (Front-L)", "3 (Front-C)", "2 (Front-R)"][idx]
    st.markdown(f'<div class="instruction">Step 3: Lineup ({idx+1}/6) : {pos_name}</div>', unsafe_allow_html=True)
    
    def player_entered():
        p_name = st.session_state.input_player_reg
        if p_name:
            st.session_state.temp_roster.append(p_name)
            if st.session_state.roster_cursor < 5:
                st.session_state.roster_cursor += 1
            else:
                st.session_state.stage = 3
        st.session_state.input_player_reg = ""

    st.text_input("Player Name", key="input_player_reg", on_change=player_entered)
    focus_input()

# --- Stage 3: Confirm ---
elif st.session_state.stage == 3:
    st.markdown('<div class="instruction">Step 4: Confirm</div>', unsafe_allow_html=True)
    r = st.session_state.temp_roster
    st.markdown(f"""
    <div class="rot-grid">
        <div class="rot-cell rot-front">4: {r[3]}</div>
        <div class="rot-cell rot-front">3: {r[4]}</div>
        <div class="rot-cell rot-front">2: {r[5]}</div>
        <div class="rot-cell">5: {r[2]}</div>
        <div class="rot-cell">6: {r[1]}</div>
        <div class="rot-cell rot-server">1: {r[0]}</div>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("**1: OK / 2: Retry**")
    
    def confirm_choice():
        val = st.session_state.input_confirm
        if val == "1":
            st.session_state.rotation = st.session_state.temp_roster
            st.session_state.stage = 4
        elif val == "2":
            st.session_state.stage = 2
            st.session_state.roster_cursor = 0
            st.session_state.temp_roster = []
    st.text_input("Choice", key="input_confirm", on_change=confirm_choice)
    focus_input()

# --- Stage 4: Libero ---
elif st.session_state.stage == 4:
    st.markdown('<div class="instruction">Step 5: Liberos</div>', unsafe_allow_html=True)
    def libero_entered():
        val = st.session_state.input_libero
        st.session_state.liberos = [x.strip() for x in val.split(',')] if val else []
        st.session_state.stage = 5
    st.text_input("Names (comma separated)", key="input_libero", on_change=libero_entered)
    focus_input()

# --- Stage 5: Phase ---
elif st.session_state.stage == 5:
    st.markdown('<div class="instruction">Step 6: First Phase</div>', unsafe_allow_html=True)
    st.markdown("**1: Serve (My) / 2: Reception (Op)**")
    def phase_entered():
        val = st.session_state.input_phase
        if val == "1": st.session_state.phase = 'S'; st.session_state.stage = 6
        elif val == "2": st.session_state.phase = 'R'; st.session_state.stage = 6
    st.text_input("Choice", key="input_phase", on_change=phase_entered)
    focus_input()

# ==========================================
# --- Stage 6: MAIN SCOUTING ---
# ==========================================
elif st.session_state.stage == 6:
    
    # --- Header (Compact) ---
    c_left, c_mid, c_right = st.columns([0.8, 1.2, 1.0]) # カラム比率調整
    
    with c_left:
        # 判例
        st.markdown("""
        <div class="legend-box">
        <b>R:</b> #:A, ":B, !:C, -:D, ^:Err<br>
        <b>S/A:</b> #:Pt, ":Good, !:OK, ^:Err
        </div>
        """, unsafe_allow_html=True)
        
    with c_mid:
        st.markdown(f'<div class="score-board">{st.session_state.score[0]}-{st.session_state.score[1]} ({st.session_state.phase})</div>', unsafe_allow_html=True)
        # 隠しボタン (Shift+Arrow用)
        b1, b2 = st.columns(2)
        if b1.button("↑ My Pt (Shift+↑)"): commit_record("#", winner='my')
        if b2.button("↓ Op Pt (Shift+↓)"): commit_record("^", winner='op')

    with c_right:
        r = st.session_state.rotation
        st.markdown(f"""
        <div class="rot-grid">
            <div class="rot-cell rot-front">{r[3]}</div>
            <div class="rot-cell rot-front">{r[4]}</div>
            <div class="rot-cell rot-front">{r[5]}</div>
            <div class="rot-cell">{r[2]}</div>
            <div class="rot-cell">{r[1]}</div>
            <div class="rot-cell rot-server">{r[0]}</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")

    col_map, col_cmd = st.columns([0.8, 1.5]) # マップを狭く、入力を広く
    
    # --- Map (Compact) ---
    with col_map:
        st.markdown("**Map**")
        # ★画像を小さく (width=230)
        court_img = create_court_img(st.session_state.points)
        val = streamlit_image_coordinates(court_img, key="main_court", width=230, height=460)
        
        if val:
            p = (val['x'], val['y'])
            if not st.session_state.points or st.session_state.points[-1] != p:
                if len(st.session_state.points) < 2:
                    st.session_state.points.append(p)
                    # 2点クリックしたら自動でStep5へ
                    if len(st.session_state.points) == 2:
                        st.session_state.scout_step = 5
                    st.rerun()
                else:
                    st.session_state.points = [p]
                    st.rerun()
        st.caption("Status: " + ("Start" if len(st.session_state.points)==0 else ("End" if len(st.session_state.points)==1 else "Done")))

    # --- Input Wizard ---
    with col_cmd:
        st.markdown('<div class="input-area">', unsafe_allow_html=True)
        
        # 1. Time
        if st.session_state.scout_step == 0:
            st.markdown("##### 1. Time")
            def time_submit():
                k = f"in_time_{st.session_state.key_time}"
                t = format_time(st.session_state[k])
                st.session_state.current_input_data['time'] = t
                st.session_state.scout_step = 1
            st.text_input("Time (ex 0513)", key=f"in_time_{st.session_state.key_time}", on_change=time_submit)
            focus_input()

        # 2. Skill
        elif st.session_state.scout_step == 1:
            st.markdown("##### 2. Skill")
            skills = {"1":"S (Serve)", "2":"R (Reception)", "3":"A (Attack)", "4":"B (Block)", "5":"D (Dig)", "6":"E (Set)"}
            for k,v in skills.items(): st.write(f"**{k}**: {v}")
            
            def skill_submit():
                k = f"in_skill_{st.session_state.key_skill}"
                val = st.session_state[k]
                s_map = {"1":"S", "2":"R", "3":"A", "4":"B", "5":"D", "6":"E"}
                if val in s_map:
                    skill = s_map[val]
                    st.session_state.current_input_data['skill'] = skill
                    if skill == 'S': # Server Auto
                        st.session_state.current_input_data['player'] = st.session_state.rotation[0]
                        st.session_state.current_input_data['setter'] = ""
                        st.session_state.current_input_data['combo'] = ""
                        st.session_state.scout_step = 4 # Mapへ
                    elif skill == 'A':
                        st.session_state.scout_step = 2 # Playerへ
                    else:
                        st.session_state.scout_step = 2
            st.text_input("Choice", key=f"in_skill_{st.session_state.key_skill}", on_change=skill_submit)
            focus_input()

        # 3. Player
        elif st.session_state.scout_step == 2:
            st.markdown("##### 3. Player")
            cand = st.session_state.rotation + st.session_state.liberos
            for i, p in enumerate(cand): st.write(f"**{i+1}**: {p}")
            
            def player_submit():
                k = f"in_player_{st.session_state.key_player}"
                try:
                    idx = int(st.session_state[k]) - 1
                    if 0 <= idx < len(cand):
                        st.session_state.current_input_data['player'] = cand[idx]
                        if st.session_state.current_input_data['skill'] == 'A':
                            st.session_state.scout_step = 25 # Setter
                        else:
                            st.session_state.scout_step = 4 # Map
                except: pass
            st.text_input("Choice", key=f"in_player_{st.session_state.key_player}", on_change=player_submit)
            focus_input()

        # 3.5 Setter
        elif st.session_state.scout_step == 25:
            st.markdown("##### 3.5 Setter")
            all_m = st.session_state.rotation + st.session_state.liberos
            def skey(n): return st.session_state.setter_counts.get(n, 0)
            setters = sorted(all_m, key=skey, reverse=True) + ["Direct/Two"]
            for i, s in enumerate(setters): st.write(f"**{i+1}**: {s}")
            
            def setter_submit():
                k = f"in_setter_{st.session_state.key_setter}"
                try:
                    idx = int(st.session_state[k]) - 1
                    if 0 <= idx < len(setters):
                        s_name = setters[idx]
                        st.session_state.current_input_data['setter'] = s_name
                        if s_name != "Direct/Two":
                            st.session_state.setter_counts[s_name] = st.session_state.setter_counts.get(s_name, 0) + 1
                        st.session_state.scout_step = 3 # Combo
                except: pass
            st.text_input("Choice", key=f"in_setter_{st.session_state.key_setter}", on_change=setter_submit)
            focus_input()

        # 3.8 Combo
        elif st.session_state.scout_step == 3:
            st.markdown("##### 3.8 Combo")
            def combo_submit():
                k = f"in_combo_{st.session_state.key_combo}"
                st.session_state.current_input_data['combo'] = st.session_state[k]
                st.session_state.scout_step = 4
            st.text_input("Combo (X5, 1, A)", key=f"in_combo_{st.session_state.key_combo}", on_change=combo_submit)
            focus_input()

        # 4. Map Wait (Compact)
        elif st.session_state.scout_step == 4:
            st.markdown("##### 4. Map Input")
            st.info("👈 左のコートをクリックしてください")

        # 5. Quality & Save
        elif st.session_state.scout_step == 5:
            st.markdown("##### 5. Quality")
            qs = [{"k":"1","v":"#","d":"Perf"},{"k":"2","v":"\"","d":"Good"},{"k":"3","v":"!","d":"OK"},{"k":"4","v":"-","d":"Poor"},{"k":"5","v":"^","d":"Err"},{"k":"6","v":"T","d":"BlockOut"}]
            
            def qual_submit():
                k_q = f"in_qual_{st.session_state.key_quality}"
                val = st.session_state[k_q]
                q_map = {q['k']: q['v'] for q in qs}
                
                # コマンド入力対応
                if val == '8': commit_record("#", winner='my') # Force My Pt
                elif val == '9': commit_record("^", winner='op') # Force Op Pt
                elif val in q_map:
                    commit_record(q_map[val])
            
            for q in qs: st.write(f"**{q['k']}**: {q['v']} ({q['d']})")
            st.write("**8**: My Pt (Force) / **9**: Op Pt (Force)")
            st.text_input("Choice", key=f"in_qual_{st.session_state.key_quality}", on_change=qual_submit)
            focus_input()

        st.markdown("</div>", unsafe_allow_html=True)
        if st.button("Reset Input"):
            st.session_state.scout_step = 0
            st.session_state.points = []
            st.rerun()

    # --- Data Output ---
    st.markdown("### Data")
    if len(st.session_state.data_log) > 0:
        df = pd.DataFrame(st.session_state.data_log)
        st.dataframe(df.iloc[::-1], height=150)
        
        # 選手交代 & リベロ & ダウンロード
        c_sub, c_dl = st.columns(2)
        with c_sub:
            with st.expander("Sub / Libero"):
                out_p = st.selectbox("OUT", st.session_state.rotation)
                in_p = st.text_input("IN Name")
                if st.button("Change"):
                    if in_p: substitute_player(out_p, in_p); st.rerun()
                
                lib_t = st.text_input("Liberos", ",".join(st.session_state.liberos))
                if st.button("Update"):
                    st.session_state.liberos = [x.strip() for x in lib_t.split(',')]
                    st.rerun()

        with c_dl:
            if st.button("FINISH (Download)"):
                buf = io.BytesIO()
                with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
                    df.to_excel(writer, index=False)
                st.download_button("Download Excel", buf.getvalue(), "scout.xlsx")
