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

# --- [기존 시스템 설정 유지] ---
ANALYSIS_LOG_FILE, BACKUP_KRX_FILE = "analysis_log_v5.json", "backup_krx.json"
MONITOR_FILE = "monitoring_v5.json"

def load_data(file_path, default_val):
    try:
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f: return json.load(f)
    except: pass
    return default_val

def save_data(file_path, data):
    with open(file_path, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=4)

@st.cache_data(ttl=600)
def get_krx_list_ultimate():
    try:
        df = fdr.StockListing('KRX')
        if df is not None and not df.empty:
            df[['Code', 'Name']].to_json(BACKUP_KRX_FILE)
            st.session_state.list_source = "✅ 실시간 KRX 데이터"
            return df[['Code', 'Name']]
    except: pass
    if os.path.exists(BACKUP_KRX_FILE):
        st.session_state.list_source = "⚠️ 서버 지연 (백업 리스트)"
        return pd.read_json(BACKUP_KRX_FILE)
    return pd.DataFrame([{"Code": "005930", "Name": "삼성전자"}])

# --- [앱 초기화 및 세션 상태 격리] ---
st.set_page_config(page_title="MSM Phoenix v5.9.42", layout="wide")

if "auth" not in st.session_state: st.session_state.auth = False
if "auto_code" not in st.session_state: st.session_state.auto_code = ""
if "curr_source" not in st.session_state: st.session_state.curr_source = "미정"
if "list_source" not in st.session_state: st.session_state.list_source = "확인 중"
# [독립성] 스캔 결과 보존용 세션
if "scan_storage" not in st.session_state: st.session_state.scan_storage = []

if not st.session_state.auth:
    st.title("🔥 Phoenix Hybrid v5.9.42")
    pwd = st.text_input("Access Key", type="password", key="entry_pwd")
    if pwd == "1234": st.session_state.auth = True; st.rerun()
    st.stop()

krx_df = get_krx_list_ultimate()
krx_df['Display'] = krx_df['Code'] + " | " + krx_df['Name']
mon_stocks = load_data(MONITOR_FILE, [])

# --- [통합 분석 엔진: v5.9.39 엄격 기준 유지] ---
def analyze_v5_engine(ticker, target_date):
    df = None
    try:
        df = fdr.DataReader(ticker, target_date - datetime.timedelta(days=150), target_date)
        if df is not None and not df.empty:
            st.session_state.curr_source = "KRX (정상)"
            df.columns = [c.upper() for c in df.columns]
            df = df.rename(columns={'시가':'OPEN','고가':'HIGH','저가':'LOW','종가':'CLOSE','거래량':'VOLUME'})
    except: pass

    if df is None or df.empty:
        try:
            yf_ticker = f"{ticker}.KS" if ticker.startswith('0') or ticker.startswith('1') else f"{ticker}.KQ"
            df_yf = yf.download(yf_ticker, start=target_date - datetime.timedelta(days=150), end=target_date + datetime.timedelta(days=1), progress=False)
            if not df_yf.empty:
                df = df_yf[['Open', 'High', 'Low', 'Close', 'Volume']]
                df.columns = ['OPEN', 'HIGH', 'LOW', 'CLOSE', 'VOLUME']
                st.session_state.curr_source = "yfinance (우회)"
        except: pass

    if df is None or df.empty: return None, None
    
    df['BODY_RATIO'] = (df['CLOSE'] - df['OPEN']).abs() / (df['HIGH'] - df['LOW'] + 1)
    df['VOL_MA'] = df['VOLUME'].rolling(20).mean()
    curr = df.iloc[-1]
    
    # 승현님의 엄격 기준 (몸통 0.7 / 거래량 5배 / CV 1.8)
    is_orig_buy = (curr['CLOSE'] > curr['OPEN']) and (curr['BODY_RATIO'] >= 0.7) and (curr['VOLUME'] >= curr['VOL_MA'] * 5)
    pre_20 = df.iloc[-21:-1]
    cv = (pre_20['CLOSE'].std() / pre_20['CLOSE'].mean()) * 100
    vol_ratio = curr['VOLUME'] / (pre_20['VOLUME'].mean() + 1)
    similarity = ((max(0, 100 - (abs(cv - 1.8) * 25))) * 0.5) + ((min(100, (vol_ratio / 10.0) * 100)) * 0.5)
    
    tag, color, is_valid = ("🟡 관망", "grey", False)
    if similarity >= 75:
        if similarity >= 85 and is_orig_buy: tag, color, is_valid = ("💎 필승합의", "red", True)
        elif similarity >= 80: tag, color, is_valid = ("🚀 급등유력", "red", True)
        else: tag, color, is_valid = ("⚔️ 단기회전", "green", True)
    
    return {"code": ticker, "curr": int(curr['CLOSE']), "t_low": int(curr['LOW']), "stop": int(curr['LOW'] * 0.96), 
            "similarity": similarity, "is_orig_buy": is_orig_buy, "tag": tag, "color": color, 
            "is_valid": is_valid, "cv": cv, "vol_ratio": vol_ratio, "body": curr['BODY_RATIO']}, df

# --- [UI 레이아웃] ---
st.sidebar.title("🔥 Phoenix Log")
# (로그 리스트 출력 생략)

# [복구] 데이터 사용 중 표시 창
st.info(f"🛰️ 리스트: {st.session_state.list_source} | 📡 서버: {st.session_state.curr_source}")

with st.container(border=True):
    c1, c2, c3 = st.columns([4, 1.5, 2])
    search_input = c1.selectbox("종목 검색", krx_df['Display'].tolist(), index=None, key="main_search")
    c2.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
    btn_click = c2.button("🔍 분석 실행", type="primary", width='stretch')
    d_input = c3.date_input("분석 기준일 (과거 학습)", value=datetime.date.today())

    target_code = ""
    if search_input: target_code = search_input.split(" | ")[0]
    elif st.session_state.auto_code: target_code = st.session_state.auto_code

    if btn_click or (target_code != ""):
        # [개별분석] 선택한 d_input 날짜 사용
        res, df = analyze_v5_engine(target_code, d_input)
        if res:
            st.markdown(f"#### 🎯 분석 판정: :{res['color']}[{res['tag']}]")
            # [차트] 휴일 제거 및 기준선 복구
            fig = go.Figure(data=[go.Candlestick(x=df.index, open=df['OPEN'], high=df['HIGH'], low=df['LOW'], close=df['CLOSE'], increasing_line_color='red', decreasing_line_color='blue')])
            fig.add_hline(y=res['t_low'], line_dash="dash", line_color="green", annotation_text="기준봉 저가")
            fig.add_hline(y=res['stop'], line_color="#BF40BF", line_width=2, annotation_text="손절라인(-4%)")
            fig.update_xaxes(type='category', nticks=10) 
            fig.update_layout(height=350, xaxis_rangeslider_visible=False, template="plotly_dark", margin=dict(l=5, r=5, t=5, b=5), dragmode=False)
            st.plotly_chart(fig, width='stretch', config={'staticPlot': True})

st.divider()
st.subheader("📡 Phoenix Independent Scanner (Today)")

# [스캔 독립성] 상단 분석과 상관없이 버튼 클릭 시 오늘 날짜로 실행
if st.button("🚀 실시간 전수 스캔 (언제든 가능)", width='stretch'):
    st.session_state.scan_storage = []
    codes = krx_df.head(500)['Code'].tolist()
    prog_bar = st.progress(0)
    today_val = datetime.date.today()
    
    for i, code in enumerate(codes):
        # 스캐너는 무조건 오늘 데이터 사용
        r, _ = analyze_v5_engine(code, today_val)
        if r and r['is_valid']:
            st.session_state.scan_storage.append(r)
        prog_bar.progress((i + 1) / 500)
    st.rerun()

if st.session_state.scan_storage:
    st.info(f"📊 스캔 결과 ({len(st.session_state.scan_storage)}개)")
    st.dataframe(pd.DataFrame(st.session_state.scan_storage).sort_values(by='similarity', ascending=False), width='stretch')
