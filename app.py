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
    
    st.title("💰 Shim's MSM Portal")
    password = st.text_input("비밀번호를 입력하세요", type="password")
    if st.button("접속"):
        # 비밀번호는 기존 설정값을 유지합니다.
        if password == st.secrets.get("password", "1234"): 
            st.session_state["password_correct"] = True
            st.rerun()
        else:
            st.error("비밀번호가 틀렸습니다.")
    return False

# --- 2. 데이터 수집 엔진 (오류 수정 및 안정성 강화) ---
@st.cache_data(ttl=600)
def get_robust_ohlcv(ticker, start, end):
    for _ in range(3): # 최대 3번 재시도하여 종목 불러오기 오류 방지
        try:
            df = stock.get_market_ohlcv_by_date(start, end, ticker)
            if df is not None and not df.empty: return df
            time.sleep(0.2) # 서버 부하 방지용 미세 지연
        except: continue
    return pd.DataFrame()

@st.cache_data(ttl=86400)
def get_verified_ticker_list():
    try:
        ksp = stock.get_market_ticker_list(market="KOSPI")
        ksq = stock.get_market_ticker_list(market="KOSDAQ")
        return list(set(ksp + ksq))
    except: return []

# --- 3. 로직 A: v3.3 (기존 수급/거래비율 중심) ---
def logic_v33(ticker, base_date):
    start_date = (base_date - datetime.timedelta(days=365)).strftime("%Y%m%d")
    end_date = base_date.strftime("%Y%m%d")
    df = get_robust_ohlcv(ticker, start_date, end_date)
    
    if df.empty: return None, "데이터 없음"
    spikes = df[df['등락률'] >= 15]
    if spikes.empty: return None, "급등 패턴 없음"

    recent_spike = spikes.tail(1)
    spike_date = recent_spike.index[0]
    spike_close, spike_open, spike_vol = recent_spike['종가'].values[0], recent_spike['시가'].values[0], recent_spike['거래량'].values[0]
    spike_body = spike_close - spike_open

    current_price = df['종가'].iloc[-1]
    current_vol = df['거래량'].iloc[-1]
    vol_ratio = current_vol / spike_vol if spike_vol != 0 else 0
    
    buy_high = spike_close - (spike_body * 0.382)
    buy_low = spike_close - (spike_body * 0.618)
    
    if vol_ratio <= 0.15 and buy_low <= current_price <= buy_high: status = "🚀 강력 추천"
    elif vol_ratio <= 0.22: status = "🛒 분할 매수"
    else: status = "⏳ 관망 대기"

    return {
        "spike_date": spike_date.strftime("%Y-%m-%d"),
        "current_price": current_price,
        "buy_zone": f"{int(buy_low):,}원 ~ {int(buy_high):,}원",
        "vol_ratio": vol_ratio,
        "stop_loss": int(spike_open * 0.98),
        "target_10": int(current_price * 1.10)
    }, status

# --- 4. 로직 B: v4.0 (고도화된 3단계 타점 중심) ---
def logic_v40(ticker, base_date):
    start_date = (base_date - datetime.timedelta(days=365)).strftime("%Y%m%d")
    end_date = base_date.strftime("%Y%m%d")
    df = get_robust_ohlcv(ticker, start_date, end_date)
    
    if df.empty or len(df) < 120: return None, "데이터 부족"
    df['vol20'] = df['거래량'].rolling(20).mean()
    
    # v4.0 강화 조건: 15% 이상 급등 + 거래량 3배 이상
    spikes = df[(df['등락률'] >= 15) & (df['거래량'] > df['vol20'] * 3)]
    if spikes.empty: return None, "기준봉 조건 미달"

    recent_spike = spikes.tail(1)
    spike_date = recent_spike.index[0]
    s_close, s_open, s_high = recent_spike['종가'].values[0], recent_spike['시가'].values[0], recent_spike['고가'].values[0]
    s_body = s_close - s_open
    
    current_price = df['종가'].iloc[-1]
    
    # v4.0 3단계 매수 구간
    b1, b2, b3 = s_close-(s_body*0.382), s_close-(s_body*0.5), s_close-(s_body*0.618)
    stop_loss = s_open * 0.98

    if b1 >= current_price > b2: status = "🟡 1차 매수"
    elif b2 >= current_price > b3: status = "🟠 2차 매수"
    elif current_price <= b3 and current_price > stop_loss: status = "🔴 3차 매수"
    else: return None, "매수 구간 이탈 또는 시세 분출"

    return {
        "spike_date": spike_date.strftime("%Y-%m-%d"),
        "current_price": current_price,
        "buy1": int(b1), "buy2": int(b2), "buy3": int(b3),
        "stop_loss": int(stop_loss),
        "target_10": max(int(s_high * 0.98), int(current_price * 1.10))
    }, status

# --- 5. 웹 UI (v3.3 포맷 기반) ---
st.set_page_config(page_title="Shim's MSM Dual", layout="wide")

if check_password():
    # 사이드바에서 로직 선택 (Dual Test용)
    st.sidebar.title("⚙️ 로직 엔진 선택")
    app_mode = st.sidebar.radio("비교할 버전을 선택하세요", ["v3.3 (기존 수급 중심)", "v4.0 (고도화 타점 중심)"])
    
    if st.sidebar.button("🔄 캐시 및 데이터 초기화"):
        st.cache_data.clear()
        st.rerun()

    st.title(f"💰 Shim's MSM {app_mode}")
    
    # 상단 컨트롤바 (v3.3 UI 유지)
    st.markdown("### 🔍 분석 제어 센터")
    c1, c2, c3 = st.columns([2, 2, 1.2])
    with c1: input_ticker = st.text_input("종목코드 6자리", value="265560")
    with c2: analysis_date = st.date_input("기준 날짜 선택", datetime.date.today())
    with c3:
        st.markdown('<div style="margin-top: 28px;"></div>', unsafe_allow_html=True)
        if st.button("📊 다시 분석하기", use_container_width=True):
            st.rerun()

    # --- 엔진별 결과 출력 ---
    if "v3.3" in app_mode:
        res, status = logic_v33(input_ticker, analysis_date)
        if res:
            st.markdown(f"#### 🎯 분석 결과: {status}")
            m1, m2, m3 = st.columns(3)
            m1.metric("현재가", f"{res['current_price']:,}원")
            m2.metric("거래비율", f"{res['vol_ratio']:.1%}")
            m3.metric("10% 목표가", f"{res['target_10']:,}원")
            
            st.table(pd.DataFrame({
                "항목": ["최근 급등일", "매수 권장구간", "손절가", "현재가"],
                "내용": [res['spike_date'], res['buy_zone'], f"{res['stop_loss']:,}원", f"{res['current_price']:,}원"]
            }))
        else: st.info(f"💡 안내: {status}")

    else: # v4.0 엔진
        res, status = logic_v40(input_ticker, analysis_date)
        if res:
            st.markdown(f"#### 🎯 분석 결과: {status}")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("현재가", f"{res['current_price']:,}원")
            m2.metric("1차 타점", f"{res['buy1']:,}원")
            m3.metric("2차 타점", f"{res['buy2']:,}원")
            m4.metric("3차 타점", f"{res['buy3']:,}원")
            
            st.table(pd.DataFrame({
                "항목": ["기준봉 날짜", "1차 지지선", "2차 지지선", "3차 지지선", "손절가", "목표가"],
                "내용": [res['spike_date'], f"{res['buy1']:,}원", f"{res['buy2']:,}원", f"{res['buy3']:,}원", f"{res['stop_loss']:,}원", f"{res['target_10']:,}원"]
            }))
        else: st.info(f"💡 안내: {status}")

    st.markdown("---")
    st.caption("※ 본 프로그램은 투자 참고용이며, 모든 투자의 책임은 본인에게 있습니다.")
