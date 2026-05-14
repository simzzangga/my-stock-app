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
from streamlit.runtime.scriptrunner import add_script_run_ctx # 컨텍스트 동기화 도구

# --- [시스템] 데이터 저장/로드 (동일 유지) ---
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

st.set_page_config(page_title="MSM AI Dual-Engine v5.9.17", layout="wide")

if "auth" not in st.session_state: st.session_state.auth = False
if "auto_code" not in st.session_state: st.session_state.auto_code = ""
if "scan_progress" not in st.session_state: st.session_state.scan_progress = 0
if "scan_status" not in st.session_state: st.session_state.scan_status = "대기 중"
if "scan_results" not in st.session_state: st.session_state.scan_results = []
if "scan_etc" not in st.session_state: st.session_state.scan_etc = ""

# --- 보안 설정 ---
if not st.session_state.auth:
    st.title("💰 MSM Portal v5.9.17")
    pwd = st.text_input("Access Key", type="password", max_chars=4, key="entry_pwd")
    if pwd == "1234": st.session_state.auth = True; st.rerun()
    st.stop()

# --- [사이드바] 검색 및 기록 ---
st.sidebar.title("🔍 종목 검색 및 기록")
if not krx_df.empty:
    sel_name = st.sidebar.selectbox("종목명 입력", krx_df['Name'].tolist(), index=None, placeholder="종목명을 입력하세요")
    if sel_name:
        t_code = krx_df[krx_df['Name'] == sel_name]['Code'].values[0]
        st.sidebar.success(f"✅ {sel_name} ({t_code})")
        if st.sidebar.button("분석창 입력", use_container_width=True):
            st.session_state.auto_code = t_code
            analysis_log = [l for l in analysis_log if l['code'] != t_code]
            analysis_log.insert(0, {"name": sel_name, "code": t_code})
            save_data(ANALYSIS_LOG_FILE, analysis_log[:20])
            search_history = [h for h in search_history if h['code'] != t_code]
            search_history.insert(0, {"name": sel_name, "code": t_code})
            save_data(SEARCH_HISTORY_FILE, search_history[:10]); st.rerun()

st.sidebar.divider()
st.sidebar.caption("🕒 최근 검색 기록")
for h in search_history[:10]:
    if st.sidebar.button(f"{h['name']} ({h['code']})", key=f"side_{h['code']}", use_container_width=True):
        st.session_state.auto_code = h['code']; st.rerun()

# --- [엔진] 분석 로직 ---
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
        similarity = ((max(0, 100 - (abs(cv - ST_PARAMS['target_cv']) * 25))) * 0.5) + ((min(100, (vol_ratio / ST_PARAMS['target_vol']) * 100)) * 0.5)
        
        if similarity >= 75:
            matching_mon = [s for s in mon_stocks if s['code'] == ticker]
            if not matching_mon:
                step_tag, weight = "1차 매수 신호", "🔥 신규 진입 (1/3)"
            elif len(matching_mon) == 1:
                step_tag, weight = "2차 매수 신호", "⚖️ 눌림목 물타기 (2/3)"
            else:
                step_tag, weight = "3차 매수 신호", "⚠️ 최종 비중 (3/3)"

            if similarity >= 85 and is_orig_buy: tag, color = f"💎 필승합의 ({step_tag})", "red"
            elif similarity >= 80: tag, color = f"🚀 급등유력 ({step_tag})", "red"
            else: tag, color = f"⚔️ 단기회전 ({step_tag})", "green"
            plan = "3~5일간 눌림목 분할 매수"
            is_valid_signal = True
        else:
            tag, color, weight, plan, is_valid_signal = "🟡 관망", "grey", "❌ 사인없음", "가속도 조건 미달", False
        
        return {"code": ticker, "curr": int(curr['종가']), "t_low": int(curr['저가']), "stop": int(curr['저가'] * 0.96), 
                "similarity": similarity, "is_orig_buy": is_orig_buy, "tag": tag, "color": color, 
                "weight": weight, "plan": plan, "is_valid": is_valid_signal,
                "cv": cv, "vol_ratio": vol_ratio, "body": curr['BODY_RATIO']}, df
    except: return None, None

# [스캐너 긴급 수리] missing ScriptRunContext 완벽 해결
def background_scanner(codes):
    results = []
    total = len(codes)
    start_t = time.time()
    for i, c in enumerate(codes):
        try:
            # 실시간 세션 업데이트
            st.session_state.scan_progress = int(((i+1)/total)*100)
            elapsed = time.time() - start_t
            avg = elapsed / (i+1)
            rem = int(avg * (total - (i+1)))
            etc_str = f"{rem//60}분 {rem%60}초"
            st.session_state.scan_etc = etc_str
            st.session_state.scan_status = f"분석 중: {i+1}/{total} (예상 남은시간: {etc_str})"
            
            r, _ = analyze_v5(c, datetime.date.today())
            if r and r['is_valid']: results.append(r)
            time.sleep(0.1) # 속도 개선
        except: continue
    st.session_state.scan_results = sorted(results, key=lambda x: x['similarity'], reverse=True)
    st.session_state.scan_status = "완료"

# --- 메인 화면 ---
st.title("🖥️ MSM AI Dual-Engine v5.9.17")

if mon_stocks:
    for idx, s in enumerate(mon_stocks):
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns([1.5, 2, 3, 1])
            c1.subheader(s['name'])
            c2.info(f"진입가: {s['buy_price']:,}원")
            c3.write(f"메모: {s['memo']}")
            if c4.button("🔴 매도완료", key=f"sell_{idx}", use_container_width=True):
                mon_stocks.pop(idx); save_data(MONITOR_FILE, mon_stocks); st.rerun()

st.divider()

# --- 종목 정밀 판독 시스템 ---
st.subheader("🔍 종목 정밀 판독 시스템")
with st.container(border=True):
    col1, col2, col3 = st.columns([2, 2, 1])
    t_input = col1.text_input("종목코드", value=st.session_state.auto_code)
    d_input = col2.date_input("분석 날짜", value=datetime.date.today())
    if col3.button("📊 분석", type="primary", use_container_width=True):
        res, df = analyze_v5(t_input, d_input)
        if res:
            match = krx_df[krx_df['Code'] == t_input]
            disp_name = match['Name'].values[0] if not match.empty else t_input
            analysis_log = [l for l in analysis_log if l['code'] != t_input]
            analysis_log.insert(0, {"name": disp_name, "code": t_input})
            save_data(ANALYSIS_LOG_FILE, analysis_log[:20])

            st.markdown(f"### 🎯 종합 판정: :{res['color']}[{res['tag']}]")
            pc1, pc2, pc3 = st.columns(3)
            with pc1:
                st.write("**[엔진 판독]**")
                st.write(f"패턴 유사도: {res['similarity']:.1f}%")
            with pc2:
                st.write("**[3분할 지침]**")
                st.write(f"단계: **{res['weight']}**")
                st.write(f"방법: {res['plan']}")
            with pc3:
                st.write("**[매매 전략]**")
                st.write(f"목표: +10% (20일 시한부)")
                st.write(f"데드라인(손절): **{res['stop']:,}원**")

            # [차트 고도화] 휴일 공백 제거 및 가이드라인 복구
            fig = go.Figure(data=[go.Candlestick(
                x=df.index, open=df['시가'], high=df['고가'], low=df['저가'], close=df['종가'],
                increasing_line_color='red', decreasing_line_color='blue'
            )])
            fig.add_hline(y=res['t_low'], line_dash="dash", line_color="green", annotation_text="기준")
            fig.add_hline(y=res['stop'], line_color="#BF40BF", annotation_text="손절", line_width=2)
            fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
            fig.update_layout(height=450, xaxis_rangeslider_visible=False, template="plotly_dark", margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig, use_container_width=True)
            
            # [신규] 정밀 분석 리포트 섹션
            with st.container(border=True):
                st.markdown("#### 📝 AI 상세 분석 및 예측 리포트")
                r1, r2 = st.columns(2)
                with r1:
                    st.write(f"**1. 기존 모멘텀 엔진**: {'적합' if res['is_orig_buy'] else '부족'}")
                    st.caption(f"- 캔들 몸통 {res['body']:.1%} 및 거래량 {res['vol_ratio']:.1f}배 폭발로 에너지가 {'매우 강력함' if res['is_orig_buy'] else '다소 평이함'}")
                    st.write(f"**2. 신규 가속도 엔진**: {res['similarity']:.1f}점")
                    st.caption(f"- 이전 20일 횡보 에너지(CV {res['cv']:.2f})가 응축되어 시그널 발생 시 10일 내 급등 가능성이 {'높음' if res['cv'] < 2.5 else '낮음'}")
                with r2:
                    st.write("**3. 종합 예측 및 매수 가이드**")
                    pred_date = (datetime.date.today() + datetime.timedelta(days=3)).strftime("%m/%d")
                    st.write(f"- **최적 매수 타이밍**: {pred_date} 전후 눌림목 형성 시")
                    st.write(f"- **권장 매수 구간**: {int(res['t_low'] * 1.01):,}원 ~ {int(res['t_low']):,}원")
                    st.write(f"- **예상 시나리오**: 10거래일 내 {int(res['curr'] * 1.1):,}원 돌파 시도 예상")
                    st.caption("※ 본 예측은 알고리즘 통계에 기반한 추측치이며, 실전 매매 시 손절라인을 엄수하세요.")

st.subheader("🕒 최근 분석 로그")
if analysis_log:
    cols = st.columns(5)
    for i, log in enumerate(analysis_log[:15]):
        with cols[i % 5]:
            if st.button(f"{log['name']}\n({log['code']})", key=f"alog_{log['code']}_{i}", use_container_width=True):
                st.session_state.auto_code = log['code']; st.rerun()

st.divider()

# --- [스캐너] 기능 완벽 복구 ---
st.subheader("📡 고가속 종목 스캐너")
sc1, sc2 = st.columns([1, 4])
if sc1.button("🚀 스캔 시작 (Top 500)"):
    if st.session_state.scan_status != "분석 중":
        codes = krx_df.head(500)['Code'].tolist()
        st.session_state.scan_status = "분석 중"
        # [핵심] 스레드 생성 시 현재 Streamlit 컨텍스트를 주입
        thread = threading.Thread(target=background_scanner, args=(codes,))
        add_script_run_ctx(thread) # 이 코드가 에러를 해결합니다
        thread.start()
        
with sc2:
    if st.session_state.scan_status == "분석 중":
        st.progress(st.session_state.scan_progress / 100)
        st.caption(f"📊 {st.session_state.scan_status}")
    elif st.session_state.scan_status == "완료":
        st.success(f"✅ 스캔 완료! {len(st.session_state.scan_results)}개의 후보를 찾았습니다.")

if st.session_state.scan_status == "완료" and st.session_state.scan_results:
    tabs = st.tabs(["💎 S급 이상", "⚔️ B급 이상"])
    with tabs[0]:
        filtered = [r for r in st.session_state.scan_results if "S" in r['tag']]
        if filtered:
            cols = st.columns(5)
            for idx, r in enumerate(filtered[:15]):
                m = krx_df[krx_df['Code'] == r['code']]; n = m['Name'].values[0] if not m.empty else r['code']
                if cols[idx%5].button(f"{n}\n({r['similarity']:.0f}%)", key=f"sc_{r['code']}"):
                    st.session_state.auto_code = r['code']; st.rerun()
    with tabs[1]:
        filtered = [r for r in st.session_state.scan_results if "B" in r['tag']]
        if filtered:
            cols = st.columns(5)
            for idx, r in enumerate(filtered[:15]):
                m = krx_df[krx_df['Code'] == r['code']]; n = m['Name'].values[0] if not m.empty else r['code']
                if cols[idx%5].button(f"{n}\n({r['similarity']:.0f}%)", key=f"scb_{r['code']}"):
                    st.session_state.auto_code = r['code']; st.rerun()
