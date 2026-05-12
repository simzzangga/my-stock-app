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

# --- 2. 데이터 수집 및 안전 장치 ---
@st.cache_data(ttl=60)
def get_safe_ohlcv(ticker, start, end):
    for _ in range(3):
        try:
            df = stock.get_market_ohlcv_by_date(start, end, ticker)
            if df is not None and not df.empty:
                return df
            time.sleep(0.1)
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
    except: pass
    return ticker_map

def get_confirmed_stock_name(ticker):
    ticker_map = get_all_ticker_map()
    name = ticker_map.get(ticker)
    if not isinstance(name, str) or not name.strip():
        try:
            name = stock.get_market_ticker_name(ticker)
            if not isinstance(name, str): name = "종목정보없음"
        except: name = "종목정보없음"
    return name

# --- 3. 핵심 분석 로직 (전체 통합 유지) ---
def run_antigravity_analysis(ticker, base_date):
    start_date = (base_date - datetime.timedelta(days=365)).strftime("%Y%m%d")
    end_date = base_date.strftime("%Y%m%d")
    
    df = get_safe_ohlcv(ticker, start_date, end_date)
    raw_name = get_confirmed_stock_name(ticker)

    if df.empty:
        return None, f"[{raw_name}] 데이터를 불러올 수 없습니다."

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

    target_price_1 = spike_close
    target_price_2 = spike_close * 1.10
    potential_yield_1 = ((target_price_1 / current_price) - 1) * 100
    potential_yield_2 = ((target_price_2 / current_price) - 1) * 100

    reliability = 100
    if len(df) < 200: reliability -= 20
    if vol_ratio > 1.0: reliability -= 15
    if (base_date - spike_date.date()).days > 60: reliability -= 10
    reliability = max(0, reliability)

    result = {
        "full_name": f"{raw_name} ({ticker})",
        "spike_date": spike_date.strftime("%Y-%m-%d"),
        "current_price": current_price,
        "current_vol": current_vol,
        "vol_ratio": vol_ratio,
        "buy_zone": f"{int(buy_zone_low):,}원 ~ {int(buy_zone_high):,}원",
        "stop_loss": int(stop_loss_price),
        "reliability": reliability,
        "potential_yield": potential_yield_1,
        "target_10_yield": potential_yield_2
    }

    if hit_10_percent: status = "👋 다음 기회에"
    elif vol_ratio <= 0.15 and buy_zone_low <= current_price <= buy_zone_high: status = "🚀 강력 추천"
    elif vol_ratio <= 0.20: status = "🛒 분할 매수"
    else: status = "⏳ 관망 대기"

    return result, status

# --- 4. 전 종목 스캔 함수 ---
def scan_market(base_date):
    ticker_map = get_all_ticker_map()
    tickers = list(ticker_map.keys())
    strong_list, split_list = [], []
    
    msg = st.empty()
    bar = st.progress(0)
    
    # 성능 최적화를 위해 거래대금 상위 종목 등으로 필터링 가능 (여기선 500개 샘플 예시)
    scan_limit = len(tickers)
    for i, t in enumerate(tickers[:scan_limit]):
        if i % 50 == 0:
            msg.text(f"🔍 시장 스캔 중... ({i}/{scan_limit})")
            bar.progress(i / scan_limit)
        
        res, status = run_antigravity_analysis(t, base_date)
        if res:
            item = {
                "종목": res['full_name'],
                "현재가": f"{res['current_price']:,}원",
                "거래비율": f"{res['vol_ratio']:.1%}",
                "기대수익": f"+{res['potential_yield']:.1f}%"
            }
            if status == "🚀 강력 추천": strong_list.append(item)
            elif status == "🛒 분할 매수": split_list.append(item)
            
    bar.empty()
    msg.empty()
    return strong_list, split_list

# --- 5. 웹 UI 구성 ---
st.set_page_config(page_title="MSM v2.9", layout="wide")

now = datetime.datetime.now()
is_trading_close = (now.weekday() < 5) and (15 == now.hour) and (0 <= now.minute <= 20)
if is_trading_close:
    st_autorefresh(interval=60 * 1000, key="mkt_watcher")

if check_password():
    st.title("💰 Shim's MSM v2.9")
    
    # [A] 상단 분석 설정 (메인 인터페이스)
    st.markdown("### 🔍 분석 제어 센터")
    c1, c2, c3 = st.columns([2, 2, 1.2])
    
    with c1:
        input_ticker = st.text_input("종목코드 6자리", value="264850")
    with c2:
        analysis_date = st.date_input("기준 날짜 선택", datetime.date.today())
    with c3:
        st.write("") # 간격 맞춤
        btn_single = st.button("🎯 개별 종목 분석", use_container_width=True)

    # [B] 개별 분석 결과 표시
    if input_ticker or btn_single:
        res, status = run_antigravity_analysis(input_ticker, analysis_date)
        if res:
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("판단", status)
            m2.metric("종목", res['full_name'])
            m3.metric("거래비율", f"{res['vol_ratio']:.1%}")
            m4.metric("기대수익", f"+{res['potential_yield']:.1f}%")
            
            st.table(pd.DataFrame({
                "항목": ["최근 급등일", "현재가", "매수구간", "손절가", "신뢰도"],
                "내용": [res['spike_date'], f"{res['current_price']:,}원", res['buy_zone'], f"{res['stop_loss']:,}원", f"{res['reliability']}%"]
            }))
        else:
            st.warning(status)

    st.markdown("---")

    # [C] 스캐너 & 백테스팅 섹션 (새로운 버튼 2개)
    st.markdown("### 📡 시장 스캐너 & 백테스팅")
    st.caption("선택한 날짜 기준으로 전 종목을 스캔합니다. 과거 날짜를 선택하면 그 당시의 추천 종목을 볼 수 있습니다.")
    
    sc_col1, sc_col2 = st.columns(2)
    
    with sc_col1:
        # 1. 위에서 선택한 날짜와 연동되는 버튼
        btn_backtest = st.button(f"📅 {analysis_date.strftime('%m/%d')} 기준 종목 스캔", use_container_width=True)
        
    with sc_col2:
        # 2. 무조건 오늘 날짜로 작동하는 버튼
        btn_today_scan = st.button("☀️ 오늘(실시간) 기준 종목 스캔", use_container_width=True)

    # 스캔 실행 로직
    target_date = None
    if btn_backtest: target_date = analysis_date
    if btn_today_scan: target_date = datetime.date.today()

    if target_date:
        st.subheader(f"📊 {target_date.strftime('%Y-%m-%d')} 기준 추천 리스트")
        strong_res, split_res = scan_market(target_date)
        
        res_c1, res_c2 = st.columns(2)
        with res_c1:
            st.success(f"🔥 강력 추천 ({len(strong_res)}개)")
            if strong_res: st.table(pd.DataFrame(strong_res))
            else: st.write("없음")
        with res_c2:
            st.info(f"🛒 분할 매수 ({len(split_res)}개)")
            if split_res: st.table(pd.DataFrame(split_res))
            else: st.write("없음")
