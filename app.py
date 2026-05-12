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

    password = st.text_input("💰 Shim's MSM v2.5 시스템 비밀번호", type="password")
    if st.button("로그인"):
        if password == st.secrets.get("password", "1234"): 
            st.session_state["password_correct"] = True
            st.rerun()
        else:
            st.error("비밀번호가 틀렸습니다.")
    return False

# --- 2. 데이터 수집 및 종목명 매핑 (안전성 & 실시간성 강화) ---

@st.cache_data(ttl=60) # 실시간 모니터링을 위해 주가 데이터 캐시는 1분만 유지
def get_safe_ohlcv(ticker, start, end):
    for _ in range(3):
        try:
            df = stock.get_market_ohlcv_by_date(start, end, ticker)
            if df is not None and not df.empty:
                return df
            time.sleep(0.5)
        except:
            continue
    return pd.DataFrame()

@st.cache_data(ttl=86400)
def get_all_ticker_map():
    ticker_map = {}
    try:
        for mkt in ["KOSPI", "KOSDAQ"]:
            tickers = stock.get_market_ticker_list(market=mkt)
            for t in tickers:
                name = stock.get_market_ticker_name(t)
                if isinstance(name, str) and name.strip():
                    ticker_map[t] = name
        if len(ticker_map) < 500: return {}
    except:
        return {}
    return ticker_map

def get_confirmed_stock_name(ticker):
    ticker_map = get_all_ticker_map()
    name = ticker_map.get(ticker)
    if not name:
        try:
            name = stock.get_market_ticker_name(ticker)
        except:
            name = "미확인종목"
    return str(name)

# --- 3. 분석 메인 로직 ---
def run_antigravity_analysis(ticker, base_date):
    start_date = (base_date - datetime.timedelta(days=365)).strftime("%Y%m%d")
    end_date = base_date.strftime("%Y%m%d")
    
    df = get_safe_ohlcv(ticker, start_date, end_date)
    stock_name = get_confirmed_stock_name(ticker)

    if df.empty:
        return None, f"[{stock_name}] 데이터를 불러올 수 없습니다."

    spikes = df[df['등락률'] >= 15]
    if spikes.empty:
        return None, "최근 1년 내 급등 패턴이 없습니다."

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
    stop_loss_price = spike_open * 0.98

    result = {
        "full_name": f"{stock_name} ({ticker})",
        "spike_date": spike_date.strftime("%Y-%m-%d"),
        "current_price": current_price,
        "current_vol": current_vol,
        "vol_ratio": vol_ratio,
        "buy_zone": f"{int(buy_zone_low):,}원 ~ {int(buy_zone_high):,}원",
        "stop_loss": int(stop_loss_price)
    }

    if hit_10_percent:
        status = "👋 다음 기회에"
    elif vol_ratio <= 0.15 and buy_zone_low <= current_price <= buy_zone_high:
        status = "🚀 강력 추천"
    elif vol_ratio <= 0.20:
        status = "🛒 분할 매수"
    else:
        status = "⏳ 관망 대기"

    return result, status

# --- 4. 웹 UI 구성 ---
st.set_page_config(page_title="Antigravity Analyzer", layout="wide")

# [핵심] 실시간 자동 업데이트 설정 (오후 3:00 ~ 3:20)
now = datetime.datetime.now()
is_trading_close = (now.weekday() < 5) and (15 == now.hour) and (0 <= now.minute <= 20)

if is_trading_close:
    # 60초마다 새로고침
    st_autorefresh(interval=60 * 1000, key="mkt_watcher")
    st.toast("현재 장 마감 모니터링 모드가 활성화되었습니다.")

if check_password():
    st.title("💰 Shim's MSM v2.5")
    st.caption(f"최종 업데이트: {now.strftime('%H:%M:%S')}")
    
    with st.sidebar:
        st.header("🔍 분석 설정")
        input_ticker = st.text_input("종목코드 6자리", value="264850")
        analysis_date = st.date_input("분석 기준일", datetime.date.today())
        if is_trading_close:
            st.success("✅ 실시간 자동 업데이트 작동 중")

    if input_ticker:
        res, status = run_antigravity_analysis(input_ticker, analysis_date)
        
        if res:
            # 상단 지표: 최종 판단을 맨 왼쪽으로
            c1, c2, c3 = st.columns([1, 1.5, 1.2])
            with c1:
                st.metric("최종 판단", status)
            with c2:
                st.metric("종목 정보", res['full_name'])
            with c3:
                st.metric("거래량 (비율)", f"{res['current_vol']:,}", f"{res['vol_ratio']:.2%}")

            st.markdown("---")
            
            # 상세 리포트 표
            report_data = {
                "항목": ["최근 급등일", "현재가", "권장 매수대", "강력 손절가", "판정 결과"],
                "분석 내용": [
                    res['spike_date'], 
                    f"{res['current_price']:,}원", 
                    res['buy_zone'], 
                    f"🛑 {res['stop_loss']:,}원", 
                    status
                ]
            }
            st.table(pd.DataFrame(report_data))
            
            if is_trading_close:
                st.warning("⚠️ 현재 장 마감 전 실시간 데이터입니다. 결정에 유의하세요.")
            st.info(f"💡 현재 **{res['full_name']}**는 {status} 상태입니다.")
        else:
            st.warning(status)
