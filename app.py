import streamlit as st
import FinanceDataReader as fdr
import yfinance as yf
import pandas as pd
import numpy as np
import datetime
import json
import os
import plotly.graph_objects as go
import time

# --- [1. 시스템 설정 및 영속성 함수] ---
SCAN_RESULT_FILE = "last_scan_results.json"
ANALYSIS_LOG_FILE, BACKUP_KRX_FILE = "analysis_log_v5.json", "backup_krx.json"

# 세션 상태 및 영속 데이터 복구 로직
if "scan_storage" not in st.session_state:
    if os.path.exists(SCAN_RESULT_FILE):
        try:
            with open(SCAN_RESULT_FILE, "r", encoding="utf-8") as f:
                st.session_state.scan_storage = json.load(f)
        except: st.session_state.scan_storage = []
    else: st.session_state.scan_storage = []

if "auto_code" not in st.session_state: st.session_state.auto_code = ""
if "server_status" not in st.session_state: st.session_state.server_status = "🛰️ 엔진 예열 중"

def load_data(file_path, default_val):
    try:
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f: return json.load(f)
    except: pass
    return default_val

def save_data(file_path, data):
    try:
        with open(file_path, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=4)
    except: pass

@st.cache_data(ttl=3600)
def get_krx_list_ultimate():
    if os.path.exists(BACKUP_KRX_FILE):
        try:
            df_l = pd.read_json(BACKUP_KRX_FILE)
            if not df_l.empty:
                st.session_state.server_status = "🔥 출격 준비 완료 (백업 모드)"
                return df_l
        except: pass
    try:
        # 경량화: 코드와 이름만 추출
        df = fdr.StockListing('KRX')[['Code', 'Name']]
        df['Code'] = df['Code'].astype(str).str.zfill(6)
        df.to_json(BACKUP_KRX_FILE)
        st.session_state.server_status = "🔥 출격 준비 완료 (시스템 정상)"
        return df
    except:
        return pd.DataFrame([{"Code": "005930", "Name": "삼성전자"}])

# --- [2. 엔진: v5.9.66 무결성 로직 보존] ---
def analyze_v5_engine(ticker, target_date):
    df = None
    ticker_str = str(ticker).zfill(6)
    # 데이터 다이어트: 패턴 분석용 240일(영업일 160일) 범위
    start_date = target_date - datetime.timedelta(days=240) 
    try:
        df = fdr.DataReader(ticker_str, start_date, target_date)
        if df is not None and not df.empty:
            df.columns = [c.upper() for c in df.columns]
            df = df.rename(columns={'시가':'OPEN','고가':'HIGH','저가':'LOW','종가':'CLOSE','거래량':'VOLUME'})
    except: pass

    if df is None or df.empty:
        try:
            yf_ticker = f"{ticker_str}.KS" if ticker_str.startswith(('0', '1')) else f"{ticker_str}.KQ"
            df_yf = yf.download(yf_ticker, start=start_date, end=target_date + datetime.timedelta(days=1), progress=False)
            if not df_yf.empty:
                if isinstance(df_yf.columns, pd.MultiIndex): df_yf.columns = df_yf.columns.get_level_values(0)
                df_yf.columns = [c.upper() for c in df_yf.columns]
                df = df_yf.rename(columns={'ADJ CLOSE': 'CLOSE'})[['OPEN', 'HIGH', 'LOW', 'CLOSE', 'VOLUME']]
        except: pass

    if df is None or df.empty: return None, None
    
    # 핵심 전투 로직 (손절 -3/-5, 비중 20/30/50 유지)
    df['BODY_RATIO'] = (df['CLOSE'] - df['OPEN']).abs() / (df['HIGH'] - df['LOW'] + 0.001)
    df['VOL_MA'] = df['VOLUME'].rolling(20).mean()
    curr = df.iloc[-1]
    vol_ratio = curr['VOLUME'] / (df['VOLUME'].iloc[-21:-1].mean() + 1)
    pre_20 = df.iloc[-21:-1]
    cv = (pre_20['CLOSE'].std() / pre_20['CLOSE'].mean()) * 100
    similarity = ((max(0, 100 - (abs(cv - 1.8) * 20))) * 0.3) + ((min(100, (vol_ratio / 5.0) * 100)) * 0.7)
    
    raw_exp = (vol_ratio * 2.5) + (similarity * 0.1)
    phase, weight_now, exp_profit, color = "🟡 관망", 0, 0, "grey"
    
    if similarity >= 85 and vol_ratio >= 5.0 and curr['BODY_RATIO'] >= 0.7:
        phase, weight_now, exp_profit, color = "🔥 3차: 강력매수", 50, round(raw_exp + 5.0 - 2.0, 2), "red"
    elif similarity >= 78 and vol_ratio >= 4.0:
        phase, weight_now, exp_profit, color = "🚀 2차: 추가매수", 30, round(raw_exp - 2.0, 2), "orange"
    elif similarity >= 70 and vol_ratio >= 3.0:
        phase, weight_now, exp_profit, color = "⚔️ 1차: 신규진입", 20, round(max(8.0, raw_exp * 0.8) - 2.0, 2), "green"
    
    target_price = int(curr['CLOSE'] * (1 + exp_profit/100))
    stop_warning = int(curr['CLOSE'] * 0.97) 
    stop_final = int(curr['CLOSE'] * 0.95)   
    
    return {
        "종목코드": ticker_str, "현재가": int(curr['CLOSE']), "유사도": round(similarity, 1),
        "상태": phase, "비중": f"{weight_now}%", "예상수익": f"{exp_profit}%",
        "목표가": target_price, "손절가(-5%)": stop_final, "거래량비": round(vol_ratio, 1),
        "is_valid": True if weight_now > 0 else False
    }, df

# --- [3. UI 레이아웃] ---
st.set_page_config(page_title="🔥 Phoenix Hybrid v5.9.70", layout="wide")

c_head1, c_head2 = st.columns([6, 2])
with c_head1:
    st.markdown(f"### 🔥 Phoenix Hybrid v5.9.70 | `{st.session_state.server_status}`")
with c_head2:
    if st.button("🔄 리스트 강제 동기화", use_container_width=True):
        if os.path.exists(BACKUP_KRX_FILE): os.remove(BACKUP_KRX_FILE)
        st.cache_data.clear(); st.rerun()

krx_df = get_krx_list_ultimate()
krx_df['Display'] = krx_df['Code'] + " | " + krx_df['Name']

st.sidebar.title("📁 Phoenix History")
analysis_log = load_data(ANALYSIS_LOG_FILE, [])
for idx, log in enumerate(analysis_log[:20]): 
    if st.sidebar.button(f"{log['name']} ({log['code']})", key=f"side_{idx}", width='stretch'):
        st.session_state.auto_code = log['code']; st.rerun()

with st.form("main_analysis_form", clear_on_submit=False):
    c1, c2, c3 = st.columns([4, 1.5, 2])
    def_idx = 0
    if st.session_state.auto_code:
        matches = [i for i, x in enumerate(krx_df['Code']) if x == str(st.session_state.auto_code).zfill(6)]
        if matches: def_idx = matches[0]
    search_input = c1.selectbox("종목 선택", krx_df['Display'].tolist(), index=def_idx)
    c2.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
    btn_click = c2.form_submit_button("🔍 초고속 분석", type="primary", use_container_width=True)
    d_input = c3.date_input("날짜 지정", value=datetime.date.today())

if btn_click or (st.session_state.auto_code != ""):
    target_code = search_input.split(" | ")[0] if search_input else st.session_state.auto_code
    res, df = analyze_v5_engine(target_code, d_input)
    if res:
        disp_name = krx_df[krx_df['Code'] == res['종목코드']]['Name'].values[0]
        temp_log = [l for l in load_data(ANALYSIS_LOG_FILE, []) if str(l['code']).zfill(6) != res['종목코드']]
        temp_log.insert(0, {"name": disp_name, "code": res['종목코드']}); save_data(ANALYSIS_LOG_FILE, temp_log[:40])
        st.session_state.auto_code = ""
        st.markdown(f"### 🎯 [{disp_name}] 전략 리포트")
        fig = go.Figure(data=[go.Candlestick(x=df.index.strftime('%y-%m-%d'), open=df['OPEN'], high=df['HIGH'], low=df['LOW'], close=df['CLOSE'], increasing_line_color='red', decreasing_line_color='blue')])
        fig.add_hline(y=res['목표가'], line_dash="dot", line_color="orange", annotation_text="목표가")
        fig.add_hline(y=res['손절가(-5%)'], line_dash="solid", line_color="red", line_width=2, annotation_text="손절선")
        fig.update_layout(height=450, xaxis_rangeslider_visible=False, template="plotly_dark")
        st.plotly_chart(fig, use_container_width=True)
        st.write(res)

st.divider()

# --- [4. 광역 스캐너 섹션 (1,000개 확장 및 정렬)] ---
col_scan1, col_scan2 = st.columns([6, 2])
with col_scan1:
    scan_btn = st.button("🚀 1,000개 종목 광역 정밀 스캔 (예상수익 순 정렬)", width='stretch')
with col_scan2:
    if st.button("📂 이전 결과 불러오기"): st.rerun()

if scan_btn:
    st.session_state.scan_storage = []
    target_count = 1000
    codes = krx_df.head(target_count)
    prog_bar = st.progress(0)
    status_text = st.empty()
    time_text = st.empty()
    
    start_time = time.time()
    for i, (idx, row) in enumerate(codes.iterrows()):
        curr_code, curr_name = row['Code'], row['Name']
        elapsed = time.time() - start_time
        avg_time = elapsed / (i + 1)
        rem_time = avg_time * (target_count - (i + 1))
        
        status_text.markdown(f"**광역 탐지 중:** `{curr_code}` ({curr_name}) | **진행:** `{i+1}/{target_count}`")
        time_text.markdown(f"⏱️ **남은 시간:** `{int(rem_time//60)}분 {int(rem_time%60)}초` (평균 {avg_time:.2f}초/건)")
        
        r, _ = analyze_v5_engine(curr_code, datetime.date.today())
        if r and r['is_valid']:
            r['종목명'] = curr_name
            st.session_state.scan_storage.append(r)
        prog_bar.progress((i + 1) / target_count)
    
    save_data(SCAN_RESULT_FILE, st.session_state.scan_storage)
    status_text.success(f"✅ 광역 스캔 완료! {len(st.session_state.scan_storage)}개 종목 포착")
    time_text.empty()
    st.rerun()

if st.session_state.scan_storage:
    st.markdown("### 📋 스캔 결과 리스트 (예상수익 높은 순)")
    scan_df = pd.DataFrame(st.session_state.scan_storage)
    
    # 예상수익 기반 정렬 로직 (v5.9.70 핵심 오더)
    scan_df['sort_val'] = scan_df['예상수익'].str.replace('%', '').astype(float)
    scan_df = scan_df.sort_values(by='sort_val', ascending=False).drop(columns=['sort_val'])
    
    cols = ['종목명', '종목코드', '상태', '비중', '현재가', '목표가', '손절가(-5%)', '예상수익', '유사도', '거래량비']
    st.dataframe(scan_df[cols], use_container_width=True)
