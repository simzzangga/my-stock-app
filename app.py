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

# --- [1. 시스템 설정 및 데이터 영속성] ---
if "scan_storage" not in st.session_state: st.session_state.scan_storage = []
if "auto_code" not in st.session_state: st.session_state.auto_code = ""

ANALYSIS_LOG_FILE, BACKUP_KRX_FILE = "analysis_log_v5.json", "backup_krx.json"

@st.cache_data(ttl=300)
def get_krx_list_ultimate():
    if os.path.exists(BACKUP_KRX_FILE):
        try:
            df_l = pd.read_json(BACKUP_KRX_FILE)
            if not df_l.empty: return df_l
        except: pass
    try:
        df = fdr.StockListing('KRX')
        if df is not None and not df.empty:
            df[['Code', 'Name']].to_json(BACKUP_KRX_FILE)
            return df[['Code', 'Name']]
    except: pass
    return pd.DataFrame([{"Code": "005930", "Name": "삼성전자"}])

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

# --- [2. 엔진: 데이터 기반 동적 수익률 및 단계별 전략 (v5.9.64)] ---
def analyze_v5_engine(ticker, target_date):
    df = None
    try:
        df = fdr.DataReader(ticker, target_date - datetime.timedelta(days=160), target_date)
        if df is not None and not df.empty:
            df.columns = [c.upper() for c in df.columns]
            df = df.rename(columns={'시가':'OPEN','고가':'HIGH','저가':'LOW','종가':'CLOSE','거래량':'VOLUME'})
    except: pass

    if df is None or df.empty:
        try:
            yf_ticker = f"{ticker}.KS" if ticker.startswith('0') or ticker.startswith('1') else f"{ticker}.KQ"
            df_yf = yf.download(yf_ticker, start=target_date - datetime.timedelta(days=200), end=target_date + datetime.timedelta(days=1), progress=False)
            if not df_yf.empty:
                if isinstance(df_yf.columns, pd.MultiIndex): df_yf.columns = df_yf.columns.get_level_values(0)
                df_yf.columns = [c.upper() for c in df_yf.columns]
                df = df_yf.rename(columns={'ADJ CLOSE': 'CLOSE'})[['OPEN', 'HIGH', 'LOW', 'CLOSE', 'VOLUME']]
        except: pass

    if df is None or df.empty: return None, None
    
    # 지표 산출
    df['BODY_RATIO'] = (df['CLOSE'] - df['OPEN']).abs() / (df['HIGH'] - df['LOW'] + 0.001)
    df['VOL_MA'] = df['VOLUME'].rolling(20).mean()
    curr = df.iloc[-1]
    vol_ratio = curr['VOLUME'] / (df['VOLUME'].iloc[-21:-1].mean() + 1)
    pre_20 = df.iloc[-21:-1]
    cv = (pre_20['CLOSE'].std() / pre_20['CLOSE'].mean()) * 100
    similarity = ((max(0, 100 - (abs(cv - 1.8) * 20))) * 0.3) + ((min(100, (vol_ratio / 5.0) * 100)) * 0.7)
    
    # 동적 수익률 매트릭스 (수급강도 비중 강화)
    raw_exp = (vol_ratio * 2.5) + (similarity * 0.1)
    
    phase, weight_now, exp_profit, color = "🟡 관망", 0, 0, "grey"
    
    # 3차: 강력 (수급 5배↑ + 유사도 85↑ + 몸통 0.7↑)
    if similarity >= 85 and vol_ratio >= 5.0 and curr['BODY_RATIO'] >= 0.7:
        phase, weight_now, exp_profit, color = "🔥 3차: 강력매수", 50, round(raw_exp + 5.0 - 2.0, 2), "red"
    # 2차: 보통 (수급 4배↑ + 유사도 78↑)
    elif similarity >= 78 and vol_ratio >= 4.0:
        phase, weight_now, exp_profit, color = "🚀 2차: 추가매수", 30, round(raw_exp - 2.0, 2), "orange"
    # 1차: 초기 (수급 3배↑ + 유사도 70↑)
    elif similarity >= 70 and vol_ratio >= 3.0:
        phase, weight_now, exp_profit, color = "⚔️ 1차: 신규진입", 20, round(max(8.0, raw_exp * 0.8) - 2.0, 2), "green"
    
    target_price = int(curr['CLOSE'] * (1 + exp_profit/100))
    
    res = {
        "code": ticker, "curr": int(curr['CLOSE']), "t_low": int(curr['LOW']), "stop": int(curr['LOW'] * 0.96),
        "similarity": similarity, "tag": phase, "color": color, "vol_ratio": vol_ratio,
        "weight": weight_now, "exp_profit": exp_profit, "target_price": target_price,
        "is_valid": True if weight_now > 0 else False
    }
    return res, df

# --- [3. UI 및 메인 제어] ---
st.set_page_config(page_title="🔥 Phoenix Hybrid v5.9.64", layout="wide")
st.markdown("<h1 style='text-align: center; color: #FF4B4B;'>🔥 Phoenix Hybrid v5.9.64</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: #888;'>Premium Analysis for PM SHIM SEUNGHYUN</p>", unsafe_allow_html=True)

krx_df = get_krx_list_ultimate()
krx_df['Display'] = krx_df['Code'].astype(str) + " | " + krx_df['Name'].astype(str)

# 사이드바 (날짜 고정 종목 변경)
st.sidebar.title("📁 Phoenix History")
analysis_log = load_data(ANALYSIS_LOG_FILE, [])
for idx, log in enumerate(analysis_log[:40]):
    if st.sidebar.button(f"{log['name']} ({log['code']})", key=f"side_{idx}", width='stretch'):
        st.session_state.auto_code = log['code']; st.rerun()

with st.form("main_analysis_form", clear_on_submit=False):
    c1, c2, c3 = st.columns([4, 1.5, 2])
    def_idx = None
    if st.session_state.auto_code:
        matches = [i for i, x in enumerate(krx_df['Code']) if x == st.session_state.auto_code]
        if matches: def_idx = matches[0]
    search_input = c1.selectbox("종목 선택", krx_df['Display'].tolist(), index=def_idx)
    c2.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
    btn_click = c2.form_submit_button("🔍 Start", type="primary", use_container_width=True)
    d_input = c3.date_input("분석 날짜 지정", value=datetime.date.today())

if btn_click or (st.session_state.auto_code != ""):
    target_code = search_input.split(" | ")[0] if search_input else st.session_state.auto_code
    res, df = analyze_v5_engine(target_code, d_input)
    if res:
        disp_name = krx_df[krx_df['Code'] == target_code]['Name'].values[0]
        temp_log = [l for l in load_data(ANALYSIS_LOG_FILE, []) if l['code'] != target_code]
        temp_log.insert(0, {"name": disp_name, "code": target_code}); save_data(ANALYSIS_LOG_FILE, temp_log[:40])
        st.session_state.auto_code = ""
        
        st.markdown(f"### 🎯 [{disp_name}] 전략 리포트 ({d_input})")
        st.markdown(f"#### 📢 엔진 판정: :{res['color']}[{res['tag']}] (유사도 {res['similarity']:.2f}%)")
        
        fig = go.Figure(data=[go.Candlestick(x=df.index.strftime('%y-%m-%d'), open=df['OPEN'], high=df['HIGH'], low=df['LOW'], close=df['CLOSE'], increasing_line_color='red', decreasing_line_color='blue')])
        fig.add_hline(y=res['target_price'], line_dash="dot", line_color="orange", annotation_text=f"타겟({res['exp_profit']}%)")
        fig.add_hline(y=res['t_low'], line_dash="dash", line_color="green", annotation_text="기준점")
        fig.update_layout(height=450, xaxis_rangeslider_visible=False, template="plotly_dark")
        st.plotly_chart(fig, use_container_width=True)

        with st.container(border=True):
            st.markdown(f"### 📊 PM SHIM 전용: 동적 수익률 및 비중 리포트")
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"""
                **[1. 단계별 매수 전략]**
                * **현 시점 권장 비중**: **오늘 {res['weight']}% 진입**
                * **전략**: `{res['tag']}` 구간이므로 정해진 비중을 엄수하십시오.
                * **최종 매집**: 시그널 강화 시 3~5일 내 100% 완성.
                """)
            with col2:
                st.markdown(f"""
                **[2. 정밀 기대 수익 분석]**
                * **데이터 기반 수익률**: `{res['exp_profit']}%`
                * **자동 매도 타겟가**: `{res['target_price']:,}원`
                * **안전 마진**: 승현님의 원칙에 따라 2% 선차감 완료.
                """)
            st.markdown("---")
            st.markdown(f"**PM's Insight**: 본 종목은 수급 강도 `{res['vol_ratio']:.2f}배`를 바탕으로 상방 에너지가 응축된 상태입니다. `{res['stop']:,}원` 이탈 전까지 시나리오는 유지됩니다.")

st.divider()
if st.button("실시간 500개 종목 정밀 스캔 시작", width='stretch'):
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
