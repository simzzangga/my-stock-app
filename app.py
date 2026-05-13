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

ST_PARAMS = {"target_cv": 2.0, "target_vol": 8.0, "target_win": 0.91}

st.set_page_config(page_title="MSM AI Dual-Engine v5.9.10", layout="wide")

if "auth" not in st.session_state: st.session_state.auth = False
if "auto_code" not in st.session_state: st.session_state.auto_code = ""
if "scan_progress" not in st.session_state: st.session_state.scan_progress = 0
if "scan_status" not in st.session_state: st.session_state.scan_status = "대기 중"
if "scan_results" not in st.session_state: st.session_state.scan_results = []
if "scan_etc" not in st.session_state: st.session_state.scan_etc = ""

# --- 보안 설정 ---
if not st.session_state.auth:
    st.title("💰 MSM Portal v5.9.10")
    pwd = st.text_input("Access Key", type="password", max_chars=4, key="entry_pwd")
    if pwd == "1234": st.session_state.auth = True; st.rerun()
    st.stop()

# --- [수정] 사이드바: 종목명 검색 및 로그 기록 로직 ---
st.sidebar.title("🏁 1억 만들기")
cur_bal = trade_data["balance"]
st.sidebar.metric("현재 자산", f"{cur_bal:,}원")

st.sidebar.divider()
st.sidebar.subheader("🔍 종목명/종목코드 검색")
if not krx_df.empty:
    sel_name = st.sidebar.selectbox("종목 검색", krx_df['Name'].tolist(), index=None, placeholder="종목명을 입력하세요")
    if sel_name:
        t_code = krx_df[krx_df['Name'] == sel_name]['Code'].values[0]
        st.sidebar.success(f"✅ {sel_name} ({t_code})")
        if st.sidebar.button("분석창 입력", use_container_width=True):
            st.session_state.auto_code = t_code
            # [수정] 분석 로그(하단 로그)에도 즉시 추가
            analysis_log = [l for l in analysis_log if l['code'] != t_code]
            analysis_log.insert(0, {"name": sel_name, "code": t_code})
            save_data(ANALYSIS_LOG_FILE, analysis_log[:20])
            # 최근 검색 기록(사이드바 로그) 유지
            search_history = [h for h in search_history if h['code'] != t_code]
            search_history.insert(0, {"name": sel_name, "code": t_code})
            save_data(SEARCH_HISTORY_FILE, search_history[:10]); st.rerun()

st.sidebar.caption("🕒 최근 검색 기록")
for h in search_history[:10]:
    if st.sidebar.button(f"{h['name']} ({h['code']})", key=f"side_{h['code']}", use_container_width=True):
        st.session_state.auto_code = h['code']; st.rerun()

# --- [엔진] 듀얼 분석 로직 ---
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
        
        if is_orig_buy and similarity >= 85: tag, color = "💎 필승합의 (S급)", "red"
        elif similarity >= 80 and not is_orig_buy: tag, color = "🔭 선취매형 (A급)", "orange"
        elif is_orig_buy: tag, color = "⚔️ 단기회전 (B급)", "green"
        else: tag, color = "🟡 관망", "grey"
        
        return {"code": ticker, "curr": int(curr['종가']), "t_low": int(curr['저가']), "stop": int(curr['저가'] * 0.97), 
                "similarity": similarity, "is_orig_buy": is_orig_buy, "tag": tag, "color": color, 
                "cv": cv, "vol_ratio": vol_ratio, "body": curr['BODY_RATIO']}, df
    except: return None, None

def background_scanner(codes):
    results = []
    total = len(codes)
    start_t = time.time()
    for i, c in enumerate(codes):
        try:
            cur_idx = i + 1
            st.session_state.scan_progress = int((cur_idx / total) * 100)
            elapsed = time.time() - start_t
            avg_time = elapsed / cur_idx
            rem_sec = int(avg_time * (total - cur_idx))
            st.session_state.scan_etc = f"{rem_sec // 60}분 {rem_sec % 60}초"
            st.session_state.scan_status = f"분석 중: {cur_idx}/{total} (남은 시간: {st.session_state.scan_etc})"
            r, _ = analyze_v5(c, datetime.date.today())
            if r and r['tag'] != "🟡 관망": results.append(r)
            time.sleep(0.35)
        except: continue
    st.session_state.scan_results = sorted(results, key=lambda x: x['similarity'], reverse=True)
    st.session_state.scan_status = "완료"

# --- 메인 화면: 실전 매매 현황 ---
st.title("🖥️ MSM AI Dual-Engine v5.9.10")

if mon_stocks:
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
                a2 = sc1.number_input("추가 매수", value=0, key=f"a2_{idx}")
                m2 = sc2.text_input("메모", key=f"m2_{idx}")
                if st.button("기록", key=f"b2_{idx}"):
                    trade_data["balance"] -= a2; s['amt1'] += a2; s['memo'] += f" | {m2}"
                    save_data(LOG_FILE, trade_data); save_data(MONITOR_FILE, mon_stocks); st.rerun()
            if c4.button("🔴 매도", key=f"sell_{idx}", use_container_width=True):
                trade_data["balance"] += int(s['amt1'] * (1 + p_rate))
                mon_stocks.pop(idx); save_data(LOG_FILE, trade_data); save_data(MONITOR_FILE, mon_stocks); st.rerun()

st.divider()

# --- 종목 정밀 판독 보드 ---
st.subheader("🔍 종목 정밀 판독 시스템")
with st.container(border=True):
    col1, col2, col3 = st.columns([2, 2, 1])
    t_input = col1.text_input("종목코드", value=st.session_state.auto_code)
    d_input = col2.date_input("분석 날짜", value=datetime.date.today())
    if col3.button("📊 트리플 판독 실행", type="primary", use_container_width=True):
        res, df = analyze_v5(t_input, d_input)
        if res:
            # [복구/수정] 분석 시점에 종목명 매칭하여 로그 기록
            match = krx_df[krx_df['Code'] == t_input]
            disp_name = match['Name'].values[0] if not match.empty else t_input
            analysis_log = [l for l in analysis_log if l['code'] != t_input]
            analysis_log.insert(0, {"name": disp_name, "code": t_input})
            save_data(ANALYSIS_LOG_FILE, analysis_log[:20])

            st.markdown(f"### 🎯 종합 판정: :{res['color']}[{res['tag']}]")
            pc1, pc2, pc3 = st.columns(3)
            with pc1:
                st.write("**[기존 엔진]**")
                st.write(f"캔들 몸통: {res['body']:.1%}")
                st.write(f"수급(거래량): {res['vol_ratio']:.1f}배")
                st.write(f"결과: {'🚀 매수적기' if res['is_orig_buy'] else '🟡 관망'}")
            with pc2:
                st.write("**[수익률 엔진]**")
                st.write(f"횡보응축(CV): {res['cv']:.2f}")
                st.write(f"패턴 유사도: {res['similarity']:.1f}%")
                st.write(f"결과: {'🔥 고승률구간' if res['similarity']>=80 else '🟡 데이터부족'}")
            with pc3:
                st.write("**[종합 매수 지침]**")
                st.write(f"현재가: {res['curr']:,}원")
                st.write(f"손절가: **{res['stop']:,}원**")
                st.write(f"비중 권고: {'강력매수(20%)' if 'S급' in res['tag'] else '분할매수(10%)'}")

            fig = go.Figure(data=[go.Candlestick(x=df.index, open=df['시가'], high=df['고가'], low=df['저가'], close=df['종가'], increasing_line_color='red', decreasing_line_color='blue')])
            fig.add_hline(y=res['t_low'], line_dash="dash", line_color="green", annotation_text="기준저가")
            fig.add_hline(y=res['stop'], line_color="magenta", annotation_text=f"STOP {res['stop']:,}")
            fig.update_layout(height=450, xaxis_rangeslider_visible=False, template="plotly_dark")
            st.plotly_chart(fig, use_container_width=True)
            
            with st.expander("📝 실전 매수 종목으로 등록"):
                amt = st.number_input("매수 금액(원)", value=int(trade_data['balance']*0.1))
                if st.button("🔥 실전 등록"):
                    trade_data["balance"] -= amt
                    mon_stocks.append({"name": disp_name, "code": t_input, "buy_price": res['curr'], "stop": res['stop'], "amt1": amt, "memo": f"유사도:{res['similarity']:.1f}%"})
                    save_data(LOG_FILE, trade_data); save_data(MONITOR_FILE, mon_stocks); st.rerun()

st.subheader("🕒 최근 분석 로그")
if analysis_log:
    cols = st.columns(5)
    for i, log in enumerate(analysis_log[:15]):
        with cols[i % 5]:
            # [수정] 로그 버튼 클릭 시 이름과 코드를 함께 표시하여 직관성 향상
            if st.button(f"{log['name']}\n({log['code']})", key=f"alog_{log['code']}_{i}", use_container_width=True):
                st.session_state.auto_code = log['code']; st.rerun()

st.divider()

# --- 스캐너 섹션 (기능 유지) ---
st.subheader("📡 전 종목 등급 스캐너")
sc1, sc2 = st.columns([1, 4])
if sc1.button("🚀 상위 500개 스캔 시작"):
    if st.session_state.scan_status != "분석 중":
        codes = krx_df.head(500)['Code'].tolist()
        threading.Thread(target=background_scanner, args=(codes,)).start()
        st.session_state.scan_status = "분석 중"
with sc2:
    if st.session_state.scan_status == "분석 중":
        st.progress(st.session_state.scan_progress / 100)
        st.caption(f"📊 {st.session_state.scan_status}")
    elif st.session_state.scan_status == "완료":
        st.success(f"✅ 스캔 완료! 필승 후보 {len(st.session_state.scan_results)}개를 발견했습니다.")

if st.session_state.scan_status == "완료" and st.session_state.scan_results:
    tabs = st.tabs(["💎 S급: 필승합의", "🔭 A급: 선취매형", "⚔️ B급: 단기회전"])
    for i, t_name in enumerate(["S급", "A급", "B급"]):
        with tabs[i]:
            filtered = [r for r in st.session_state.scan_results if t_name in r['tag']]
            if filtered:
                cols = st.columns(5)
                for idx, r in enumerate(filtered[:10]):
                    with cols[idx % 5]:
                        # [수정] 스캔 결과에서도 종목명 매칭 표시
                        m = krx_df[krx_df['Code'] == r['code']]
                        n = m['Name'].values[0] if not m.empty else r['code']
                        if st.button(f"{n}\n({r['similarity']:.0f}%)", key=f"btn_{t_name}_{r['code']}"):
                            st.session_state.auto_code = r['code']; st.rerun()
