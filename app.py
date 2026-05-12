import streamlit as st
from pykrx import stock
import pandas as pd
import datetime

# --- 1. 보안 설정 (Streamlit Secrets 활용) ---
def check_password():
    """비밀번호가 올바른지 확인하는 함수"""
    def password_entered():
        if st.session_state["password"] == st.secrets["password"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # 보안을 위해 비밀번호 삭제
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input("Antigravity 시스템 비밀번호를 입력하세요", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("비밀번호가 틀렸습니다. 다시 입력하세요", type="password", on_change=password_entered, key="password")
        return False
    else:
        return True

# --- 2. Antigravity 핵심 분석 엔진 ---
def run_antigravity_analysis(ticker, base_date):
    try:
        # 데이터 수집 (기준일로부터 1년 전까지)
        start_date = (base_date - datetime.timedelta(days=365)).strftime("%Y%m%d")
        end_date = base_date.strftime("%Y%m%d")
        
        df = stock.get_market_ohlcv_by_date(start_date, end_date, ticker)
        if df.empty or len(df) < 10:
            return None, "데이터를 불러올 수 없습니다. 종목코드를 확인하세요."

        # 1. 최근 15% 이상 급등한 날(Spike Day) 찾기
        spikes = df[df['등락률'] >= 15]
        if spikes.empty:
            return None, "최근 1년 내 급등 패턴(15% 이상)이 발견되지 않았습니다."

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
        
        # 급등 이후 현재까지 최고가 확인 (수익 달성 여부)
        after_spike = df.loc[spike_date:]
        max_high_after = after_spike['고가'].max()
        hit_10_percent = max_high_after >= spike_close * 1.10

        # 3. 매수 적정가 및 손절가 계산
        # 피보나치 눌림목 (38.2% ~ 61.8%)
        buy_zone_high = spike_close - (spike_body * 0.382)
        buy_zone_low = spike_close - (spike_body * 0.618)
        stop_loss_price = spike_open * 0.98 # 급등날 시가 -2%를 강력 손절선으로 설정

        # --- 판단 로직 ---
        result = {
            "name": stock.get_market_ticker_name(ticker),
            "spike_date": spike_date.strftime("%Y-%m-%d"),
            "current_price": current_price,
            "vol_ratio": vol_ratio,
            "buy_zone": f"{int(buy_zone_low):,}원 ~ {int(buy_zone_high):,}원",
            "stop_loss": int(stop_loss_price)
        }

        if hit_10_percent:
            status = "👋 다음 기회에 (이미 10% 이상 수익 달성 후 조정 중)"
        elif vol_ratio <= 0.15 and buy_zone_low <= current_price <= buy_zone_high:
            status = "🚀 강력 추천 (거래량 급감 + 최적 매수 가격대 진입)"
        elif vol_ratio <= 0.20:
            status = "🛒 분할 매수 (거래량은 마랐으나 가격 조정을 지켜보며 진입)"
        else:
            status = "⏳ 관망 (에너지가 더 응축되어야 함 - 거래량 감소 대기)"

        return result, status

    except Exception as e:
        return None, f"에러 발생: {str(e)}"

# --- 3. 웹 화면 구성 ---
st.set_page_config(page_title="Antigravity Stock Analyzer", layout="wide")

if check_password():
    st.title("💰 Antigravity v2.0: 실시간 주식 분석기")
    st.markdown("---")

    # 사이드바 입력창
    with st.sidebar:
        st.header("🔍 분석 설정")
        input_ticker = st.text_input("종목코드 6자리", value="264850")
        analysis_date = st.date_input("분석 기준일", datetime.date.today())
        st.info("기준일을 변경하면 자동으로 실시간 분석이 실행됩니다.")

    # 실시간 분석 실행
    if input_ticker:
        res, status = run_antigravity_analysis(input_ticker, analysis_date)
        
        if res:
            # 결과 요약 카드
            col1, col2, col3 = st.columns(3)
            col1.metric("종목명", res['name'])
            col2.metric("현재 거래량 비율", f"{res['vol_ratio']:.2%}")
            col3.metric("판단", status)

            st.markdown("### 📊 상세 분석 리포트")
            report_df = pd.DataFrame({
                "항목": ["최근 급등일", "현재가", "권장 매수 가격대", "자동 매도(손절) 기준가", "최종 판단"],
                "값": [res['spike_date'], f"{res['current_price']:,}원", res['buy_zone'], f"🚨 {res['stop_loss']:,}원", status]
            })
            st.table(report_df)
            
            st.success(f"**전략 가이드:** {status} 상태입니다. 손절가는 {res['stop_loss']:,}원으로 설정하여 대응하세요.")
        else:
            st.error(status)
