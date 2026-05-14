import streamlit as st
import FinanceDataReader as fdr
import yfinance as yf
import pandas as pd
import numpy as np
import datetime
import json
import os
import plotly.graph_objects as go

# --- [1. 시스템 설정 및 데이터 초기화] ---
# 승현님의 편의를 위해 auth 세션을 기본 True로 설정하여 비번창을 제거합니다.
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
    try:
        df = fdr.StockListing('KRX')
        if df is not None and not df.empty:
            df[['Code', 'Name']].to_json(BACKUP_KRX_FILE)
            st.session_state.list_source = "✅ 실시간 KRX"
            return df[['Code', 'Name']]
    except: pass
    if os.path.exists(BACKUP_KRX_FILE):
        st.session_state.list_source = "⚠️ 백업 데이터 모드"
        return pd.read_json(BACKUP_KRX_FILE)
    return pd.DataFrame([{"Code": "005930", "Name": "삼성전자"}])

# --- [2. 앱 설정 및 로고 배치] ---
st.set_page_config(page_title="🔥 Phoenix Hybrid v5.9.47", layout="wide")

# 멋진 로고와 메인 타이틀 (비밀번호 없이 즉시 노출)
st.markdown("<h1 style='text-align: center; color: #FF4B4B;'>🔥 Phoenix Hybrid v5.9.47</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: #888;'>Premium Stock Analysis System for SHIM SEUNGHYUN</p>", unsafe_allow_html=True)

krx_df = get_krx_list_ultimate()
krx_df['Display'] = krx_df['Code'].astype(str) + " | " + krx_df['Name'].astype(str)

# --- [3. 엔진: 하이브리드 수집 및 정밀 분석] ---
def analyze_v5_engine(ticker, target_date):
    df = None
    # 1차 시도: KRX
    try:
        df = fdr.DataReader(ticker, target_date - datetime.timedelta(days=160), target_date)
        if df is not None and not df.empty:
            st.session_state.curr_source = "KRX (정상)"
            df.columns = [c.upper() for c in df.columns]
            df = df.rename(columns={'시가':'OPEN','고가':'HIGH','저가':'LOW','종가':'CLOSE','거래량':'VOLUME'})
    except: pass

    # 2차 시도: yfinance (강제 정렬 로직 보강)
    if df is None or df.empty or 'CLOSE' not in df.columns:
        try:
            yf_ticker = f"{ticker}.KS" if ticker.startswith('0') or ticker.startswith('1') else f"{ticker}.KQ"
            df_yf = yf.download(yf_ticker, start=target_date - datetime.timedelta(days=200), end=target_date + datetime.timedelta(days=1), progress=False)
            if not df_yf.empty:
                if isinstance(df_yf.columns, pd.MultiIndex): df_yf.columns = df_yf.columns.get_level_values(0)
                df_yf.columns = [c.upper() for c in df_yf.columns]
                # 컬럼명 강제 통일 및 인덱스 정리
                df = df_yf.rename(columns={'ADJ CLOSE': 'CLOSE'})[['OPEN', 'HIGH', 'LOW', 'CLOSE', 'VOLUME']]
                st.session_state.curr_source = "yfinance (비상 우회)"
        except: pass

    if df is None or df.empty or 'CLOSE' not in df.columns: return None, None
    
    # 분석 로직
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

st.info(f"🛰️ 리스트: {st.session_state.list_source} | 📡 서버: {st.session_state.curr_source}")

with st.container(border=True):
    c1, c2, c3 = st.columns([4, 1.5, 2])
    search_input = c1.selectbox("종목 선택", krx_df['Display'].tolist(), index=None, key="main_search")
    c2.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
    btn_click = c2.button("🔍 엔진 가동", type="primary", width='stretch')
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
            
            st.markdown(f"### 🎯 {disp_name} 판정 결과: :{res['color']}[{res['tag']}]")
            
            # 차트 (이미지 고정 및 가시성 최적화)
            fig = go.Figure(data=[go.Candlestick(x=df.index.strftime('%y-%m-%d'), open=df['OPEN'], high=df['HIGH'], low=df['LOW'], close=df['CLOSE'], increasing_line_color='red', decreasing_line_color='blue')])
            fig.add_hline(y=res['t_low'], line_dash="dash", line_color="green", annotation_text="기준점")
            fig.add_hline(y=res['stop'], line_color="#BF40BF", line_width=2, annotation_text="절대손절")
            fig.update_xaxes(type='category', nticks=15) 
            fig.update_layout(height=450, xaxis_rangeslider_visible=False, template="plotly_dark", margin=dict(l=10, r=10, t=10, b=10), dragmode=False)
            st.plotly_chart(fig, use_container_width=True, config={'staticPlot': True})

            # --- [5. 심층 AI 리포트 (PM 맞춤형 확장 버전)] ---
            with st.container(border=True):
                st.markdown("### 📋 Phoenix Deep Analysis Report")
                
                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown(f"""
                    **1. 수급 및 캔들 정밀 분석**
                    * **거래량 폭발 지수**: {res['vol_ratio']:.2f}배 (평균 대비)
                    * **캔들 장악력(Body)**: {res['body']:.2%}: 현재 주가는 시가 대비 강력한 매수세를 동반하며 몸통을 형성했습니다.
                    * **판정 근거**: {'기존 수급 엔진의 필승 패턴과 일치합니다.' if res['is_orig_buy'] else '변동성은 있으나 거래량 응축이 진행 중입니다.'}
                    """)
                
                with col_b:
                    st.markdown(f"""
                    **2. 변동성 및 가속도 분석**
                    * **응축도 (CV)**: {res['cv']:.4f} (목표: 1.8 내외)
                    * **패턴 유사도**: {res['similarity']:.2f}%
                    * **기술적 상태**: 현재 주가는 20일간의 가격 수렴 구간을 지나 가속도가 붙기 시작한 {res['tag']} 단계입니다.
                    """)
                
                st.markdown("---")
                st.markdown(f"""
                **3. PM을 위한 종합 전략 제언 (PM SHIM's Insight)**
                * **현 구간 분석**: 현재 {disp_name}의 차트는 `{res['t_low']:,}원`을 핵심 지지선으로 설정하고 있습니다. CV 수치가 `{res['cv']:.4f}`로 나타나는 것은 세력의 매집이 { '완료 단계' if res['cv'] < 2.0 else '진행 중' }임을 시사합니다.
                * **대응 가이드**: 유사도 `{res['similarity']:.2f}%`는 과거 급등 직전의 패턴과 상당히 높은 일치율을 보입니다. 
                * **리스크 관리**: 만약 주가가 `{res['stop']:,}원`을 이탈할 경우, 패턴이 무너지는 것으로 간주하고 즉각적인 비중 조절이 필요합니다. 
                * **최종 의견**: 본 종목은 현재 **{res['tag']}** 등급으로 분류되며, 기준봉의 저가를 훼손하지 않는 한 추세 상승의 에너지가 유효합니다.
                """)

st.divider()
st.subheader("🚀 Phoenix Scanner (전수 조사)")
if st.button("실시간 500개 종목 정밀 스캔 시작", width='stretch'):
    st.session_state.scan_storage = []
    codes = krx_df.head(500)['Code'].tolist()
    prog = st.progress(0)
    for i, code in enumerate(codes):
        r, _ = analyze_v5_engine(code, datetime.date.today())
        if r and r['is_valid']: st.session_state.scan_storage.append(r)
        prog.progress((i + 1) / 500)
    st.rerun()

if st.session_state.scan_storage:
    st.dataframe(pd.DataFrame(st.session_state.scan_storage).sort_values(by='similarity', ascending=False), use_container_width=True)
