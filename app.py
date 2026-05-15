import streamlit as st
import FinanceDataReader as fdr
import yfinance as yf
import pandas as pd
import numpy as np
import datetime
import json
import os
import plotly.graph_objects as go
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- [1. 시스템 설정 및 영속성 함수] ---
SCAN_RESULT_FILE = "last_scan_results.json"
ANALYSIS_LOG_FILE, BACKUP_KRX_FILE = "analysis_log_v5.json", "backup_krx.json"

# 세션 상태 초기화
if "scan_storage" not in st.session_state:
    if os.path.exists(SCAN_RESULT_FILE):
        try:
            with open(SCAN_RESULT_FILE, "r", encoding="utf-8") as f:
                st.session_state.scan_storage = json.load(f)
        except: st.session_state.scan_storage = []
    else: st.session_state.scan_storage = []

if "auto_code" not in st.session_state: st.session_state.auto_code = ""
if "server_status" not in st.session_state: st.session_state.server_status = "🛰️ 엔진 점화 중..."
if "last_viewed" not in st.session_state: st.session_state.last_viewed = None

def load_data(file_path, default_val):
    try:
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f: return json.load(f)
    except: pass
    return default_val

def save_data(file_path, data):
    try:
        with open(file_path, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=4)
    except: pass

@st.cache_data(ttl=3600, show_spinner=False)
def get_krx_list_ultimate():
    if os.path.exists(BACKUP_KRX_FILE):
        try:
            df_l = pd.read_json(BACKUP_KRX_FILE)
            if not df_l.empty:
                st.session_state.server_status = "🔥 출격 준비 완료 (LOCAL FAST)"
                return df_l
        except: pass
    
    try:
        df = fdr.StockListing('KRX')[['Code', 'Name']]
        df['Code'] = df['Code'].astype(str).str.zfill(6)
        df.to_json(BACKUP_KRX_FILE)
        st.session_status = "🔥 출격 준비 완료 (SERVER LIVE)"
        return df
    except:
        return pd.DataFrame([{"Code": "005930", "Name": "삼성전자"}])

# --- [2. 엔진: v5.9.73 무결성 로직 보존] ---
def analyze_v5_engine(ticker, target_date):
    df = None
    ticker_str = str(ticker).zfill(6)
    start_date = target_date - datetime.timedelta(days=240) 
    try:
        df = fdr.DataReader(ticker_str, start_date, target_date)
        if df is not None and not df.empty:
            df.columns = [c.upper() for c in df.columns]
            rename_dict = {'시가':'OPEN','고가':'HIGH','저가':'LOW','종가':'CLOSE','거래량':'VOLUME'}
            df = df.rename(columns={k: v for k, v in rename_dict.items() if k in df.columns})
    except: pass

    if df is None or df.empty:
        try:
            yf_ticker = f"{ticker_str}.KS" if ticker_str.startswith(('0', '1')) else f"{ticker_str}.KQ"
            df_yf = yf.download(yf_ticker, start=start_date, end=target_date + datetime.timedelta(days=1), progress=False)
            if not df_yf.empty:
                if isinstance(df_yf.columns, pd.MultiIndex): df_yf.columns = df_yf.columns.get_level_values(0)
                df_yf.columns = [c.upper() for c in df_yf.columns]
                df = df_yf.rename(columns={'ADJ CLOSE': 'CLOSE'})[['OPEN', 'HIGH', 'LOW', 'CLOSE', 'VOLUME']]
        except: pass

    if df is None or df.empty: return None, None
    
    body_ratio_val = (df['CLOSE'] - df['OPEN']).abs() / (df['HIGH'] - df['LOW'] + 0.001)
    df['BODY_RATIO'] = body_ratio_val
    curr = df.iloc[-1]
    vol_ratio = curr['VOLUME'] / (df['VOLUME'].iloc[-21:-1].mean() + 1)
    pre_20 = df.iloc[-21:-1]
    cv_val = (pre_20['CLOSE'].std() / pre_20['CLOSE'].mean()) * 100
    
    similarity = ((max(0, 100 - (abs(cv_val - 1.8) * 20))) * 0.3) + ((min(100, (vol_ratio / 5.0) * 100)) * 0.7)
    raw_exp = (vol_ratio * 2.5) + (similarity * 0.1)
    phase, weight_now, exp_profit = "🟡 관망", 0, 0
    
    if similarity >= 85 and vol_ratio >= 5.0 and curr['BODY_RATIO'] >= 0.7:
        phase, weight_now, exp_profit = "🔥 3차: 강력매수", 50, round(raw_exp + 5.0 - 2.0, 2)
    elif similarity >= 78 and vol_ratio >= 4.0:
        phase, weight_now, exp_profit = "🚀 2차: 추가매수", 30, round(raw_exp - 2.0, 2)
    elif similarity >= 70 and vol_ratio >= 3.0:
        phase, weight_now, exp_profit = "⚔️ 1차: 신규진입", 20, round(max(8.0, raw_exp * 0.8) - 2.0, 2)
    
    fit_score = 0
    if 82.5 <= similarity <= 88.0: fit_score += 30
    if 2.8 <= vol_ratio <= 4.2: fit_score += 30
    if 1.5 <= cv_val <= 2.2: fit_score += 25
    if 0.65 <= curr['BODY_RATIO'] <= 0.85: fit_score += 15
    
    return {
        "종목코드": ticker_str, "현재가": int(curr['CLOSE']), "유사도": round(similarity, 1),
        "상태": phase, "비중": f"{weight_now}%", "예상수익": f"{exp_profit}%",
        "목표가": int(curr['CLOSE'] * (1 + exp_profit/100)), "손절가": int(curr['CLOSE'] * 0.95), 
        "거래량비": round(vol_ratio, 1), "CV": round(cv_val, 2), "몸통비율": round(curr['BODY_RATIO'], 2),
        "적합도": fit_score, "is_valid": True if weight_now > 0 else False,
        "스캔날짜": target_date.strftime('%Y-%m-%d')
    }, df

# --- [3. UI 레이아웃] ---
st.set_page_config(page_title="🔥 Phoenix Parallel v5.9.80", layout="wide")

krx_df = get_krx_list_ultimate()
krx_df['Display'] = krx_df['Code'] + " | " + krx_df['Name']

c_head1, c_head2 = st.columns([6, 2])
with c_head1: st.markdown(f"### 🔥 Phoenix Parallel v5.9.80 | `{st.session_state.server_status}`")
with c_head2:
    if st.button("🔄 리스트 동기화", use_container_width=True):
        if os.path.exists(BACKUP_KRX_FILE): os.remove(BACKUP_KRX_FILE)
        st.cache_data.clear(); st.rerun()

# [사이드바 Fix] 삭제 없는 고정 리스트
st.sidebar.title("📁 Phoenix History")
analysis_log = load_data(ANALYSIS_LOG_FILE, [])
for idx, log in enumerate(analysis_log[:20]): 
    if st.sidebar.button(f"{log['name']} ({log['code']})", key=f"side_{log['code']}_{idx}", width='stretch'):
        st.session_state.auto_code = log['code']; st.rerun()

with st.form("main_analysis_form"):
    c1, c2, c3 = st.columns([4, 1.5, 2])
    # [Default Fix] 마지막 확인 종목 유지
    def_idx = None
    target_val = st.session_state.auto_code if st.session_state.auto_code else st.session_state.last_viewed
    if target_val:
        matches = [i for i, x in enumerate(krx_df['Code']) if x == str(target_val).zfill(6)]
        if matches: def_idx = matches[0]
    
    search_input = c1.selectbox("종목 선택", krx_df['Display'].tolist(), index=def_idx, placeholder="종목을 선택하세요")
    c2.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
    btn_click = c2.form_submit_button("🔍 초고속 분석", type="primary", use_container_width=True)
    d_input = c3.date_input("날짜 지정", value=datetime.date.today())

if btn_click or (st.session_state.auto_code != ""):
    target_code = search_input.split(" | ")[0] if search_input else st.session_state.auto_code
    res, df = analyze_v5_engine(target_code, d_input)
    if res:
        st.session_state.last_viewed = res['종목코드']
        disp_name = krx_df[krx_df['Code'] == res['종목코드']]['Name'].values[0]
        # 로그 업데이트 (중복 제거)
        temp_log = [l for l in load_data(ANALYSIS_LOG_FILE, []) if str(l['code']).zfill(6) != res['종목코드']]
        temp_log.insert(0, {"name": disp_name, "code": res['종목코드']}); save_data(ANALYSIS_LOG_FILE, temp_log[:40])
        st.session_state.auto_code = ""
        st.markdown(f"## 🎯 [{disp_name}] 전략 리포트")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("전투 상태", res['상태'])
        m2.metric("예상 수익률", res['예상수익'], delta=f"적합도 {res['적합도']}%")
        m3.metric("목표 타격가", f"{res['목표가']:,}원")
        m4.metric("최종 손절선", f"{res['손절가']:,}원", delta="-5%", delta_color="inverse")
        fig = go.Figure(data=[go.Candlestick(x=df.index.strftime('%y-%m-%d'), open=df['OPEN'], high=df['HIGH'], low=df['LOW'], close=df['CLOSE'], increasing_line_color='red', decreasing_line_color='blue')])
        fig.update_layout(height=400, xaxis_rangeslider_visible=False, template="plotly_dark", margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)

st.divider()

# --- [4. 광역 병렬 스캐너] ---
if st.button("🚀 전 종목 광역 정밀 병렬 스캔 (Parallel Engine)", width='stretch'):
    st.session_state.scan_storage = []
    prog_bar = st.progress(0)
    status_text = st.empty()
    time_text = st.empty()
    start_time = time.time()
    total_stocks = len(krx_df)
    
    results_found = []
    # [Parallel 핵심] 25개 스레드로 병렬 처리
    with ThreadPoolExecutor(max_workers=25) as executor:
        future_to_stock = {executor.submit(analyze_v5_engine, row['Code'], datetime.date.today()): row for _, row in krx_df.iterrows()}
        completed = 0
        for future in as_completed(future_to_stock):
            completed += 1
            row = future_to_stock[future]
            try:
                r, _ = future.result()
                if r and r['is_valid']:
                    r['종목명'] = f"[{r['스캔날짜']}] {row['Name']}"
                    results_found.append(r)
            except: pass
            
            if completed % 10 == 0 or completed == total_stocks:
                elapsed = time.time() - start_time
                avg = elapsed / completed
                rem = avg * (total_stocks - completed)
                prog_bar.progress(completed / total_stocks)
                status_text.markdown(f"**📡 광역 정찰 중:** `{completed}/{total_stocks}` (포착: {len(results_found)})")
                time_text.markdown(f"⏱️ **예상 남은 시간:** `{int(rem//60)}분 {int(rem%60)}초` ")

    st.session_state.scan_storage = results_found
    save_data(SCAN_RESULT_FILE, st.session_state.scan_storage)
    st.rerun()

if st.session_state.scan_storage:
    scan_df = pd.DataFrame(st.session_state.scan_storage)
    scan_df['exp_val'] = scan_df['예상수익'].str.replace('%', '').astype(float)
    scan_df = scan_df.sort_values(by=['적합도', 'exp_val'], ascending=[False, False]).drop(columns=['exp_val'])
    
    st.markdown(f"### 📋 스캔 결과 ({len(scan_df)}개 포착)")
    cols = ['종목명', '종목코드', '적합도', '상태', '비중', '현재가', '목표가', '손절가', '예상수익', '유사도', '거래량비', 'CV', '몸통비율']
    st.dataframe(scan_df[cols], use_container_width=True, hide_index=True)
