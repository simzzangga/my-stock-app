import streamlit as st
from pykrx import stock
import pandas as pd
import datetime
import time

# --- 1. 보안 및 세션 초기화 ---
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

# --- 2. 초고속 데이터 엔진 ---
@st.cache_data(ttl=86400)
def get_ticker_names():
    """모든 종목명 캐싱 (매번 호출 방지)"""
    df = stock.get_market_ohlcv_by_date(datetime.date.today().strftime("%Y%m%d"), 
                                        datetime.date.today().strftime("%Y%m%d"), "ALL")
    # pykrx의 get_market_ticker_name 대신 일괄 데이터 활용
    tickers = stock.get_market_ticker_list()
    return {t: stock.get_market_ticker_name(t) for t in tickers}

@st.cache_data(ttl=600)
def get_robust_ohlcv(ticker, start, end):
    for _ in range(3):
        try:
            df = stock.get_market_ohlcv_by_date(start, end, ticker)
            if df is not None and not df.empty: return df
            time.sleep(0.1)
        except: continue
    return pd.DataFrame()

# --- 3. 정밀 분석 로직 (필터링된 종목 전용) ---
def run_analysis(ticker, base_date, mode):
    start_date = (base_date - datetime.timedelta(days=365)).strftime("%Y%m%d")
    end_date = base_date.strftime("%Y%m%d")
    df = get_robust_ohlcv(ticker, start_date, end_date)
    if df.empty: return None, "데이터 없음"

    current_price = df['종가'].iloc[-1]
    
    if "v3.3" in mode:
        spikes = df[df['등락률'] >= 15]
        if spikes.empty: return None, "패턴 없음"
        recent = spikes.tail(1)
        s_close, s_open, s_vol = recent['종가'].values[0], recent['시가'].values[0], recent['거래량'].values[0]
        s_body = s_close - s_open
        vol_ratio = df['거래량'].iloc[-1] / s_vol if s_vol != 0 else 0
        b_high, b_low = s_close - (s_body * 0.382), s_close - (s_body * 0.618)
        
        status = "🚀 강력 추천" if vol_ratio <= 0.15 and b_low <= current_price <= b_high else "🛒 분할 매수" if vol_ratio <= 0.22 else "⏳ 관망"
        return {"spike_date": recent.index[0].strftime("%Y-%m-%d"), "current_price": current_price, "target": int(current_price*1.1), "vol_ratio": vol_ratio, "buy_zone": f"{int(b_low):,}~{int(b_high):,}", "stop": int(s_open*0.98)}, status
    
    else: # v4.0
        df['vol20'] = df['거래량'].rolling(20).mean()
        spikes = df[(df['등락률'] >= 15) & (df['거래량'] > df['vol20'] * 3)]
        if spikes.empty: return None, "조건 미달"
        recent = spikes.tail(1)
        s_close, s_open, s_high = recent['종가'].values[0], recent['시가'].values[0], recent['고가'].values[0]
        s_body = s_close - s_open
        b1, b2, b3 = s_close-(s_body*0.382), s_close-(s_body*0.5), s_close-(s_body*0.618)
        
        status = "🟡 1차" if b1 >= current_price > b2 else "🟠 2차" if b2 >= current_price > b3 else "🔴 3차" if current_price > s_open*0.98 else "⏳ 이탈"
        return {"spike_date": recent.index[0].strftime("%Y-%m-%d"), "current_price": current_price, "b1": int(b1), "b2": int(b2), "b3": int(b3), "target": int(s_high*0.98), "stop": int(s_open*0.98)}, status

# --- 4. 메인 UI ---
st.set_page_config(page_title="Shim's MSM Dual Pro", layout="wide")

if check_password():
    ticker_dict = get_ticker_names()
    
    st.sidebar.title("⚙️ 시스템 설정")
    app_mode = st.sidebar.radio("분석 엔진", ["v3.3 (수급 중심)", "v4.0 (타점 중심)"])
    
    st.title(f"📊 Shim's MSM {app_mode}")

    # [A] 종목 정밀 분석
    st.markdown("### 🔍 개별 종목 분석")
    with st.expander("분석기 열기", expanded=True):
        c1, c2, c3 = st.columns([2, 2, 1.2])
        input_ticker = c1.text_input("종목코드", value="265560")
        analysis_date = c2.date_input("기준 날짜", datetime.date.today())
        if c3.button("📊 분석 실행", use_container_width=True):
            res, status = run_analysis(input_ticker, analysis_date, app_mode)
            if res:
                st.success(f"🎯 {ticker_dict.get(input_ticker, '')} - {status}")
                st.json(res)
            else: st.info(status)

    st.markdown("---")

    # [B] 고속 전수 스캐너 (핵심 개선 부분)
    st.markdown("### 📡 초고속 시장 스캐너")
    if st.button("🚀 전 종목 스캔 (약 10초 소요)", use_container_width=True):
        target_date_str = analysis_date.strftime("%Y%m%d")
        
        with st.status("시장 데이터를 분석 중입니다...", expanded=True) as status_box:
            # 1. 해당 날짜 전 종목 등락률 일괄 조회 (단 1번의 호출)
            st.write("1단계: 전체 시장 데이터 수집...")
            df_market = stock.get_market_ohlcv_by_date(target_date_str, target_date_str, "ALL")
            
            # 2. 등락률 15% 이상 종목만 1차 필터링
            st.write("2단계: 급등 후보군 선별...")
            candidates = df_market[df_market['등락률'] >= 15].index.tolist()
            
            # 3. 필터링된 종목(약 10~30개)만 정밀 로직 실행
            st.write(f"3단계: {len(candidates)}개 후보 종목 정밀 분석...")
            found = []
            for t in candidates:
                res, status = run_analysis(t, analysis_date, app_mode)
                if res and ("매수" in status or "추천" in status):
                    found.append({
                        "종목명": ticker_dict.get(t, t),
                        "코드": t,
                        "전망": status,
                        "현재가": f"{res['current_price']:,}원",
                        "목표가": f"{res['target']:,}원"
                    })
            status_box.update(label="스캔 완료!", state="complete", expanded=False)

        if found:
            st.dataframe(pd.DataFrame(found), use_container_width=True)
        else:
            st.write("해당 날짜에 조건에 맞는 종목이 없습니다.")
