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
    password = st.text_input("💰 Shim's MSM v3.3", type="password")
    if st.button("로그인"):
        if password == st.secrets.get("password", "1234"): 
            st.session_state["password_correct"] = True
            st.rerun()
        else:
            st.error("비밀번호가 틀렸습니다.")
    return False

# --- 2. 데이터 수집 및 점검 ---
@st.cache_data(ttl=600)
def get_robust_ohlcv(ticker, start, end):
    for i in range(3): # 재시도 횟수 최적화
        try:
            df = stock.get_market_ohlcv_by_date(start, end, ticker)
            if df is not None and not df.empty:
                return df
            time.sleep(0.2)
        except:
            continue
    return pd.DataFrame()

@st.cache_data(ttl=86400)
def get_verified_ticker_list():
    """KRX 서버 장애 대비 3중 방어 로직"""
    try:
        ksp = stock.get_market_ticker_list(market="KOSPI")
        time.sleep(0.1)
        ksq = stock.get_market_ticker_list(market="KOSDAQ")
        combined = list(set(ksp + ksq))
        
        if not combined:
            # 개별 리스트가 비어있을 경우 전체 리스트 시도
            combined = stock.get_market_ticker_list(market="ALL")
            
        return combined if combined else []
    except Exception:
        # IndexError 방지를 위해 에러 발생 시 빈 리스트 반환
        return []

# --- 3. 핵심 분석 로직 (매도 전략 및 호가 단위 보정) ---
def run_antigravity_analysis(ticker, base_date):
    if not ticker or len(ticker) != 6:
        return None, "종목코드 6자리를 입력하세요"

    start_date = (base_date - datetime.timedelta(days=365)).strftime("%Y%m%d")
    end_date = base_date.strftime("%Y%m%d")
    
    df = get_robust_ohlcv(ticker, start_date, end_date)
    try: 
        raw_name = stock.get_market_ticker_name(ticker)
    except: 
        raw_name = "Unknown"

    if df.empty: return None, "데이터 응답 없음"

    # 급등 패턴 분석 (기준: 등락률 15% 이상)
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
    # 이미 급등 종가 대비 10% 이상 상승했었는지 체크
    hit_10_percent = max_high_after >= spike_close * 1.10

    # 구간 계산
    buy_zone_high = spike_close - (spike_body * 0.382)
    buy_zone_low = spike_close - (spike_body * 0.618)
    stop_loss_price = spike_open * 0.98
    
    # 10% 자동 매도 목표가 (현재가 기준 10% 상승 가격)
    target_raw = current_price * 1.10
    # 한국 주식 호가 단위 간이 보정 (10원 단위 반올림)
    target_sell_price = round(target_raw, -1)
    
    # 기대 수익 및 분석 신뢰도
    potential_yield = ((spike_close / current_price) - 1) * 100
    
    reliability = 100
    if len(df) < 200: reliability -= 20
    if vol_ratio > 1.0: reliability -= 15
    # 목표가가 너무 높으면(전고점 대비 5% 이상) 도달 가능성 낮음으로 판단
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

    # 최종 판단
    if hit_10_percent: status = "👋 다음 기회에 (이미 시세 분출)"
    elif vol_ratio <= 0.15 and buy_zone_low <= current_price <= buy_zone_high:
        status = "🚀 강력 추천"
    elif vol_ratio <= 0.22:
        status = "🛒 분할 매수"
    else: status = "⏳ 관망 대기"

    return result, status

# --- 4. 시장 스캔 함수 ---
def scan_market_full(base_date):
    tickers = get_verified_ticker_list()
    if not tickers:
        st.error("데이터 수집 엔진 오류. 잠시 후 다시 시도해 주세요.")
        return [], []

    strong_list, split_list = [], []
    msg = st.empty()
    bar = st.progress(0)
    
    total = len(tickers)
    for i, t in enumerate(tickers):
        if i % 100 == 0:
            msg.info(f"📡 {base_date} 기준 자동매도 유효 종목 스캔: {i}/{total}")
            bar.progress(i / total)
        
        res, status = run_antigravity_analysis(t, base_date)
        if res:
            item = {
                "종목": res['full_name'],
                "현재가": f"{res['current_price']:,}원",
                "10%매도가": f"{res['target_10']:,}원",
                "거래비율": f"{res['vol_ratio']:.1%}",
                "기대수익": f"+{res['potential_yield']:.1f}%"
            }
            if status == "🚀 강력 추천": strong_list.append(item)
            elif status == "🛒 분할 매수": split_list.append(item)
            
    bar.empty()
    msg.empty()
    return strong_list, split_list

# --- 5. 웹 UI 구성 ---
st.set_page_config(page_title="Shim's MSM v3.3", layout="wide")

if check_password():
    st.title("💰 Shim's MSM v3.3")
    
    st.markdown("### 🔍 분석 제어 센터")
    c1, c2, c3 = st.columns([2, 2, 1.2])
    with c1: 
        input_ticker = st.text_input("종목코드 6자리", value="484810")
    with c2: 
        analysis_date = st.date_input("기준 날짜 선택", datetime.date.today())
    with c3:
        st.write("")
        # 버튼 이름 변경: 캐시 초기화 -> 데이터 다시 분석
        if st.button("🔄 데이터 다시 분석", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    # [B] 개별 종목 정밀 분석
    res, status = run_antigravity_analysis(input_ticker, analysis_date)
    if res:
        st.markdown(f"#### 🎯 {res['full_name']} 분석 및 매도 전략")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("판단", status)
        m2.metric("10% 자동매도가", f"{res['target_10']:,}원")
        m3.metric("기대수익(급등종가)", f"+{res['potential_yield']:.1f}%")
        m4.metric("분석 신뢰도", f"{res['reliability']}%")
        
        st.table(pd.DataFrame({
            "항목": ["최근 급등일", "현재가", "매수 권장구간 (매집)", "10% 자동매도 타겟", "손절가 (대응)"],
            "내용": [res['spike_date'], f"{res['current_price']:,}원", res['buy_zone'], f"{res['target_10']:,}원", f"{res['stop_loss']:,}원"]
        }))
    else:
        st.warning(f"안내: {status}")

    st.markdown("---")

    # [C] 전체 시장 스캐너
    st.markdown("### 📡 시장 전수 스캐너 (10% 수익 실현 타겟)")
    sc_col1, sc_col2 = st.columns(2)
    with sc_col1: 
        btn_backtest = st.button(f"📅 {analysis_date.strftime('%m/%d')} 기준 스캔", use_container_width=True)
    with sc_col2: 
        btn_today_scan = st.button("☀️ 오늘 기준 실시간 스캔", use_container_width=True)

    target_date = None
    if btn_backtest: target_date = analysis_date
    elif btn_today_scan: target_date = datetime.date.today()

    if target_date:
        st.subheader(f"📊 {target_date.strftime('%Y-%m-%d')} 추천 및 매도 타겟 리스트")
        strong_res, split_res = scan_market_full(target_date)
        
        res_c1, res_c2 = st.columns(2)
        with res_c1:
            st.success(f"🔥 강력 추천 ({len(strong_res)}개)")
            if strong_res: st.table(pd.DataFrame(strong_res))
            else: st.write("조건에 부합하는 종목이 없습니다.")
        with res_c2:
            st.info(f"🛒 분할 매수 ({len(split_res)}개)")
            if split_res: st.table(pd.DataFrame(split_res))
            else: st.write("조건에 부합하는 종목이 없습니다.")
