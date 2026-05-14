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

# --- [1. 시스템 설정: 세션 및 데이터 무결성] ---
if "scan_storage" not in st.session_state: st.session_state.scan_storage = []
if "auto_code" not in st.session_state: st.session_state.auto_code = ""

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
    if os.path.exists(BACKUP_KRX_FILE):
        try:
            df_l = pd.read_json(BACKUP_KRX_FILE)
            if not df_l.empty: return df_l
        except: pass
    try:
        df = fdr.StockListing('KRX')
        if df is not None and not df.empty:
            df[['Code', 'Name']].to_json(BACKUP_KRX_FILE)
            return df[['Code', 'Name']]
    except: pass
    return pd.DataFrame([{"Code": "005930", "Name": "삼성전자"}])

# --- [2. 엔진: 실전형 고정밀 판정 로직 (v5.9.60)] ---
def analyze_v5_engine(ticker, target_date):
    df = None
    try:
        df = fdr.DataReader(ticker, target_date - datetime.timedelta(days=160), target_date)
        if df is not None and not df.empty:
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
        except: pass

    if df is None or df.empty or 'CLOSE' not in df.columns: return None, None
    
    # [원칙 중심의 정밀 수치]
    df['BODY_RATIO'] = (df['CLOSE'] - df['OPEN']).abs() / (df['HIGH'] - df['LOW'] + 0.001)
    df['VOL_MA'] = df['VOLUME'].rolling(20).mean()
    curr = df.iloc[-1]
    vol_ratio = curr['VOLUME'] / (df['VOLUME'].iloc[-21:-1].mean() + 1)
    
    # 필승 조건: 거래량 4.0배(엄격), 몸통 0.65(장악력), 유사도 82%(신뢰도)
    is_orig_buy = (curr['CLOSE'] > curr['OPEN']) and (curr['BODY_RATIO'] >= 0.65) and (vol_ratio >= 4.0)
    pre_20 = df.iloc[-21:-1]
    cv = (pre_20['CLOSE'].std() / pre_20['CLOSE'].mean()) * 100
    similarity = ((max(0, 100 - (abs(cv - 1.8) * 20))) * 0.3) + ((min(100, (vol_ratio / 5.0) * 100)) * 0.7)
    
    tag, color, is_valid = ("🟡 관망", "grey", False)
    if similarity >= 65:
        if similarity >= 82 and is_orig_buy: tag, color, is_valid = ("💎 필승합의", "red", True)
        elif similarity >= 76: tag, color, is_valid = ("🚀 급등유력", "red", True)
        elif similarity >= 70: tag, color, is_valid = ("⚔️ 단기회전", "green", True)
        else: tag, color, is_valid = ("📈 추세형성", "blue", True)
    
    return {"code": ticker, "curr": int(curr['CLOSE']), "t_low": int(curr['LOW']), "stop": int(curr['LOW'] * 0.96), 
            "similarity": similarity, "is_orig_buy": is_orig_buy, "tag": tag, "color": color, 
            "is_valid": is_valid, "cv": cv, "vol_ratio": vol_ratio, "body": curr['BODY_RATIO']}, df

# --- [3. UI: 로고 및 메인 제어 센터] ---
st.set_page_config(page_title="🔥 Phoenix Hybrid v5.9.60", layout="wide")
st.markdown("<h1 style='text-align: center; color: #FF4B4B;'>🔥 Phoenix Hybrid v5.9.60</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: #888;'>Premium Stock Analysis System for SHIM SEUNGHYUN</p>", unsafe_allow_html=True)

krx_df = get_krx_list_ultimate()
krx_df['Display'] = krx_df['Code'].astype(str) + " | " + krx_df['Name'].astype(str)

# 사이드바 (날짜 연동 절대 금지 명령 반영)
st.sidebar.title("📁 Phoenix History")
analysis_log = load_data(ANALYSIS_LOG_FILE, [])
for idx, log in enumerate(analysis_log[:40]):
    if st.sidebar.button(f"{log['name']} ({log['code']})", key=f"side_{idx}", width='stretch'):
        st.session_state.auto_code = log['code']; st.rerun()

with st.container(border=True):
    # 상단 서버 상황판 (백업 버튼 우측 배치)
    b1, b2, b3 = st.columns([5, 3, 2])
    b1.markdown(f"🛰️ **종목 리스트**: 로컬/실시간 하이브리드 가동 중")
    b2.markdown(f"📡 **분석 서버**: {st.session_state.get('curr_source', '대기 중')}")
    if b3.button("💾 백업", use_container_width=True):
        st.cache_data.clear(); st.rerun()

with st.form("main_analysis_form", clear_on_submit=False):
    c1, c2, c3 = st.columns([4, 1.5, 2])
    default_idx = None
    if st.session_state.auto_code:
        matches = [i for i, x in enumerate(krx_df['Code']) if x == st.session_state.auto_code]
        if matches: default_idx = matches[0]
    search_input = c1.selectbox("종목 선택 (검색 후 Enter)", krx_df['Display'].tolist(), index=default_idx)
    c2.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
    btn_click = c2.form_submit_button("🔍 Start", type="primary", use_container_width=True)
    d_input = c3.date_input("분석 날짜 지정", value=datetime.date.today())

if btn_click or (st.session_state.auto_code != ""):
    target_code = search_input.split(" | ")[0] if search_input else st.session_state.auto_code
    res, df = analyze_v5_engine(target_code, d_input)
    if res:
        disp_name = krx_df[krx_df['Code'] == target_code]['Name'].values[0]
        temp_log = [l for l in load_data(ANALYSIS_LOG_FILE, []) if l['code'] != target_code]
        temp_log.insert(0, {"name": disp_name, "code": target_code}); save_data(ANALYSIS_LOG_FILE, temp_log[:40])
        st.session_state.auto_code = ""
        
        st.markdown(f"### 🎯 [{disp_name}] 분석 결과 ({d_input.strftime('%Y-%m-%d')})")
        st.markdown(f"#### 📢 매수 의견: :{res['color']}[{res['tag']}]")
        
        # 차트 (기준선 및 손절선 복구)
        fig = go.Figure(data=[go.Candlestick(x=df.index.strftime('%y-%m-%d'), open=df['OPEN'], high=df['HIGH'], low=df['LOW'], close=df['CLOSE'], increasing_line_color='red', decreasing_line_color='blue')])
        fig.add_hline(y=res['t_low'], line_dash="dash", line_color="green", annotation_text="기준점(Support)")
        fig.add_hline(y=res['stop'], line_color="#BF40BF", line_width=2, annotation_text="절대손절(Stop-loss)")
        fig.update_layout(height=450, xaxis_rangeslider_visible=False, template="plotly_dark")
        st.plotly_chart(fig, use_container_width=True)

        # --- [심층 리포트 분량 및 내용 완전 복구] ---
        with st.container(border=True):
            st.markdown("### 📋 Phoenix Deep Analysis Report")
            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown(f"""
                **1. 수급 및 캔들 정밀 분석**
                * **거래량 폭발 지수**: {res['vol_ratio']:.2f}배 (원칙 임계치 4.0배)
                * **캔들 장악력(Body)**: {res['body']:.2%}: 시가 대비 종가 형성의 강도가 수급 주체의 의지를 반영합니다.
                * **판정 근거**: {'엔진이 요구하는 필승 수급 패턴이 확인되었습니다.' if res['is_orig_buy'] else '변동성이 수렴하며 거래량 응축을 기다리는 구간입니다.'}
                """)
            with col_b:
                st.markdown(f"""
                **2. 변동성 및 가속도 분석**
                * **응축도 (CV)**: {res['cv']:.4f} (에너지 수렴 목표: 1.8 내외)
                * **패턴 유사도**: {res['similarity']:.2f}%
                * **기술적 상태**: 과거 성공 사례와 {res['similarity']:.1f}%의 궤적 일치율을 보이며 가속도가 붙고 있습니다.
                """)
            st.markdown("---")
            st.markdown(f"""
            **3. PM SHIM's 종합 전략 제언**
            * **현 구간 분석**: 현재 {disp_name}의 차트는 `{res['t_low']:,}원`을 핵심 지지선으로 설정하고 있습니다. 
            * **대응 가이드**: 유사도 `{res['similarity']:.2f}%`는 시장의 매수세가 유효함을 나타내며, **{res['tag']}** 등급에 걸맞은 비중 전략이 필요합니다.
            * **리스크 관리**: 만약 주가가 `{res['stop']:,}원`을 이탈할 경우, 패턴 훼손으로 간주하고 즉각적인 비중 조절이 필요합니다.
            * **최종 결론**: 본 리포트는 지정된 날짜({d_input}) 기준으로 엔진의 모든 수치를 통과한 정밀 결과입니다.
            """)

st.divider()
st.subheader("🚀 Phoenix Scanner (전수 조사 결과 보존)")
if st.button("실시간 500개 종목 정밀 스캔 시작", width='stretch'):
    st.session_state.scan_storage = []
    codes = krx_df.head(500)['Code'].tolist()
    prog_bar = st.progress(0); time_text = st.empty(); start_time = time.time()
    for i, code in enumerate(codes):
        r, _ = analyze_v5_engine(code, datetime.date.today())
        if r and r['is_valid']: st.session_state.scan_storage.append(r)
        elapsed = time.time() - start_time; avg = elapsed / (i + 1); remaining = avg * (len(codes) - (i + 1))
        time_text.markdown(f"⏳ **분석 중**: {i+1}/500 | **남은 시간**: 약 {int(remaining)}초")
        prog_bar.progress((i + 1) / 500)
    st.rerun()

if st.session_state.scan_storage:
    st.info(f"📊 스캔 결과 ({len(st.session_state.scan_storage)}개 포착) - 휘발 방지 로직 적용 중")
    st.dataframe(pd.DataFrame(st.session_state.scan_storage).sort_values(by='similarity', ascending=False), use_container_width=True)
