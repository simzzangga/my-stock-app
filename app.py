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

st.set_page_config(page_title="MSM AI Dual-Engine v5.9.19", layout="wide")

# 세션 상태 초기화 (스캐너 핵심 제어용)
if "auth" not in st.session_state: st.session_state.auth = False
if "auto_code" not in st.session_state: st.session_state.auto_code = ""
if "scanning" not in st.session_state: st.session_state.scanning = False
if "scan_progress" not in st.session_state: st.session_state.scan_progress = 0
if "scan_status" not in st.session_state: st.session_state.scan_status = "대기 중"
if "scan_results" not in st.session_state: st.session_state.scan_results = []
if "scan_etc" not in st.session_state: st.session_state.scan_etc = "0분 0초"

# --- 보안 설정 ---
if not st.session_state.auth:
    st.title("💰 MSM Portal v5.9.19")
    pwd = st.text_input("Access Key", type="password", max_chars=4, key="entry_pwd")
    if pwd == "1234": st.session_state.auth = True; st.rerun()
    st.stop()

# --- [사이드바] 분석 기록 (최대 40개 정렬) ---
st.sidebar.title("🕒 분석 기록 (Max 40)")
if analysis_log:
    for idx, log in enumerate(analysis_log[:40]):
        if st.sidebar.button(f"{log['name']} ({log['code']})", key=f"side_log_{idx}", use_container_width=True):
            st.session_state.auto_code = log['code']; st.rerun()

# --- [엔진] 듀얼 분석 로직 ---
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
            if similarity >= 85 and is_orig_buy: tag, color = f"💎 필승합의 ({step})", "red"
            elif similarity >= 80: tag, color = f"🚀 급등유력 ({step})", "red"
            else: tag, color = f"⚔️ 단기회전 ({step})", "green"
            is_valid = True
        else:
            tag, color, is_valid = "🟡 관망", "grey", False
        
        return {"code": ticker, "curr": int(curr['종가']), "t_low": int(curr['저가']), "stop": int(curr['저가'] * 0.96), 
                "similarity": similarity, "is_orig_buy": is_orig_buy, "tag": tag, "color": color, 
                "is_valid": is_valid, "cv": cv, "vol_ratio": vol_ratio, "body": curr['BODY_RATIO']}, df
    except: return None, None

# [스캐너 재설계] 스레드가 도망가지 못하도록 Lock 및 Context 보강
def run_heavy_scanner(codes, current_date):
    results = []
    total = len(codes)
    start_time = time.time()
    
    for i, code in enumerate(codes):
        try:
            # 실시간 상태 업데이트
            progress = int(((i + 1) / total) * 100)
            elapsed = time.time() - start_time
            avg_time = elapsed / (i + 1)
            rem_sec = int(avg_time * (total - (i + 1)))
            etc = f"{rem_sec // 60}분 {rem_sec % 60}초"
            
            # 세션에 상태 직접 주입
            st.session_state.scan_progress = progress
            st.session_state.scan_etc = etc
            st.session_state.scan_status = f"분석 중: {i+1}/{total} (예상 남은시간: {etc})"
            
            # 실제 분석 수행
            r, _ = analyze_v5(code, current_date)
            if r and r['is_valid']:
                results.append(r)
            
            # API 제한 방지 및 분석 속도 유지
            time.sleep(0.4) 
        except:
            continue
            
    st.session_state.scan_results = sorted(results, key=lambda x: x['similarity'], reverse=True)
    st.session_state.scan_status = "완료"
    st.session_state.scanning = False

# --- 메인 화면 ---
st.title("🖥️ MSM AI Dual-Engine v5.9.19")

# [검색 및 분석 섹션]
st.subheader("🔍 종목 정밀 판독 시스템")
with st.container(border=True):
    c1, c2, c3 = st.columns([4, 1, 2])
    # 종목명 검색
    search_term = c1.selectbox("종목명 검색", krx_df['Name'].tolist(), index=None, placeholder="분석할 종목명을 선택하세요")
    d_input = c3.date_input("분석 기준일", value=datetime.date.today())
    
    # [수정] 명시적인 검색 버튼 (모바일 대응)
    if c2.button("🔍 분석", type="primary", use_container_width=True) or (search_term and st.session_state.auto_code != krx_df[krx_df['Name'] == search_term]['Code'].values[0]):
        if search_term:
            target_code = krx_df[krx_df['Name'] == search_term]['Code'].values[0]
            st.session_state.auto_code = target_code
            
            res, df = analyze_v5(target_code, d_input)
            if res:
                # 로그 업데이트 (사이드바용)
                analysis_log = [l for l in analysis_log if l['code'] != target_code]
                analysis_log.insert(0, {"name": search_term, "code": target_code})
                save_data(ANALYSIS_LOG_FILE, analysis_log[:40])

                st.markdown(f"### 🎯 {search_term} ({target_code}) 판정: :{res['color']}[{res['tag']}]")
                # 결과 보드
                pc1, pc2, pc3 = st.columns(3)
                pc1.metric("패턴 유사도", f"{res['similarity']:.1f}%")
                pc2.metric("지침", res['tag'])
                pc3.metric("손절 데드라인", f"{res['stop']:,}원")

                # 차트 (가이드라인 복구 및 공백 제거)
                fig = go.Figure(data=[go.Candlestick(x=df.index, open=df['시가'], high=df['고가'], low=df['저가'], close=df['종가'], 
                                                     increasing_line_color='red', decreasing_line_color='blue')])
                fig.add_hline(y=res['t_low'], line_dash="dash", line_color="green", annotation_text="기준")
                fig.add_hline(y=res['stop'], line_color="#BF40BF", annotation_text="손절", line_width=2)
                fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
                fig.update_layout(height=450, xaxis_rangeslider_visible=False, template="plotly_dark")
                st.plotly_chart(fig, use_container_width=True)

                # 상세 리포트
                with st.container(border=True):
                    st.markdown("#### 📝 AI 정밀 예측 분석")
                    r1, r2 = st.columns(2)
                    r1.write(f"- **모멘텀**: {res['vol_ratio']:.1f}배 / **응축도**: CV {res['cv']:.2f}")
                    r2.write(f"- **권장 진입가**: {int(res['t_low']):,}원 내외")
                    if st.button("🔥 실전 매수 리스트 등록"):
                        mon_stocks.append({"name": search_term, "code": target_code, "buy_price": res['curr'], "memo": f"{res['tag']}"})
                        save_data(MONITOR_FILE, mon_stocks); st.rerun()

st.divider()

# --- [스캐너] 전면 복구 및 강화 ---
st.subheader("📡 고가속 종목 스캐너 (Top 500)")
s_col1, s_col2 = st.columns([1, 4])

if s_col1.button("🚀 스캔 시작", use_container_width=True):
    if not st.session_state.scanning:
        codes_to_scan = krx_df.head(500)['Code'].tolist()
        st.session_state.scanning = True
        st.session_state.scan_status = "준비 중..."
        st.session_state.scan_progress = 0
        
        # 백그라운드 스레드 실행
        scan_thread = threading.Thread(target=run_heavy_scanner, args=(codes_to_scan, datetime.date.today()))
        add_script_run_ctx(scan_thread)
        scan_thread.start()

with s_col2:
    if st.session_state.scanning:
        st.progress(st.session_state.scan_progress / 100)
        st.write(f"📊 {st.session_state.scan_status}")
    elif st.session_state.scan_status == "완료":
        st.success(f"✅ 스캔 완료! {len(st.session_state.scan_results)}개의 유망 종목 포착")

if st.session_state.scan_status == "완료" and st.session_state.scan_results:
    t1, t2 = st.tabs(["💎 S급 리스트", "⚔️ B급 리스트"])
    with t1:
        s_list = [r for r in st.session_state.scan_results if "S" in r['tag']]
        cols = st.columns(5)
        for idx, r in enumerate(s_list[:15]):
            m = krx_df[krx_df['Code'] == r['code']]; name = m['Name'].values[0] if not m.empty else r['code']
            if cols[idx % 5].button(f"{name}\n({r['similarity']:.0f}%)", key=f"s_res_{idx}"):
                st.session_state.auto_code = r['code']; st.rerun()
