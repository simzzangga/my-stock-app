import streamlit as st
from pykrx import stock
import pandas as pd
import datetime
import time

# --- 1. 보안 설정 (Streamlit Secrets) ---
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False
    
    if st.session_state["password_correct"]:
        return True

    password = st.text_input("Antigravity 시스템 비밀번호를 입력하세요", type="password")
    if st.button("로그인"):
        if password == st.secrets.get("password", "1234"): # secrets 미설정 시 대비
            st.session_state["password_correct"] = True
            st.rerun()
        else:
            st.error("비밀번호가 틀렸습니다.")
    return False

# --- 2. 안전한 데이터 수집 함수 ---
@st.cache_data(ttl=3600)
def get_safe_ohlcv(ticker, start, end):
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
def get_safe_stock_name(ticker):
    try:
        # pykrx의 종목명 출력 신뢰도를 높이기 위해 전종목 리스트에서 검색 시도
        name = stock.get_market_ticker_name(ticker)
        if name and name.strip():
            return name
    except:
        pass
    return "미확인종목"

# --- 3. 분석 로직 ---
def run_antigravity_analysis(ticker, base_date):
    start_date = (base_date - datetime.timedelta(days=365)).strftime("%Y%m%d")
    end_date = base_date.strftime("%Y%m%d")
    
    df = get_safe_ohlcv(ticker, start_date, end_date)
    stock_name = get_safe_stock_name(ticker)

    if df.empty:
        return None, "데이터를 불러올 수 없습니다. 코드를 확인하세요."

    # 1. 급등 패턴 찾기
    spikes = df[df['등락률'] >= 15]
    if spikes.empty:
        return None, "최근 1년 내 15% 이상 급등한 이력이 없습니다."

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

    # 결과 데이터 구성
    result = {
        "name": f"{stock_name} ({ticker})", # 종목명:종목코드 형식 강제
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

# --- 4. 웹 UI ---
st.set_page_config(page_title="Antigravity Analyzer", layout="wide")

if check_password():
    st.title("💰 MSM v2.2 (Layout Optimized)")
    
    with st.sidebar:
        st.header("🔍 분석 설정")
        input_ticker = st.text_input("종목코드 6자리", value="264850")
        analysis_date = st.date_input("분석 기준일", datetime.date.today())

    if input_ticker:
        res, status = run_antigravity_analysis(input_ticker, analysis_date)
        
        if res:
            # 상단 지표 표시 (순서 변경: 최종판단이 맨 왼쪽)
            c1, c2, c3 = st.columns([1.5, 1.5, 1])
            c1.metric("최종 판단", status)
            c2.metric("종목 정보", res['name'])
            # 거래량 수치와 비율 병기
            c3.metric("현재 거래량", f"{res['current_vol']:,}", f"{res['vol_ratio']:.2%} (기준대비)")

            st.markdown("---")
            
            # 상세 리포트 표 (기존 레이아웃 유지)
            report_data = {
                "항목": ["최근 급등일", "현재가", "권장 매수대", "강력 손절가(자동매도)", "최종 판정"],
                "분석 내용": [
                    res['spike_date'], 
                    f"{res['current_price']:,}원", 
                    res['buy_zone'], 
                    f"🛑 {res['stop_loss']:,}원", 
                    status
                ]
            }
            st.table(pd.DataFrame(report_data))
            
            st.info(f"💡 **가이드:** 현재 **{status}** 상태입니다. 손절가 {res['stop_loss']:,}원은 반드시 기계적으로 대응하세요.")
        else:
            st.warning(status)
