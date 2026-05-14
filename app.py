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

# --- [시스템] 데이터 저장 및 로드 ---
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

@st.cache_data(ttl=86400)
def get_krx_list_phoenix():
    try:
        df = fdr.StockListing('KRX')
        if df is not None and not df.empty: return df[['Code', 'Name']]
    except: pass
    return pd.DataFrame([{"Code": "005930", "Name": "삼성전자"}, {"Code": "000660", "Name": "SK하이닉스"}])

krx_df = get_krx_list_phoenix()
mon_stocks = load_data(MONITOR_FILE, [])
ST_PARAMS = {"target_cv": 1.8, "target_vol": 10.0}

st.set_page_config(page_title="MSM Phoenix Observatory v5.9.27", layout="wide")

if "auth" not in st.session_state: st.session_state.auth = False
if "auto_code" not in st.session_state: st.session_state.auto_code = ""
if "scan_status" not in st.session_state: st.session_state.scan_status = "대기"
if "scan_progress" not in st.session_state: st.session_state.scan_progress = 0
if "scan_results" not in st.session_state: st.session_state.scan_results = []

# --- 보안 진입 ---
if not st.session_state.auth:
    st.title("🔥 Phoenix Observatory v5.9.27")
    pwd = st.text_input("Access Key", type="password", key="entry_pwd")
    if pwd == "1234": st.session_state.auth = True; st.rerun()
    st.stop()

# --- [사이드바] Phoenix 분석 기록 (40개) ---
st.sidebar.title("🔥 Phoenix Log (Max 40)")
analysis_log = load_data(ANALYSIS_LOG_FILE, [])
for idx, log in enumerate(analysis_log[:40]):
    if st.sidebar.button(f"{log['name']} ({log['code']})", key=f"side_{idx}", use_container_width=True):
        st.session_state.auto_code = log['code']; st.rerun()

# --- [엔진] 정밀 분석 로직 ---
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
            weight = "🔥 신규" if not matching_mon else "⚖️ 눌림목 물타기"
            tag, color, is_valid = (f"💎 필승합의 ({step})", "red", True) if similarity >= 85 and is_orig_buy else (f"🚀 급등유력 ({step})", "red", True) if similarity >= 80 else (f"⚔️ 단기회전 ({step})", "green", True)
        else: tag, color, weight, is_valid = "🟡 관망", "grey", "❌ 없음", False
        
        return {"code": ticker, "curr": int(curr['종가']), "t_low": int(curr['저가']), "stop": int(curr['저가'] * 0.96), 
                "similarity": similarity, "is_orig_buy": is_orig_buy, "tag": tag, "color": color, "weight": weight,
                "is_valid": is_valid, "cv": cv, "vol_ratio": vol_ratio, "body": curr['BODY_RATIO']}, df
    except: return None, None

# --- 메인 화면 ---
st.markdown("### 🔥 MSM Phoenix Observatory")

with st.container(border=True):
    c1, c2, c3 = st.columns([4, 1, 2])
    search_term = c1.selectbox("종목명 검색", krx_df['Name'].tolist(), index=None, placeholder="새 종목 입력 시 클릭 (자동 초기화)", key="main_search")
    d_input = c3.date_input("분석 기준일", value=datetime.date.today())

    target_code = ""
    if search_term: target_code = krx_df[krx_df['Name'] == search_term]['Code'].values[0]
    elif st.session_state.auto_code: target_code = st.session_state.auto_code

    if c2.button("🔍 분석", type="primary", use_container_width=True) or (target_code != ""):
        res, df = analyze_v5(target_code, d_input)
        if res:
            disp_name = krx_df[krx_df['Code'] == target_code]['Name'].values[0] if target_code in krx_df['Code'].values else target_code
            # 로그 저장
            temp_log = [l for l in load_data(ANALYSIS_LOG_FILE, []) if l['code'] != target_code]
            temp_log.insert(0, {"name": disp_name, "code": target_code}); save_data(ANALYSIS_LOG_FILE, temp_log[:40])
            
            st.markdown(f"#### 🎯 {disp_name} ({target_code}) 판정: :{res['color']}[{res['tag']}]")
            pc1, pc2, pc3 = st.columns(3)
            pc1.metric("유사도", f"{res['similarity']:.1f}%")
            pc2.metric("지침", res['weight'])
            pc3.metric("손절 데드라인", f"{res['stop']:,}원")

            fig = go.Figure(data=[go.Candlestick(x=df.index, open=df['시가'], high=df['고가'], low=df['저가'], close=df['종가'], increasing_line_color='red', decreasing_line_color='blue')])
            fig.add_hline(y=res['t_low'], line_dash="dash", line_color="green", annotation_text="기준")
            fig.add_hline(y=res['stop'], line_color="#BF40BF", line_width=2, annotation_text="손절선")
            fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
            fig.update_layout(height=400, xaxis_rangeslider_visible=False, template="plotly_dark", margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig, use_container_width=True)
            
            # [복구] AI 상세 분석 리포트 섹션 (실전 등록 버튼 제거 및 정밀 분석 추가)
            with st.container(border=True):
                st.markdown("#### 📝 AI 상세 분석 및 예측 리포트")
                r1, r2 = st.columns(2)
                with r1:
                    st.write(f"**1. 엔진별 판독 결과**")
                    st.caption(f"- 기존 엔진: {'🚀 매수 적합' if res['is_orig_buy'] else '🟡 수급 대기'} (몸통 {res['body']:.1%}, 거래량 {res['vol_ratio']:.1f}배)")
                    st.caption(f"- 가속도 엔진: 유사도 {res['similarity']:.1f}% (응축도 CV {res['cv']:.2f})")
                with r2:
                    st.write(f"**2. 실전 매매 가이드**")
                    pred_date = (d_input + datetime.timedelta(days=3)).strftime("%m/%d")
                    st.caption(f"- **매수 타이밍**: {pred_date} 전후 3~5일간 눌림목 분할 접근")
                    st.caption(f"- **목표 시나리오**: 10일 이내 10% 수익 도달 예상 (20일 시한부 매매)")
                    st.caption(f"- **대응**: {res['stop']:,}원 이탈 시 또는 20거래일 경과 시 즉시 손절")

st.divider()
# --- [스캐너] ---
st.subheader("📡 Phoenix High-Speed Scanner")
# (스캐너 코드 생략 - 안정적인 v5.9.21 방식 유지)
