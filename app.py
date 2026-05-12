import streamlit as st
from pykrx import stock
import pandas as pd
import datetime
import time

# --- 1. 보안 및 세션 설정 ---
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False
    
    if st.session_state["password_correct"]:
        return True

    # 첫 화면 로그인 UI
    st.title("💰 Shim's MSM Portal")
    password = st.text_input("비밀번호를 입력하세요", type="password")
    if st.button("접속", use_container_width=True):
        if password == st.secrets.get("password", "1234"): 
            st.session_state["password_correct"] = True
            st.rerun() # 즉시 메인 화면으로 진입
        else:
            st.error("비밀번호가 틀렸습니다.")
    return False

# --- 2. 최근 조회 종목 로그 관리 ---
def add_to_recent_logs(ticker_name):
    if "recent_logs" not in st.session_state:
        st.session_state["recent_logs"] = []
    
    # 중복 제거 후 최신 항목을 맨 앞으로
    if ticker_name in st.session_state["recent_logs"]:
        st.session_state["recent_logs"].remove(ticker_name)
    st.session_state["recent_logs"].insert(0, ticker_name)
    
    # 최근 10개까지만 유지
    st.session_state["recent_logs"] = st.session_state["recent_logs"][:10]

# --- 3. 데이터 수집 엔진 (안정성 강화) ---
@st.cache_data(ttl=600)
def get_robust_ohlcv(ticker, start, end):
    for _ in range(3):
        try:
            df = stock.get_market_ohlcv_by_date(start, end, ticker)
            if df is not None and not df.empty: return df
            time.sleep(0.2)
        except: continue
    return pd.DataFrame()

# --- 4. 분석 로직 (v3.3 & v4.0) ---
def logic_v33(ticker, base_date):
    start_date = (base_date - datetime.timedelta(days=365)).strftime("%Y%m%d")
    end_date = base_date.strftime("%Y%m%d")
    df = get_robust_ohlcv(ticker, start_date, end_date)
    if df.empty: return None, "데이터 없음"
    
    spikes = df[df['등락률'] >= 15]
    if spikes.empty: return None, "패턴 없음"
    
    recent_spike = spikes.tail(1)
    s_close, s_open, s_vol = recent_spike['종가'].values[0], recent_spike['시가'].values[0], recent_spike['거래량'].values[0]
    s_body = s_close - s_open
    current_price = df['종가'].iloc[-1]
    vol_ratio = df['거래량'].iloc[-1] / s_vol if s_vol != 0 else 0
    
    b_high, b_low = s_close - (s_body * 0.382), s_close - (s_body * 0.618)
    status = "🚀 강력 추천" if vol_ratio <= 0.15 and b_low <= current_price <= b_high else "🛒 분할 매수" if vol_ratio <= 0.22 else "⏳ 관망"
    
    return {"spike_date": recent_spike.index[0].strftime("%Y-%m-%d"), "current_price": current_price, "buy_zone": f"{int(b_low):,}~{int(b_high):,}", "vol_ratio": vol_ratio, "stop_loss": int(s_open*0.98), "target_10": int(current_price*1.1)}, status

def logic_v40(ticker, base_date):
    start_date = (base_date - datetime.timedelta(days=365)).strftime("%Y%m%d")
    end_date = base_date.strftime("%Y%m%d")
    df = get_robust_ohlcv(ticker, start_date, end_date)
    if df.empty or len(df) < 120: return None, "데이터 부족"
    
    df['vol20'] = df['거래량'].rolling(20).mean()
    spikes = df[(df['등락률'] >= 15) & (df['거래량'] > df['vol20'] * 3)]
    if spikes.empty: return None, "조건 미달"
    
    recent = spikes.tail(1)
    s_close, s_open, s_high = recent['종가'].values[0], recent['시가'].values[0], recent['고가'].values[0]
    s_body = s_close - s_open
    current_price = df['종가'].iloc[-1]
    
    b1, b2, b3 = s_close-(s_body*0.382), s_close-(s_body*0.5), s_close-(s_body*0.618)
    stop_loss = s_open * 0.98

    if b1 >= current_price > b2: status = "🟡 1차 매수"
    elif b2 >= current_price > b3: status = "🟠 2차 매수"
    elif current_price <= b3 and current_price > stop_loss: status = "🔴 3차 매수"
    else: return None, "구간 이탈"

    return {"spike_date": recent.index[0].strftime("%Y-%m-%d"), "current_price": current_price, "buy1": int(b1), "buy2": int(b2), "buy3": int(b3), "stop_loss": int(stop_loss), "target_10": max(int(s_high*0.98), int(current_price*1.1))}, status

# --- 5. 메인 UI ---
st.set_page_config(page_title="Shim's MSM Dual", layout="wide")

if check_password():
    # 사이드바 설정
    st.sidebar.title("⚙️ 로직 선택")
    app_mode = st.sidebar.radio("버전 선택", ["v3.3 (수급 중심)", "v4.0 (타점 중심)"])
    
    st.title(f"💰 Shim's MSM {app_mode}")
    
    # 검색 섹션
    st.markdown("### 🔍 종목 분석")
    c1, c2, c3 = st.columns([2, 2, 1.2])
    with c1: input_ticker = st.text_input("종목코드 6자리", value="265560")
    with c2: analysis_date = st.date_input("기준 날짜", datetime.date.today())
    with c3:
        st.markdown('<div style="margin-top: 28px;"></div>', unsafe_allow_html=True)
        analyze_btn = st.button("📊 분석 실행", use_container_width=True)

    # 분석 수행 및 로그 기록
    if input_ticker:
        try:
            ticker_name = f"{stock.get_market_ticker_name(input_ticker)} ({input_ticker})"
            
            if "v3.3" in app_mode:
                res, status = logic_v33(input_ticker, analysis_date)
                if res:
                    add_to_recent_logs(ticker_name) # 로그 추가
                    st.success(f"🎯 {ticker_name} 분석 완료: {status}")
                    m1, m2, m3 = st.columns(3)
                    m1.metric("현재가", f"{res['current_price']:,}원")
                    m2.metric("거래비율", f"{res['vol_ratio']:.1%}")
                    m3.metric("목표가", f"{res['target_10']:,}원")
                    st.table(pd.DataFrame({"항목": ["최근급등", "매수구간", "손절가"], "내용": [res['spike_date'], res['buy_zone'], f"{res['stop_loss']:,}원"]}))
                else: st.info(status)
            else:
                res, status = logic_v40(input_ticker, analysis_date)
                if res:
                    add_to_recent_logs(ticker_name) # 로그 추가
                    st.success(f"🎯 {ticker_name} 분석 완료: {status}")
                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("현재가", f"{res['current_price']:,}원")
                    m2.metric("1차", f"{res['buy1']:,}원")
                    m3.metric("2차", f"{res['buy2']:,}원")
                    m4.metric("3차", f"{res['buy3']:,}원")
                    st.table(pd.DataFrame({"항목": ["기준일", "손절가", "목표가"], "내용": [res['spike_date'], f"{res['stop_loss']:,}원", f"{res['target_10']:,}원"]}))
                else: st.info(status)
        except: st.error("종목 정보를 불러올 수 없습니다.")

    # --- 하단 최근 본 종목 로그 ---
    st.markdown("---")
    st.markdown("### 🕒 최근 조회 기록")
    if "recent_logs" in st.session_state and st.session_state["recent_logs"]:
        cols = st.columns(5) # 5개씩 한 줄에 표시
        for i, log in enumerate(st.session_state["recent_logs"]):
            cols[i % 5].button(log, key=f"log_{i}_{log}", use_container_width=True)
    else:
        st.caption("최근 조회한 종목이 없습니다.")
