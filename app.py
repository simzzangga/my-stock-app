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
        if password == st.secrets["password"]:
            st.session_state["password_correct"] = True
            st.rerun()
        else:
            st.error("비밀번호가 틀렸습니다.")
    return False

# --- 2. 안전한 데이터 수집 함수 (재시도 로직 포함) ---
@st.cache_data(ttl=3600) # 한 시간 동안 데이터 캐싱하여 서버 부하 감소
def get_safe_ohlcv(ticker, start, end):
    for _ in range(3): # 최대 3번 재시도
        try:
            df = stock.get_market_ohlcv_by_date(start, end, ticker)
            if not df.empty:
                return df
            time.sleep(1) # 잠시 대기 후 재시도
        except:
            continue
    return pd.DataFrame()

@st.cache_data(ttl=86400)
def get_safe_stock_name(ticker):
    try:
        name = stock.get_market_ticker_name(ticker)
        if name:
            return name
    except:
        pass
    return f"Ticker:{ticker}"

# --- 3. Make Some Money (v2.1) ---
def run_antigravity_analysis(ticker, base_date):
    # 날짜 설정
    start_date = (base_date - datetime.timedelta(days=365)).strftime("%Y%m%d")
    end_date = base_date.strftime("%Y%m%d")
    
    # 데이터 수집
    df = get_safe_ohlcv(ticker, start_date, end_date)
    stock_name = get_safe_stock_name(ticker)

    if df.empty:
        return None, "데이터를 불러올 수 없습니다. 서버 상태를 확인하거나 잠시 후 시도하세요."

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
    
    # 급등 이후 수익 달성 여부 (고가 기준 10%)
    after_spike = df.loc[spike_date:]
    max_high_after = after_spike['고가'].max()
    hit_10_percent = max_high_after >= spike_close * 1.10

    # 3. 가격 전략 수립
    buy_zone_high = spike_close - (spike_body * 0.382)
    buy_zone_low = spike_close - (spike_body * 0.618)
    stop_loss_price = spike_open * 0.98

    # --- 최종 판정 ---
    result = {
        "name": stock_name,
        "spike_date": spike_date.strftime("%Y-%m-%d"),
        "current_price": current_price,
        "vol_ratio": vol_ratio,
        "buy_zone": f"{int(buy_zone_low):,}원 ~ {int(buy_zone_high):,}원",
        "stop_loss": int(stop_loss_price)
    }

    if hit_10_percent:
        status = "👋 다음 기회에 (이미 목표 수익 달성 후 조정 중)"
    elif vol_ratio <= 0.15 and buy_zone_low <= current_price <= buy_zone_high:
        status = "🚀 강력 추천 (거래량 급감 + 최적 가격대 진입)"
    elif vol_ratio <= 0.20:
        status = "🛒 분할 매수 (거래량 마름, 가격 분할 대응)"
    else:
        status = "⏳ 관망 (거래량 감소 및 에너지 응축 대기)"

    return result, status

# --- 4. 웹 UI 구성 ---
st.set_page_config(page_title="Antigravity Analyzer", layout="wide")

if check_password():
    st.title("💰 MSM v2.1 (안전 모드)")
    
    with st.sidebar:
        st.header("🔍 분석 설정")
        input_ticker = st.text_input("종목코드 6자리", value="264850")
        analysis_date = st.date_input("분석 기준일", datetime.date.today())

    if input_ticker:
        res, status = run_antigravity_analysis(input_ticker, analysis_date)
        
        if res:
            # 상단 지표 표시
            c1, c2, c3 = st.columns(3)
            # [수정] metric value는 문자열이나 숫자로 변환하여 에러 방지
            c1.metric("종목명", str(res['name']))
            c2.metric("거래량 비율", f"{res['vol_ratio']:.2%}")
            c3.metric("최종 판단", status)

            st.markdown("---")
            
            # 상세 리포트 표
            report_data = {
                "항목": ["최근 급등일", "현재가", "권장 매수대", "강력 손절가(자동매도)", "판단 결과"],
                "분석 내용": [
                    res['spike_date'], 
                    f"{res['current_price']:,}원", 
                    res['buy_zone'], 
                    f"🛑 {res['stop_loss']:,}원", 
                    status
                ]
            }
            st.table(pd.DataFrame(report_data))
            
            # 하단 가이드
            st.info(f"💡 **가이드:** 현재 {status} 상태입니다. 손절가는 시가 하단인 {res['stop_loss']:,}원을 반드시 엄수하세요.")
        else:
            st.warning(status)
