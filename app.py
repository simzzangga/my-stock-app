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

# --- [1. 변수 선언 및 초기화 (최우선 순위)] ---
# 앱이 죽지 않도록 변수부터 무조건 생성합니다.
if "list_source" not in st.session_state: st.session_state.list_source = "⚠️ 연결 확인 중"
if "curr_source" not in st.session_state: st.session_state.curr_source = "📡 대기 중"
if "auth" not in st.session_state: st.session_state.auth = False
if "auto_code" not in st.session_state: st.session_state.auto_code = ""
if "scan_storage" not in st.session_state: st.session_state.scan_storage = []

ANALYSIS_LOG_FILE, BACKUP_KRX_FILE = "analysis_log_v5.json", "backup_krx.json"
MONITOR_FILE = "monitoring_v5.json"

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

@st.cache_data(ttl=300)
def get_krx_list_ultimate():
    # KRX 서버 에러(Service Unavailable) 발생 시 즉시 백업/우회로 전환
    try:
        df = fdr.StockListing('KRX')
        if df is not None and not df.empty:
            df[['Code', 'Name']].to_json(BACKUP_KRX_FILE)
            st.session_state.list_source = "✅ 실시간 KRX"
            return df[['Code', 'Name']]
    except: pass
    
    if os.path.exists(BACKUP_KRX_FILE):
        st.session_state.list_source = "⚠️ 로컬 백업 데이터"
        return pd.read_json(BACKUP_KRX_FILE)
    
    st.session_state.list_source = "❌ 서버 에러 (비상 모드)"
    return pd.DataFrame([{"Code": "005930", "Name": "삼성전자"}])

# --- [2. 앱 설정 및 보안] ---
st.set_page_config(page_title="MSM Phoenix v5.9.46", layout="wide")

if not st.session_state.auth:
    st.title("🔥 Phoenix Hybrid v5.9.46")
    pwd = st.text_input("Access Key", type="password", key="entry_pwd")
    if pwd == "1234": st.session_state.auth = True; st.rerun()
    st.stop()

# 리스트 로드 (실패해도 앱은 돌아감)
krx_df = get_krx_list_ultimate()
krx_df['Display'] = krx_df['Code'].astype(str) + " | " + krx_df['Name'].astype(str)

# --- [3. 엔진: 데이터 수집 및 엄격 분석] ---
def analyze_v5_engine(ticker, target_date):
    df = None
    try:
        df = fdr.DataReader(ticker, target_date - datetime.timedelta(days=160), target_date)
        if df is not None and not df.empty:
            st.session_state.curr_source = "KRX"
            df.columns = [c.upper() for c in df.columns]
            df = df.rename(columns={'시가':'OPEN','고가':'HIGH','저가':'LOW','종가':'CLOSE','거래량':'VOLUME'})
    except: pass

    if df is None or df.empty or 'CLOSE' not in df.columns:
        try:
            yf_ticker = f"{ticker}.KS" if ticker.startswith('0') or ticker.startswith('1') else f"{ticker}.KQ"
            df_yf = yf.download(yf_ticker, start=target_date - datetime.timedelta(days=160), end=target_date + datetime.timedelta(days=1), progress=False)
            if not df_yf.empty:
                df = df_yf.copy()
                if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                df.columns = [c.upper() for c in df.columns]
                if 'ADJ CLOSE' in df.columns: df = df.rename(columns={'ADJ CLOSE': 'CLOSE'})
                df = df[['OPEN', 'HIGH', 'LOW', 'CLOSE', 'VOLUME']]
                st.session_state.curr_source = "yfinance"
        except: pass

    if df is None or df.empty or 'CLOSE' not in df.columns: return None, None
    
    # [수치] 엄격 기준 (몸통 0.7 / 거래량 5배 / CV 1.8)
    df['BODY_RATIO'] = (df['CLOSE'] - df['OPEN']).abs() / (df['HIGH'] - df['LOW'] + 0.001)
    df['VOL_MA'] = df['VOLUME'].rolling(20).mean()
    curr = df.iloc[-1]
    
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

# --- [4. UI: 사이드바 및 정보창] ---
st.sidebar.title("🔥 Phoenix Log")
analysis_log = load_data(ANALYSIS_LOG_FILE, [])
for idx, log in enumerate(analysis_log[:40]):
    if st.sidebar.button(f"{log['name']} ({log['code']})", key=f"side_{idx}", width='stretch'):
        st.session_state.auto_code = log['code']; st.rerun()

# [중요] 변수가 초기화되었으므로 여기서 에러가 나지 않습니다.
st.info(f"🛰️ 리스트: {st.session_state.list_source} | 📡 서버: {st.session_state.curr_source}")

with st.container(border=True):
    c1, c2, c3 = st.columns([4, 1.5, 2])
    search_input = c1.selectbox("종목 검색", krx_df['Display'].tolist(), index=None, key="main_search")
    c2.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
    btn_click = c2.button("🔍 분석 실행", type="primary", width='stretch')
    d_input = c3.date_input("기준일", value=datetime.date.today())

    target_code = ""
    if search_input: target_code = search_input.split(" | ")[0]
    elif st.session_state.auto_code: target_code = st.session_state.auto_code

    if btn_click or (target_code != ""):
        res, df = analyze_v5_engine(target_code, d_input)
        if res:
            disp_name = krx_df[krx_df['Code'] == target_code]['Name'].values[0] if target_code in krx_df['Code'].values else target_code
            temp_log = [l for l in load_data(ANALYSIS_LOG_FILE, []) if l['code'] != target_code]
            temp_log.insert(0, {"name": disp_name, "code": target_code}); save_data(ANALYSIS_LOG_FILE, temp_log[:40])
            
            st.markdown(f"#### 🎯 {disp_name} 판정: :{res['color']}[{res['tag']}]")
            
            # [차트 디테일 보장]
            fig = go.Figure(data=[go.Candlestick(x=df.index.strftime('%m-%d'), open=df['OPEN'], high=df['HIGH'], low=df['LOW'], close=df['CLOSE'], increasing_line_color='red', decreasing_line_color='blue')])
            fig.add_hline(y=res['t_low'], line_dash="dash", line_color="green", annotation_text="기준")
            fig.add_hline(y=res['stop'], line_color="#BF40BF", line_width=2, annotation_text="손절")
            fig.update_xaxes(type='category', nticks=10) 
            fig.update_layout(height=350, xaxis_rangeslider_visible=False, template="plotly_dark", margin=dict(l=5, r=5, t=5, b=5), dragmode=False)
            st.plotly_chart(fig, width='stretch', config={'staticPlot': True})

            with st.container(border=True):
                st.markdown("#### 📝 AI 상세 리포트")
                r1, r2 = st.columns(2)
                with r1:
                    st.caption(f"- 거래량 강도: {res['vol_ratio']:.2f}배")
                    st.caption(f"- 캔들 몸통: {res['body']:.1%}")
                with r2:
                    st.caption(f"- 응축도(CV): {res['cv']:.4f}")
                    st.caption(f"- 유사도: {res['similarity']:.2f}%")

st.divider()
st.subheader("📡 Phoenix Scanner (Today)")

if st.button("🚀 실시간 전수 스캔", width='stretch'):
    st.session_state.scan_storage = []
    codes = krx_df.head(500)['Code'].tolist()
    prog_bar = st.progress(0)
    today_val = datetime.date.today()
    for i, code in enumerate(codes):
        r, _ = analyze_v5_engine(code, today_val)
        if r and r['is_valid']: st.session_state.scan_storage.append(r)
        prog_bar.progress((i + 1) / 500)
    st.rerun()

if st.session_state.scan_storage:
    st.info(f"📊 스캔 결과 ({len(st.session_state.scan_storage)}개 포착)")
    st.dataframe(pd.DataFrame(st.session_state.scan_storage).sort_values(by='similarity', ascending=False), width='stretch')
