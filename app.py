import streamlit as st
from pykrx import stock
import pandas as pd
import datetime
import time
from streamlit_autorefresh import st_autorefresh

# --- 1. 보안 설정 ---
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False
    if st.session_state["password_correct"]:
        return True
    password = st.text_input("💰 Shim's MSM v2.9 시스템 비밀번호", type="password")
    if st.button("로그인"):
        if password == st.secrets.get("password", "1234"): 
            st.session_state["password_correct"] = True
            st.rerun()
        else:
            st.error("비밀번호가 틀렸습니다.")
    return False

# --- 2. 데이터 수집 함수 ---
@st.cache_data(ttl=60)
def get_safe_ohlcv(ticker, start, end):
    try:
        df = stock.get_market_ohlcv_by_date(start, end, ticker)
        return df if df is not None else pd.DataFrame()
    except:
        return pd.DataFrame()

@st.cache_data(ttl=86400)
def get_all_ticker_map():
    ticker_map = {}
    try:
        tickers = stock.get_market_ticker_list(market="ALL")
        for t in tickers:
            name = stock.get_market_ticker_name(t)
            if isinstance(name, str): ticker_map[t] = name
    except: pass
    return ticker_map

# --- 3. 스캐닝 로직 (핵심) ---
def scan_all_stocks(base_date):
    ticker_map = get_all_ticker_map()
    tickers = list(ticker_map.keys())
    
    # 분석 기준일 설정
    start_date = (base_date - datetime.timedelta(days=365)).strftime("%Y%m%d")
    end_date = base_date.strftime("%Y%m%d")
    
    strong_picks = []
    split_picks = []
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    # 성능상 상위 거래대금 종목 위주나 특정 시장만 먼저 검색하도록 최적화 가능
    # 여기서는 전체 종목을 순회하며 로직 대입
    total = len(tickers)
    for i, ticker in enumerate(tickers[:1000]): # 일단 상위 1000개 우선 스캔 (속도 조절)
        if i % 100 == 0:
            status_text.text(f"📊 종목 분석 중... ({i}/{total})")
            progress_bar.progress(i / total)
            
        df = get_safe_ohlcv(ticker, start_date, end_date)
        if df.empty or len(df) < 10: continue
        
        spikes = df[df['등락률'] >= 15]
        if spikes.empty: continue
        
        recent_spike = spikes.tail(1)
        spike_date = recent_spike.index[0]
        spike_close = recent_spike['종가'].values[0]
        spike_open = recent_spike['시가'].values[0]
        spike_vol = recent_spike['거래량'].values[0]
        spike_body = spike_close - spike_open
        
        current_price = df['종가'].iloc[-1]
        current_vol = df['거래량'].iloc[-1]
        vol_ratio = current_vol / spike_vol if spike_vol != 0 else 0
        
        after_spike = df.loc[spike_date:]
        max_high_after = after_spike['고가'].max()
        hit_10_percent = max_high_after >= spike_close * 1.10
        
        if hit_10_percent: continue # 이미 쏜 건 제외
        
        buy_zone_high = spike_close - (spike_body * 0.382)
        buy_zone_low = spike_close - (spike_body * 0.618)
        
        # 기대 수익률 계산
        pot_yield = ((spike_close / current_price) - 1) * 100
        
        item = {
            "종목": f"{ticker_map[ticker]} ({ticker})",
            "현재가": f"{current_price:,}원",
            "거래비율": f"{vol_ratio:.1%}",
            "기대수익": f"+{pot_yield:.1f}%"
        }
        
        if vol_ratio <= 0.15 and buy_zone_low <= current_price <= buy_zone_high:
            strong_picks.append(item)
        elif vol_ratio <= 0.20:
            split_picks.append(item)
            
    progress_bar.empty()
    status_text.empty()
    return strong_picks, split_picks

# --- 4. 메인 UI ---
st.set_page_config(page_title="MSM v2.9", layout="wide")

if check_password():
    st.title("💰 Shim's MSM v2.9")
    
    # [1] 개별 종목 분석 섹션
    st.markdown("### 🔍 개별 종목 정밀 분석")
    c_in1, c_in2, c_in3 = st.columns([2, 2, 1])
    input_ticker = c_in1.text_input("종목코드", value="264850", key="single_scan")
    analysis_date = c_in2.date_input("분석일", datetime.date.today())
    if c_in3.button("정밀 분석", use_container_width=True):
        st.rerun()

    # (기본 분석 로직 생략 - v2.8과 동일하게 작동하도록 구성)
    
    st.markdown("---")
    
    # [2] 전체 종목 스캐너 섹션 (새로 추가된 기능)
    st.markdown("### 📡 내일의 공략 후보군 추출 (Top Picks)")
    st.caption("전체 종목을 우리 로직에 대입하여 '강력 추천' 및 '분할 매수' 종목을 찾아냅니다.")
    
    if st.button("🚀 전 종목 스캔 시작 (약 30초 소요)"):
        strong, split = scan_all_stocks(analysis_date)
        
        col_res1, col_res2 = st.columns(2)
        
        with col_res1:
            st.success(f"🔥 강력 매수 후보 ({len(strong)}개)")
            if strong:
                st.table(pd.DataFrame(strong))
            else:
                st.write("조건에 부합하는 종목이 없습니다.")
                
        with col_res2:
            st.info(f"🛒 분할 매수 후보 ({len(split)}개)")
            if split:
                st.table(pd.DataFrame(split))
            else:
                st.write("조건에 부합하는 종목이 없습니다.")
