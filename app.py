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

    password = st.text_input("💰 Shim's MSM v2.8 시스템 비밀번호", type="password")
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

# --- 3. 분석 및 수익률 계산 로직 ---
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

    # --- 예상 최대 수익률 계산 (New!) ---
    # 1차 목표: 전고점(급등일 종가) / 2차 목표: 급등일 종가 + 10%
    target_price_1 = spike_close
    target_price_2 = spike_close * 1.10
    
    potential_yield_1 = ((target_price_1 / current_price) - 1) * 100
    potential_yield_2 = ((target_price_2 / current_price) - 1) * 100

    # 신뢰도 계산
    reliability = 100
    if len(df) < 200: reliability -= 20
    if vol_ratio > 1.0: reliability -= 15
    if (base_date - spike_date.date()).days > 60: reliability -= 10
    reliability = max(0, reliability)

    display_name = f"{raw_name} ({ticker})"

    result = {
        "full_name": display_name,
        "spike_date": spike_date.strftime("%Y-%m-%d"),
        "current_price": current_price,
        "current_vol": current_vol,
        "vol_ratio": vol_ratio,
        "buy_zone": f"{int(buy_zone_low):,}원 ~ {int(buy_zone_high):,}원",
        "stop_loss": int(stop_loss_price),
        "reliability": reliability,
        "potential_yield": potential_yield_1, # 전고점 기준 수익률
        "target_10_yield": potential_yield_2  # 10% 돌파 시 수익률
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
st.set_page_config(page_title="MSM v2.8", layout="wide")

now = datetime.datetime.now()
is_trading_close = (now.weekday() < 5) and (15 == now.hour) and (0 <= now.minute <= 20)
if is_trading_close:
    st_autorefresh(interval=60 * 1000, key="mkt_watcher")

if check_password():
    st.title("💰 Shim's MSM v2.8")
    
    # 입력 영역
    st.markdown("### 🔍 종목 분석 설정")
    col_input1, col_input2, col_input3 = st.columns([2, 2, 1])
    with col_input1:
        input_ticker = st.text_input("종목코드 6자리", value="264850", label_visibility="collapsed")
    with col_input2:
        analysis_date = st.date_input("분석일", datetime.date.today(), label_visibility="collapsed")
    with col_input3:
        btn_analyze = st.button("🚀 분석 실행", use_container_width=True)

    st.markdown("---")

    if input_ticker or btn_analyze:
        res, status = run_antigravity_analysis(input_ticker, analysis_date)
        
        if res:
            # 1. 상단 주요 지표
            c1, c2, c3, c4 = st.columns([1, 1.2, 1, 1.2])
            c1.metric("최종 판단", status)
            c2.metric("종목 정보", res['full_name'])
            c3.metric("거래량 비율", f"{res['vol_ratio']:.2%}")
            # [추가] 예상 수익률 지표를 상단에 배치
            c4.metric("기대 수익률", f"+{res['potential_yield']:.1f}%", f"Max +{res['target_10_yield']:.1f}%")

            st.markdown("---")
            
            # 2. 분석 상세 테이블
            report_data = {
                "항목": ["최근 급등일", "현재가", "권장 매수대", "전고점 회복 시", "최종 목표(10%)", "강력 손절가"],
                "분석 내용": [
                    res['spike_date'], 
                    f"{res['current_price']:,}원", 
                    res['buy_zone'], 
                    f"익절 시 약 +{res['potential_yield']:.1f}%", 
                    f"익절 시 약 +{res['target_10_yield']:.1f}%", 
                    f"🛑 {res['stop_loss']:,}원"
                ]
            }
            st.table(pd.DataFrame(report_data))
            
            # 3. 신뢰도 지표
            st.markdown(f"#### 📊 분석 데이터 신뢰도: **{res['reliability']}%**")
            st.progress(res['reliability'] / 100)
            
            st.info(f"💡 **예상 수익률 근거**: 현재가 대비 이전 급등날의 종가까지 회복할 경우의 수익률입니다.")
        else:
            st.warning(status)
