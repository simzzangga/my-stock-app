import streamlit as st
import FinanceDataReader as fdr
import pandas as pd
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

# 데이터 초기화
trade_data = load_data(LOG_FILE, {"balance": 10000000})
mon_stocks = load_data(MONITOR_FILE, [])
search_history = load_data(SEARCH_HISTORY_FILE, [])
analysis_log = load_data(ANALYSIS_LOG_FILE, [])
krx_df = get_krx_list()

st.set_page_config(page_title="Shim's 100M Project", layout="wide")

# 세션 상태 관리
if "auth" not in st.session_state: st.session_state.auth = False
if "auto_code" not in st.session_state: st.session_state.auto_code = ""
if "scan_progress" not in st.session_state: st.session_state.scan_progress = 0
if "scan_status" not in st.session_state: st.session_state.scan_status = "대기 중"
if "scan_results" not in st.session_state: st.session_state.scan_results = []

# --- [1단계] 보안 설정 ---
if not st.session_state.auth:
    st.title("💰 Shim's MSM Portal v5.2")
    pwd = st.text_input("Access Key", type="password", max_chars=4)
    if len(pwd) == 4 and pwd == "1234":
        st.session_state.auth = True
        st.rerun()
    st.stop()

# --- [2단계] 사이드바 ---
st.sidebar.title("🏁 1억 만들기")
st.sidebar.metric("현재 자산", f"{trade_data['balance']:,}원")
if not krx_df.empty:
    selected_name = st.sidebar.selectbox("종목명 검색", krx_df['Name'].tolist(), index=None)
    if selected_name:
        target_code = krx_df[krx_df['Name'] == selected_name]['Code'].values[0]
        if st.sidebar.button(f"✅ {selected_name} 선택"):
            st.session_state.auto_code = target_code
            st.rerun()

# --- 분석 엔진 ---
def analyze_v5(ticker, base_date):
    try:
        df = fdr.DataReader(ticker, base_date - datetime.timedelta(days=100), base_date)
        if df.empty or len(df) < 20: return None, None
        df.columns = [c.upper() for c in df.columns]
        df = df.rename(columns={'OPEN':'시가','HIGH':'고가','LOW':'저가','CLOSE':'종가','VOLUME':'거래량'})
        df['BODY'] = (df['종가'] - df['시가']).abs() / (df['고가'] - df['저가'])
        df['VOL_MA'] = df['거래량'].rolling(20).mean()
        spikes = df[(df['종가'] > df['시가']) & (df['BODY'] > 0.7) & (df['거래량'] > df['VOL_MA'] * 5)]
        if spikes.empty: return None, df
        target = spikes.tail(1).iloc[0]
        curr = df.iloc[-1]
        res = {
            "code": ticker, "curr": int(curr['종가']), "t_low": int(target['저가']),
            "stop": int(target['저가'] * 0.95), "is_buy": target['저가'] <= curr['종가'] <= target['저가'] * 1.05
        }
        return res, df
    except: return None, None

# --- 비동기 스캔 함수 ---
def background_scanner(codes):
    results = []
    total = len(codes)
    for i, c in enumerate(codes):
        st.session_state.scan_progress = int(((i + 1) / total) * 100)
        st.session_state.scan_status = f"분석 중: {i+1}/{total}"
        r, _ = analyze_v5(c, datetime.date.today())
        if r: results.append(r)
    st.session_state.scan_results = results
    st.session_state.scan_status = "완료"
    save_data(SCAN_FILE, {"results": results, "time": datetime.datetime.now().strftime("%H:%M")})

# --- [3단계] 메인 화면 ---
st.title("🖥️ 살까 말까, 팔까 말까")

# 실전 매매 관리 섹션 (기존 기능 유지)
if mon_stocks:
    st.subheader("📌 실전 매매 관리")
    for idx, s in enumerate(mon_stocks):
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns([1.5, 2, 3, 1])
            c1.metric(s['name'], f"{s['buy_price']:,}원", f"손절 {s['stop']:,}")
            c2.info(f"진입액: {s['amt1']:,}원\n메모: {s.get('memo', '-')}")
            with c3:
                sc1, sc2 = st.columns(2)
                a2 = sc1.number_input("2차 매수액", value=int(trade_data['balance']*0.12), key=f"a2_{idx}")
                m2 = sc2.text_input("추가 대응 메모", key=f"m2_{idx}")
                if st.button("추가 매수 기록", key=f"b2_{idx}"):
                    trade_data["balance"] -= a2; s['amt1'] += a2; s['memo'] += f" | 2차:{m2}"
                    save_data(LOG_FILE, trade_data); save_data(MONITOR_FILE, mon_stocks); st.rerun()
            if c4.button("🔴 매도/삭제", key=f"sell_{idx}", use_container_width=True):
                mon_stocks.pop(idx); save_data(MONITOR_FILE, mon_stocks); st.rerun()

st.divider()
st.subheader("🔍 종목 정밀 분석")
with st.container(border=True):
    col_s1, col_s2, col_s3 = st.columns([2, 2, 1])
    input_ticker = col_s1.text_input("종목코드 입력", value=st.session_state.auto_code)
    # 날짜 고정 유지 로직
    analysis_date = col_s2.date_input("분석 기준일", value=datetime.date.today() if "current_date" not in st.session_state else st.session_state.current_date)
    st.session_state.current_date = analysis_date
    btn_analysis = col_s3.button("📊 분석", use_container_width=True, type="primary")

if btn_analysis and input_ticker:
    res, df = analyze_v5(input_ticker, analysis_date)
    if res:
        # [복구] 분석 로그 저장 로직
        disp_name = input_ticker
        if not krx_df.empty:
            match = krx_df[krx_df['Code'] == input_ticker]
            if not match.empty: disp_name = match['Name'].values[0]
        
        analysis_log = [l for l in analysis_log if l['code'] != input_ticker]
        analysis_log.insert(0, {"name": disp_name, "code": input_ticker})
        save_data(ANALYSIS_LOG_FILE, analysis_log[:20])
        
        st.success(f"🎯 {disp_name} 분석 완료")
        fig = go.Figure(data=[go.Candlestick(x=df.index, open=df['시가'], high=df['고가'], low=df['저가'], close=df['종가'],
                                            increasing_line_color='red', decreasing_line_color='blue')])
        fig.add_hline(y=res['t_low'], line_dash="dash", line_color="green")
        st.plotly_chart(fig, use_container_width=True)

        with st.expander("📝 매수 전략 등록"):
            c_m1, c_m2 = st.columns(2)
            buy_memo = c_m1.text_input("매수 메모")
            buy_amt = c_m2.number_input("매수 금액(원)", value=int(trade_data['balance']*0.08))
            if st.button("🔥 실전 매수 종목으로 등록"):
                trade_data["balance"] -= buy_amt
                mon_stocks.append({"name": disp_name, "buy_price": res['curr'], "stop": res['stop'], "amt1": buy_amt, "memo": buy_memo})
                save_data(LOG_FILE, trade_data); save_data(MONITOR_FILE, mon_stocks); st.rerun()

# --- [복구] 최근 정밀 분석 로그 섹션 ---
st.divider()
st.subheader("🕒 최근 정밀 분석")
if analysis_log:
    cols = st.columns(5)
    for i, log in enumerate(analysis_log[:20]):
        with cols[i % 5]:
            if st.button(f"{log['name']}\n{log['code']}", key=f"alog_{log['code']}_{i}", use_container_width=True):
                st.session_state.auto_code = log['code']
                st.rerun()

# --- [6단계] 시장 스캐너 (비동기 유지) ---
st.divider()
st.subheader("📡 백그라운드 전략 스캐너")
c_scan1, c_scan2 = st.columns([1, 4])
if c_scan1.button("🚀 스캔 시작", use_container_width=True):
    if st.session_state.scan_status != "분석 중":
        codes = krx_df.head(500)['Code'].tolist()
        thread = threading.Thread(target=background_scanner, args=(codes,))
        thread.start()
        st.session_state.scan_status = "분석 중"

with c_scan2:
    if st.session_state.scan_status == "분석 중":
        st.progress(st.session_state.scan_progress / 100)
        st.caption(f"⏳ {st.session_state.scan_status}... (다른 조작 가능)")
    elif st.session_state.scan_status == "완료":
        st.success(f"✅ 스캔 완료! ({len(st.session_state.scan_results)}개 발견)")

if st.session_state.scan_results:
    with st.expander("📂 스캔 결과 리스트", expanded=True):
        cols = st.columns(4)
        for idx, item in enumerate(st.session_state.scan_results):
            with cols[idx % 4]:
                st.code(f"{item['code']}")
                if st.button("입력", key=f"scan_btn_{item['code']}"):
                    st.session_state.auto_code = item['code']
                    st.rerun()
