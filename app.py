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
    password = st.text_input("💰 Shim's MSM v3.1 시스템 비밀번호", type="password")
    if st.button("로그인"):
        if password == st.secrets.get("password", "1234"): 
            st.session_state["password_correct"] = True
            st.rerun()
        else:
            st.error("비밀번호가 틀렸습니다.")
    return False

# --- 2. 데이터 수집 (안정성 극대화) ---
@st.cache_data(ttl=600)
def get_robust_ohlcv(ticker, start, end):
    """실패 시 최대 5번 재시도하여 데이터를 반드시 가져옵니다."""
    for i in range(5):
        try:
            df = stock.get_market_ohlcv_by_date(start, end, ticker)
            if df is not None and not df.empty:
                return df
            time.sleep(0.15)
        except:
            continue
    return pd.DataFrame()

@st.cache_data(ttl=86400)
def get_verified_ticker_list():
    """코스피/코스닥 전체 종목을 안전하게 병합합니다."""
    try:
        ksp = stock.get_market_ticker_list(market="KOSPI")
        ksq = stock.get_market_ticker_list(market="KOSDAQ")
        return list(set(ksp + ksq))
    except:
        return stock.get_market_ticker_list(market="ALL")

# --- 3. 핵심 분석 로직 (V2.9 기능 완전 유지) ---
def run_antigravity_analysis(ticker, base_date):
    start_date = (base_date - datetime.timedelta(days=365)).strftime("%Y%m%d")
    end_date = base_date.strftime("%Y%m%d")
    
    df = get_robust_ohlcv(ticker, start_date, end_date)
    raw_name = stock.get_market_ticker_name(ticker)

    if df.empty:
        return None, "데이터 없음"

    spikes = df[df['등락률'] >= 15]
    if spikes.empty:
        return None, "패턴 없음"

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

    # V2.9의 수익률 및 신뢰도 계산 유지
    potential_yield_1 = ((spike_close / current_price) - 1) * 100
    potential_yield_2 = ((spike_close * 1.1 / current_price) - 1) * 100

    reliability = 100
    if len(df) < 200: reliability -= 20
    if vol_ratio > 1.0: reliability -= 15
    if (base_date - spike_date.date()).days > 60: reliability -= 10
    reliability = max(0, reliability)

    result = {
        "full_name": f"{raw_name} ({ticker})",
        "spike_date": spike_date.strftime("%Y-%m-%d"),
        "current_price": current_price,
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

# --- 4. 정밀 전 종목 스캔 함수 ---
def scan_market_full(base_date):
    tickers = get_verified_ticker_list()
    strong_list, split_list = [], []
    
    msg = st.empty()
    bar = st.progress(0)
    
    total = len(tickers)
    for i, t in enumerate(tickers):
        if i % 40 == 0:
            msg.info(f"🔍 전수 조사 중: {i}/{total} (누락 방지 모드 활성)")
            bar.progress(i / total)
        
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
st.set_page_config(page_title="MSM v3.1", layout="wide")

if check_password():
    st.title("💰 Shim's MSM v3.1")
    
    # [A] 상단 분석 설정
    st.markdown("### 🔍 분석 제어 센터")
    c1, c2, c3 = st.columns([2, 2, 1.2])
    with c1:
        input_ticker = st.text_input("종목코드 6자리", value="484810")
    with c2:
        analysis_date = st.date_input("기준 날짜 선택", datetime.date.today())
    with c3:
        st.write("")
        if st.button("🧹 캐시 초기화", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    # [B] 개별 분석 결과 표시 (V2.9 디자인 유지)
    res, status = run_antigravity_analysis(input_ticker, analysis_date)
    if res:
        st.markdown(f"#### 🎯 {res['full_name']} 분석 결과")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("판단", status)
        m2.metric("거래비율", f"{res['vol_ratio']:.1%}")
        m3.metric("기대수익", f"+{res['potential_yield']:.1f}%")
        m4.metric("신뢰도", f"{res['reliability']}%")
        
        st.table(pd.DataFrame({
            "항목": ["최근 급등일", "현재가", "매수구간", "손절가", "10% 목표가 수익률"],
            "내용": [res['spike_date'], f"{res['current_price']:,}원", res['buy_zone'], f"{res['stop_loss']:,}원", f"+{res['target_10_yield']:.1f}%"]
        }))
    else:
        st.warning(f"분석 결과: {status}")

    st.markdown("---")

    # [C] 스캐너 & 백테스팅
    st.markdown("### 📡 시장 스캐너 (정밀 백테스팅)")
    sc_col1, sc_col2 = st.columns(2)
    with sc_col1:
        btn_backtest = st.button(f"📅 {analysis_date.strftime('%m/%d')} 기준 전수 스캔", use_container_width=True)
    with sc_col2:
        btn_today_scan = st.button("☀️ 오늘 기준 전수 스캔", use_container_width=True)

    target_date = None
    if btn_backtest: target_date = analysis_date
    elif btn_today_scan: target_date = datetime.date.today()

    if target_date:
        st.subheader(f"📊 {target_date.strftime('%Y-%m-%d')} 추천 리스트")
        strong_res, split_res = scan_market_full(target_date)
        
        res_c1, res_c2 = st.columns(2)
        with res_c1:
            st.success(f"🔥 강력 추천 ({len(strong_res)}개)")
            if strong_res: st.table(pd.DataFrame(strong_res))
            else: st.write("조건 부합 종목 없음")
        with res_c2:
            st.info(f"🛒 분할 매수 ({len(split_res)}개)")
            if split_res: st.table(pd.DataFrame(split_res))
            else: st.write("조건 부합 종목 없음")
