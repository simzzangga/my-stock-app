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
    password = st.text_input("💰 Shim's MSM v3.0 시스템 비밀번호", type="password")
    if st.button("로그인"):
        if password == st.secrets.get("password", "1234"): 
            st.session_state["password_correct"] = True
            st.rerun()
        else:
            st.error("비밀번호가 틀렸습니다.")
    return False

# --- 2. 데이터 수집 (안정성 극대화) ---
@st.cache_data(ttl=600) # 전수조사 결과는 10분간 유지
def get_robust_ohlcv(ticker, start, end):
    """실패 시 최대 5번까지 재시도하며 데이터를 반드시 가져옵니다."""
    for i in range(5):
        try:
            df = stock.get_market_ohlcv_by_date(start, end, ticker)
            if df is not None and not df.empty:
                return df
            time.sleep(0.2 * (i + 1)) # 재시도 시 대기 시간 증가
        except:
            continue
    return pd.DataFrame()

@st.cache_data(ttl=86400)
def get_verified_ticker_list():
    """KOSPI와 KOSDAQ 리스트를 각각 가져와서 합쳐 누락을 방지합니다."""
    try:
        kospi = stock.get_market_ticker_list(market="KOSPI")
        kosdaq = stock.get_market_ticker_list(market="KOSDAQ")
        return list(set(kospi + kosdaq))
    except:
        return stock.get_market_ticker_list(market="ALL")

# --- 3. 핵심 분석 로직 (기능 복구) ---
def analyze_logic(ticker, base_date):
    start_dt = (base_date - datetime.timedelta(days=365)).strftime("%Y%m%d")
    end_dt = base_date.strftime("%Y%m%d")
    
    df = get_robust_ohlcv(ticker, start_dt, end_dt)
    if df.empty: return None, "NO_DATA"

    spikes = df[df['등락률'] >= 15]
    if spikes.empty: return None, "NO_PATTERN"

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

    buy_zone_high = spike_close - (spike_body * 0.382)
    buy_zone_low = spike_close - (spike_body * 0.618)
    
    # 결과 데이터 구성
    result = {
        "name": stock.get_market_ticker_name(ticker),
        "code": ticker,
        "current_price": current_price,
        "vol_ratio": vol_ratio,
        "potential_yield": ((spike_close / current_price) - 1) * 100,
        "buy_zone": f"{int(buy_zone_low):,}~{int(buy_zone_high):,}"
    }

    if hit_10_percent: status = "EXIT"
    elif vol_ratio <= 0.15 and buy_zone_low <= current_price <= buy_zone_high: status = "STRONG"
    elif vol_ratio <= 0.20: status = "SPLIT"
    else: status = "WAIT"

    return result, status

# --- 4. 전 종목 전수 스캔 (시간 소요되더라도 정확히) ---
def deep_scan_market(target_date):
    tickers = get_verified_ticker_list()
    total = len(tickers)
    strong_res, split_res = [], []
    
    msg = st.empty()
    bar = st.progress(0)
    
    for i, t in enumerate(tickers):
        # 30개 종목마다 상태 업데이트
        if i % 30 == 0:
            msg.info(f"⏳ 전수 스캔 중: {i}/{total} 종목 진행 (누락 방지 모드)")
            bar.progress(i / total)
        
        res, status = analyze_logic(t, target_date)
        if res:
            row = {
                "종목": f"{res['name']} ({res['code']})",
                "현재가": f"{res['current_price']:,}원",
                "거래비율": f"{res['vol_ratio']:.1%}",
                "기대수익": f"+{res['potential_yield']:.1f}%"
            }
            if status == "STRONG": strong_res.append(row)
            elif status == "SPLIT": split_res.append(row)
            
    bar.empty()
    msg.empty()
    return strong_res, split_res

# --- 5. UI 구성 ---
st.set_page_config(page_title="MSM v3.0", layout="wide")

if check_password():
    st.title("💰 Shim's MSM v3.0 (Full Scan)")
    
    # 분석 제어 센터
    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        input_ticker = st.text_input("개별 분석 종목코드", value="484810")
    with col2:
        target_date = st.date_input("기준 날짜", datetime.date.today())
    with col3:
        st.write("")
        if st.button("🧹 시스템 캐시 초기화"):
            st.cache_data.clear()
            st.success("캐시가 제거되었습니다.")

    # 스캐너 버튼
    st.markdown("---")
    sc1, sc2 = st.columns(2)
    with sc1:
        btn_backtest = st.button(f"📅 {target_date.strftime('%Y-%m-%d')} 전수 스캔", use_container_width=True)
    with sc2:
        btn_today = st.button("☀️ 오늘 실시간 전수 스캔", use_container_width=True)

    scan_dt = None
    if btn_backtest: scan_dt = target_date
    elif btn_today: scan_dt = datetime.date.today()

    if scan_dt:
        s_list, p_list = deep_scan_market(scan_dt)
        
        r_col1, r_col2 = st.columns(2)
        with r_col1:
            st.success(f"🚀 강력 추천 ({len(s_list)}개)")
            if s_list: st.table(pd.DataFrame(s_list))
            else: st.write("해당 조건의 종목이 없습니다.")
        with r_col2:
            st.info(f"🛒 분할 매수 ({len(p_list)}개)")
            if p_list: st.table(pd.DataFrame(p_list))
            else: st.write("해당 조건의 종목이 없습니다.")
