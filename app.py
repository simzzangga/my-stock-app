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

# --- 2. 데이터 수집 엔진 ---
@st.cache_data(ttl=600)
def get_robust_ohlcv(ticker, start, end):
    for _ in range(3):
        try:
            df = stock.get_market_ohlcv_by_date(start, end, ticker)
            if df is not None and not df.empty: return df
            time.sleep(0.1)
        except: continue
    return pd.DataFrame()

@st.cache_data(ttl=86400)
def get_verified_ticker_list():
    try:
        ksp = stock.get_market_ticker_list(market="KOSPI")
        ksq = stock.get_market_ticker_list(market="KOSDAQ")
        return list(set(ksp + ksq))
    except: return []

# --- 3. 핵심 분석 로직 (v4.0 기반) ---
def run_antigravity_analysis(ticker, base_date):
    if not ticker or len(ticker) != 6: return None, "종목코드 오류"

    start_date = (base_date - datetime.timedelta(days=365)).strftime("%Y%m%d")
    end_date = base_date.strftime("%Y%m%d")
    
    df = get_robust_ohlcv(ticker, start_date, end_date)
    try: raw_name = stock.get_market_ticker_name(ticker)
    except: raw_name = "Unknown"

    if df.empty or len(df) < 120: return None, "데이터 부족"

    df['ma5'] = df['종가'].rolling(5).mean()
    df['ma20'] = df['종가'].rolling(20).mean()
    df['vol20'] = df['거래량'].rolling(20).mean()

    # 기준봉 탐색 (v4.0 강화 조건)
    spikes = df[(df['등락률'] >= 15) & (df['종가'] > df['시가']) & (df['거래량'] > df['vol20'] * 3)]
    if spikes.empty: return None, "기준봉 조건 미달"

    recent_spike = spikes.tail(1)
    spike_date = recent_spike.index[0]
    spike_close, spike_open, spike_high, spike_vol = \
        recent_spike['종가'].values[0], recent_spike['시가'].values[0], \
        recent_spike['고가'].values[0], recent_spike['거래량'].values[0]
    
    spike_body = spike_close - spike_open
    after_spike = df.loc[spike_date:].iloc[1:]
    
    if len(after_spike) < 3: return None, "눌림 형성 초기"

    current_price = df['종가'].iloc[-1]
    current_vol = df['거래량'].iloc[-1]

    # 시세 분출 여부 및 수급 체크
    if after_spike['고가'].max() >= spike_close * 1.10: return None, "시세 분출 완료"
    recent_vol_avg = after_spike['거래량'].tail(5).mean()
    vol_ratio = recent_vol_avg / spike_vol if spike_vol != 0 else 999
    if current_vol > df['vol20'].iloc[-1] * 0.9: return None, "수급 조절 중"

    # 3단계 매수 구간 계산
    buy1, buy2, buy3 = spike_close - (spike_body * 0.382), \
                       spike_close - (spike_body * 0.5), \
                       spike_close - (spike_body * 0.618)
    stop_loss = spike_open * 0.98

    # 이평선 지지 확인
    ma_ok = (df['ma5'].iloc[-1] > df['ma20'].iloc[-1]) and (current_price > df['ma20'].iloc[-1] * 0.95)
    if not ma_ok: return None, "이평선 조건 부적합"

    # 신호 판정
    status = None
    if buy1 >= current_price > buy2: status = "🟡 1차 매수"
    elif buy2 >= current_price > buy3: status = "🟠 2차 매수"
    elif current_price <= buy3 and current_price > stop_loss: status = "🔴 3차 매수"
    else: return None, "매수 구간 이탈"

    target_10 = max(int(spike_high * 0.98), int(current_price * 1.10))
    
    return {
        "full_name": f"{raw_name} ({ticker})",
        "spike_date": spike_date.strftime("%Y-%m-%d"),
        "current_price": current_price,
        "target_10": target_10,
        "buy1": int(buy1), "buy2": int(buy2), "buy3": int(buy3),
        "stop_loss": int(stop_loss),
        "reliability": 100 - int(vol_ratio * 100), # 간략화된 신뢰도 계산
        "potential_yield": ((target_10 / current_price) - 1) * 100
    }, status

# --- 4. 시장 스캔 함수 ---
def scan_market_full(base_date):
    tickers = get_verified_ticker_list()
    if not tickers: return [], [], []
    b1_list, b2_list, b3_list = [], [], []
    msg, bar = st.empty(), st.progress(0)
    for i, t in enumerate(tickers):
        if i % 100 == 0:
            msg.info(f"📡 {base_date.strftime('%Y-%m-%d')} 전수 스캔 중...")
            bar.progress(i / len(tickers))
        res, status = run_antigravity_analysis(t, base_date)
        if res:
            item = {"종목": res['full_name'], "현재가": f"{res['current_price']:,}원", "목표가": f"{res['target_10']:,}원", "수익률": f"+{res['potential_yield']:.1f}%"}
            if status == "🟡 1차 매수": b1_list.append(item)
            elif status == "🟠 2차 매수": b2_list.append(item)
            elif status == "🔴 3차 매수": b3_list.append(item)
    bar.empty(); msg.empty()
    return b1_list, b2_list, b3_list

# --- 5. 웹 UI (Restored View) ---
st.set_page_config(page_title="Shim's MSM v3.3", layout="wide")

if check_password():
    st.title("💰 Shim's MSM v3.3")
    
    st.markdown("### 🔍 분석 제어 센터")
    c1, c2, c3 = st.columns([2, 2, 1.2])
    with c1: input_ticker = st.text_input("종목코드 6자리", value="265560")
    with c2: analysis_date = st.date_input("기준 날짜 선택", datetime.date.today())
    with c3:
        st.markdown('<div style="margin-top: 28px;"></div>', unsafe_allow_html=True)
        if st.button("🔄 데이터 다시 분석", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    # [복구된 섹션] 개별 종목 분석 결과 표
    res, status = run_antigravity_analysis(input_ticker, analysis_date)
    if res:
        st.markdown(f"#### 🎯 {res['full_name']} 분석 결과 및 매매 전략")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("판단", status)
        m2.metric("목표 매도가", f"{res['target_10']:,}원")
        m3.metric("기대 수익", f"+{res['potential_yield']:.1f}%")
        m4.metric("분석 상태", "정상")
        
        # 이전 버전의 상세 결과 표 복구
        df_result = pd.DataFrame({
            "항목": ["최근 급등일", "현재가", "1차 매수 타점", "2차 매수 타점", "3차 매수 타점", "손절가", "목표가"],
            "내용": [
                res['spike_date'], 
                f"{res['current_price']:,}원", 
                f"{res['buy1']:,}원", 
                f"{res['buy2']:,}원", 
                f"{res['buy3']:,}원", 
                f"{res['stop_loss']:,}원", 
                f"{res['target_10']:,}원"
            ]
        })
        st.table(df_result)
    else:
        st.info(f"💡 분석 결과: {status}")

    st.markdown("---")

    # 시장 스캐너
    st.markdown("### 📡 시장 전수 스캐너")
    sc1, sc2 = st.columns(2)
    with sc1: btn_back = st.button(f"📅 {analysis_date.strftime('%m/%d')} 기준 스캔", use_container_width=True)
    with sc2: btn_today = st.button("☀️ 오늘 기준 실시간 스캔", use_container_width=True)

    t_date = analysis_date if btn_back else (datetime.date.today() if btn_today else None)
    if t_date:
        b1, b2, b3 = scan_market_full(t_date)
        res_c1, res_c2, res_c3 = st.columns(3)
        with res_c1:
            st.success(f"🟡 1차 매수 ({len(b1)}개)")
            if b1: st.table(pd.DataFrame(b1))
        with res_c2:
            st.warning(f"🟠 2차 매수 ({len(b2)}개)")
            if b2: st.table(pd.DataFrame(b2))
        with res_c3:
            st.error(f"🔴 3차 매수 ({len(b3)}개)")
            if b3: st.table(pd.DataFrame(b3))
