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
import requests

# --- [1. 시스템 설정] ---
ANALYSIS_LOG_FILE, BACKUP_KRX_FILE = "analysis_log_v5.json", "backup_krx.json"
MONITOR_FILE = "monitoring_v5.json"

def load_data(file_path, default_val):
    try:
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f: return json.load(f)
    except: pass
    return default_val

def save_data(file_path, data):
    with open(file_path, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=4)

@st.cache_data(ttl=600)
def get_krx_list_ultimate():
    try:
        df = fdr.StockListing('KRX')
        if df is not None and not df.empty:
            df[['Code', 'Name']].to_json(BACKUP_KRX_FILE)
            st.session_state.list_source = "✅ 실시간 KRX 데이터"
            return df[['Code', 'Name']]
    except: pass
    if os.path.exists(BACKUP_KRX_FILE):
        st.session_state.list_source = "⚠️ 서버 지연 (백업 리스트)"
        return pd.read_json(BACKUP_KRX_FILE)
    return pd.DataFrame([{"Code": "005930", "Name": "삼성전자"}])

# --- [2. 앱 초기화] ---
st.set_page_config(page_title="MSM Phoenix v5.9.37", layout="wide")

if "auth" not in st.session_state: st.session_state.auth = False
if "auto_code" not in st.session_state: st.session_state.auto_code = ""
if "scan_status" not in st.session_state: st.session_state.scan_status = "대기"
if "curr_source" not in st.session_state: st.session_state.curr_source = "미정"
if "list_source" not in st.session_state: st.session_state.list_source = "확인 중"

if not st.session_state.auth:
    st.title("🔥 Phoenix Hybrid v5.9.37")
    pwd = st.text_input("Access Key", type="password", key="entry_pwd")
    if pwd == "1234": st.session_state.auth = True; st.rerun()
    st.stop()

krx_df = get_krx_list_ultimate()
krx_df['Display'] = krx_df['Code'] + " | " + krx_df['Name']
mon_stocks = load_data(MONITOR_FILE, [])

# --- [3. 분석 엔진] ---
def analyze_v5_hybrid(ticker, base_date):
    df = None
    try:
        df = fdr.DataReader(ticker, base_date - datetime.timedelta(days=120), base_date)
        if df is not None and not df.empty:
            st.session_state.curr_source = "KRX (정상)"
            df.columns = [c.upper() for c in df.columns]
            df = df.rename(columns={'시가':'OPEN','고가':'HIGH','저가':'LOW','종가':'CLOSE','거래량':'VOLUME'})
    except: pass

    if df is None or df.empty:
        try:
            yf_ticker = f"{ticker}.KS" if ticker.startswith('0') or ticker.startswith('1') else f"{ticker}.KQ"
            df_yf = yf.download(yf_ticker, start=base_date - datetime.timedelta(days=120), end=base_date, progress=False)
            if not df_yf.empty:
                df = df_yf[['Open', 'High', 'Low', 'Close', 'Volume']]
                df.columns = ['OPEN', 'HIGH', 'LOW', 'CLOSE', 'VOLUME']
                st.session_state.curr_source = "yfinance (우회)"
        except: pass

    if df is None or df.empty: return None, None
    
    df['BODY_RATIO'] = (df['CLOSE'] - df['OPEN']).abs() / (df['HIGH'] - df['LOW'] + 1)
    df['VOL_MA'] = df['VOLUME'].rolling(20).mean()
    curr = df.iloc[-1]
    is_orig_buy = (curr['CLOSE'] > curr['OPEN']) and (curr['BODY_RATIO'] > 0.7) and (curr['VOLUME'] > curr['VOL_MA'] * 5)
    pre_20 = df.iloc[-21:-1]
    cv = (pre_20['CLOSE'].std() / pre_20['CLOSE'].mean()) * 100
    vol_ratio = curr['VOLUME'] / (pre_20['VOLUME'].mean() + 1)
    similarity = ((max(0, 100 - (abs(cv - 1.8) * 25))) * 0.5) + ((min(100, (vol_ratio / 10.0) * 100)) * 0.5)
    
    tag, color, is_valid = ("🟡 관망", "grey", False)
    if similarity >= 75:
        step = "1차" if ticker not in [s['code'] for s in mon_stocks] else "추가"
        tag, color, is_valid = (f"💎 필승합의 ({step})", "red", True) if similarity >= 85 and is_orig_buy else (f"🚀 급등유력 ({step})", "red", True) if similarity >= 80 else (f"⚔️ 단기회전 ({step})", "green", True)
    
    return {"code": ticker, "curr": int(curr['CLOSE']), "t_low": int(curr['LOW']), "stop": int(curr['LOW'] * 0.96), 
            "similarity": similarity, "is_orig_buy": is_orig_buy, "tag": tag, "color": color, 
            "is_valid": is_valid, "cv": cv, "vol_ratio": vol_ratio, "body": curr['BODY_RATIO']}, df

# --- [4. UI 레이아웃] ---
st.sidebar.title("🔥 Phoenix Log (Max 40)")
analysis_log = load_data(ANALYSIS_LOG_FILE, [])
for idx, log in enumerate(analysis_log[:40]):
    if st.sidebar.button(f"{log['name']} ({log['code']})", key=f"side_{idx}", width='stretch'):
        st.session_state.auto_code = log['code']; st.rerun()

st.info(f"🛰️ 리스트: {st.session_state.list_source} | 📡 서버: {st.session_state.curr_source}")

with st.container(border=True):
    c1, c2, c3 = st.columns([4, 1.5, 2])
    search_input = c1.selectbox("종목 검색", krx_df['Display'].tolist(), index=None, placeholder="코드 또는 이름 입력", key="main_search")
    c2.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
    btn_click = c2.button("🔍 분석 실행", type="primary", width='stretch')
    d_input = c3.date_input("분석 기준일", value=datetime.date.today())

    target_code = ""
    if search_input: target_code = search_input.split(" | ")[0]
    elif st.session_state.auto_code: target_code = st.session_state.auto_code

    if btn_click or (target_code != ""):
        res, df = analyze_v5_hybrid(target_code, d_input)
        if res:
            disp_name = krx_df[krx_df['Code'] == target_code]['Name'].values[0] if target_code in krx_df['Code'].values else target_code
            temp_log = [l for l in load_data(ANALYSIS_LOG_FILE, []) if l['code'] != target_code]
            temp_log.insert(0, {"name": disp_name, "code": target_code}); save_data(ANALYSIS_LOG_FILE, temp_log[:40])
            st.markdown(f"#### 🎯 {disp_name} ({target_code}) 판정: :{res['color']}[{res['tag']}]")
            
            # [디테일] 차트 이미지화 (줌/드래그 차단)
            fig = go.Figure(data=[go.Candlestick(x=df.index, open=df['OPEN'], high=df['HIGH'], low=df['LOW'], close=df['CLOSE'], increasing_line_color='red', decreasing_line_color='blue')])
            fig.add_hline(y=res['t_low'], line_dash="dash", line_color="green", annotation_text="기준")
            fig.add_hline(y=res['stop'], line_color="#BF40BF", line_width=2, annotation_text="손절선")
            fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
            fig.update_layout(height=350, xaxis_rangeslider_visible=False, template="plotly_dark", margin=dict(l=5, r=5, t=5, b=5), dragmode=False)
            st.plotly_chart(fig, width='stretch', config={'staticPlot': True}) # staticPlot=True로 그림처럼 고정
            
            # [디테일] 리포트 상세화 (전략 삭제, 수치 데이터 극대화)
            with st.container(border=True):
                st.markdown("#### 📝 AI 심층 수치 리포트")
                r1, r2 = st.columns(2)
                with r1:
                    st.write("**📊 기존 수급 엔진 결과**")
                    st.caption(f"- **거래량 강도**: 평소 대비 {res['vol_ratio']:.2f}배 폭증 (기준 5배 대비 {'충족' if res['vol_ratio'] >= 5 else '미달'})")
                    st.caption(f"- **캔들 장악력**: 몸통 비중 {res['body']:.1%} (실질적 매수세가 가격을 {int(res['body']*100)}% 지배 중)")
                    st.caption(f"- **수급 판정**: {'🚀 기관/외인 대량 유입 가능성' if res['is_orig_buy'] else '🟡 단순 변동성 혹은 기술적 반등'}")
                with r2:
                    st.write("**📉 가속도 정밀 엔진 결과**")
                    st.caption(f"- **응축도(CV)**: {res['cv']:.4f} (타겟 1.8 대비 오차범위 내 응축 여부 판독)")
                    st.caption(f"- **패턴 유사도**: {res['similarity']:.2f}% (역사적 급등 패턴과의 수치적 일치도)")
                    st.caption(f"- **리스크 방어**: 저가 대비 하방 4% 지점 {res['stop']:,}원 설정")
                st.divider()
                st.caption(f"📍 **분석 데이터**: {st.session_state.curr_source} 서버 기반 / 기준가 {res['curr']:,}원 / 손절가 {res['stop']:,}원")

st.divider()
st.subheader("📡 Phoenix Scanner (Top 500)")
if st.button("🚀 실시간 전수 스캔", width='stretch'):
    st.session_state.scan_results = []
    codes = krx_df.head(500)['Code'].tolist()
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, code in enumerate(codes):
        status_text.text(f"분석 중: {i+1}/500 ({krx_df[krx_df['Code']==code]['Name'].values[0]})")
        r, _ = analyze_v5_hybrid(code, datetime.date.today())
        if r and r['is_valid']: st.session_state.scan_results.append(r)
        progress_bar.progress((i + 1) / 500)
    st.success(f"스캔 완료! {len(st.session_state.scan_results)}개 종목 포착")
