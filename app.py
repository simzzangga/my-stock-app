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

# --- [1. 시스템 설정 및 데이터 초기화] ---
if "list_source" not in st.session_state: st.session_state.list_source = "🛰️ 서버 연결 중"
if "curr_source" not in st.session_state: st.session_state.curr_source = "📡 대기 중"
if "auto_code" not in st.session_state: st.session_state.auto_code = ""
if "scan_storage" not in st.session_state: st.session_state.scan_storage = []

ANALYSIS_LOG_FILE, BACKUP_KRX_FILE = "analysis_log_v5.json", "backup_krx.json"

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

@st.cache_data(ttl=300)
def get_krx_list_ultimate():
    # 검색 기능 수정을 위해 로컬 백업을 최우선으로 탐색하여 지연 제거
    if os.path.exists(BACKUP_KRX_FILE):
        try:
            df_l = pd.read_json(BACKUP_KRX_FILE)
            if not df_l.empty:
                st.session_state.list_source = "✅ 백업 데이터 로드됨"
                return df_l
        except: pass
    try:
        df = fdr.StockListing('KRX')
        if df is not None and not df.empty:
            df[['Code', 'Name']].to_json(BACKUP_KRX_FILE)
            st.session_state.list_source = "✅ 실시간 KRX 연결됨"
            return df[['Code', 'Name']]
    except: pass
    return pd.DataFrame([{"Code": "005930", "Name": "삼성전자"}])

# --- [2. 앱 설정 및 로고 배치] ---
st.set_page_config(page_title="🔥 Phoenix Hybrid v5.9.52", layout="wide")

# [변경 1] 타이틀 명칭 변경
st.markdown("<h1 style='text-align: center; color: #FF4B4B;'>🔥 Phoenix Hybrid v5.9.52</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: #888;'>Premium Stock Analysis System for SHIM SEUNGHYUN</p>", unsafe_allow_html=True)

krx_df = get_krx_list_ultimate()
krx_df['Display'] = krx_df['Code'].astype(str) + " | " + krx_df['Name'].astype(str)

# --- [3. 엔진: 하이브리드 수집 및 정밀 분석] ---
def analyze_v5_engine(ticker, target_date):
    df = None
    try:
        df = fdr.DataReader(ticker, target_date - datetime.timedelta(days=160), target_date)
        if df is not None and not df.empty:
            st.session_state.curr_source = "KRX (정상)"
            df.columns = [c.upper() for c in df.columns]
            df = df.rename(columns={'시가':'OPEN','고가':'HIGH','저가':'LOW','종가':'CLOSE','거래량':'VOLUME'})
    except: pass

    if df is None or df.empty or 'CLOSE' not in df.columns:
        try:
            yf_ticker = f"{ticker}.KS" if ticker.startswith('0') or ticker.startswith('1') else f"{ticker}.KQ"
            df_yf = yf.download(yf_ticker, start=target_date - datetime.timedelta(days=200), end=target_date + datetime.timedelta(days=1), progress=False)
            if not df_yf.empty:
                if isinstance(df_yf.columns, pd.MultiIndex): df_yf.columns = df_yf.columns.get_level_values(0)
                df_yf.columns = [c.upper() for c in df_yf.columns]
                df = df_yf.rename(columns={'ADJ CLOSE': 'CLOSE'})[['OPEN', 'HIGH', 'LOW', 'CLOSE', 'VOLUME']]
                st.session_state.curr_source = "yfinance (비상 우회)"
        except: pass

    if df is None or df.empty or 'CLOSE' not in df.columns: return None, None
    
    df['BODY_RATIO'] = (df['CLOSE'] - df['OPEN']).abs() / (df['HIGH'] - df['LOW'] + 0.001)
    df['VOL_MA'] = df['VOLUME'].rolling(20).mean()
    curr = df.iloc[-1]
    
    is_orig_buy = (curr['CLOSE'] > curr['OPEN']) and (curr['BODY_RATIO'] >= 0.7) and (curr['VOLUME'] >= curr['VOL_MA'] * 5)
    pre_20 = df.iloc[-21:-1]
    cv = (pre_20['CLOSE'].std() / pre_20['CLOSE'].mean()) * 100
    vol_ratio = curr['VOLUME'] / (pre_20['VOLUME'].mean() + 1)
    similarity = ((max(0, 100 - (abs(cv - 1.8) * 25))) * 0.5) + ((min(100, (vol_ratio / 10.0) * 100)) * 0.5)
    
    tag, color, is_valid = ("🟡 관망", "grey", False)
    if similarity >= 75:
        if similarity >= 85 and is_orig_buy: tag, color, is_valid = ("💎 필승합의", "red", True)
        elif similarity >= 80: tag, color, is_valid = ("🚀 급등유력", "red", True)
        else: tag, color, is_valid = ("⚔️ 단기회전", "green", True)
    
    return {"code": ticker, "curr": int(curr['CLOSE']), "t_low": int(curr['LOW']), "stop": int(curr['LOW'] * 0.96), 
            "similarity": similarity, "is_orig_buy": is_orig_buy, "tag": tag, "color": color, 
            "is_valid": is_valid, "cv": cv, "vol_ratio": vol_ratio, "body": curr['BODY_RATIO']}, df

# --- [4. UI: 사이드바 로그 및 메인 화면] ---
st.sidebar.title("📁 Phoenix History")
analysis_log = load_data(ANALYSIS_LOG_FILE, [])
for idx, log in enumerate(analysis_log[:40]):
    if st.sidebar.button(f"{log['name']} ({log['code']})", key=f"side_{idx}", width='stretch'):
        st.session_state.auto_code = log['code']; st.rerun()

with st.container(border=True):
    b1, b2, b3 = st.columns([5, 3, 2])
    b1.markdown(f"🛰️ **종목 리스트**: {st.session_state.list_source}")
    b2.markdown(f"📡 **분석 서버**: {st.session_state.curr_source}")
    # [변경 2] 버튼명 [백업]으로 변경
    if b3.button("💾 백업", use_container_width=True, type="secondary"):
        st.cache_data.clear()
        st.rerun()

with st.container(border=True):
    c1, c2, c3 = st.columns([4, 1.5, 2])
    # [변경 5] 검색 기능 수정: 리스트가 비어있지 않도록 보장
    options_list = krx_df['Display'].tolist() if not krx_df.empty else ["005930 | 삼성전자"]
    search_input = c1.selectbox("종목 선택 (검색 가능)", options_list, index=None, key="main_search")
    
    c2.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
    # [변경 3] 버튼명 [Start]로 변경
    btn_click = c2.button("🔍 Start", type="primary", width='stretch')
    d_input = c3.date_input("기준일 선택", value=datetime.date.today())

    target_code = ""
    if search_input: target_code = search_input.split(" | ")[0]
    elif st.session_state.auto_code: target_code = st.session_state.auto_code

    if btn_click or (target_code != ""):
        res, df = analyze_v5_engine(target_code, d_input)
        if res:
            disp_name = krx_df[krx_df['Code'] == target_code]['Name'].values[0] if target_code in krx_df['Code'].values else target_code
            temp_log = [l for l in load_data(ANALYSIS_LOG_FILE, []) if l['code'] != target_code]
            temp_log.insert(0, {"name": disp_name, "code": target_code}); save_data(ANALYSIS_LOG_FILE, temp_log[:40])
            st.session_state.auto_code = ""
            
            st.markdown(f"### 🎯 {disp_name} 판정 결과: :{res['color']}[{res['tag']}]")
            
            fig = go.Figure(data=[go.Candlestick(x=df.index.strftime('%y-%m-%d'), open=df['OPEN'], high=df['HIGH'], low=df['LOW'], close=df['CLOSE'], increasing_line_color='red', decreasing_line_color='blue')])
            fig.add_hline(y=res['t_low'], line_dash="dash", line_color="green", annotation_text="기준점")
            fig.add_hline(y=res['stop'], line_color="#BF40BF", line_width=2, annotation_text="절대손절")
            fig.update_xaxes(type='category', nticks=15) 
            fig.update_layout(height=450, xaxis_rangeslider_visible=False, template="plotly_dark", margin=dict(l=10, r=10, t=10, b=10), dragmode=False)
            st.plotly_chart(fig, use_container_width=True, config={'staticPlot': True})

            with st.container(border=True):
                st.markdown("### 📋 Phoenix Deep Analysis Report")
                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown(f"**1. 수급 분석**: 거래량 {res['vol_ratio']:.2f}배 | 캔들 장악력 {res['body']:.2%}")
                with col_b:
                    st.markdown(f"**2. 변동성 분석**: 응축도(CV) {res['cv']:.4f} | 패턴 유사도 {res['similarity']:.2f}%")
                st.markdown(f"**3. PM 제언**: 현재 **{res['tag']}** 등급으로 판정됩니다.")

st.divider()
st.subheader("🚀 Phoenix Scanner (전수 조사)")

if st.button("실시간 500개 종목 정밀 스캔 시작", width='stretch'):
    st.session_state.scan_storage = []
    codes = krx_df.head(500)['Code'].tolist()
    prog_bar = st.progress(0)
    time_text = st.empty()
    
    start_time = time.time()
    for i, code in enumerate(codes):
        r, _ = analyze_v5_engine(code, datetime.date.today())
        if r and r['is_valid']: st.session_state.scan_storage.append(r)
        
        # [v5.9.50 유지] 남은 시간 추측 기능
        elapsed = time.time() - start_time
        avg = elapsed / (i + 1)
        remaining = avg * (len(codes) - (i + 1))
        time_text.markdown(f"⏳ **분석 중**: {i+1}/500 | **남은 예상 시간**: 약 {int(remaining)}초")
        prog_bar.progress((i + 1) / 500)
    
    time_text.success(f"✅ 스캔 완료 (총 {len(st.session_state.scan_storage)}건 포착)")

# [변경 4] 스캔 결과 유지 로직: 세션 상태를 직접 출력하여 휘발 방지
if st.session_state.scan_storage:
    st.info(f"📊 스캔 결과 ({len(st.session_state.scan_storage)}개 포착)")
    st.dataframe(pd.DataFrame(st.session_state.scan_storage).sort_values(by='similarity', ascending=False), use_container_width=True)
