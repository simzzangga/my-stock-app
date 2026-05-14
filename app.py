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
import threading
import requests
from streamlit.runtime.scriptrunner import add_script_run_ctx

# --- [1. 데이터 이중화 및 삼중 방어 리스트 시스템] ---
LOG_FILE, MONITOR_FILE = "trade_v5_log.json", "monitoring_v5.json"
ANALYSIS_LOG_FILE, BACKUP_KRX_FILE = "analysis_log_v5.json", "backup_krx.json"

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
            df_cleaned = df[['Code', 'Name']]
            df_cleaned.to_json(BACKUP_KRX_FILE)
            st.session_state.list_source = "✅ 실시간 KRX 데이터"
            st.session_state.last_backup = datetime.datetime.now().strftime("%H:%M")
            return df_cleaned
    except: pass
    if os.path.exists(BACKUP_KRX_FILE):
        st.session_state.list_source = "⚠️ KRX 장애 (백업 리스트)"
        return pd.read_json(BACKUP_KRX_FILE)
    return pd.DataFrame([{"Code": "005930", "Name": "삼성전자"}])

# --- [2. 앱 설정 및 세션 초기화] ---
st.set_page_config(page_title="MSM Phoenix Hybrid v5.9.35", layout="wide")

if "auth" not in st.session_state: st.session_state.auth = False
if "auto_code" not in st.session_state: st.session_state.auto_code = ""
if "scan_status" not in st.session_state: st.session_state.scan_status = "대기"
if "scan_progress" not in st.session_state: st.session_state.scan_progress = 0
if "scan_results" not in st.session_state: st.session_state.scan_results = []
if "curr_source" not in st.session_state: st.session_state.curr_source = "미정"
if "list_source" not in st.session_state: st.session_state.list_source = "확인 중"
if "last_backup" not in st.session_state: st.session_state.last_backup = "-"

if not st.session_state.auth:
    st.title("🔥 Phoenix Hybrid v5.9.35")
    pwd = st.text_input("Access Key", type="password", key="entry_pwd")
    if pwd == "1234": st.session_state.auth = True; st.rerun()
    st.stop()

krx_df = get_krx_list_ultimate()
# [디테일] 검색창 자동완성 편의를 위한 '코드 | 이름' 리스트
krx_df['Display'] = krx_df['Code'] + " | " + krx_df['Name']
mon_stocks = load_data(MONITOR_FILE, [])
ST_PARAMS = {"target_cv": 1.8, "target_vol": 10.0}

# --- [3. 분석 엔진: 컬럼명 불일치 에러(KeyError) 완벽 방어] ---
def analyze_v5_hybrid(ticker, base_date):
    df = None
    try:
        df = fdr.DataReader(ticker, base_date - datetime.timedelta(days=120), base_date)
        if df is not None and not df.empty:
            st.session_state.curr_source = "KRX (정상)"
            # [디테일] 어떤 언어로 들어오든 엔진용 영문 표준으로 강제 맵핑
            df.columns = [c.upper() for c in df.columns]
            rename_map = {'시가': 'OPEN', '고가': 'HIGH', '저가': 'LOW', '종가': 'CLOSE', '거래량': 'VOLUME'}
            df = df.rename(columns=rename_map)
    except: pass

    if df is None or df.empty:
        try:
            yf_ticker = f"{ticker}.KS" if ticker.startswith('0') or ticker.startswith('1') else f"{ticker}.KQ"
            df_yf = yf.download(yf_ticker, start=base_date - datetime.timedelta(days=120), end=base_date, progress=False)
            if not df_yf.empty:
                df = df_yf[['Open', 'High', 'Low', 'Close', 'Volume']]
                df.columns = ['OPEN', 'HIGH', 'LOW', 'CLOSE', 'VOLUME']
                st.session_state.curr_source = "yfinance (우회)"
        except: pass

    if df is None or df.empty: return None, None
    
    # 엔진 로직 (모두 영문 대문자 컬럼 사용)
    df['BODY_RATIO'] = (df['CLOSE'] - df['OPEN']).abs() / (df['HIGH'] - df['LOW'] + 1)
    df['VOL_MA'] = df['VOLUME'].rolling(20).mean()
    curr = df.iloc[-1]
    is_orig_buy = (curr['CLOSE'] > curr['OPEN']) and (curr['BODY_RATIO'] > 0.7) and (curr['VOLUME'] > curr['VOL_MA'] * 5)
    pre_20 = df.iloc[-21:-1]
    cv = (pre_20['CLOSE'].std() / pre_20['CLOSE'].mean()) * 100
    vol_ratio = curr['VOLUME'] / (pre_20['VOLUME'].mean() + 1)
    similarity = ((max(0, 100 - (abs(cv - ST_PARAMS['target_cv']) * 25))) * 0.5) + ((min(100, (vol_ratio / ST_PARAMS['target_vol']) * 100)) * 0.5)
    
    if similarity >= 75:
        step = "1차" if ticker not in [s['code'] for s in mon_stocks] else "추가"
        tag, color, is_valid = (f"💎 필승합의 ({step})", "red", True) if similarity >= 85 and is_orig_buy else (f"🚀 급등유력 ({step})", "red", True) if similarity >= 80 else (f"⚔️ 단기회전 ({step})", "green", True)
    else: tag, color, is_valid = "🟡 관망", "grey", False
    
    return {"code": ticker, "curr": int(curr['CLOSE']), "t_low": int(curr['LOW']), "stop": int(curr['LOW'] * 0.96), 
            "similarity": similarity, "is_orig_buy": is_orig_buy, "tag": tag, "color": color, 
            "is_valid": is_valid, "cv": cv, "vol_ratio": vol_ratio, "body": curr['BODY_RATIO']}, df

def run_stable_scanner(codes, current_date):
    results = []
    total = len(codes)
    start_time = time.time()
    for i, code in enumerate(codes):
        try:
            st.session_state.scan_progress = int(((i + 1) / total) * 100)
            st.session_state.scan_status = f"분석 중: {i+1}/{total}"
            r, _ = analyze_v5_hybrid(code, current_date)
            if r and r['is_valid']: results.append(r)
            time.sleep(0.3)
        except: continue
    st.session_state.scan_results = sorted(results, key=lambda x: x['similarity'], reverse=True)
    st.session_state.scan_status = "완료"

# --- [4. UI 레이아웃: 모든 디테일 통합] ---
st.sidebar.title("🔥 Phoenix Log (Max 40)")
analysis_log = load_data(ANALYSIS_LOG_FILE, [])
for idx, log in enumerate(analysis_log[:40]):
    if st.sidebar.button(f"{log['name']} ({log['code']})", key=f"side_{idx}", use_container_width=True):
        st.session_state.auto_code = log['code']; st.rerun()

b1, b2 = st.columns([6, 1])
with b1: st.info(f"🛰️ 리스트: {st.session_state.list_source} ({st.session_state.last_backup}) | 📡 분석 서버: {st.session_state.curr_source}")
with b2:
    if st.button("💾 외출전 백업", use_container_width=True):
        get_krx_list_ultimate.clear(); get_krx_list_ultimate(); st.toast("백업 완료!")

with st.container(border=True):
    c1, c2, c3 = st.columns([4, 1.5, 2])
    # [디테일] 검색창 리스트를 '코드 | 이름'으로 표시
    search_input = c1.selectbox("종목 검색 (코드 또는 이름)", krx_df['Display'].tolist(), index=None, placeholder="코드 또는 이름 입력", key="main_search")
    c2.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
    btn_click = c2.button("🔍 분석 실행", type="primary", use_container_width=True)
    d_input = c3.date_input("분석 기준일", value=datetime.date.today())

    target_code = ""
    if search_input: target_code = search_input.split(" | ")[0] # 코드 부분만 추출
    elif st.session_state.auto_code: target_code = st.session_state.auto_code

    if btn_click or (target_code != ""):
        res, df = analyze_v5_hybrid(target_code, d_input)
        if res:
            disp_name = krx_df[krx_df['Code'] == target_code]['Name'].values[0] if target_code in krx_df['Code'].values else target_code
            temp_log = [l for l in load_data(ANALYSIS_LOG_FILE, []) if l['code'] != target_code]
            temp_log.insert(0, {"name": disp_name, "code": target_code}); save_data(ANALYSIS_LOG_FILE, temp_log[:40])
            st.markdown(f"#### 🎯 {disp_name} ({target_code}) 판정: :{res['color']}[{res['tag']}]")
            pc1, pc2, pc3 = st.columns(3); pc1.metric("유사도", f"{res['similarity']:.1f}%"); pc2.metric("현재가", f"{res['curr']:,}원"); pc3.metric("🔥 마지노선", f"{res['stop']:,}원")
            fig = go.Figure(data=[go.Candlestick(x=df.index, open=df['OPEN'], high=df['HIGH'], low=df['LOW'], close=df['CLOSE'], increasing_line_color='red', decreasing_line_color='blue')])
            fig.add_hline(y=res['t_low'], line_dash="dash", line_color="green", annotation_text="기준")
            fig.add_hline(y=res['stop'], line_color="#BF40BF", line_width=2, annotation_text="손절선")
            fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
            fig.update_layout(height=400, xaxis_rangeslider_visible=False, template="plotly_dark", margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig, use_container_width=True)
            with st.container(border=True):
                st.markdown("#### 📝 AI 상세 분석 및 예측 리포트")
                r1, r2 = st.columns(2)
                with r1:
                    st.caption(f"- 기존 엔진: {'🚀 매수 적합' if res['is_orig_buy'] else '🟡 수급 대기'} (몸통 {res['body']:.1%}, 거래량 {res['vol_ratio']:.1f}배)")
                    st.caption(f"- 가속도 엔진: 유사도 {res['similarity']:.1f}% (응축도 CV {res['cv']:.2f})")
                with r2:
                    st.caption(f"- **전략**: 10일 내 10% 수익 (20일 시한부)")
                    st.caption(f"- **데이터**: {st.session_state.curr_source} 서버 기반 분석됨")

st.divider()
st.subheader("📡 Phoenix High-Speed Scanner (Top 500)")
sc1, sc2 = st.columns([1, 4])
if sc1.button("🚀 스캔 시작", use_container_width=True):
    if not krx_df.empty:
        st.session_state.scan_results = []
        st.session_state.scan_status = "분석 중..."
        codes = krx_df.head(500)['Code'].tolist()
        t = threading.Thread(target=run_stable_scanner, args=(codes, datetime.date.today()))
        add_script_run_ctx(t)
        t.start()
with sc2:
    if st.session_state.scan_status != "완료" and st.session_state.scan_status != "대기":
        st.progress(st.session_state.scan_progress / 100)
        st.write(f"📊 {st.session_state.scan_status}")
