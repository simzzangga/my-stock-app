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

    password = st.text_input("💰 Shim's MSM v2.7 시스템 비밀번호", type="password")
    if st.button("로그인"):
        if password == st.secrets.get("password", "1234"): 
            st.session_state["password_correct"] = True
            st.rerun()
        else:
            st.error("비밀번호가 틀렸습니다.")
    return False

# --- 2. 데이터 수집 및 안전 장치 ---

@st.cache_data(ttl=60)
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
        tickers = stock.get_market_ticker_list(market="ALL")
        for t in tickers:
            name = stock.get_market_ticker_name(t)
            if isinstance(name, str) and len(name) > 0:
                ticker_map[t] = name
    except:
        pass
    return ticker_map

def get_confirmed_stock_name(ticker):
    ticker_map = get_all_ticker_map()
    name = ticker_map.get(ticker)
    if not isinstance(name, str) or not name.strip():
        try:
            name = stock.get_market_ticker_name(ticker)
            if not isinstance(name, str): name = "종목정보없음"
        except:
            name = "종목정보없음"
    return name

# --- 3. 분석 및 신뢰도 계산 로직 ---
def run_antigravity_analysis(ticker, base_date):
    start_date = (base_date - datetime.timedelta(days=365)).strftime("%Y%m%d")
    end_date = base_date.strftime("%Y%m%d")
    
    df = get_safe_ohlcv(ticker, start_date, end_date)
    raw_name = get_confirmed_stock_name(ticker)

    if df.empty:
        return None, f"[{raw_name}] 데이터를 불러올 수 없습니다.", 0

    spikes = df[df['등락률'] >= 15]
    if spikes.empty:
        return None, "최근 1년 내 급등 패턴이 없습니다.", 0

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

    # --- 신뢰도 계산 (Reliability Score) ---
    reliability = 100
    if len(df) < 200: reliability -= 20  # 데이터 기간 부족
    if vol_ratio > 1.0: reliability -= 15  # 거래량이 너무 터짐 (매도세 가능성)
    if raw_name == "종목정보없음": reliability -= 10
    if (base_date - spike_date.date()).days > 60: reliability -= 10 # 급등 후 너무 오래 지남
    reliability = max(0, reliability)

    display_name = f"{raw_name} ({ticker})" if "DataFrame" not in str(raw_name) else f"TICKER: {ticker}"

    result = {
        "full_name": display_name,
        "spike_date": spike_date.strftime("%Y-%m-%d"),
        "current_price": current_price,
        "current_vol": current_vol,
        "vol_ratio": vol_ratio,
        "buy_zone": f"{int(buy_zone_low):,}원 ~ {int(buy_zone_high):,}원",
        "stop_loss": int(stop_loss_price),
        "reliability": reliability
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
st.set_page_config(page_title="MSM v2.7", layout="wide")

# 장 마감 자동 업데이트 (오후 3:00 ~ 3:20)
now = datetime.datetime.now()
is_trading_close = (now.weekday() < 5) and (15 == now.hour) and (0 <= now.minute <= 20)
if is_trading_close:
    st_autorefresh(interval=60 * 1000, key="mkt_watcher")

if check_password():
    st.title("💰 Shim's MSM v2.7")
    st.caption(f"기준 시각: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # --- 입력 영역 (사이드바에서 메인으로 이동) ---
    st.markdown("### 🔍 종목 분석 설정")
    col_input1, col_input2, col_input3 = st.columns([2, 2, 1])
    
    with col_input1:
        input_ticker = st.text_input("종목코드 6자리", value="264850", label_visibility="collapsed")
    with col_input2:
        analysis_date = st.date_input("분석일", datetime.date.today(), label_visibility="collapsed")
    with col_input3:
        # 분석 버튼 추가
        btn_analyze = st.button("🚀 분석 실행", use_container_width=True)

    st.markdown("---")

    if input_ticker or btn_analyze:
        res, status = run_antigravity_analysis(input_ticker, analysis_date)
        
        if res:
            # 1. 상단 지표
            c1, c2, c3 = st.columns([1, 1.5, 1.2])
            c1.metric("최종 판단", status)
            c2.metric("종목 정보", res['full_name'])
            c3.metric("거래량 (비율)", f"{res['current_vol']:,}", f"{res['vol_ratio']:.2%}")

            st.markdown("---")
            
            # 2. 결과 표
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
            
            # 3. 신뢰도 표시 (추가된 기능)
            st.markdown(f"#### 📊 분석 데이터 신뢰도: **{res['reliability']}%**")
            st.progress(res['reliability'] / 100)
            
            # 4. 하단 안내
            if is_trading_close:
                st.warning("⚠️ 현재 실시간 자동 갱신 중입니다. (장 마감 대응 모드)")
            st.info(f"💡 분석 의견: 현재 **{res['full_name']}**는 {status} 전략이 유효합니다.")
        else:
            st.warning(status)
