import streamlit as st
import FinanceDataReader as fdr
import pandas as pd
import numpy as np
import datetime
import json
import os
import plotly.graph_objects as go
import time
import threading

# --- [시스템] 데이터 저장/로드 ---
SEARCH_HISTORY_FILE = "search_history_v5.json"
ANALYSIS_LOG_FILE = "analysis_log_v5.json"
SCAN_FILE = "scan_results_v5.json"

def load_data(file_path, default_val):
    try:
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f: return json.load(f)
    except: pass
    return default_val

def save_data(file_path, data):
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

@st.cache_data(ttl=86400)
def get_krx_list():
    try:
        df = fdr.StockListing('KRX')
        return df[['Code', 'Name']]
    except: return pd.DataFrame(columns=['Code', 'Name'])

search_history = load_data(SEARCH_HISTORY_FILE, [])
analysis_log = load_data(ANALYSIS_LOG_FILE, [])
krx_df = get_krx_list()

ST_PARAMS = {"target_cv": 2.0, "target_vol": 8.0, "target_win": 0.91}

# --- 모바일 가독성을 위한 CSS 주입 ---
st.set_page_config(page_title="MSM AI v5.9.4", layout="wide")
st.markdown("""
    <style>
    .main .block-container {padding-top: 1rem; padding-bottom: 1rem;}
    .stMetric {background-color: #1e1e1e; padding: 10px; border-radius: 10px;}
    div[data-testid="stExpander"] {border: none !important;}
    button {height: 2.5rem !important;}
    p {font-size: 0.9rem !important;}
    </style>
    """, unsafe_allow_html=True)

if "auth" not in st.session_state: st.session_state.auth = False
if "auto_code" not in st.session_state: st.session_state.auto_code = ""
if "scan_progress" not in st.session_state: st.session_state.scan_progress = 0
if "scan_status" not in st.session_state: st.session_state.scan_status = "대기"
if "scan_results" not in st.session_state: st.session_state.scan_results = []

# --- 보안 설정 ---
if not st.session_state.auth:
    st.title("💰 MSM AI v5.9.4")
    pwd = st.text_input("Key", type="password", max_chars=4)
    if pwd == "1234": st.session_state.auth = True; st.rerun()
    st.stop()

# --- [사이드바] 모바일 대응 간소화 ---
st.sidebar.title("🔍 탐색")
if not krx_df.empty:
    selected_name = st.sidebar.selectbox("종목명/코드", krx_df['Name'].tolist(), index=None)
    if selected_name:
        target_code = krx_df[krx_df['Name'] == selected_name]['Code'].values[0]
        if st.sidebar.button("입력", use_container_width=True):
            st.session_state.auto_code = target_code
            search_history = [h for h in search_history if h['code'] != target_code]
            search_history.insert(0, {"name": selected_name, "code": target_code})
            save_data(SEARCH_HISTORY_FILE, search_history[:5]); st.rerun()

st.sidebar.caption("🕒 최근 검색")
for h in search_history[:5]:
    if st.sidebar.button(f"{h['name']}", key=f"side_{h['code']}", use_container_width=True):
        st.session_state.auto_code = h['code']; st.rerun()

# --- [분석 엔진] 로직 유지 ---
def analyze_v5(ticker, base_date):
    try:
        df = fdr.DataReader(ticker, base_date - datetime.timedelta(days=100), base_date)
        if df.empty or len(df) < 30: return None, None
        df.columns = [c.upper() for c in df.columns]
        df = df.rename(columns={'OPEN':'시가','HIGH':'고가','LOW':'저가','CLOSE':'종가','VOLUME':'거래량'})
        pre_20 = df.iloc[-21:-1]
        cv = (pre_20['종가'].std() / pre_20['종가'].mean()) * 100
        vol_ma20 = pre_20['거래량'].mean()
        vol_ratio = df.iloc[-1]['거래량'] / vol_ma20 if vol_ma20 > 0 else 0
        cv_score = max(0, 100 - (abs(cv - ST_PARAMS['target_cv']) * 20))
        vol_score = min(100, (vol_ratio / ST_PARAMS['target_vol']) * 100)
        similarity = (cv_score * 0.4) + (vol_score * 0.6)
        t_low = int(df.iloc[-1]['저가'])
        stop_price = int(t_low * 0.97)
        is_buy_zone = (df.iloc[-1]['종가'] >= t_low) and (df.iloc[-1]['종가'] <= t_low * 1.05)
        return {"code": ticker, "curr": int(df.iloc[-1]['종가']), "t_low": t_low, "stop": stop_price, "similarity": similarity, "is_buy": is_buy_zone, "cv": cv, "vol_ratio": vol_ratio}, df
    except: return None, None

def background_scanner(codes):
    results = []
    total = len(codes)
    for i, c in enumerate(codes):
        try:
            st.session_state.scan_progress = int(((i + 1) / total) * 100)
            st.session_state.scan_status = f"{i+1}/{total}"
            r, _ = analyze_v5(c, datetime.date.today())
            if r and r['is_buy']: results.append(r)
            time.sleep(0.3)
        except: continue
    st.session_state.scan_results = sorted(results, key=lambda x: x['similarity'], reverse=True)
    st.session_state.scan_status = "완료"

# --- [메인] 레이아웃 최적화 ---
st.subheader("🎯 엔진 판독 리포트")
if st.session_state.auto_code:
    res, _ = analyze_v5(st.session_state.auto_code, datetime.date.today())
    if res:
        c1, c2, c3 = st.columns(3)
        c1.metric("유사도", f"{res['similarity']:.1f}%")
        opinion = "🔥 강력매수" if res['similarity'] >= 85 and res['is_buy'] else ("✅ 매수고려" if res['similarity'] >= 60 and res['is_buy'] else "🟡 관망")
        c2.metric("의견", opinion)
        c3.metric("손절가", f"{res['stop']:,}")
        st.caption(f"💡 {res['similarity']:.1f}% 일치 | {res['stop']:,}원 엄수")
else:
    st.info("종목 선택 시 판독 시작")

# --- 분석 입력창 ---
with st.container(border=True):
    col_in1, col_in2, col_in3 = st.columns([2, 2, 1])
    t_input = col_in1.text_input("코드", value=st.session_state.auto_code, label_visibility="collapsed")
    d_input = col_in2.date_input("날짜", value=datetime.date.today(), label_visibility="collapsed")
    btn = col_in3.button("📊", type="primary", use_container_width=True)

if btn and t_input:
    res, df = analyze_v5(t_input, d_input)
    if res:
        # 로그 저장
        disp_name = t_input
        if not krx_df.empty:
            match = krx_df[krx_df['Code'] == t_input]; disp_name = match['Name'].values[0] if not match.empty else t_input
        analysis_log = [l for l in analysis_log if l['code'] != t_input]
        analysis_log.insert(0, {"name": disp_name, "code": t_input})
        save_data(ANALYSIS_LOG_FILE, analysis_log[:10])

        # 차트
        fig = go.Figure(data=[go.Candlestick(x=df.index, open=df['시가'], high=df['고가'], low=df['저가'], close=df['종가'], increasing_line_color='red', decreasing_line_color='blue')])
        fig.add_hline(y=res['t_low'], line_dash="dash", line_color="green")
        fig.add_hline(y=res['stop'], line_color="magenta", annotation_text=f"STOP {res['stop']:,}")
        fig.update_layout(height=350, margin=dict(l=10, r=10, t=10, b=10), xaxis_rangeslider_visible=False, template="plotly_dark")
        st.plotly_chart(fig, use_container_width=True)

# --- 최근 로그 (슬림 버튼) ---
st.caption("🕒 최근 분석 로그")
if analysis_log:
    cols = st.columns(5)
    for i, log in enumerate(analysis_log[:10]):
        with cols[i % 5]:
            if st.button(f"{log['name'][:4]}", key=f"alog_{log['code']}_{i}", use_container_width=True):
                st.session_state.auto_code = log['code']; st.rerun()

st.divider()

# --- 스캐너 (컴팩트 뷰) ---
st.subheader("📡 스캐너 & TOP 10")
sc1, sc2 = st.columns([1, 2])
if sc1.button("🚀 스캔", use_container_width=True):
    if st.session_state.scan_status != "분석 중":
        codes = krx_df.head(200)['Code'].tolist()
        threading.Thread(target=background_scanner, args=(codes,)).start()
        st.session_state.scan_status = "분석 중"
with sc2:
    if st.session_state.scan_status != "완료":
        st.caption(f"상태: {st.session_state.scan_status}")
    else:
        st.success(f"발견: {len(st.session_state.scan_results)}개")

if st.session_state.scan_status == "완료" and st.session_state.scan_results:
    st.markdown("**🏆 AI 유사도 TOP 5**")
    top_5 = st.session_state.scan_results[:5]
    t_cols = st.columns(5)
    for idx, r in enumerate(top_5):
        with t_cols[idx]:
            if st.button(f"{r['code']}\n{r['similarity']:.0f}%", key=f"top_{r['code']}", use_container_width=True):
                st.session_state.auto_code = r['code']; st.rerun()
