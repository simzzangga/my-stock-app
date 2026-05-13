import streamlit as st
import FinanceDataReader as fdr
import pandas as pd
import datetime
import time

# --- 1. 보안 및 세션 초기화 ---
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False
    if st.session_state["password_correct"]: return True

    st.title("💰 Shim's MSM Portal (FDR Edition)")
    password = st.text_input("비밀번호를 입력하세요", type="password")
    if st.button("접속", use_container_width=True):
        if password == st.secrets.get("password", "1234"): 
            st.session_state["password_correct"] = True
            st.rerun()
        else: st.error("비밀번호가 틀렸습니다.")
    return False

# --- 2. 안정성 강화 데이터 엔진 (FDR 기반) ---
@st.cache_data(ttl=86400)
def get_ticker_dict():
    """KRX 전체 종목 리스트 및 종목명 캐싱"""
    try:
        # FDR을 사용하여 국내 상장사 목록 일괄 수집
        df_krx = fdr.StockListing('KRX')
        return dict(zip(df_krx['Code'], df_krx['Name']))
    except:
        return {"005930": "삼성전자"}

@st.cache_data(ttl=600)
def get_robust_ohlcv(ticker, start, end):
    """FDR 기반 데이터 수집 (네이버 금융 소스 활용으로 안정성 높음)"""
    for _ in range(3):
        try:
            df = fdr.DataReader(ticker, start, end)
            if df is not None and not df.empty:
                # pykrx 로직 호환을 위한 컬럼명 변경
                df = df.rename(columns={
                    'Open': '시가', 'High': '고가', 'Low': '저가', 
                    'Close': '종가', 'Volume': '거래량', 'Change': '등락률'
                })
                # FDR의 등락률은 소수점(0.15)이므로 % 단위(15.0)로 변환
                df['등락률'] = df['등락률'] * 100
                return df
            time.sleep(0.1)
        except: continue
    return pd.DataFrame()

def add_to_recent_logs(ticker, name):
    if "recent_logs" not in st.session_state: st.session_state["recent_logs"] = []
    log_entry = f"{name} ({ticker})"
    if log_entry in st.session_state["recent_logs"]: st.session_state["recent_logs"].remove(log_entry)
    st.session_state["recent_logs"].insert(0, log_entry)
    st.session_state["recent_logs"] = st.session_state["recent_logs"][:10]

# --- 3. 분석 엔진 (v3.3 & v4.0) ---
def run_analysis(ticker, base_date, mode):
    start_date = (base_date - datetime.timedelta(days=365)).strftime("%Y-%m-%d")
    end_date = base_date.strftime("%Y-%m-%d")
    df = get_robust_ohlcv(ticker, start_date, end_date)
    if df.empty: return None, "데이터 없음"

    current_price = df['종가'].iloc[-1]
    
    if "v3.3" in mode:
        spikes = df[df['등락률'] >= 15]
        if spikes.empty: return None, "급등 패턴 없음"
        recent = spikes.tail(1)
        s_close, s_open, s_vol = recent['종가'].values[0], recent['시가'].values[0], recent['거래량'].values[0]
        s_body = s_close - s_open
        vol_ratio = df['거래량'].iloc[-1] / s_vol if s_vol != 0 else 0
        b_high, b_low = s_close - (s_body * 0.382), s_close - (s_body * 0.618)
        
        if vol_ratio <= 0.15 and b_low <= current_price <= b_high: status = "🚀 강력 추천"
        elif vol_ratio <= 0.22: status = "🛒 분할 매수"
        elif current_price < s_open * 0.98: status = "🚨 매도/이탈"
        else: status = "⏳ 관망"
        
        return {"spike_date": recent.index[0].strftime("%Y-%m-%d"), "current_price": current_price, "target": int(current_price*1.1), "vol_ratio": vol_ratio, "buy_zone": f"{int(b_low):,}~{int(b_high):,}", "stop": int(s_open*0.98)}, status
    
    else: # v4.0
        df['vol20'] = df['거래량'].rolling(20).mean()
        spikes = df[(df['등락률'] >= 15) & (df['거래량'] > df['vol20'] * 3)]
        if spikes.empty: return None, "조건 미달"
        recent = spikes.tail(1)
        s_close, s_open, s_high = recent['종가'].values[0], recent['시가'].values[0], recent['고가'].values[0]
        s_body = s_close - s_open
        b1, b2, b3 = s_close-(s_body*0.382), s_close-(s_body*0.5), s_close-(s_body*0.618)
        
        if b1 >= current_price > b2: status = "🟡 1차 타점"
        elif b2 >= current_price > b3: status = "🟠 2차 타점"
        elif b3 >= current_price > s_open*0.98: status = "🔴 3차 타점"
        else: status = "⏳ 이탈/관망"
        
        return {"spike_date": recent.index[0].strftime("%Y-%m-%d"), "current_price": current_price, "b1": int(b1), "b2": int(b2), "b3": int(b3), "target": int(s_high*0.98), "stop": int(s_open*0.98)}, status

# --- 4. 메인 UI ---
st.set_page_config(page_title="Shim's MSM Dual Pro", layout="wide")

if check_password():
    ticker_dict = get_ticker_dict()
    
    st.sidebar.title("⚙️ 시스템 설정")
    app_mode = st.sidebar.radio("분석 엔진 선택", ["v3.3 (수급 중심)", "v4.0 (타점 중심)"])
    
    st.title(f"📊 Shim's MSM Dual Pro - {app_mode}")

    # [A] 종목 정밀 분석
    st.markdown("### 🔍 개별 종목 분석")
    with st.container(border=True):
        c1, c2, c3 = st.columns([2, 2, 1.2])
        input_ticker = c1.text_input("종목코드", value="265560")
        analysis_date = c2.date_input("기준 날짜", datetime.date.today())
        btn_run = c3.button("📊 분석 실행", use_container_width=True, type="primary")

    if btn_run or input_ticker:
        name = ticker_dict.get(input_ticker, "알 수 없는 종목")
        res, status = run_analysis(input_ticker, analysis_date, app_mode)
        if res:
            add_to_recent_logs(input_ticker, name)
            st.success(f"🎯 {name} ({input_ticker}) - {status}")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("현재가", f"{res['current_price']:,}원")
            m2.metric("목표가", f"{res['target']:,}원")
            if "v3.3" in app_mode:
                m3.metric("거래비율", f"{res['vol_ratio']:.1%}")
                st.table(pd.DataFrame({"항목": ["기준일", "매수구간", "손절가"], "내용": [res['spike_date'], res['buy_zone'], f"{res['stop']:,}원"]}))
            else:
                m3.metric("1차 타점", f"{res['b1']:,}원")
                st.table(pd.DataFrame({"항목": ["기준일", "2차타점", "3차타점", "손절가"], "내용": [res['spike_date'], f"{res['b2']:,}원", f"{res['b3']:,}원", f"{res['stop']:,}원"]}))
        else: st.info(status)

    st.markdown("---")

    # [B] 고속 시장 스캐너
    st.markdown("### 📡 시장 스캐너 (FDR 기반)")
    if st.button("🚀 전 종목 스캔 시작", use_container_width=True):
        with st.status("분석 중...", expanded=True) as status_box:
            # 전체 종목 등락률 조회
            st.write("1단계: 전체 시장 데이터 로드...")
            target_date_str = analysis_date.strftime("%Y-%m-%d")
            # fdr.StockListing을 활용해 등락률 필터링 우회 가능하나,
            # 정확도를 위해 등락률이 높은 후보군을 먼저 선별
            df_list = fdr.StockListing('KRX')
            candidates = df_list[df_list['ChgPct'] >= 10]['Code'].tolist()
            
            st.write(f"2단계: {len(candidates)}개 후보 종목 정밀 분석...")
            found = []
            for t in candidates:
                res, status = run_analysis(t, analysis_date, app_mode)
                if res and ("매수" in status or "추천" in status):
                    found.append({
                        "종목명": ticker_dict.get(t, t),
                        "코드": t,
                        "상태": status,
                        "현재가": f"{res['current_price']:,}원",
                        "목표가": f"{res['target']:,}원"
                    })
            status_box.update(label="스캔 완료!", state="complete", expanded=False)
            if found: st.dataframe(pd.DataFrame(found), use_container_width=True)
            else: st.write("조건 부합 종목 없음")

    # [C] 최근 조회 기록
    if "recent_logs" in st.session_state and st.session_state["recent_logs"]:
        st.markdown("---")
        st.markdown("### 🕒 최근 조회 기록")
        cols = st.columns(5)
        for i, log in enumerate(st.session_state["recent_logs"]):
            cols[i % 5].button(log, key=f"log_{i}", use_container_width=True)
