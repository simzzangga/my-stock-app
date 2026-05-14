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

@st.cache_data(ttl=3600) # 캐시 시간 단축 (데이터 꼬임 방지)
def get_krx_list():
    try:
        df = fdr.StockListing('KRX')
        return df[['Code', 'Name']]
    except: return pd.DataFrame(columns=['Code', 'Name'])

krx_df = get_krx_list()
analysis_log = load_data(ANALYSIS_LOG_FILE, [])
mon_stocks = load_data(MONITOR_FILE, [])
ST_PARAMS = {"target_cv": 1.8, "target_vol": 10.0}

st.set_page_config(page_title="MSM AI Dual-Engine v5.9.20", layout="wide")

# 세션 상태 강제 초기화
if "auth" not in st.session_state: st.session_state.auth = False
if "auto_code" not in st.session_state: st.session_state.auto_code = ""
if "scanning" not in st.session_state: st.session_state.scanning = False
if "scan_progress" not in st.session_state: st.session_state.scan_progress = 0
if "scan_status" not in st.session_state: st.session_state.scan_status = "대기 중"
if "scan_results" not in st.session_state: st.session_state.scan_results = []
if "scan_etc" not in st.session_state: st.session_state.scan_etc = ""

# --- 보안 설정 ---
if not st.session_state.auth:
    st.title("💰 MSM Portal v5.9.20")
    pwd = st.text_input("Access Key", type="password", max_chars=4, key="entry_pwd")
    if pwd == "1234": st.session_state.auth = True; st.rerun()
    st.stop()

# --- [사이드바] 분석 기록 (Max 40) ---
st.sidebar.title("🕒 분석 기록 (Max 40)")
for idx, log in enumerate(analysis_log[:40]):
    if st.sidebar.button(f"{log['name']} ({log['code']})", key=f"side_log_{idx}", use_container_width=True):
        st.session_state.auto_code = log['code']; st.rerun()

# --- [엔진] 듀얼 분석 로직 (캐시 없이 실시간 데이터 강제 호출) ---
def analyze_v5_live(ticker, base_date):
    try:
        # 캐시를 타지 않는 실시간 호출
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
            step = "1차" if not matching_mon else ("2차" if len(matching_mon)==1 else "3차")
            tag, color, is_valid = (f"💎 필승합의 ({step})", "red", True) if similarity >= 85 and is_orig_buy else (f"🚀 급등유력 ({step})", "red", True) if similarity >= 80 else (f"⚔️ 단기회전 ({step})", "green", True)
        else: tag, color, is_valid = "🟡 관망", "grey", False
        
        return {"code": ticker, "curr": int(curr['종가']), "t_low": int(curr['저가']), "stop": int(curr['저가'] * 0.96), 
                "similarity": similarity, "is_orig_buy": is_orig_buy, "tag": tag, "color": color, 
                "is_valid": is_valid, "cv": cv, "vol_ratio": vol_ratio, "body": curr['BODY_RATIO']}, df
    except: return None, None

# [스캐너 재설계] 실시간 상태 갱신형
def real_time_scanner(codes, current_date):
    results = []
    total = len(codes)
    start_time = time.time()
    
    for i, code in enumerate(codes):
        try:
            # 현재 어떤 종목을 분석 중인지 이름을 가져와서 상태창에 표시
            name_match = krx_df[krx_df['Code'] == code]['Name'].values
            current_name = name_match[0] if len(name_match) > 0 else code
            
            # 진행률 및 ETC 계산
            progress = int(((i + 1) / total) * 100)
            elapsed = time.time() - start_time
            avg = elapsed / (i + 1)
            rem = int(avg * (total - (i + 1)))
            etc = f"{rem // 60}분 {rem % 60}초"
            
            # 세션 상태 강제 업데이트
            st.session_state.scan_progress = progress
            st.session_state.scan_etc = etc
            st.session_state.scan_status = f"[{progress}%] 분석 중: {current_name} ({i+1}/{total})"
            
            # 실시간 분석 엔진 호출
            r, _ = analyze_v5_live(code, current_date)
            if r and r['is_valid']:
                results.append(r)
            
            # 분석 간격 유지 (초당 약 2~3종목 분석)
            time.sleep(0.4) 
        except: continue
            
    st.session_state.scan_results = sorted(results, key=lambda x: x['similarity'], reverse=True)
    st.session_state.scan_status = "완료"
    st.session_state.scanning = False

# --- 메인 화면 ---
st.title("🖥️ MSM AI Dual-Engine v5.9.20")

# [검색 및 분석]
st.subheader("🔍 종목 정밀 판독 시스템")
with st.container(border=True):
    c1, c2, c3 = st.columns([4, 1, 2])
    search_term = c1.selectbox("종목명 검색", krx_df['Name'].tolist(), index=None, placeholder="분석할 종목명을 선택하세요")
    d_input = c3.date_input("분석 기준일", value=datetime.date.today())
    
    if c2.button("🔍 분석", type="primary", use_container_width=True) or search_term:
        if search_term:
            target_code = krx_df[krx_df['Name'] == search_term]['Code'].values[0]
            st.session_state.auto_code = target_code
            res, df = analyze_v5_live(target_code, d_input)
            if res:
                # 분석 로그 저장 (40개)
                analysis_log = [l for l in load_data(ANALYSIS_LOG_FILE, []) if l['code'] != target_code]
                analysis_log.insert(0, {"name": search_term, "code": target_code})
                save_data(ANALYSIS_LOG_FILE, analysis_log[:40])

                st.markdown(f"### 🎯 {search_term} ({target_code}) 판정: :{res['color']}[{res['tag']}]")
                pc1, pc2, pc3 = st.columns(3)
                pc1.metric("패턴 유사도", f"{res['similarity']:.1f}%")
                pc2.metric("지침", res['tag'])
                pc3.metric("손절 데드라인", f"{res['stop']:,}원")

                fig = go.Figure(data=[go.Candlestick(x=df.index, open=df['시가'], high=df['고가'], low=df['저가'], close=df['종가'], 
                                                     increasing_line_color='red', decreasing_line_color='blue')])
                fig.add_hline(y=res['t_low'], line_dash="dash", line_color="green", annotation_text="기준")
                fig.add_hline(y=res['stop'], line_color="#BF40BF", annotation_text="손절", line_width=2)
                fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
                fig.update_layout(height=450, xaxis_rangeslider_visible=False, template="plotly_dark")
                st.plotly_chart(fig, use_container_width=True)

st.divider()

# --- [스캐너] 실시간 갱신형 로직 ---
st.subheader("📡 고가속 종목 스캐너 (Top 500)")
s_col1, s_col2 = st.columns([1, 4])

if s_col1.button("🚀 스캔 시작", use_container_width=True):
    if not st.session_state.scanning:
        # 스캔 시작 시 기존 결과 강제 삭제
        st.session_state.scan_results = []
        st.session_state.scanning = True
        st.session_state.scan_status = "데이터 동기화 중..."
        
        codes_to_scan = krx_df.head(500)['Code'].tolist()
        scan_thread = threading.Thread(target=real_time_scanner, args=(codes_to_scan, datetime.date.today()))
        add_script_run_ctx(scan_thread)
        scan_thread.start()

with s_col2:
    if st.session_state.scanning:
        st.progress(st.session_state.scan_progress / 100)
        st.write(f"📊 **{st.session_state.scan_status}**")
        st.caption(f"⏱️ 예상 남은 시간: {st.session_state.scan_etc}")
    elif st.session_state.scan_status == "완료":
        st.success(f"✅ 스캔 완료! {len(st.session_state.scan_results)}개의 유망 종목 발견")

if st.session_state.scan_status == "완료" and st.session_state.scan_results:
    t1, t2 = st.tabs(["💎 S급 리스트", "⚔️ B급 리스트"])
    with t1:
        s_list = [r for r in st.session_state.scan_results if "S" in r['tag']]
        cols = st.columns(5)
        for idx, r in enumerate(s_list[:15]):
            m = krx_df[krx_df['Code'] == r['code']]; name = m['Name'].values[0] if not m.empty else r['code']
            if cols[idx % 5].button(f"{name}\n({r['similarity']:.0f}%)", key=f"s_res_{idx}"):
                st.session_state.auto_code = r['code']; st.rerun()
