import streamlit as st
import FinanceDataReader as fdr
import yfina nce as yf
import pandas as pd
import numpy as np
import datetime
import json
import os
import plotly.graph_objects as go
import time

# --- [1. 시스템 설정 및 데이터 로드] ---
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

# --- [2. 앱 초기화 및 세션 요새화] ---
st.set_page_config(page_title="MSM Phoenix v5.9.44", layout="wide")

if "auth" not in st.session_state: st.session_state.auth = False
if "auto_code" not in st.session_state: st.session_state.auto_code = ""
if "curr_source" not in st.session_state: st.session_state.curr_source = "연결 대기"
if "scan_storage" not in st.session_state: st.session_state.scan_storage = []

if not st.session_state.auth:
    st.title("🔥 Phoenix Hybrid v5.9.44")
    pwd = st.text_input("Access Key", type="password", key="entry_pwd")
    if pwd == "1234": st.session_state.auth = True; st.rerun()
    st.stop()

krx_df = get_krx_list_ultimate()
krx_df['Display'] = krx_df['Code'] + " | " + krx_df['Name']

# --- [3. 엔진: 무결성 데이터 처리 및 엄격 기준] ---
def analyze_v5_engine(ticker, target_date):
    df = None
    try:
        df = fdr.DataReader(ticker, target_date - datetime.timedelta(days=160), target_date)
        if df is not None and not df.empty:
            st.session_state.curr_source = "KRX (정상)"
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
                # KeyError 방지를 위한 명시적 컬럼 선택
                df = df[['OPEN', 'HIGH', 'LOW', 'CLOSE', 'VOLUME']]
                st.session_state.curr_source = "yfinance (우회)"
        except: pass

    if df is None or df.empty or 'CLOSE' not in df.columns: return None, None
    
    # [디테일] 엄격한 수치 (몸통 0.7 / 거래량 5배 / CV 1.8)
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

# --- [4. UI: 로그 및 상단 배너] ---
st.sidebar.title("🔥 Phoenix Log")
analysis_log = load_data(ANALYSIS_LOG_FILE, [])
for idx, log in enumerate(analysis_log[:40]):
    if st.sidebar.button(f"{log['name']} ({log['code']})", key=f"side_{idx}", width='stretch'):
        st.session_state.auto_code = log['code']; st.rerun()

st.info(f"🛰️ 리스트: {st.session_state.list_source} | 📡 서버: {st.session_state.curr_source}")

with st.container(border=True):
    c1, c2, c3 = st.columns([4, 1.5, 2])
    search_input = c1.selectbox("종목 검색", krx_df['Display'].tolist(), index=None, key="main_search")
    c2.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
    btn_click = c2.button("🔍 분석 실행", type="primary", width='stretch')
    d_input = c3.date_input("분석 기준일 (학습용)", value=datetime.date.today())

    target_code = ""
    if search_input: target_code = search_input.split(" | ")[0]
    elif st.session_state.auto_code: target_code = st.session_state.auto_code

    if btn_click or (target_code != ""):
        res, df = analyze_v5_engine(target_code, d_input)
        if res:
            disp_name = krx_df[krx_df['Code'] == target_code]['Name'].values[0] if target_code in krx_df['Code'].values else target_code
            # 로그 업데이트
            temp_log = [l for l in load_data(ANALYSIS_LOG_FILE, []) if l['code'] != target_code]
            temp_log.insert(0, {"name": disp_name, "code": target_code}); save_data(ANALYSIS_LOG_FILE, temp_log[:40])
            
            st.markdown(f"#### 🎯 {disp_name} ({target_code}) 판정: :{res['color']}[{res['tag']}]")
            
            # [차트 디테일] 휴일제거 / 기준선 / 날짜간소화 / 이미지고정
            fig = go.Figure(data=[go.Candlestick(
                x=df.index.strftime('%m-%d'), 
                open=df['OPEN'], high=df['HIGH'], low=df['LOW'], close=df['CLOSE'], 
                increasing_line_color='red', decreasing_line_color='blue'
            )])
            fig.add_hline(y=res['t_low'], line_dash="dash", line_color="green", annotation_text="기준")
            fig.add_hline(y=res['stop'], line_color="#BF40BF", line_width=2, annotation_text="손절")
            fig.update_xaxes(type='category', nticks=10) 
            fig.update_layout(height=350, xaxis_rangeslider_visible=False, template="plotly_dark", margin=dict(l=5, r=5, t=5, b=5), dragmode=False)
            st.plotly_chart(fig, width='stretch', config={'staticPlot': True})

            with st.container(border=True):
                st.markdown("#### 📝 AI 심층 수치 리포트")
                r1, r2 = st.columns(2)
                with r1:
                    st.write("**📊 기존 수급 엔진**")
                    st.caption(f"- 거래량 강도: {res['vol_ratio']:.2f}배")
                    st.caption(f"- 캔들 장악력(몸통): {res['body']:.1%}")
                with r2:
                    st.write("**📉 가속도 정밀 엔진**")
                    st.caption(f"- 응축도(CV): {res['cv']:.4f}")
                    st.caption(f"- 패턴 유사도: {res['similarity']:.2f}%")

st.divider()
st.subheader("📡 Phoenix Independent Scanner (Today)")

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
    st.info(f"📊 실시간 스캔 결과 ({len(st.session_state.scan_storage)}개 포착)")
    st.dataframe(pd.DataFrame(st.session_state.scan_storage).sort_values(by='similarity', ascending=False), width='stretch')
