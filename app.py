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
from streamlit.runtime.scriptrunner import add_script_run_ctx

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

st.set_page_config(page_title="MSM AI Dual-Engine v5.9.18", layout="wide")

if "auth" not in st.session_state: st.session_state.auth = False
if "auto_code" not in st.session_state: st.session_state.auto_code = ""
if "scan_progress" not in st.session_state: st.session_state.scan_progress = 0
if "scan_status" not in st.session_state: st.session_state.scan_status = "대기 중"
if "scan_results" not in st.session_state: st.session_state.scan_results = []
if "scan_etc" not in st.session_state: st.session_state.scan_etc = ""

# --- 보안 설정 ---
if not st.session_state.auth:
    st.title("💰 MSM Portal v5.9.18")
    pwd = st.text_input("Access Key", type="password", max_chars=4, key="entry_pwd")
    if pwd == "1234": st.session_state.auth = True; st.rerun()
    st.stop()

# --- [수정] 사이드바: 40개 분석 로그 기록 전용 공간 ---
st.sidebar.title("🕒 분석 기록 (Max 40)")
st.sidebar.caption("최근 분석한 종목 리스트입니다.")
for idx, log in enumerate(analysis_log[:40]):
    if st.sidebar.button(f"{log['name']} ({log['code']})", key=f"side_log_{log['code']}_{idx}", use_container_width=True):
        st.session_state.auto_code = log['code']; st.rerun()

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
            step_tag = "1차" if not matching_mon else ("2차" if len(matching_mon)==1 else "3차")
            if similarity >= 85 and is_orig_buy: tag, color = f"💎 필승합의 ({step_tag})", "red"
            elif similarity >= 80: tag, color = f"🚀 급등유력 ({step_tag})", "red"
            else: tag, color = f"⚔️ 단기회전 ({step_tag})", "green"
            is_valid = True
        else:
            tag, color, is_valid = "🟡 관망", "grey", False
        
        return {"code": ticker, "curr": int(curr['종가']), "t_low": int(curr['저가']), "stop": int(curr['저가'] * 0.96), 
                "similarity": similarity, "is_orig_buy": is_orig_buy, "tag": tag, "color": color, 
                "is_valid": is_valid, "cv": cv, "vol_ratio": vol_ratio, "body": curr['BODY_RATIO']}, df
    except: return None, None

def background_scanner(codes):
    results = []
    total = len(codes)
    start_t = time.time()
    for i, c in enumerate(codes):
        try:
            st.session_state.scan_progress = int(((i+1)/total)*100)
            elapsed = time.time() - start_t
            avg = elapsed / (i+1)
            rem = int(avg * (total - (i+1)))
            st.session_state.scan_etc = f"{rem//60}분 {rem%60}초"
            st.session_state.scan_status = f"분석 중: {i+1}/{total} (남은시간: {st.session_state.scan_etc})"
            
            # 실제 분석 함수 호출 (이 부분이 누락되면 즉시 완료됨)
            r, _ = analyze_v5(c, datetime.date.today())
            if r and r['is_valid']: results.append(r)
            time.sleep(0.5) # 실제 스캔 속도감 유지 및 서버 부하 방지
        except: continue
    st.session_state.scan_results = sorted(results, key=lambda x: x['similarity'], reverse=True)
    st.session_state.scan_status = "완료"

# --- 메인 화면 ---
st.title("🖥️ MSM AI Dual-Engine v5.9.18")

# [수정] 종목 정밀 판독 및 검색 강화 (모바일 대응 검색 버튼)
st.subheader("🔍 종목 정밀 판독 및 검색")
with st.container(border=True):
    c_search, c_btn, c_date = st.columns([4, 1, 2])
    
    # 종목명/코드 통합 검색
    search_input = c_search.selectbox("종목명 또는 코드 입력", krx_df['Name'].tolist(), index=None, placeholder="검색할 종목명을 입력하세요")
    d_input = c_date.date_input("분석 날짜", value=datetime.date.today(), label_visibility="collapsed")
    
    # 모바일 엔터 대신 사용할 검색 버튼
    if c_btn.button("🔍 검색/분석", type="primary", use_container_width=True) or search_input:
        if search_input:
            t_code = krx_df[krx_df['Name'] == search_input]['Code'].values[0]
            st.session_state.auto_code = t_code
            
            res, df = analyze_v5(t_code, d_input)
            if res:
                # 로그 기록 (40개까지 유지)
                analysis_log = [l for l in analysis_log if l['code'] != t_code]
                analysis_log.insert(0, {"name": search_input, "code": t_code})
                save_data(ANALYSIS_LOG_FILE, analysis_log[:40])

                st.markdown(f"### 🎯 {search_input} 판정: :{res['color']}[{res['tag']}]")
                pc1, pc2, pc3 = st.columns(3)
                with pc1:
                    st.write("**[엔진 판독]** 유사도", f"{res['similarity']:.1f}%")
                with pc2:
                    st.write("**[3분할 지침]**", f"{res['tag']}")
                with pc3:
                    st.write("**[데드라인]**", f"{res['stop']:,}원")

                fig = go.Figure(data=[go.Candlestick(x=df.index, open=df['시가'], high=df['고가'], low=df['저가'], close=df['종가'], increasing_line_color='red', decreasing_line_color='blue')])
                fig.add_hline(y=res['t_low'], line_dash="dash", line_color="green", annotation_text="기준")
                fig.add_hline(y=res['stop'], line_color="#BF40BF", annotation_text="손절", line_width=2)
                fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
                fig.update_layout(height=450, xaxis_rangeslider_visible=False, template="plotly_dark")
                st.plotly_chart(fig, use_container_width=True)
                
                # 정밀 리포트 (유지)
                with st.container(border=True):
                    st.markdown("#### 📝 AI 상세 분석 및 예측 리포트")
                    r1, r2 = st.columns(2)
                    with r1:
                        st.write(f"**모멘텀**: {res['vol_ratio']:.1f}배 / **응축도**: {res['cv']:.2f}")
                    with r2:
                        st.write(f"**예상 매수구간**: {int(res['t_low']):,}원 부근")
                        if st.button("🔥 실전 매수 리스트 등록"):
                            mon_stocks.append({"name": search_input, "code": t_code, "buy_price": res['curr'], "memo": f"{res['tag']}"})
                            save_data(MONITOR_FILE, mon_stocks); st.rerun()

st.divider()

# --- [스캐너] 정상화 (실제 분석 수행) ---
st.subheader("📡 고가속 종목 스캐너 (Top 500)")
sc1, sc2 = st.columns([1, 4])
if sc1.button("🚀 스캔 시작"):
    if st.session_state.scan_status != "분석 중":
        codes = krx_df.head(500)['Code'].tolist()
        st.session_state.scan_status = "분석 중"
        thread = threading.Thread(target=background_scanner, args=(codes,))
        add_script_run_ctx(thread)
        thread.start()
with sc2:
    if st.session_state.scan_status == "분석 중":
        st.progress(st.session_state.scan_progress / 100)
        st.caption(f"📊 {st.session_state.scan_status}")
    elif st.session_state.scan_status == "완료":
        st.success(f"✅ 발견: {len(st.session_state.scan_results)}개")

if st.session_state.scan_status == "완료" and st.session_state.scan_results:
    tabs = st.tabs(["💎 S급", "⚔️ B급"])
    with tabs[0]:
        f1 = [r for r in st.session_state.scan_results if "S" in r['tag']]
        cols = st.columns(5)
        for idx, r in enumerate(f1[:15]):
            m = krx_df[krx_df['Code'] == r['code']]; n = m['Name'].values[0] if not m.empty else r['code']
            if cols[idx%5].button(f"{n}\n({r['similarity']:.0f}%)", key=f"sc_{r['code']}"):
                st.session_state.auto_code = r['code']; st.rerun()
