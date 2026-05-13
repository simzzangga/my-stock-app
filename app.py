import streamlit as st
from pykrx import stock
import pandas as pd
import datetime
import time

# --- 1. 보안 및 초기화 ---
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False
    if st.session_state["password_correct"]: return True

    st.title("💰 Shim's MSM Portal")
    password = st.text_input("비밀번호를 입력하세요", type="password")
    if st.button("접속", use_container_width=True):
        if password == st.secrets.get("password", "1234"): 
            st.session_state["password_correct"] = True
            st.rerun()
        else: st.error("비밀번호가 틀렸습니다.")
    return False

# --- 2. 안정성 강화 데이터 엔진 (Caching 최적화) ---
@st.cache_data(ttl=86400)
def get_master_ticker_dict():
    """종목코드:종목명 매핑 사전 생성"""
    try:
        tickers = stock.get_market_ticker_list(market="ALL")
        return {t: stock.get_market_ticker_name(t) for t in tickers}
    except: return {}

@st.cache_data(ttl=600)
def get_robust_ohlcv(ticker, start, end):
    """안정적인 OHLCV 데이터 수집"""
    for _ in range(3):
        try:
            df = stock.get_market_ohlcv_by_date(start, end, ticker)
            if df is not None and not df.empty: return df
            time.sleep(0.2)
        except: continue
    return pd.DataFrame()

def add_to_recent_logs(ticker, name):
    """최근 조회 기록 업데이트"""
    if "recent_logs" not in st.session_state: st.session_state["recent_logs"] = []
    log_entry = f"{name} ({ticker})"
    if log_entry in st.session_state["recent_logs"]: st.session_state["recent_logs"].remove(log_entry)
    st.session_state["recent_logs"].insert(0, log_entry)
    st.session_state["recent_logs"] = st.session_state["recent_logs"][:10]

# --- 3. 분석 엔진 (v3.3 & v4.0) ---
def run_analysis(ticker, base_date, mode):
    start_date = (base_date - datetime.timedelta(days=365)).strftime("%Y%m%d")
    end_date = base_date.strftime("%Y%m%d")
    df = get_robust_ohlcv(ticker, start_date, end_date)
    if df.empty: return None, "데이터 없음"

    # 공통 변수 계산
    current_price = df['종가'].iloc[-1]
    
    if "v3.3" in mode:
        # [v3.3] 수급 및 급등 패턴 중심
        spikes = df[df['등락률'] >= 15]
        if spikes.empty: return None, "급등 패턴 없음 (관망)"
        
        recent = spikes.tail(1)
        s_close, s_open, s_vol = recent['종가'].values[0], recent['시가'].values[0], recent['거래량'].values[0]
        s_body = s_close - s_open
        vol_ratio = df['거래량'].iloc[-1] / s_vol if s_vol != 0 else 0
        
        # 피보나치 조정대 기반 타점
        b_high, b_low = s_close - (s_body * 0.382), s_close - (s_body * 0.618)
        
        # 상태 판정 로직 (매수/관망/주의)
        if vol_ratio <= 0.15 and b_low <= current_price <= b_high: 
            status = "🚀 강력 매수 추천" 
        elif vol_ratio <= 0.22 and current_price >= b_low:
            status = "🛒 분할 매수 가능"
        elif current_price < s_open * 0.98:
            status = "🚨 매도/손절 주의"
        else:
            status = "⏳ 관망 대기"
            
        return {
            "spike_date": recent.index[0].strftime("%Y-%m-%d"),
            "current_price": current_price,
            "target": int(current_price * 1.1),
            "vol_ratio": vol_ratio,
            "buy_zone": f"{int(b_low):,} ~ {int(b_high):,}",
            "stop": int(s_open * 0.98)
        }, status
    
    else: # [v4.0] 고도화 타점 엔진
        df['vol20'] = df['거래량'].rolling(20).mean()
        # 기준봉 조건 강화: 15% 이상 급등 + 평균 거래량 대비 3배 이상
        spikes = df[(df['등락률'] >= 15) & (df['거래량'] > df['vol20'] * 3)]
        
        if spikes.empty: return None, "기준봉 미달 (관망)"
        
        recent = spikes.tail(1)
        s_close, s_open, s_high = recent['종가'].values[0], recent['시가'].values[0], recent['고가'].values[0]
        s_body = s_close - s_open
        
        # 3단계 정밀 타점
        b1, b2, b3 = s_close-(s_body*0.382), s_close-(s_body*0.5), s_close-(s_body*0.618)
        stop_loss = s_open * 0.98

        # 상태 판정
        if b1 >= current_price > b2: status = "🟡 1차 매수 타점"
        elif b2 >= current_price > b3: status = "🟠 2차 매수 타점"
        elif b3 >= current_price > stop_loss: status = "🔴 3차 매수 타점"
        elif current_price <= stop_loss: status = "🚨 매도 (손절 이탈)"
        else: status = "⏳ 관망 (구간 상단)"

        return {
            "spike_date": recent.index[0].strftime("%Y-%m-%d"),
            "current_price": current_price,
            "b1": int(b1), "b2": int(b2), "b3": int(b3),
            "target": int(s_high * 0.98),
            "stop": int(stop_loss)
        }, status

# --- 4. 메인 UI ---
st.set_page_config(page_title="Shim's MSM Dual Pro", layout="wide")
ticker_dict = get_master_ticker_dict()

if check_password():
    st.sidebar.title("⚙️ 분석 시스템 설정")
    app_mode = st.sidebar.radio("엔진 모드 선택", ["v3.3 (수급 중심)", "v4.0 (타점 중심)"])
    
    st.title(f"📊 Shim's MSM Dual - {app_mode}")

    # [A] 종목 검색 및 분석
    st.markdown("### 🔍 실시간 종목 전망 분석")
    c1, c2, c3 = st.columns([2, 2, 1.2])
    with c1: 
        input_ticker = st.text_input("종목코드 6자리", value="265560")
    with c2: 
        analysis_date = st.date_input("기준 날짜", datetime.date.today())
    with c3:
        st.markdown('<div style="margin-top: 28px;"></div>', unsafe_allow_html=True)
        btn_run = st.button("📊 분석 실행", use_container_width=True)

    if input_ticker:
        name = ticker_dict.get(input_ticker, "알 수 없는 종목")
        res, status = run_analysis(input_ticker, analysis_date, app_mode)
        
        if res:
            add_to_recent_logs(input_ticker, name)
            
            # 분석 결과 헤더
            st.info(f"📍 **{name} ({input_ticker})** 분석 결과: **{status}**")
            
            # 주요 지표 출력
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("현재가", f"{res['current_price']:,}원")
            m2.metric("전망 목표가", f"{res['target']:,}원")
            
            if "v3.3" in app_mode:
                m3.metric("거래비율", f"{res['vol_ratio']:.1%}")
                m4.metric("손절선", f"{res['stop']:,}원")
                
                # 결과 테이블
                st.table(pd.DataFrame({
                    "항목": ["최근 급등일", "매수 권장구간", "전망"],
                    "내용": [res['spike_date'], res['buy_zone'], status]
                }))
            else:
                m3.metric("1차 타점", f"{res['b1']:,}원")
                m4.metric("손절선", f"{res['stop']:,}원")
                
                # 결과 테이블
                st.table(pd.DataFrame({
                    "항목": ["기준봉 날짜", "2차 타점", "3차 타점", "전망"],
                    "내용": [res['spike_date'], f"{res['b2']:,}원", f"{res['b3']:,}원", status]
                }))
        else:
            st.warning(f"분석 안내: {status}")

    st.markdown("---")

    # [B] 전수 스캔 시스템
    st.markdown("### 📡 시장 전수 스캐너 (전망 필터링)")
    if st.button(f"🚀 {analysis_date.strftime('%m/%d')} 시장 전체 스캔 시작", use_container_width=True):
        tickers = list(ticker_dict.keys())
        found = []
        bar = st.progress(0)
        msg = st.empty()
        
        for i, t in enumerate(tickers):
            if i % 100 == 0:
                msg.info(f"진행 중: {i}/{len(tickers)} 종목 분석...")
                bar.progress(i / len(tickers))
            
            res, status = run_analysis(t, analysis_date, app_mode)
            # 매수 신호가 있는 종목만 필터링
            if res and "매수" in status:
                found.append({
                    "종목명": ticker_dict.get(t),
                    "코드": t,
                    "분석 상태": status,
                    "현재가": f"{res['current_price']:,}",
                    "목표가": f"{res['target']:,}"
                })
        
        bar.empty(); msg.empty()
        if found:
            st.success(f"검색 완료! {len(found)}개의 유망 종목을 찾았습니다.")
            st.table(pd.DataFrame(found))
        else:
            st.write("현재 조건에 부합하는 종목이 없습니다.")

    # [C] 최근 조회 기록
    st.markdown("---")
    st.markdown("### 🕒 최근 조회 기록")
    if "recent_logs" in st.session_state and st.session_state["recent_logs"]:
        cols = st.columns(5)
        for i, log in enumerate(st.session_state["recent_logs"]):
            if cols[i % 5].button(log, key=f"log_{i}", use_container_width=True):
                # 클릭 시 해당 종목코드를 추출하여 재분석할 수 있도록 확장 가능
                pass
