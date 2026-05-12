import streamlit as st
from pykrx import stock
import pandas as pd
import datetime
import time

# --- 1. 보안 설정 ---
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False
    if st.session_state["password_correct"]:
        return True
    password = st.text_input("💰 Shim's MSM v3.3 ", type="password")
    if st.button("로그인"):
        if password == st.secrets.get("password", "1234"): 
            st.session_state["password_correct"] = True
            st.rerun()
        else:
            st.error("비밀번호가 틀렸습니다.")
    return False

# --- 2. 데이터 수집 엔진 ---
@st.cache_data(ttl=600)
def get_robust_ohlcv(ticker, start, end):
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
def get_verified_ticker_list():
    try:
        ksp = stock.get_market_ticker_list(market="KOSPI")
        ksq = stock.get_market_ticker_list(market="KOSDAQ")
        combined = list(set(ksp + ksq))
        return combined if combined else []
    except:
        return []

# --- 3. 분석 로직 ---
def run_antigravity_analysis(ticker, base_date):
    if not ticker or len(ticker) != 6:
        return None, "종목코드를 확인하세요"

    start_date = (base_date - datetime.timedelta(days=365)).strftime("%Y%m%d")
    end_date = base_date.strftime("%Y%m%d")
    
    df = get_robust_ohlcv(ticker, start_date, end_date)
    try: raw_name = stock.get_market_ticker_name(ticker)
    except: raw_name = "Unknown"

    if df.empty: return None, "데이터 응답 없음"

    spikes = df[df['등락률'] >= 15]
    if spikes.empty: return None, "최근 1년 내 급등 패턴 없음"

    recent_spike = spikes.tail(1)
    spike_date = recent_spike.index[0]
    spike_close = recent_spike['종가'].values[0]
    spike_open = recent_spike['시가'].values[0]
    spike_vol = recent_spike['거래량'].values[0]
    spike_high = recent_spike['고가'].values[0]
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
    target_sell_price = round(current_price * 1.10, -1)
    
    potential_yield = ((spike_close / current_price) - 1) * 100
    
    reliability = 100
    if len(df) < 200: reliability -= 20
    if vol_ratio > 1.0: reliability -= 15
    if target_sell_price > spike_high * 1.05: reliability -= 10 
    reliability = max(0, reliability)

    result = {
        "full_name": f"{raw_name} ({ticker})",
        "spike_date": spike_date.strftime("%Y-%m-%d"),
        "current_price": current_price,
        "vol_ratio": vol_ratio,
        "buy_zone": f"{int(buy_zone_low):,}원 ~ {int(buy_zone_high):,}원",
        "stop_loss": int(stop_loss_price),
        "target_10": int(target_sell_price),
        "reliability": reliability,
        "potential_yield": potential_yield
    }

    if hit_10_percent: status = "👋 다음 기회에 (이미 분출)"
    elif vol_ratio <= 0.15 and buy_zone_low <= current_price <= buy_zone_high: status = "🚀 강력 추천"
    elif vol_ratio <= 0.22: status = "🛒 분할 매수"
    else: status = "⏳ 관망 대기"

    return result, status

# --- 4. 시장 스캔 ---
def scan_market_full(base_date):
    tickers = get_verified_ticker_list()
    if not tickers: return [], []
    strong_list, split_list = [], []
    bar = st.progress(0)
    for i, t in enumerate(tickers):
        if i % 100 == 0: bar.progress(i / len(tickers))
        res, status = run_antigravity_analysis(t, base_date)
        if res:
            item = {"종목": res['full_name'], "현재가": f"{res['current_price']:,}원", "10%매도가": f"{res['target_10']:,}원", "거래비율": f"{res['vol_ratio']:.1%}", "기대수익": f"+{res['potential_yield']:.1f}%"}
            if status == "🚀 강력 추천": strong_list.append(item)
            elif status == "🛒 분할 매수": split_list.append(item)
    bar.empty()
    return strong_list, split_list

# --- 5. UI 구성 ---
st.set_page_config(page_title="Shim's MSM v3.3", layout="wide")

if check_password():
    st.title("💰 Shim's MSM v3.3 ")
    
    st.markdown("### 🔍 분석 제어 센터")
    c1, c2, c3 = st.columns([2, 2, 1.2])
    with c1: 
        input_ticker = st.text_input("종목코드 6자리", value="265560")
    with c2: 
        analysis_date = st.date_input("기준 날짜 선택", datetime.date.today())
    with c3:
        # 버튼 위치 정렬을 위한 여백 추가
        st.markdown('<div style="margin-top: 28px;"></div>', unsafe_allow_html=True)
        if st.button("🔄 데이터 다시 분석", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    # [B] 개별 분석 결과 (Empty DataFrame 출력 방지 로직)
    res, status = run_antigravity_analysis(input_ticker, analysis_date)
    
    if res:
        st.markdown(f"#### 🎯 {res['full_name']} 분석 및 매도 전략")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("판단", status)
        m2.metric("10% 자동매도가", f"{res['target_10']:,}원")
        m3.metric("기대수익", f"+{res['potential_yield']:.1f}%")
        m4.metric("신뢰도", f"{res['reliability']}%")
        
        # 테이블 생성
        df_display = pd.DataFrame({
            "항목": ["최근 급등일", "현재가", "매수 권장구간", "10% 자동매도 타겟", "손절가"],
            "내용": [res['spike_date'], f"{res['current_price']:,}원", res['buy_zone'], f"{res['target_10']:,}원", f"{res['stop_loss']:,}원"]
        })
        st.table(df_display)
    else:
        # 데이터가 없을 때 "Empty DataFrame" 대신 깔끔한 경고 메시지 출력
        st.info(f"💡 분석 정보: {status}")

    st.markdown("---")

    # [C] 스캐너 UI 생략 (동일)
    st.markdown("### 📡 시장 전수 스캐너")
    sc1, sc2 = st.columns(2)
    with sc1: btn_back = st.button(f"📅 {analysis_date.strftime('%m/%d')} 기준 스캔", use_container_width=True)
    with sc2: btn_now = st.button("☀️ 오늘 기준 실시간 스캔", use_container_width=True)
    
    t_date = analysis_date if btn_back else (datetime.date.today() if btn_now else None)
    if t_date:
        s_res, p_res = scan_market_full(t_date)
        rc1, rc2 = st.columns(2)
        with rc1:
            st.success(f"🔥 강력 추천 ({len(s_res)})")
            if s_res: st.table(pd.DataFrame(s_res))
        with rc2:
            st.info(f"🛒 분할 매수 ({len(p_res)})")
            if p_res: st.table(pd.DataFrame(p_res))
