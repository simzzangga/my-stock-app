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

# --- [1. 초경량 시스템 설정 및 함수 복구] ---
if "scan_storage" not in st.session_state: st.session_state.scan_storage = []
if "auto_code" not in st.session_state: st.session_state.auto_code = ""
if "server_status" not in st.session_state: st.session_state.server_status = "🛰️ 엔진 예열 중"

ANALYSIS_LOG_FILE, BACKUP_KRX_FILE = "analysis_log_v5.json", "backup_krx.json"

# [복구 완료] 로그 저장/로드 함수
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
                st.session_state.server_status = "⚡ 초고속 로컬 모드 가동"
                return df_l
        except: pass
    try:
        df = fdr.StockListing('KRX')[['Code', 'Name']]
        df['Code'] = df['Code'].astype(str).str.zfill(6)
        df.to_json(BACKUP_KRX_FILE)
        st.session_state.server_status = "📡 KRX 서버 동기화 완료"
        return df
    except:
        return pd.DataFrame([{"Code": "005930", "Name": "삼성전자"}])

# --- [2. 엔진: 데이터 범위 최적화 (v5.9.68)] ---
def analyze_v5_engine(ticker, target_date):
    df = None
    ticker_str = str(ticker).zfill(6)
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
    
    # [v5.9.66 무결성 로직 동일 유지]
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
    integrity = 100 if (df.index[-1].date() >= target_date - datetime.timedelta(days=3)) else 60

    return {
        "code": ticker_str, "curr": int(curr['CLOSE']), "t_low": int(curr['LOW']), 
        "stop_final": stop_final, "stop_warning": stop_warning,
        "similarity": similarity, "tag": phase, "color": color, "vol_ratio": vol_ratio,
        "weight": weight_now, "exp_profit": exp_profit, "target_price": target_price,
        "integrity": integrity, "is_valid": True if weight_now > 0 else False
    }, df

# --- [3. UI 레이아웃 및 제어 센터] ---
st.set_page_config(page_title="🔥 Phoenix Hybrid v5.9.68", layout="wide")

c_head1, c_head2 = st.columns([6, 2])
with c_head1:
    st.markdown(f"### 🔥 Phoenix Hybrid v5.9.68 | `{st.session_state.server_status}`")
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
        disp_name = krx_df[krx_df['Code'] == res['code']]['Name'].values[0]
        temp_log = [l for l in load_data(ANALYSIS_LOG_FILE, []) if str(l['code']).zfill(6) != res['code']]
        temp_log.insert(0, {"name": disp_name, "code": res['code']}); save_data(ANALYSIS_LOG_FILE, temp_log[:40])
        st.session_state.auto_code = ""
        
        st.markdown(f"### 🎯 [{disp_name}] 전략 리포트")
        fig = go.Figure(data=[go.Candlestick(x=df.index.strftime('%y-%m-%d'), open=df['OPEN'], high=df['HIGH'], low=df['LOW'], close=df['CLOSE'], increasing_line_color='red', decreasing_line_color='blue')])
        fig.add_hline(y=res['target_price'], line_dash="dot", line_color="orange", annotation_text=f"타겟({res['exp_profit']}%)")
        fig.add_hline(y=res['stop_final'], line_dash="solid", line_color="red", line_width=2, annotation_text="손절(-5%)")
        fig.update_layout(height=450, xaxis_rangeslider_visible=False, template="plotly_dark")
        st.plotly_chart(fig, use_container_width=True)

        with st.container(border=True):
            col1, col2 = st.columns(2)
            with col1: st.markdown(f"**[비중]** 오늘 **{res['weight']}%** 진입 (`{res['tag']}`)")
            with col2: st.markdown(f"**[수익/손절]** 목표 `{res['target_price']:,}원` / 손절 `{res['stop_final']:,}원`")

st.divider()
if st.button("🚀 500개 종목 초정밀 스캔", width='stretch'):
    st.session_state.scan_storage = []
    codes = krx_df.head(500)['Code'].tolist()
    prog_bar = st.progress(0)
    for i, code in enumerate(codes):
        r, _ = analyze_v5_engine(code, datetime.date.today())
        if r and r['is_valid']: st.session_state.scan_storage.append(r)
        prog_bar.progress((i + 1) / 500)
    st.rerun()

if st.session_state.scan_storage:
    st.dataframe(pd.DataFrame(st.session_state.scan_storage).sort_values(by='similarity', ascending=False), use_container_width=True)
