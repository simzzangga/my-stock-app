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

# --- [시스템] 데이터 로드 로직 보강 ---
LOG_FILE, MONITOR_FILE = "trade_v5_log.json", "monitoring_v5.json"
ANALYSIS_LOG_FILE = "analysis_log_v5.json"

def load_data(file_path, default_val):
    try:
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f: return json.load(f)
    except: pass
    return default_val

def save_data(file_path, data):
    with open(file_path, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=4)

# [긴급 수정] KRX 서버 장애 대비 예외 처리 추가
@st.cache_data(ttl=3600)
def get_krx_list():
    try:
        df = fdr.StockListing('KRX')
        if df is None or df.empty:
            raise ValueError("Empty Data")
        return df[['Code', 'Name']]
    except Exception as e:
        # 서버 장애 시 안내 메시지 출력 및 빈 데이터프레임 반환하여 크래시 방지
        st.error(f"⚠️ KRX 서버 응답 지연 발생 (종목 리스트를 가져올 수 없습니다). 잠시 후 새로고침 하세요.")
        return pd.DataFrame(columns=['Code', 'Name'])

# 데이터 초기화
krx_df = get_krx_list()
analysis_log = load_data(ANALYSIS_LOG_FILE, [])
mon_stocks = load_data(MONITOR_FILE, [])
ST_PARAMS = {"target_cv": 1.8, "target_vol": 10.0}

st.set_page_config(page_title="MSM AI Engine v5.9.22", layout="wide")

# 세션 상태 (스캐너 제어 전용)
if "auth" not in st.session_state: st.session_state.auth = False
if "auto_code" not in st.session_state: st.session_state.auto_code = ""
if "scan_status" not in st.session_state: st.session_state.scan_status = "대기"
if "scan_progress" not in st.session_state: st.session_state.scan_progress = 0
if "scan_results" not in st.session_state: st.session_state.scan_results = []
if "scan_etc" not in st.session_state: st.session_state.scan_etc = ""

# --- 보안 설정 ---
if not st.session_state.auth:
    pwd = st.text_input("Access Key", type="password", key="entry_pwd")
    if pwd == "1234": st.session_state.auth = True; st.rerun()
    st.stop()

# --- 사이드바 및 엔진 로직 (v5.9.21 유지) ---
st.sidebar.title("🕒 분석 기록 (Max 40)")
for idx, log in enumerate(analysis_log[:40]):
    if st.sidebar.button(f"{log['name']} ({log['code']})", key=f"side_log_{idx}", use_container_width=True):
        st.session_state.auto_code = log['code']; st.rerun()

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
            step = "1차" if not matching_mon else ("2차" if len(matching_mon)==1 else "3차")
            tag, color, is_valid = (f"💎 필승합의 ({step})", "red", True) if similarity >= 85 and is_orig_buy else (f"🚀 급등유력 ({step})", "red", True) if similarity >= 80 else (f"⚔️ 단기회전 ({step})", "green", True)
            plan = "3~5일간 눌림목 분할 매수"
        else:
            tag, color, plan, is_valid = "🟡 관망", "grey", "조건 미달", False
        
        return {"code": ticker, "curr": int(curr['종가']), "t_low": int(curr['저가']), "stop": int(curr['저가'] * 0.96), 
                "similarity": similarity, "is_orig_buy": is_orig_buy, "tag": tag, "color": color, 
                "plan": plan, "is_valid": is_valid, "cv": cv, "vol_ratio": vol_ratio, "body": curr['BODY_RATIO']}, df
    except: return None, None

def run_stable_scanner(codes, current_date):
    results = []
    total = len(codes)
    start_time = time.time()
    for i, code in enumerate(codes):
        try:
            st.session_state.scan_progress = int(((i + 1) / total) * 100)
            st.session_state.scan_status = f"분석 중: {i+1}/{total}"
            elapsed = time.time() - start_time
            avg = elapsed / (i + 1)
            rem = int(avg * (total - (i + 1)))
            st.session_state.scan_etc = f"{rem // 60}분 {rem % 60}초"
            r, _ = analyze_v5(code, current_date)
            if r and r['is_valid']: results.append(r)
            time.sleep(0.3)
        except: continue
    st.session_state.scan_results = sorted(results, key=lambda x: x['similarity'], reverse=True)
    st.session_state.scan_status = "완료"

# --- 메인 화면 UI ---
st.title("🖥️ MSM AI Dual-Engine v5.9.22")

# [검색창] 종목 리스트가 비어있을 때를 위한 처리
st.subheader("🔍 종목 정밀 판독 시스템")
with st.container(border=True):
    c1, c2, c3 = st.columns([4, 1, 2])
    # 서버 에러 시 텍스트 입력으로라도 분석 가능하게 함
    if not krx_df.empty:
        search_term = c1.selectbox("종목명 검색", krx_df['Name'].tolist(), index=None, placeholder="종목명을 선택하세요")
    else:
        search_term = c1.text_input("종목코드 직접 입력 (서버 지연 시)", placeholder="예: 005930")
        
    d_input = c3.date_input("분석 기준일", value=datetime.date.today())
    
    if c2.button("🔍 분석", type="primary", use_container_width=True):
        if search_term:
            # 종목명에서 코드를 추출하거나 직접 입력된 코드 사용
            if not krx_df.empty and search_term in krx_df['Name'].tolist():
                target_code = krx_df[krx_df['Name'] == search_term]['Code'].values[0]
                display_name = search_term
            else:
                target_code = search_term
                display_name = search_term
            
            st.session_state.auto_code = target_code
            res, df = analyze_v5(target_code, d_input)
            if res:
                # 로그 저장
                analysis_log = [l for l in load_data(ANALYSIS_LOG_FILE, []) if l['code'] != target_code]
                analysis_log.insert(0, {"name": display_name, "code": target_code})
                save_data(ANALYSIS_LOG_FILE, analysis_log[:40])
                
                st.markdown(f"### 🎯 {display_name} ({target_code}) 판정: :{res['color']}[{res['tag']}]")
                pc1, pc2, pc3 = st.columns(3); pc1.metric("유사도", f"{res['similarity']:.1f}%"); pc2.metric("지침", res['tag']); pc3.metric("손절가", f"{res['stop']:,}원")
                fig = go.Figure(data=[go.Candlestick(x=df.index, open=df['시가'], high=df['고가'], low=df['저가'], close=df['종가'], increasing_line_color='red', decreasing_line_color='blue')])
                fig.add_hline(y=res['t_low'], line_dash="dash", line_color="green", annotation_text="기준"); fig.add_hline(y=res['stop'], line_color="#BF40BF", annotation_text="손절", line_width=2)
                fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])]); fig.update_layout(height=400, xaxis_rangeslider_visible=False, template="plotly_dark")
                st.plotly_chart(fig, use_container_width=True)

st.divider()

# --- [스캐너] ---
st.subheader("📡 고가속 종목 스캐너 (Top 500)")
sc1, sc2 = st.columns([1, 4])
if sc1.button("🚀 스캔 시작", use_container_width=True):
    if not krx_df.empty:
        st.session_state.scan_results = []
        st.session_state.scan_status = "준비 중..."
        codes = krx_df.head(500)['Code'].tolist()
        t = threading.Thread(target=run_stable_scanner, args=(codes, datetime.date.today()))
        add_script_run_ctx(t)
        t.start()
    else:
        st.warning("⚠️ 종목 리스트가 없어 스캐너를 실행할 수 없습니다. 서버가 정상화될 때까지 기다려주세요.")

with sc2:
    if st.session_state.scan_status != "완료" and st.session_state.scan_status != "대기":
        st.progress(st.session_state.scan_progress / 100)
        st.write(f"📊 {st.session_state.scan_status} | ⏳ 남은 시간: {st.session_state.scan_etc}")
    elif st.session_state.scan_status == "완료":
        st.success(f"✅ 스캔 완료!")
