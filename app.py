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
LOG_FILE = "trade_v5_log.json"
MONITOR_FILE = "monitoring_v5.json"
SCAN_FILE = "scan_results_v5.json"
SEARCH_HISTORY_FILE = "search_history_v5.json"
ANALYSIS_LOG_FILE = "analysis_log_v5.json"

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

trade_data = load_data(LOG_FILE, {"balance": 10000000})
mon_stocks = load_data(MONITOR_FILE, [])
search_history = load_data(SEARCH_HISTORY_FILE, [])
analysis_log = load_data(ANALYSIS_LOG_FILE, [])
krx_df = get_krx_list()

ST_PARAMS = {"target_cv": 1.8, "target_vol": 10.0}

st.set_page_config(page_title="MSM AI Dual-Engine v5.9.14", layout="wide")

if "auth" not in st.session_state: st.session_state.auth = False
if "auto_code" not in st.session_state: st.session_state.auto_code = ""
if "scan_progress" not in st.session_state: st.session_state.scan_progress = 0
if "scan_status" not in st.session_state: st.session_state.scan_status = "대기 중"
if "scan_results" not in st.session_state: st.session_state.scan_results = []

# --- 보안 설정 ---
if not st.session_state.auth:
    st.title("💰 MSM Portal v5.9.14")
    pwd = st.text_input("Access Key", type="password", max_chars=4, key="entry_pwd")
    if pwd == "1234": st.session_state.auth = True; st.rerun()
    st.stop()

# --- 사이드바 ---
st.sidebar.title("🏁 1억 만들기")
cur_bal = trade_data["balance"]
st.sidebar.metric("현재 자산", f"{cur_bal:,}원")
if not krx_df.empty:
    sel_name = st.sidebar.selectbox("종목 검색", krx_df['Name'].tolist(), index=None)
    if sel_name:
        t_code = krx_df[krx_df['Name'] == sel_name]['Code'].values[0]
        if st.sidebar.button("분석창 입력", use_container_width=True):
            st.session_state.auto_code = t_code; st.rerun()

# --- [엔진] 분석 및 3분할 차수 판정 로직 ---
def analyze_v5(ticker, base_date):
    try:
        df = fdr.DataReader(ticker, base_date - datetime.timedelta(days=120), base_date)
        if df.empty or len(df) < 30: return None, None
        df.columns = [c.upper() for c in df.columns]
        df = df.rename(columns={'OPEN':'시가','HIGH':'고가','LOW':'저가','CLOSE':'종가','VOLUME':'거래량'})
        
        # 1. 지표 계산
        df['BODY_RATIO'] = (df['종가'] - df['시가']).abs() / (df['고가'] - df['저가'] + 1)
        df['VOL_MA'] = df['거래량'].rolling(20).mean()
        curr = df.iloc[-1]
        is_orig_buy = (curr['종가'] > curr['시가']) and (curr['BODY_RATIO'] > 0.7) and (curr['거래량'] > curr['VOL_MA'] * 5)
        
        pre_20 = df.iloc[-21:-1]
        cv = (pre_20['종가'].std() / pre_20['종가'].mean()) * 100
        vol_ratio = curr['거래량'] / (pre_20['거래량'].mean() + 1)
        similarity = ((max(0, 100 - (abs(cv - ST_PARAMS['target_cv']) * 25))) * 0.5) + ((min(100, (vol_ratio / ST_PARAMS['target_vol']) * 100)) * 0.5)
        
        # 2. 매수 사인 및 차수 판정 (수정된 핵심 로직)
        if similarity >= 75:
            # 실전 모니터링 리스트에 해당 종목이 있는지 확인하여 차수 결정
            matching_mon = [s for s in mon_stocks if s['code'] == ticker]
            if not matching_mon:
                step_tag = "1차 매수 신호"
                weight = "🔥 신규 진입 (1/3)"
            elif len(matching_mon) == 1:
                step_tag = "2차 매수 신호 (눌림목)"
                weight = "⚖️ 추가 물타기 (2/3)"
            else:
                step_tag = "3차 매수 신호 (최종)"
                weight = "⚠️ 최종 비중 (3/3)"

            if similarity >= 85 and is_orig_buy: tag, color = f"💎 필승합의 ({step_tag})", "red"
            elif similarity >= 80: tag, color = f"🚀 급등유력 ({step_tag})", "red"
            else: tag, color = f"⚔️ 단기회전 ({step_tag})", "green"
            
            plan = f"전략: 3~5일간 눌림목 분할 매수 | 목표가: {int(curr['종가']*1.1):,}원"
            is_valid_signal = True
        else:
            tag, color, weight, plan = "🟡 관망", "grey", "❌ 사인없음", "가속도 조건 미달"
            is_valid_signal = False
        
        return {"code": ticker, "curr": int(curr['종가']), "t_low": int(curr['저가']), "stop": int(curr['저가'] * 0.96), 
                "similarity": similarity, "is_orig_buy": is_orig_buy, "tag": tag, "color": color, 
                "weight": weight, "plan": plan, "is_valid": is_valid_signal,
                "cv": cv, "vol_ratio": vol_ratio, "body": curr['BODY_RATIO']}, df
    except: return None, None

# --- 메인 화면 ---
st.title("🖥️ MSM AI Dual-Engine v5.9.14")

st.divider()

# 종목 정밀 판독 시스템
st.subheader("🔍 종목 정밀 판독 시스템")
with st.container(border=True):
    col1, col2, col3 = st.columns([2, 2, 1])
    t_input = col1.text_input("종목코드", value=st.session_state.auto_code)
    d_input = col2.date_input("분석 날짜", value=datetime.date.today())
    if col3.button("📊 분석", type="primary", use_container_width=True):
        res, df = analyze_v5(t_input, d_input)
        if res:
            st.markdown(f"### 🎯 종합 판정: :{res['color']}[{res['tag']}]")
            pc1, pc2, pc3 = st.columns(3)
            with pc1:
                st.write("**[엔진 판독 결과]**")
                st.write(f"기존엔진: {'🚀 매수' if res['is_orig_buy'] else '🟡 관망'}")
                st.write(f"패턴 유사도: {res['similarity']:.1f}%")
            with pc2:
                st.write("**[3분할 매수 지침]**")
                st.write(f"단계: **{res['weight']}**")
                st.write(f"방법: 3~5일간 눌림목 분할")
            with pc3:
                st.write("**[종합 매매 전략]**")
                st.write(f"목표: **+10% (20일 시한부)**")
                st.write(f"손절: **20일 경과 시 즉시**")
                st.write(f"최종 데드라인: {res['stop']:,}원")

            fig = go.Figure(data=[go.Candlestick(x=df.index, open=df['시가'], high=df['고가'], low=df['저가'], close=df['종가'], increasing_line_color='red', decreasing_line_color='blue')])
            fig.update_layout(height=450, xaxis_rangeslider_visible=False, template="plotly_dark")
            st.plotly_chart(fig, use_container_width=True)
