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

    password = st.text_input("Shim's MSM v2.3 시스템 비밀번호를 입력하세요", type="password")
    if st.button("로그인"):
        # st.secrets에 password가 설정되어 있어야 합니다. 테스트용이라면 직접 문자열 비교 가능
        if password == st.secrets.get("password", "1234"): 
            st.session_state["password_correct"] = True
            st.rerun()
        else:
            st.error("비밀번호가 틀렸습니다.")
    return False

# --- 2. 데이터 수집 함수 (호출 순서 에러 방지를 위해 상단 배치) ---

@st.cache_data(ttl=3600)
def get_safe_ohlcv(ticker, start, end):
    """주가 데이터를 안전하게 가져오는 함수"""
    for _ in range(3):
        try:
            df = stock.get_market_ohlcv_by_date(start, end, ticker)
            if not df.empty:
                return df
            time.sleep(0.5)
        except:
            continue
    return pd.DataFrame()

@st.cache_data(ttl=86400)
def get_all_ticker_map():
    """전종목 리스트를 미리 로드하여 종목명 누락 방지"""
    try:
        # 코스피(KOSPI), 코스닥(KOSDAQ) 전체 리스트 로드
        df_kospi = stock.get_market_ticker_list(market="KOSPI")
        df_kosdaq = stock.get_market_ticker_list(market="KOSDAQ")
        tickers = df_kospi + df_kosdaq
        
        # 딕셔너리로 매핑 (속도 및 정확도 향상)
        ticker_map = {}
        for t in tickers:
            ticker_map[t] = stock.get_market_ticker_name(t)
        return ticker_map
    except:
        return {}

def get_confirmed_stock_name(ticker):
    """캐시된 맵에서 종목명을 가져오고 실패 시 재시도"""
    ticker_map = get_all_ticker_map()
    name = ticker_map.get(ticker)
    
    if not name:
        try:
            name = stock.get_market_ticker_name(ticker)
        except:
            name = None
    return name if name else "미확인종목"

# --- 3. 분석 메인 로직 ---
def run_antigravity_analysis(ticker, base_date):
    start_date = (base_date - datetime.timedelta(days=365)).strftime("%Y%m%d")
    end_date = base_date.strftime("%Y%m%d")
    
    # 함수 정의가 상단에 있어 에러가 발생하지 않음
    df = get_safe_ohlcv(ticker, start_date, end_date)
    stock_name = get_confirmed_stock_name(ticker)

    if df.empty:
        return None, "데이터를 불러올 수 없습니다. 종목코드나 장 운영일을 확인하세요."

    # 1. 급등 패턴(15% 이상) 찾기
    spikes = df[df['등락률'] >= 15]
    if spikes.empty:
        return None, "최근 1년 내 급등 패턴이 발견되지 않은 종목입니다."

    recent_spike = spikes.tail(1)
    spike_date = recent_spike.index[0]
    spike_close = recent_spike['종가'].values[0]
    spike_open = recent_spike['시가'].values[0]
    spike_vol = recent_spike['거래량'].values[0]
    spike_body = spike_close - spike_open

    # 2. 현재 상태 분석
    current_price = df['종가'].iloc[-1]
    current_vol = df['거래량'].iloc[-1]
    vol_ratio = current_vol / spike_vol
    
    after_spike = df.loc[spike_date:]
    max_high_after = after_spike['고가'].max()
    hit_10_percent = max_high_after >= spike_close * 1.10

    # 3. 가격 전략
    buy_zone_high = spike_close - (spike_body * 0.382)
    buy_zone_low = spike_close - (spike_body * 0.618)
    stop_loss_price = spike_open * 0.98

    # 최종 데이터 패키징
    result = {
        "full_name": f"{stock_name} ({ticker})",
        "spike_date": spike_date.strftime("%Y-%m-%d"),
        "current_price": current_price,
        "current_vol": current_vol,
        "vol_ratio": vol_ratio,
        "buy_zone": f"{int(buy_zone_low):,}원 ~ {int(buy_zone_high):,}원",
        "stop_loss": int(stop_loss_price)
    }

    # 판정 기준
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

if check_password():
    st.title("💰 Shim's MSM v2.3")
    
    with st.sidebar:
        st.header("🔍 분석 설정")
        input_ticker = st.text_input("종목코드 6자리", value="264850")
        analysis_date = st.date_input("분석 기준일", datetime.date.today())

    if input_ticker:
        res, status = run_antigravity_analysis(input_ticker, analysis_date)
        
        if res:
            # 1. 상단 지표 영역 (요청하신 순서 및 거래량 추가)
            c1, c2, c3 = st.columns([1, 1.5, 1.2])
            with c1:
                st.metric("최종 판단", status)
            with c2:
                st.metric("종목 정보", res['full_name'])
            with c3:
                st.metric("거래량 (비율)", f"{res['current_vol']:,}", f"{res['vol_ratio']:.2%}")

            st.markdown("---")
            
            # 2. 상세 리포트 표 (기존 레이아웃 유지)
            report_data = {
                "항목": ["최근 급등일", "현재가", "권장 매수대", "강력 손절가(자동매도)", "최종 결과"],
                "분석 내용": [
                    res['spike_date'], 
                    f"{res['current_price']:,}원", 
                    res['buy_zone'], 
                    f"🛑 {res['stop_loss']:,}원", 
                    status
                ]
            }
            st.table(pd.DataFrame(report_data))
            
            st.info(f"💡 **가이드:** 현재 {res['full_name']} 종목은 **{status}** 상태입니다. 가격 대응 원칙을 준수하세요.")
        else:
            st.warning(status)
