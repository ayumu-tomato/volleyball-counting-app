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

# ==========================================
# 1. 設定 & JS制御
# ==========================================
st.set_page_config(page_title="Volleyball Scouter Ver.3.9", layout="wide")

st.markdown("""
<style>
    .instruction { font-size: 24px; font-weight: bold; color: #1f77b4; margin-bottom: 10px; }
    .score-board { font-size: 50px; font-weight: 900; text-align: center; background: #333; color: white; padding: 10px; border-radius: 10px; }
    .input-area { border: 2px solid #1f77b4; padding: 20px; border-radius: 10px; background-color: white; }
    .rot-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 5px; text-align: center; font-weight: bold; }
    .rot-cell { border: 2px solid #555; padding: 10px; background: white; border-radius: 5px; }
    .rot-front { background: #ffebeb; }
    .rot-server { border-color: red; color: red; }
</style>
""", unsafe_allow_html=True)

# ★ JS1: キーボードショートカット (常駐)
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
        """,
        height=0
    )

# ★ JS2: 自動フォーカス (入力欄表示直後に呼ぶ)
def focus_input():
    components.html(
        """
        <script>
            setTimeout(function() {
                const doc = window.parent.document;
                const inputs = doc.querySelectorAll('input[type="text"]');
                // 画面上の一番最後のテキスト入力欄にフォーカスする
                if (inputs.length > 0) {
                    inputs[inputs.length - 1].focus();
                }
            }, 300); // 描画待ち
        </script>
        """,
        height=0
    )

# セッション初期化
defaults = {
    'stage': 0, 'roster_cursor': 0, 'temp_roster': [], 'scout_step': 0,
    'set_name': '1', 'video_url': '', 'liberos': [], 'rotation': [], 'score': [0, 0], 'phase': 'R',
    'current_input_data': {}, 'data_log': [], 'points': [], 'setter_counts': {},
    'key_time': 0, 'key_skill': 0, 'key_player': 0, 'key_setter': 0, 'key_combo': 0, 'key_quality': 0, 'key_map': 0
}
for k, v in defaults.items():
    if k not in st.session_state: st.session_state[k] = v

# ショートカットは毎回注入
inject_shortcuts()

# ==========================================
# 2. ロジック関数
# ==========================================
def get_zone(x, y, w, h):
    cx, cy = (x / w) * 9, (1 - (y / h)) * 18 
    if 0 <= cy < 9: # 自コート
        r, c = int(cy//3), int(cx//3)
        if r==0: return [5,6,1][c]
        if r==1: return [7,8,9][c]
        if r==2: return [4,3,2][c]
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
    ax.plot([3,3], [9,18], c='gray', ls=':', lw=0.5); ax.plot([6,6], [9,18], c='gray', ls=':', lw=0.5)

    for i, p in enumerate(points):
        px, py = (p[0]/300)*9, (1-(p[1]/600))*18
        col = "blue" if i==0 else "red"
        lbl = "S" if i==0 else "E"
        ax.scatter(px, py, s=200, c=col, zorder=10, edgecolors='white')
        ax.text(px, py, lbl, color='white', ha='center', va='center', fontweight='bold')
        if i==1: 
            sx, sy = (points[0][0]/300)*9, (1-(points[0][1]/600))*18
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

def update_score(winner):
    if winner == 'my':
        st.session_state.score[0] += 1
        st.session_state.phase = 'S'
        rotate_team()
        st.toast("My Point! Rotated.", icon="⭕")
    elif winner == 'op':
        st.session_state.score[1] += 1
        st.session_state.phase = 'R'
        st.toast("Opponent Point.", icon="❌")

def reset_input_keys():
    st.session_state.key_time += 1
    st.session_state.key_skill += 1
    st.session_state.key_player += 1
    st.session_state.key_setter += 1
    st.session_state.key_combo += 1
    st.session_state.key_quality += 1
    st.session_state.key_map += 1

def commit_record(quality, winner=None):
    curr = st.session_state.current_input_data
    s_z, e_z = "", ""
    if len(st.session_state.points)>=1: s_z = get_zone(st.session_state.points[0][0], st.session_state.points[0][1], 300, 600)
    if len(st.session_state.points)>=2: e_z = get_zone(st.session_state.points[1][0], st.session_state.points[1][1], 300, 600)
    
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
    
    if winner:
        update_score(winner)
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
    st.markdown('<div class="instruction">Step 1: セット番号を入力</div>', unsafe_allow_html=True)
    def set_entered():
        val = st.session_state.input_set
        if val:
            st.session_state.set_name = val
            st.session_state.stage = 1
    st.text_input("Set Number", key="input_set", on_change=set_entered)
    focus_input() # ★自動フォーカス呼び出し

# --- Stage 1: URL Input ---
elif st.session_state.stage == 1:
    st.markdown('<div class="instruction">Step 2: 動画URLを入力</div>', unsafe_allow_html=True)
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
    pos_name = ["1 (Server/Back-R)", "6 (Back-C)", "5 (Back-L)", "4 (Front-L)", "3 (Front-C)", "2 (Front-Right)"][idx]
    st.markdown(f'<div class="instruction">Step 3: スタメン入力 ({idx+1}/6)</div>', unsafe_allow_html=True)
    st.info(f"ポジション: **{pos_name}** の選手名を入力")
    
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
    if st.session_state.temp_roster: st.write("入力済み:", st.session_state.temp_roster)
    focus_input()

# --- Stage 3: Confirm ---
elif st.session_state.stage == 3:
    st.markdown('<div class="instruction">Step 4: メンバー確認</div>', unsafe_allow_html=True)
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
    st.markdown("**1: OK / 2: 修正**")
    
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
    st.markdown('<div class="instruction">Step 5: リベロ登録 (任意)</div>', unsafe_allow_html=True)
    def libero_entered():
        val = st.session_state.input_libero
        st.session_state.liberos = [x.strip() for x in val.split(',')] if val else []
        st.session_state.stage = 5
    st.text_input("Names (comma separated)", key="input_libero", on_change=libero_entered)
    focus_input()

# --- Stage 5: Phase ---
elif st.session_state.stage == 5:
    st.markdown('<div class="instruction">Step 6: 開始フェーズ</div>', unsafe_allow_html=True)
    st.markdown("**1: Serve (自チーム) / 2: Reception (相手サーブ)**")
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
    
    # UI Header
    c1, c2, c3 = st.columns([1, 1.5, 1])
    with c1: st.info("S/A: #=Ace/Pt, \"=Good, !=Cont, ^=Err\nR: #=A, \"=B, !=C, -=D, ^=Err")
    with c2: 
        st.markdown(f'<div class="score-board">{st.session_state.score[0]} - {st.session_state.score[1]}</div>', unsafe_allow_html=True)
        st.markdown(f"<h3 style='text-align:center'>Phase: {st.session_state.phase}</h3>", unsafe_allow_html=True)
        
        b1, b2 = st.columns(2)
        if b1.button("↑ My Pt (Shift+↑)"): commit_record("#", winner='my')
        if b2.button("↓ Op Pt (Shift+↓)"): commit_record("^", winner='op')

    with c3:
        r = st.session_state.rotation
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

    st.divider()

    col_map, col_cmd = st.columns([1, 1.5])
    
    # --- Map ---
    with col_map:
        st.markdown("##### Map (Click Start -> End)")
        court_img = create_court_img(st.session_state.points)
        val = streamlit_image_coordinates(court_img, key="main_court", width=300, height=600)
        
        if val:
            p = (val['x'], val['y'])
            if not st.session_state.points or st.session_state.points[-1] != p:
                if len(st.session_state.points) < 2:
                    st.session_state.points.append(p)
                    if len(st.session_state.points) == 2:
                        st.session_state.scout_step = 5
                    st.rerun()
                else:
                    st.session_state.points = [p]
                    st.rerun()
        st.caption("Startをタップ" if len(st.session_state.points)==0 else ("Endをタップ" if len(st.session_state.points)==1 else "OK (Next)"))

    # --- Input Wizard ---
    with col_cmd:
        st.markdown('<div class="input-area">', unsafe_allow_html=True)
        
        # 1. Time
        if st.session_state.scout_step == 0:
            st.markdown("##### 1. Time (例: 0513 -> 05:13)")
            def time_submit():
                k = f"in_time_{st.session_state.key_time}"
                t = format_time(st.session_state[k])
                st.session_state.current_input_data['time'] = t
                st.session_state.scout_step = 1
            st.text_input("Time", key=f"in_time_{st.session_state.key_time}", on_change=time_submit)
            focus_input() # ★ここに配置

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
            focus_input() # ★ここに配置

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
            focus_input() # ★ここに配置

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
            focus_input() # ★ここに配置

        # 3.8 Combo
        elif st.session_state.scout_step == 3:
            st.markdown("##### 3.8 Combo (e.g. X5, 1, A)")
            def combo_submit():
                k = f"in_combo_{st.session_state.key_combo}"
                st.session_state.current_input_data['combo'] = st.session_state[k]
                st.session_state.scout_step = 4
            st.text_input("Combo", key=f"in_combo_{st.session_state.key_combo}", on_change=combo_submit)
            focus_input() # ★ここに配置

        # 4. Map Wait
        elif st.session_state.scout_step == 4:
            st.markdown("##### 4. Map Input")
            st.info("👈 左のコートを2回クリックしてください")

        # 5. Quality & Save
        elif st.session_state.scout_step == 5:
            st.markdown("##### 5. Quality (Select & Save)")
            qs = [{"k":"1","v":"#","d":"Perfect"},{"k":"2","v":"\"","d":"Good"},{"k":"3","v":"!","d":"OK"},{"k":"4","v":"-","d":"Poor"},{"k":"5","v":"^","d":"Error"},{"k":"6","v":"T","d":"BlockOut"}]
            
            def qual_submit():
                k_q = f"in_qual_{st.session_state.key_quality}"
                val = st.session_state[k_q]
                q_map = {q['k']: q['v'] for q in qs}
                if val in q_map:
                    commit_record(q_map[val])
            
            for q in qs: st.write(f"**{q['k']}**: {q['v']} ({q['d']})")
            st.text_input("Choice", key=f"in_qual_{st.session_state.key_quality}", on_change=qual_submit)
            focus_input() # ★ここに配置

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
        if st.button("FINISH (Download)"):
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False)
            st.download_button("Download Excel", buf.getvalue(), "scout.xlsx")
