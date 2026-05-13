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

# --- [수익률 엔진] 고도화 파라미터 (90% 승률 기준점) ---
ST_PARAMS = {"target_cv": 2.0, "target_vol": 8.0, "target_win": 0.91}

st.set_page_config(page_title="MSM AI Engine v5.9.3", layout="wide")

if "auth" not in st.session_state: st.session_state.auth = False
if "auto_code" not in st.session_state: st.session_state.auto_code = ""
if "scan_progress" not in st.session_state: st.session_state.scan_progress = 0
if "scan_status" not in st.session_state: st.session_state.scan_status = "대기 중"
if "scan_results" not in st.session_state: st.session_state.scan_results = []

# --- 보안 설정 ---
if not st.session_state.auth:
    st.title("💰 MSM AI Engine v5.9.3")
    pwd = st.text_input("Access Key", type="password", max_chars=4)
    if pwd == "1234": st.session_state.auth = True; st.rerun()
    st.stop()

# --- [사이드바] 검색 로그 (유지) ---
st.sidebar.title("🔍 종목 탐색")
if not krx_df.empty:
    selected_name = st.sidebar.selectbox("종목명/코드 검색", krx_df['Name'].tolist(), index=None)
    if selected_name:
        target_code = krx_df[krx_df['Name'] == selected_name]['Code'].values[0]
        st.sidebar.success(f"선택: `{target_code}`")
        if st.sidebar.button("분석창 즉시 입력", use_container_width=True):
            st.session_state.auto_code = target_code
            search_history = [h for h in search_history if h['code'] != target_code]
            search_history.insert(0, {"name": selected_name, "code": target_code})
            save_data(SEARCH_HISTORY_FILE, search_history[:10]); st.rerun()

st.sidebar.subheader("🕒 최근 검색 기록")
for h in search_history[:10]:
    if st.sidebar.button(f"{h['name']} ({h['code']})", key=f"side_{h['code']}", use_container_width=True):
        st.session_state.auto_code = h['code']; st.rerun()

# --- [핵심 엔진] 패턴 유사도 분석 및 매수 의견 도출 ---
def analyze_v5(ticker, base_date):
    try:
        df = fdr.DataReader(ticker, base_date - datetime.timedelta(days=120), base_date)
        if df.empty or len(df) < 30: return None, None
        df.columns = [c.upper() for c in df.columns]
        df = df.rename(columns={'OPEN':'시가','HIGH':'고가','LOW':'저가','CLOSE':'종가','VOLUME':'거래량'})
        
        # 1. 이전 20일 횡보 에너지 분석 (CV)
        pre_20 = df.iloc[-21:-1]
        cv = (pre_20['종가'].std() / pre_20['종가'].mean()) * 100
        
        # 2. 거래량 폭발력 분석
        vol_ma20 = pre_20['거래량'].mean()
        vol_ratio = df.iloc[-1]['거래량'] / vol_ma20 if vol_ma20 > 0 else 0
        
        # 3. 패턴 유사도 계산 (승률 90% 모델 대비 % 일치도)
        # CV가 2.0에 가까울수록, 거래량이 8배에 가까울수록 100%에 수렴
        cv_score = max(0, 100 - (abs(cv - ST_PARAMS['target_cv']) * 20))
        vol_score = min(100, (vol_ratio / ST_PARAMS['target_vol']) * 100)
        similarity = (cv_score * 0.4) + (vol_score * 0.6)
        
        # 4. 기준 양봉 저가 및 손절가 설정
        t_low = int(df.iloc[-1]['저가'])
        stop_price = int(t_low * 0.97) # 기준저가 -3%
        
        is_buy_zone = (df.iloc[-1]['종가'] >= t_low) and (df.iloc[-1]['종가'] <= t_low * 1.05)
        
        res = {
            "code": ticker, "curr": int(df.iloc[-1]['종가']), "t_low": t_low,
            "stop": stop_price, "similarity": similarity, "is_buy": is_buy_zone,
            "cv": cv, "vol_ratio": vol_ratio
        }
        return res, df
    except: return None, None

def background_scanner(codes):
    results = []
    total = len(codes)
    for i, c in enumerate(codes):
        try:
            st.session_state.scan_progress = int(((i + 1) / total) * 100)
            st.session_state.scan_status = f"분석 중: {i+1}/{total}"
            r, _ = analyze_v5(c, datetime.date.today())
            if r and r['is_buy']: results.append(r)
            time.sleep(0.3) 
        except: continue
    st.session_state.scan_results = sorted(results, key=lambda x: x['similarity'], reverse=True)
    st.session_state.scan_status = "완료"

# --- [메인] 화면 ---
st.title("🖥️ MSM AI 고도화 판독기 v5.9.3")

# [상단] 수익률 엔진 판독 리포트 (유사도 중심)
with st.container(border=True):
    st.subheader("🔬 AI 수익률 모델 엔진 판독 결과")
    if st.session_state.auto_code:
        res, _ = analyze_v5(st.session_state.auto_code, datetime.date.today())
        if res:
            c1, c2, c3 = st.columns(3)
            c1.metric("필승 패턴 유사도", f"{res['similarity']:.1f}%")
            
            # 매수 의견 판정
            if res['similarity'] >= 85 and res['is_buy']:
                opinion = "🔥 강력 매수 추천"
                advice = f"과거 승률 91% 구간과 매우 유사합니다. 손절가 {res['stop']:,}원을 엄수하세요."
            elif res['similarity'] >= 60 and res['is_buy']:
                opinion = "✅ 매수 고려"
                advice = "양호한 패턴입니다. 분할 매수로 접근 가능합니다."
            else:
                opinion = "🟡 관망 의견"
                advice = "패턴 유사도가 낮거나 기준 이격도를 벗어났습니다."
            
            c2.metric("수익률 엔진 의견", opinion)
            c3.metric("필수 손절가", f"{res['stop']:,}원")
            st.info(f"💡 **엔진 어드바이스**: {advice}")
    else:
        st.write("종목을 선택하면 AI 엔진의 매수 의견과 패턴 유사도가 여기에 표시됩니다.")

st.divider()

# [중앙] 종목 정밀 분석 차트
st.subheader("🔍 실시간 종목 분석 차트")
with st.container(border=True):
    col_in1, col_in2, col_in3 = st.columns([2, 2, 1])
    t_input = col_in1.text_input("종목코드", value=st.session_state.auto_code)
    d_input = col_in2.date_input("분석 날짜", value=datetime.date.today())
    
    if col_in3.button("📊 판독 및 차트 생성", type="primary", use_container_width=True):
        res, df = analyze_v5(t_input, d_input)
        if res:
            # 로그 저장
            disp_name = t_input
            if not krx_df.empty:
                match = krx_df[krx_df['Code'] == t_input]; disp_name = match['Name'].values[0] if not match.empty else t_input
            analysis_log = [l for l in analysis_log if l['code'] != t_input]
            analysis_log.insert(0, {"name": disp_name, "code": t_input})
            save_data(ANALYSIS_LOG_FILE, analysis_log[:20])

            # 차트 시각화
            fig = go.Figure(data=[go.Candlestick(x=df.index, open=df['시가'], high=df['고가'], low=df['저가'], close=df['종가'], 
                                                increasing_line_color='red', decreasing_line_color='blue')])
            # 가이드 라인 복구
            fig.add_hline(y=res['t_low'], line_dash="dash", line_color="green", annotation_text="기준 저가")
            fig.add_hline(y=res['stop'], line_color="magenta", annotation_text=f"손절선({res['stop']:,})")
            
            fig.update_layout(height=500, xaxis_rangeslider_visible=False, template="plotly_dark")
            st.plotly_chart(fig, use_container_width=True)
            
            if res['similarity'] >= 60:
                st.success(f"🎯 **{disp_name}** 판독: {opinion} (유사도 {res['similarity']:.1f}%) | 손절가: {res['stop']:,}원")

# [하단] 로그 및 스캐너 (기능 유지)
st.subheader("🕒 최근 정밀 분석 로그")
if analysis_log:
    cols = st.columns(5)
    for i, log in enumerate(analysis_log[:20]):
        with cols[i % 5]:
            if st.button(f"{log['name']}\n{log['code']}", key=f"alog_{log['code']}_{i}", use_container_width=True):
                st.session_state.auto_code = log['code']; st.rerun()

st.divider()
st.subheader("📡 백그라운드 전략 스캐너 & TOP 10")
s_col1, s_col2 = st.columns([1, 4])
if s_col1.button("🚀 스캔 시작"):
    if st.session_state.scan_status != "분석 중":
        codes = krx_df.head(300)['Code'].tolist()
        threading.Thread(target=background_scanner, args=(codes,)).start()
        st.session_state.scan_status = "분석 중"
with s_col2:
    if st.session_state.scan_status == "분석 중":
        st.progress(st.session_state.scan_progress / 100)
    elif st.session_state.scan_status == "완료":
        st.success(f"✅ 발견: {len(st.session_state.scan_results)}개 (유사도 순 정렬)")

if st.session_state.scan_status == "완료" and st.session_state.scan_results:
    st.markdown("### 🏆 AI 엔진 선정 유사도 TOP 10")
    top_10 = st.session_state.scan_results[:10]
    t_cols = st.columns(5)
    for idx, r in enumerate(top_10):
        with t_cols[idx % 5]:
            with st.container(border=True):
                st.markdown(f"**RANK {idx+1}**")
                st.code(r['code'])
                st.caption(f"유사도: {r['similarity']:.1f}%")
                if st.button("즉시 분석", key=f"top_{r['code']}"):
                    st.session_state.auto_code = r['code']; st.rerun()
