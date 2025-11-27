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
# 1. 設定 & ステート管理
# ==========================================
st.set_page_config(page_title="Volleyball Scouter Ver.3.0", layout="wide")

# CSS: 入力フォームを目立たせる & UI調整
st.markdown("""
<style>
    .instruction { font-size: 24px; font-weight: bold; color: #1f77b4; margin-bottom: 10px; }
    .status-box { padding: 15px; background-color: #f0f2f6; border-radius: 10px; margin-bottom: 20px; }
    .score-board { font-size: 50px; font-weight: 900; text-align: center; background: #333; color: white; padding: 10px; border-radius: 10px; }
    .input-area { border: 2px solid #1f77b4; padding: 20px; border-radius: 10px; background-color: white; }
    
    /* ローテーション表示 */
    .rot-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 5px; text-align: center; font-weight: bold; }
    .rot-cell { border: 2px solid #555; padding: 10px; background: white; border-radius: 5px; }
    .rot-front { background: #ffebeb; }
    .rot-server { border-color: red; color: red; }
</style>
""", unsafe_allow_html=True)

# セッション状態の初期化
defaults = {
    'stage': 0,          # 0:Set, 1:URL, 2:Roster, 3:Confirm, 4:Libero, 5:Phase, 6:Main
    'roster_cursor': 0,  # スタメン入力中のカーソル(0-5)
    'temp_roster': [],   # スタメン一時保存
    'scout_step': 0,     # 0:Time, 1:Skill, 2:Player, 3:Combo(opt), 4:Map, 5:Quality
    
    'set_name': '1',
    'video_url': '',
    'liberos': [],
    'rotation': [],
    'score': [0, 0],     # [My, Op]
    'phase': 'R',
    
    'current_input_data': {}, # 現在入力中の行データ
    'data_log': [],      # 全データログ
    'points': [],        # マップクリック座標
    'setter_counts': {}  # セッター使用頻度
}

for k, v in defaults.items():
    if k not in st.session_state: st.session_state[k] = v

# ==========================================
# 2. ロジック関数
# ==========================================

# --- ゾーン判定 (自チーム目線修正版) ---
def get_zone(x, y, w, h):
    # 画像座標 (左上0,0) -> 9x18mコート
    # x: 0-w -> 0-9
    # y: 0-h -> 18-0 (下から上へ)
    
    cx = (x / w) * 9
    cy = (1 - (y / h)) * 18 
    
    # 自コート (下半分: 0 <= Y < 9)
    if 0 <= cy < 9:
        row = int(cy // 3) # 0(Back), 1(Mid), 2(Front)
        col = int(cx // 3) # 0(Left), 1(Center), 2(Right)
        
        # 修正: 自チーム目線 (Server looking at net)
        # Left(0) -> Zone 5/4, Right(2) -> Zone 1/2
        
        if row == 0: return [5, 6, 1][col] # Back: Left=5, Mid=6, Right=1
        if row == 1: return [7, 8, 9][col] # Mid: (DataVolley standard)
        if row == 2: return [4, 3, 2][col] # Front: Left=4, Mid=3, Right=2
        
    # 相手コート (上半分: 9 <= Y <= 18)
    elif 9 <= cy <= 18:
        # 相手目線でのゾーン (ネットに近い方がFront)
        is_front = (cy < 13.5)
        col_img = int(cx // 3) # 0(画左=OpRight), 1(OpCenter), 2(画右=OpLeft)
        
        if is_front: # Front (2,3,4)
            if col_img == 0: return 2
            if col_img == 1: return 3
            if col_img == 2: return 4
        else: # Back (1,6,5)
            if col_img == 0: return 1
            if col_img == 1: return 6
            if col_img == 2: return 5
    return 0

# --- コート画像 ---
def create_court_img(points):
    fig, ax = plt.subplots(figsize=(4, 8))
    ax.add_patch(patches.Rectangle((0, 0), 9, 18, fc='#FFCC99', ec='black', lw=2))
    ax.plot([0,9], [9,9], c='red', lw=3)
    ax.plot([0,9], [6,6], c='black', lw=1); ax.plot([0,9], [12,12], c='black', lw=1)
    
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

# --- 時間変換 ---
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

# --- ゲームロジック ---
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

# ==========================================
# 3. アプリ進行フロー (Stages)
# ==========================================

# --- Stage 0: Set Input ---
if st.session_state.stage == 0:
    st.markdown('<div class="instruction">Step 1: セット番号を入力してください</div>', unsafe_allow_html=True)
    def set_entered():
        if st.session_state.input_set:
            st.session_state.set_name = st.session_state.input_set
            st.session_state.stage = 1
    st.text_input("Set Number", key="input_set", on_change=set_entered)

# --- Stage 1: URL Input ---
elif st.session_state.stage == 1:
    st.markdown('<div class="instruction">Step 2: 動画URLを入力してください</div>', unsafe_allow_html=True)
    def url_entered():
        st.session_state.video_url = st.session_state.input_url
        st.session_state.stage = 2
        st.session_state.roster_cursor = 0
        st.session_state.temp_roster = []
    st.text_input("YouTube URL", key="input_url", on_change=url_entered)

# --- Stage 2: Starting Lineup (Sequential) ---
elif st.session_state.stage == 2:
    idx = st.session_state.roster_cursor
    pos_name = ["1 (Server/Back-Right)", "6 (Back-Center)", "5 (Back-Left)", "4 (Front-Left)", "3 (Front-Center)", "2 (Front-Right)"][idx]
    
    st.markdown(f'<div class="instruction">Step 3: スターティングメンバー入力 ({idx+1}/6)</div>', unsafe_allow_html=True)
    st.info(f"ポジション: **{pos_name}** の選手名を入力してエンター")
    
    def player_entered():
        p_name = st.session_state.input_player
        if p_name:
            st.session_state.temp_roster.append(p_name)
            if st.session_state.roster_cursor < 5:
                st.session_state.roster_cursor += 1
            else:
                st.session_state.stage = 3 # 確認画面へ
        st.session_state.input_player = "" # Clear input

    st.text_input("Player Name", key="input_player", on_change=player_entered)
    
    # 現在の入力状況
    if st.session_state.temp_roster:
        st.write("入力済み:", st.session_state.temp_roster)

# --- Stage 3: Confirmation ---
elif st.session_state.stage == 3:
    st.markdown('<div class="instruction">Step 4: メンバー確認</div>', unsafe_allow_html=True)
    
    # ローテーション表示
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
    
    st.markdown("---")
    st.markdown("**選択してください (番号を入力):**")
    st.markdown("1. **OK** (次へ)")
    st.markdown("2. **修正** (最初からやり直す)")
    
    def confirm_choice():
        val = st.session_state.input_confirm
        if val == "1":
            st.session_state.rotation = st.session_state.temp_roster
            st.session_state.stage = 4
        elif val == "2":
            st.session_state.stage = 2
            st.session_state.roster_cursor = 0
            st.session_state.temp_roster = []
    
    st.text_input("Choice (1 or 2)", key="input_confirm", on_change=confirm_choice)

# --- Stage 4: Libero ---
elif st.session_state.stage == 4:
    st.markdown('<div class="instruction">Step 5: リベロ登録</div>', unsafe_allow_html=True)
    st.markdown("リベロの名前を入力してください（いない場合はそのままエンター）")
    
    def libero_entered():
        val = st.session_state.input_libero
        if val:
            st.session_state.liberos = [x.strip() for x in val.split(',')]
        else:
            st.session_state.liberos = []
        st.session_state.stage = 5
        
    st.text_input("Libero Name (カンマ区切りで複数可)", key="input_libero", on_change=libero_entered)

# --- Stage 5: First Phase ---
elif st.session_state.stage == 5:
    st.markdown('<div class="instruction">Step 6: 開始フェーズ選択</div>', unsafe_allow_html=True)
    st.markdown("**1. サーブ (自チーム)**")
    st.markdown("**2. レセプション (相手サーブ)**")
    
    def phase_entered():
        val = st.session_state.input_phase
        if val == "1":
            st.session_state.phase = 'S'
            st.session_state.stage = 6
        elif val == "2":
            st.session_state.phase = 'R'
            st.session_state.stage = 6
            
    st.text_input("Choice (1 or 2)", key="input_phase", on_change=phase_entered)

# ==========================================
# --- Stage 6: MAIN SCOUTING ---
# ==========================================
elif st.session_state.stage == 6:
    
    # --- 共通UI (スコア & ローテ) ---
    c_left, c_mid, c_right = st.columns([1, 1.5, 1])
    
    with c_left:
        st.markdown("**Quality判例**")
        st.info("S/A: #=Ace/Pt, \"=Good, !=Cont, ^=Err\nR: #=A, \"=B, !=C, -=D, ^=Err")
        
    with c_mid:
        st.markdown(f'<div class="score-board">{st.session_state.score[0]} - {st.session_state.score[1]}</div>', unsafe_allow_html=True)
        st.markdown(f"<h3 style='text-align:center'>Phase: {st.session_state.phase}</h3>", unsafe_allow_html=True)
        # 簡易スコア操作
        c1, c2 = st.columns(2)
        if c1.button("↑ My Pt (+1)"):
            st.session_state.score[0] += 1; st.session_state.phase = 'S'; rotate_team(); st.rerun()
        if c2.button("↓ Op Pt (+1)"):
            st.session_state.score[1] += 1; st.session_state.phase = 'R'; st.rerun()

    with c_right:
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

    st.markdown("---")

    # --- スカウティング入力エリア ---
    col_map, col_cmd = st.columns([1, 1.5])
    
    # 1. マップ (Start/End)
    with col_map:
        st.markdown("##### Map Click (Start -> End)")
        court_img = create_court_img(st.session_state.points)
        val = streamlit_image_coordinates(court_img, key="main_court", width=300, height=600)
        
        if val:
            p = (val['x'], val['y'])
            if not st.session_state.points or st.session_state.points[-1] != p:
                if len(st.session_state.points) < 2:
                    st.session_state.points.append(p)
                    st.rerun()
                else:
                    st.session_state.points = [p]
                    st.rerun()
        
        msg = "Startをタップ" if len(st.session_state.points)==0 else ("Endをタップ" if len(st.session_state.points)==1 else "OK")
        st.caption(f"Status: {msg}")

    # 2. キーボード入力エリア (Wizard)
    with col_cmd:
        st.markdown('<div class="input-area">', unsafe_allow_html=True)
        
        # --- Step 0: Time ---
        if st.session_state.scout_step == 0:
            st.markdown("##### 1. Time Input")
            st.write("例: 0513 -> 05:13")
            def time_submit():
                t = format_time(st.session_state.in_time)
                st.session_state.current_input_data['time'] = t
                st.session_state.scout_step = 1 # Next
            st.text_input("Time", key="in_time", on_change=time_submit)
            
        # --- Step 1: Skill ---
        elif st.session_state.scout_step == 1:
            st.markdown("##### 2. Select Skill")
            skills = {"1": "S (Serve)", "2": "R (Reception)", "3": "A (Attack)", "4": "B (Block)", "5": "D (Dig)", "6": "E (Set)"}
            for k,v in skills.items(): st.write(f"**{k}**: {v}")
            
            def skill_submit():
                val = st.session_state.in_skill
                s_map = {"1":"S", "2":"R", "3":"A", "4":"B", "5":"D", "6":"E"}
                if val in s_map:
                    skill = s_map[val]
                    st.session_state.current_input_data['skill'] = skill
                    
                    # サーバー自動選択ロジック
                    if skill == 'S':
                        st.session_state.current_input_data['player'] = st.session_state.rotation[0]
                        st.session_state.current_input_data['setter'] = ""
                        st.session_state.current_input_data['combo'] = ""
                        st.session_state.scout_step = 4 # Mapへスキップ
                    elif skill == 'A':
                        st.session_state.scout_step = 2 # Player選択へ
                    else:
                        st.session_state.scout_step = 2
                
            st.text_input("Skill Number", key="in_skill", on_change=skill_submit)

        # --- Step 2: Player & Setter ---
        elif st.session_state.scout_step == 2:
            st.markdown("##### 3. Select Player")
            # 候補リスト (ローテ + リベロ)
            candidates = st.session_state.rotation + st.session_state.liberos
            for i, p in enumerate(candidates):
                st.write(f"**{i+1}**: {p}")
            
            def player_submit():
                try:
                    idx = int(st.session_state.in_player) - 1
                    if 0 <= idx < len(candidates):
                        st.session_state.current_input_data['player'] = candidates[idx]
                        if st.session_state.current_input_data['skill'] == 'A':
                            st.session_state.scout_step = 25 # Setter選択へ(便宜上25とする)
                        else:
                            st.session_state.scout_step = 4 # Mapへ
                except: pass
            st.text_input("Player Number", key="in_player", on_change=player_submit)

        # --- Step 2.5: Setter & Combo (Only for Attack) ---
        elif st.session_state.scout_step == 25:
            st.markdown("##### 3.5 Select Setter")
            # 頻度順セッターリスト
            all_members = st.session_state.rotation + st.session_state.liberos
            def sort_key(n): return st.session_state.setter_counts.get(n, 0)
            setters = sorted(all_members, key=sort_key, reverse=True) + ["Direct/Two"]
            
            for i, s in enumerate(setters): st.write(f"**{i+1}**: {s}")
            
            def setter_submit():
                try:
                    idx = int(st.session_state.in_setter) - 1
                    if 0 <= idx < len(setters):
                        s_name = setters[idx]
                        st.session_state.current_input_data['setter'] = s_name
                        # カウント更新
                        if s_name != "Direct/Two":
                            st.session_state.setter_counts[s_name] = st.session_state.setter_counts.get(s_name, 0) + 1
                        st.session_state.scout_step = 3 # Comboへ
                except: pass
            st.text_input("Setter Number", key="in_setter", on_change=setter_submit)

        elif st.session_state.scout_step == 3:
            st.markdown("##### 3.8 Input Combo")
            def combo_submit():
                st.session_state.current_input_data['combo'] = st.session_state.in_combo
                st.session_state.scout_step = 4
            st.text_input("Combo (e.g. X5, 1, A)", key="in_combo", on_change=combo_submit)

        # --- Step 4: Map Wait ---
        elif st.session_state.scout_step == 4:
            st.markdown("##### 4. Map Input")
            st.info("左のコート図を2回タップしてください (Start -> End)")
            if len(st.session_state.points) == 2:
                st.success("OK! Enterを押して進む")
                def map_done():
                    st.session_state.scout_step = 5
                st.text_input("Press Enter", key="map_wait", on_change=map_done)

        # --- Step 5: Quality & Save ---
        elif st.session_state.scout_step == 5:
            st.markdown("##### 5. Select Quality")
            
            # Qualityリスト
            qs = [
                {"key": "1", "val": "#", "desc": "Perfect / Point"},
                {"key": "2", "val": "\"", "desc": "Good / Effect"}, # Double quote
                {"key": "3", "val": "!", "desc": "OK / Continue"},
                {"key": "4", "val": "-", "desc": "Poor / Chance"},
                {"key": "5", "val": "^", "desc": "Error / Blocked"},
                {"key": "6", "val": "T", "desc": "BlockOut (Pt)"}
            ]
            
            # ボタンで表示 (Keyboard入力も可能にするためtext_inputも置くが、ボタンが早い)
            cols = st.columns(3)
            for i, q in enumerate(qs):
                if cols[i%3].button(f"{q['key']}. {q['val']} ({q['desc']})"):
                    # 登録処理
                    curr = st.session_state.current_input_data
                    
                    # 座標
                    if len(st.session_state.points) >= 1:
                        s_z = get_zone(st.session_state.points[0][0], st.session_state.points[0][1], 300, 600)
                        curr['start_zone'] = s_z
                    if len(st.session_state.points) >= 2:
                        e_z = get_zone(st.session_state.points[1][0], st.session_state.points[1][1], 300, 600)
                        curr['end_zone'] = e_z
                    
                    # データ構築
                    final_row = {
                        "set": st.session_state.set_name,
                        "score": f"{st.session_state.score[0]}-{st.session_state.score[1]}",
                        "phase": st.session_state.phase,
                        "setter": curr.get('setter', ''),
                        "player": curr.get('player', ''),
                        "skill": curr.get('skill', ''),
                        "combo": curr.get('combo', ''),
                        "quality": q['val'],
                        "start_zone": curr.get('start_zone', ''),
                        "end_zone": curr.get('end_zone', ''),
                        "memo": "",
                        "video_url": st.session_state.video_url,
                        "video_time": time_to_sec(curr.get('time', ''))
                    }
                    
                    st.session_state.data_log.append(final_row)
                    update_score(curr.get('skill'), q['val'])
                    
                    # リセット & Step 0に戻る
                    st.session_state.points = []
                    st.session_state.current_input_data = {}
                    st.session_state.scout_step = 0
                    st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)
        
        # キャンセルボタン
        if st.button("Reset Input (最初から)"):
            st.session_state.scout_step = 0
            st.session_state.current_input_data = {}
            st.session_state.points = []
            st.rerun()

    # --- データ出力 ---
    st.markdown("### Recorded Data")
    if len(st.session_state.data_log) > 0:
        df = pd.DataFrame(st.session_state.data_log)
        st.dataframe(df.iloc[::-1], height=200) # 新しい順
        
        if st.button("FINISH (Download)"):
            # Excel
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False)
            st.download_button("Download Excel", buf.getvalue(), "scout.xlsx")
