import streamlit as st
import FinanceDataReader as fdr
import pandas as pd
import datetime
import json
import os
import plotly.graph_objects as go
import time

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

if "auto_code" not in st.session_state: st.session_state.auto_code = ""
if "auth" not in st.session_state: st.session_state.auth = False

# --- [1단계] 보안 설정 (기존 유지) ---
if not st.session_state.auth:
    st.title("💰 Shim's MSM Portal v5.2")
    st.info("1억 프로젝트 From 202605")
    pwd = st.text_input("Access Key (4 digits)", type="password", max_chars=4, key="entry_pwd")
    if len(pwd) == 4 and pwd == "1234":
        st.session_state.auth = True
        st.rerun()
    st.stop()

# --- [2단계] 사이드바 (기존 유지) ---
st.sidebar.title("🏁 1억 만들기")
st.sidebar.metric("현재 자산", f"{trade_data['balance']:,}원")
st.sidebar.progress(min(trade_data['balance'] / 100000000, 1.0))

st.sidebar.divider()
st.sidebar.subheader("🔍 종목명/종목코드 검색")
if not krx_df.empty:
    selected_name = st.sidebar.selectbox("종목명 검색", krx_df['Name'].tolist(), index=None, placeholder="코드 확인용")
    if selected_name:
        target_code = krx_df[krx_df['Name'] == selected_name]['Code'].values[0]
        if st.sidebar.button(f"✅ {selected_name} : {target_code}", use_container_width=True):
            st.session_state.auto_code = target_code
            st.rerun()

st.sidebar.caption("🕒 최근 검색 기록")
for h in search_history[:10]:
    if st.sidebar.button(f"{h['name']} ({h['code']})", key=f"side_{h['code']}", use_container_width=True):
        st.session_state.auto_code = h['code']
        st.rerun()

# --- 분석 엔진 (V5.2 고도화 버전 유지) ---
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
            "stop": int(target['저가'] * 0.95), "vol_force": (1 - (curr['거래량'] / target['거래량'])) * 100,
            "dist": (curr['종가'] - target['저가']) / target['저가'],
            "is_buy": target['저가'] <= curr['종가'] <= target['저가'] * 1.05
        }
        return res, df
    except: return None, None

# --- [3단계] 메인 화면 ---
st.title("🖥️ 살까 말까, 팔까 말까")

# 실전 매매 관리 (보유 종목)
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
    analysis_date = col_s2.date_input("분석 기준일", value=datetime.date.today() if "current_date" not in st.session_state else st.session_state.current_date)
    st.session_state.current_date = analysis_date
    btn_analysis = col_s3.button("📊 분석", use_container_width=True, type="primary")

if btn_analysis and input_ticker:
    res, df = analyze_v5(input_ticker, analysis_date)
    if res:
        disp_name = input_ticker
        if not krx_df.empty:
            match = krx_df[krx_df['Code'] == input_ticker]
            if not match.empty: disp_name = match['Name'].values[0]
        
        # 분석 로그 저장 (기존 유지)
        analysis_log = [l for l in analysis_log if l['code'] != input_ticker]
        analysis_log.insert(0, {"name": disp_name, "code": input_ticker})
        save_data(ANALYSIS_LOG_FILE, analysis_log[:20])
        
        st.success(f"🎯 {disp_name} 분석 결과: {'🚀 매수 적기' if res['is_buy'] else '🟡 관망'}")
        
        fig = go.Figure(data=[go.Candlestick(x=df.index, open=df['시가'], high=df['고가'], low=df['저가'], close=df['종가'],
                                            increasing_line_color='red', decreasing_line_color='blue')])
        fig.add_hline(y=res['t_low'], line_dash="dash", line_color="green", annotation_text="기준봉 저가")
        fig.add_hline(y=res['stop'], line_color="magenta", annotation_text="손절선")
        fig.update_layout(height=450, xaxis_rangeslider_visible=False, template="plotly_dark")
        st.plotly_chart(fig, use_container_width=True)

        with st.expander("📝 매수 전략 등록"):
            c_m1, c_m2 = st.columns(2)
            buy_memo = c_m1.text_input("매수 메모")
            buy_amt = c_m2.number_input("매수 금액(원)", value=int(trade_data['balance']*0.08))
            if st.button("🔥 실전 매수 종목으로 등록"):
                trade_data["balance"] -= buy_amt
                mon_stocks.append({"name": disp_name, "buy_price": res['curr'], "stop": res['stop'], "amt1": buy_amt, "memo": buy_memo})
                save_data(LOG_FILE, trade_data); save_data(MONITOR_FILE, mon_stocks); st.rerun()

# --- 최근 정밀 분석 로그 (기존 유지) ---
st.divider()
st.subheader("🕒 최근 정밀 분석")
if analysis_log:
    cols = st.columns(5)
    for i, log in enumerate(analysis_log[:20]):
        with cols[i % 5]:
            if st.button(f"{log['name']}\n{log['code']}", key=f"alog_{log['code']}_{i}", use_container_width=True):
                st.session_state.auto_code = log['code']
                st.rerun()

# --- [수정] 시장 스캐너 (중단 방지 및 결과 보존 강화) ---
st.divider()
st.subheader("📡 오후 3시 전략 스캐너")
if st.button("🚀 전 종목 스캔 (상위 500개)", use_container_width=True):
    if not krx_df.empty:
        progress_bar = st.progress(0)
        status_text = st.empty()
        krx_codes = krx_df.head(500)['Code'].tolist()
        total = len(krx_codes)
        all_res = []
        start_t = time.time()

        for i, c in enumerate(krx_codes):
            # 스캔 중 사이드바 조작에 의한 끊김을 방지하기 위해 데이터를 즉시 리스트에 담음
            r, _ = analyze_v5(c, datetime.date.today())
            if r: all_res.append(r)
            
            pct = (i + 1) / total
            elap = time.time() - start_t
            eta = (elap / pct) - elap if pct > 0 else 0
            progress_bar.progress(pct)
            status_text.text(f"⏳ {i+1}/{total} 분석 중... (예상 시간: {int(eta)}초)")

        # 결과를 세션과 파일에 동시에 영구 저장하여 리셋 방지
        scan_data = {"results": all_res, "time": datetime.datetime.now().strftime("%H:%M")}
        st.session_state.last_scan_data = scan_data
        save_data(SCAN_FILE, scan_data)
        
        progress_bar.empty()
        status_text.success(f"✅ 스캔 완료! ({len(all_res)}개 발견)")
        st.rerun()

# 스캔 결과 출력 섹션 (저장된 데이터를 기반으로 출력)
saved_scan = st.session_state.get("last_scan_data", load_data(SCAN_FILE, None))
if saved_scan:
    st.info(f"최근 스캔 시점: {saved_scan['time']}")
    res_list = saved_scan['results']
    if res_list:
        cols = st.columns(4)
        for idx, item in enumerate(res_list):
            with cols[idx % 4]:
                with st.expander(f"{item['code']} ({item['curr']:,}원)"):
                    st.write(f"눌림목: {item['dist']:.1%}")
                    if st.button("분석창 입력", key=f"scan_btn_{item['code']}"):
                        st.session_state.auto_code = item['code']
                        st.rerun()
    else:
        st.warning("조건에 맞는 종목이 없습니다. 장 마감 후 다시 시도해 보세요.")
