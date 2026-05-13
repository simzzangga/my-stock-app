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

st.set_page_config(page_title="MSM AI Dual-Engine v5.9.7", layout="wide")

# 세션 상태 확장 (타이머 및 진행률용)
if "auth" not in st.session_state: st.session_state.auth = False
if "auto_code" not in st.session_state: st.session_state.auto_code = ""
if "scan_progress" not in st.session_state: st.session_state.scan_progress = 0
if "scan_status" not in st.session_state: st.session_state.scan_status = "대기 중"
if "scan_results" not in st.session_state: st.session_state.scan_results = []
if "scan_start_time" not in st.session_state: st.session_state.scan_start_time = 0
if "scan_etc" not in st.session_state: st.session_state.scan_etc = ""

# --- 보안 설정 ---
if not st.session_state.auth:
    st.title("💰 MSM AI Engine v5.9.7")
    pwd = st.text_input("Access Key", type="password", max_chars=4)
    if pwd == "1234": st.session_state.auth = True; st.rerun()
    st.stop()

# --- [사이드바] 검색 로그 유지 ---
st.sidebar.title("🔍 종목 탐색")
if not krx_df.empty:
    selected_name = st.sidebar.selectbox("종목명/코드 검색", krx_df['Name'].tolist(), index=None)
    if selected_name:
        target_code = krx_df[krx_df['Name'] == selected_name]['Code'].values[0]
        if st.sidebar.button("분석창 즉시 입력", use_container_width=True):
            st.session_state.auto_code = target_code
            search_history = [h for h in search_history if h['code'] != target_code]
            search_history.insert(0, {"name": selected_name, "code": target_code})
            save_data(SEARCH_HISTORY_FILE, search_history[:10]); st.rerun()

st.sidebar.subheader("🕒 최근 검색")
for h in search_history[:10]:
    if st.sidebar.button(f"{h['name']}", key=f"side_{h['code']}", use_container_width=True):
        st.session_state.auto_code = h['code']; st.rerun()

# --- [핵심 엔진] ---
def analyze_v5(ticker, base_date):
    try:
        df = fdr.DataReader(ticker, base_date - datetime.timedelta(days=120), base_date)
        if df.empty or len(df) < 30: return None, None
        df.columns = [c.upper() for c in df.columns]
        df = df.rename(columns={'OPEN':'시가','HIGH':'고가','LOW':'저가','CLOSE':'종가','VOLUME':'거래량'})
        
        df['BODY_RATIO'] = (df['종가'] - df['시가']).abs() / (df['고가'] - df['저가'] + 1)
        df['VOL_MA'] = df['거래량'].rolling(20).mean()
        curr = df.iloc[-1]
        is_orig_buy = (curr['종가'] > curr['시가']) and (curr['BODY_RATIO'] > 0.7) and (curr['거래량'] > curr['VOL_MA'] * 5)
        
        pre_20 = df.iloc[-21:-1]
        cv = (pre_20['종가'].std() / pre_20['종가'].mean()) * 100
        vol_ratio = curr['거래량'] / (pre_20['거래량'].mean() + 1)
        similarity = ((max(0, 100 - (abs(cv - 2.0) * 20))) * 0.4) + ((min(100, (vol_ratio / 8.0) * 100)) * 0.6)
        
        if is_orig_buy and similarity >= 85: tag = "💎 필승합의 (S급)"
        elif similarity >= 80 and not is_orig_buy: tag = "🔭 선취매형 (A급)"
        elif is_orig_buy: tag = "⚔️ 단기회전 (B급)"
        else: tag = "🟡 관망"
        
        return {"code": ticker, "curr": int(curr['종가']), "t_low": int(curr['저가']), "stop": int(curr['저가'] * 0.97), "similarity": similarity, "tag": tag}, df
    except: return None, None

# [스캐너 강화] 타이머 및 ETC 계산 로직 추가
def background_scanner(codes):
    results = []
    total = len(codes)
    start_t = time.time()
    for i, c in enumerate(codes):
        try:
            current_idx = i + 1
            st.session_state.scan_progress = int((current_idx / total) * 100)
            
            # 남은 시간(ETC) 계산
            elapsed = time.time() - start_t
            avg_time = elapsed / current_idx
            remaining_seconds = int(avg_time * (total - current_idx))
            st.session_state.scan_etc = f"{remaining_seconds // 60}분 {remaining_seconds % 60}초"
            st.session_state.scan_status = f"분석 중: {current_idx}/{total} (예상 남은 시간: {st.session_state.scan_etc})"
            
            r, _ = analyze_v5(c, datetime.date.today())
            if r and r['tag'] != "🟡 관망": results.append(r)
            time.sleep(0.35) 
        except: continue
    
    st.session_state.scan_results = sorted(results, key=lambda x: x['similarity'], reverse=True)
    st.session_state.scan_status = "완료"
    save_data(SCAN_FILE, {"results": st.session_state.scan_results, "date": str(datetime.date.today())})

# --- [메인] 화면 ---
st.title("🖥️ MSM AI Dual-Engine v5.9.7")

if st.session_state.auto_code:
    res, df = analyze_v5(st.session_state.auto_code, datetime.date.today())
    if res:
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("전략 등급", res['tag'])
            c2.metric("패턴 유사도", f"{res['similarity']:.1f}%")
            c3.metric("판독가", f"{res['curr']:,}원")
            c4.metric("손절가", f"{res['stop']:,}원")
            
            fig = go.Figure(data=[go.Candlestick(x=df.index, open=df['시가'], high=df['고가'], low=df['저가'], close=df['종가'], increasing_line_color='red', decreasing_line_color='blue')])
            fig.add_hline(y=res['t_low'], line_dash="dash", line_color="green", annotation_text="기준저가")
            fig.add_hline(y=res['stop'], line_color="magenta", annotation_text=f"STOP {res['stop']:,}")
            fig.update_layout(height=400, xaxis_rangeslider_visible=False, template="plotly_dark")
            st.plotly_chart(fig, use_container_width=True)

st.divider()

# [강화] 타이머가 포함된 스캐너 섹션
st.subheader("📡 전략 등급 스캐너 (오후 2시 50분 권장)")
s_col1, s_col2 = st.columns([1, 4])

if s_col1.button("🚀 상위 500개 스캔", use_container_width=True):
    if st.session_state.scan_status != "분석 중":
        codes = krx_df.head(500)['Code'].tolist()
        st.session_state.scan_start_time = time.time()
        threading.Thread(target=background_scanner, args=(codes,)).start()
        st.session_state.scan_status = "분석 중"

with s_col2:
    if st.session_state.scan_status == "분석 중":
        st.progress(st.session_state.scan_progress / 100)
        st.caption(f"📊 진행 상황: {st.session_state.scan_status}")
    elif st.session_state.scan_status == "완료":
        st.success(f"✅ 스캔 완료! 필승 후보 {len(st.session_state.scan_results)}개를 찾았습니다.")

if st.session_state.scan_status == "완료" and st.session_state.scan_results:
    tabs = st.tabs(["💎 S급: 필승합의", "🔭 A급: 선취매형", "⚔️ B급: 단기회전"])
    for i, t_name in enumerate(["S급", "A급", "B급"]):
        with tabs[i]:
            filtered = [r for r in st.session_state.scan_results if t_name in r['tag']]
            if filtered:
                cols = st.columns(5)
                for idx, r in enumerate(filtered[:10]):
                    with cols[idx % 5]:
                        if st.button(f"{r['code']}\n({r['similarity']:.0f}%)", key=f"btn_{t_name}_{r['code']}"):
                            st.session_state.auto_code = r['code']; st.rerun()
            else: st.write(f"현재 {t_name} 종목이 없습니다.")

st.subheader("🕒 최근 분석 로그")
if analysis_log:
    cols = st.columns(5)
    for i, log in enumerate(analysis_log[:10]):
        with cols[i % 5]:
            if st.button(f"{log['name']}", key=f"alog_{log['code']}_{i}", use_container_width=True):
                st.session_state.auto_code = log['code']; st.rerun()
