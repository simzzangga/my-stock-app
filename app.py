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

trade_data = load_data(LOG_FILE, {"balance": 10000000})
mon_stocks = load_data(MONITOR_FILE, [])
search_history = load_data(SEARCH_HISTORY_FILE, [])
analysis_log = load_data(ANALYSIS_LOG_FILE, [])
krx_df = get_krx_list()

st.set_page_config(page_title="Shim's 100M Project", layout="wide")

if "auth" not in st.session_state: st.session_state.auth = False
if "auto_code" not in st.session_state: st.session_state.auto_code = ""
if "scan_progress" not in st.session_state: st.session_state.scan_progress = 0
if "scan_status" not in st.session_state: st.session_state.scan_status = "대기 중"
if "scan_results" not in st.session_state: st.session_state.scan_results = []

# --- [1단계] 보안 설정 ---
if not st.session_state.auth:
    st.title("💰 Shim's MSM Portal v5.2")
    st.info("1억 프로젝트 From 202605")
    pwd = st.text_input("Access Key", type="password", max_chars=4)
    if len(pwd) == 4 and pwd == "1234":
        st.session_state.auth = True
        st.rerun()
    st.stop()

# --- [2단계] 사이드바 (자산 및 검색 로그) ---
st.sidebar.title("🏁 1억 만들기")
current_balance = trade_data["balance"]
st.sidebar.metric("현재 자산", f"{current_balance:,}원")
st.sidebar.progress(min(current_balance / 100000000, 1.0))

with st.sidebar.expander("⚙️ 자산 수동 수정"):
    new_bal = st.number_input("금액 입력", value=current_balance, step=10000)
    if st.sidebar.button("자산 강제 업데이트"):
        trade_data["balance"] = new_bal
        save_data(LOG_FILE, trade_data); st.rerun()

st.sidebar.divider()
st.sidebar.subheader("🔍 종목명/종목코드 검색")
if not krx_df.empty:
    selected_name = st.sidebar.selectbox("종목명 검색", krx_df['Name'].tolist(), index=None)
    if selected_name:
        target_code = krx_df[krx_df['Name'] == selected_name]['Code'].values[0]
        if st.sidebar.button(f"✅ {selected_name} 선택"):
            st.session_state.auto_code = target_code
            search_history = [h for h in search_history if h['code'] != target_code]
            search_history.insert(0, {"name": selected_name, "code": target_code})
            save_data(SEARCH_HISTORY_FILE, search_history[:10]); st.rerun()

st.sidebar.caption("🕒 최근 검색 기록")
for h in search_history[:10]:
    if st.sidebar.button(f"{h['name']} ({h['code']})", key=f"side_{h['code']}", use_container_width=True):
        st.session_state.auto_code = h['code']; st.rerun()

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
        return {"code": ticker, "curr": int(curr['종가']), "t_low": int(target['저가']), "stop": int(target['저가'] * 0.95), "is_buy": target['저가'] <= curr['종가'] <= target['저가'] * 1.05}, df
    except: return None, None

# [개선] 백그라운드 스캐너 안정화 버전
def background_scanner(codes):
    results = []
    total = len(codes)
    for i, c in enumerate(codes):
        try:
            st.session_state.scan_progress = int(((i + 1) / total) * 100)
            st.session_state.scan_status = f"분석 중: {i+1}/{total}"
            
            r, _ = analyze_v5(c, datetime.date.today())
            if r: results.append(r)
            
            # 서버 부하 방지용 지연
            time.sleep(0.2) 
            
            # 중간 저장 (중단 대비)
            if (i + 1) % 10 == 0:
                st.session_state.scan_results = results
        except:
            continue
            
    st.session_state.scan_results = results
    st.session_state.scan_status = "완료"
    save_data(SCAN_FILE, {"results": results, "time": datetime.datetime.now().strftime("%H:%M")})

# --- [3단계] 메인 화면: 실전 매매 관리 (수익률 반영) ---
st.title("🖥️ 살까 말까, 팔까 말까")
if mon_stocks:
    st.subheader("📌 실전 매매 관리 (수익률 반영)")
    for idx, s in enumerate(mon_stocks):
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns([1.5, 2, 3, 1])
            try:
                curr_df = fdr.DataReader(s['code'], datetime.date.today() - datetime.timedelta(days=7))
                live_p = int(curr_df.iloc[-1]['Close'])
            except: live_p = s['buy_price']
            
            p_rate = (live_p - s['buy_price']) / s['buy_price']
            c1.metric(s['name'], f"{live_p:,}원", f"{p_rate:.2%}")
            c2.info(f"매수: {s['buy_price']:,}원 / 진입액: {s['amt1']:,}원")
            
            with c3:
                sc1, sc2 = st.columns(2)
                a2 = sc1.number_input("추가 매수", value=0, step=10000, key=f"a2_{idx}")
                m2 = sc2.text_input("메모", key=f"m2_{idx}")
                if st.button("추가 기록", key=f"b2_{idx}"):
                    trade_data["balance"] -= a2; s['amt1'] += a2; s['memo'] += f" | {m2}"
                    save_data(LOG_FILE, trade_data); save_data(MONITOR_FILE, mon_stocks); st.rerun()
            
            if c4.button("🔴 매도", key=f"sell_{idx}", use_container_width=True):
                final_ret = int(s['amt1'] * (1 + p_rate))
                trade_data["balance"] += final_ret
                mon_stocks.pop(idx)
                save_data(LOG_FILE, trade_data); save_data(MONITOR_FILE, mon_stocks); st.rerun()

st.divider()
st.subheader("🔍 종목 정밀 분석")
with st.container(border=True):
    col1, col2, col3 = st.columns([2, 2, 1])
    input_ticker = col1.text_input("종목코드 입력", value=st.session_state.auto_code)
    analysis_date = col2.date_input("분석 기준일", value=datetime.date.today() if "current_date" not in st.session_state else st.session_state.current_date)
    st.session_state.current_date = analysis_date
    if col3.button("📊 분석", use_container_width=True, type="primary"):
        res, df = analyze_v5(input_ticker, analysis_date)
        if res:
            disp_name = input_ticker
            if not krx_df.empty:
                match = krx_df[krx_df['Code'] == input_ticker]
                if not match.empty: disp_name = match['Name'].values[0]
            analysis_log = [l for l in analysis_log if l['code'] != input_ticker]
            analysis_log.insert(0, {"name": disp_name, "code": input_ticker})
            save_data(ANALYSIS_LOG_FILE, analysis_log[:20])
            st.success(f"🎯 {disp_name} 분석 완료")
            fig = go.Figure(data=[go.Candlestick(x=df.index, open=df['시가'], high=df['고가'], low=df['저가'], close=df['종가'], increasing_line_color='red', decreasing_line_color='blue')])
            fig.add_hline(y=res['t_low'], line_dash="dash", line_color="green", annotation_text="기준봉 저가")
            fig.update_layout(height=450, xaxis_rangeslider_visible=False, template="plotly_dark")
            st.plotly_chart(fig, use_container_width=True)
            with st.expander("📝 매수 전략 등록"):
                buy_amt = st.number_input("매수 금액(원)", value=int(trade_data['balance']*0.08))
                if st.button("🔥 실전 매수 등록"):
                    trade_data["balance"] -= buy_amt
                    mon_stocks.append({"name": disp_name, "code": input_ticker, "buy_price": res['curr'], "stop": res['stop'], "amt1": buy_amt, "memo": ""})
                    save_data(LOG_FILE, trade_data); save_data(MONITOR_FILE, mon_stocks); st.rerun()

st.divider()
st.subheader("🕒 최근 정밀 분석 로그")
if analysis_log:
    cols = st.columns(5)
    for i, log in enumerate(analysis_log[:20]):
        with cols[i % 5]:
            if st.button(f"{log['name']}\n{log['code']}", key=f"alog_{log['code']}_{i}", use_container_width=True):
                st.session_state.auto_code = log['code']; st.rerun()

st.divider()
st.subheader("📡 백그라운드 전략 스캐너")
c_scan1, c_scan2 = st.columns([1, 4])
if c_scan1.button("🚀 스캔 시작", use_container_width=True):
    if st.session_state.scan_status != "분석 중":
        codes = krx_df.head(500)['Code'].tolist()
        threading.Thread(target=background_scanner, args=(codes,)).start()
        st.session_state.scan_status = "분석 중"

with c_scan2:
    if st.session_state.scan_status == "분석 중":
        st.progress(st.session_state.scan_progress / 100)
        st.caption(f"⏳ {st.session_state.scan_status}... (다른 조작 가능)")
    elif st.session_state.scan_status == "완료":
        st.success(f"✅ 스캔 완료! ({len(st.session_state.scan_results)}개 후보 발견)")

if st.session_state.scan_results:
    with st.expander("📂 스캔 결과 리스트", expanded=True):
        cols = st.columns(4)
        for idx, item in enumerate(st.session_state.scan_results):
            with cols[idx % 4]:
                st.code(item['code'])
                if st.button("입력", key=f"scan_btn_{item['code']}"):
                    st.session_state.auto_code = item['code']; st.rerun()
