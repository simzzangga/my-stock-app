import streamlit as st
import FinanceDataReader as fdr
import pandas as pd
import datetime
import time

# --- 1. 보안 및 세션 설정 ---
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False
    if st.session_state["password_correct"]: return True

    st.title("💰 Shim's MSM Portal")
    password = st.text_input("비밀번호를 입력하세요", type="password")
    if st.button("접속", use_container_width=True):
        if password == st.secrets.get("password", "1234"): 
            st.session_state["password_correct"] = True
            st.rerun()
        else: st.error("비밀번호가 틀렸습니다.")
    return False

# --- 2. 데이터 엔진 (FDR 기반) ---
@st.cache_data(ttl=86400)
def get_ticker_dict():
    try:
        df_krx = fdr.StockListing('KRX')
        code_to_name = dict(zip(df_krx['Code'].astype(str), df_krx['Name']))
        name_to_code = dict(zip(df_krx['Name'], df_krx['Code'].astype(str)))
        # 거래대금 상위 종목 리스트 (스캔 속도 향상용)
        top_tickers = df_krx.sort_values(by='Amount', ascending=False)['Code'].head(500).tolist()
        return code_to_name, name_to_code, top_tickers
    except:
        return {"005930": "삼성전자"}, {"삼성전자": "005930"}, ["005930"]

@st.cache_data(ttl=600)
def get_robust_ohlcv(ticker, start, end):
    if not ticker: return pd.DataFrame()
    for _ in range(3):
        try:
            df = fdr.DataReader(ticker, start, end)
            if df is not None and not df.empty:
                df.columns = [c.upper() for c in df.columns]
                rename_map = {'OPEN': '시가', 'HIGH': '고가', 'LOW': '저가', 'CLOSE': '종가', 'VOLUME': '거래량', 'CHANGE': '등락률'}
                df = df.rename(columns=rename_map)
                if '등락률' not in df.columns: df['등락률'] = df['종가'].pct_change()
                df['등락률'] = df['등락률'].fillna(0) * 100
                return df
            time.sleep(0.05)
        except: continue
    return pd.DataFrame()

def add_search_log(log_text):
    if "search_logs" not in st.session_state: st.session_state["search_logs"] = []
    if log_text in st.session_state["search_logs"]: st.session_state["search_logs"].remove(log_text)
    st.session_state["search_logs"].insert(0, log_text)
    st.session_state["search_logs"] = st.session_state["search_logs"][:10]

# --- 3. 분석 엔진 (v3.3 & v4.0) ---
def run_analysis(ticker, base_date, mode):
    # 최근 1년간의 데이터 로드
    start_date = (base_date - datetime.timedelta(days=365)).strftime("%Y-%m-%d")
    end_date = base_date.strftime("%Y-%m-%d")
    df = get_robust_ohlcv(ticker, start_date, end_date)
    
    if df.empty or len(df) < 15: return None, "데이터 부족"
    
    current_price = int(df['종가'].iloc[-1])
    
    if "v3.3" in mode:
        spikes = df[df['등락률'] >= 15]
        if spikes.empty: return None, "패턴 없음"
        recent = spikes.tail(1)
        s_date = recent.index[0]
        # 너무 오래된 기준봉(60일 이상)은 제외
        if (base_date - s_date.date()).days > 60: return None, "기준봉 노후화"
        
        s_close, s_open, s_vol = int(recent['종가'].iloc[0]), int(recent['시가'].iloc[0]), float(recent['거래량'].iloc[0])
        s_body = s_close - s_open
        vol_ratio = float(df['거래량'].iloc[-1]) / s_vol if s_vol != 0 else 0
        b_high, b_low = s_close - (s_body * 0.382), s_close - (s_body * 0.618)
        
        if vol_ratio <= 0.20 and b_low <= current_price <= b_high: status = "🚀 강력 추천"
        elif vol_ratio <= 0.30 and current_price >= b_low: status = "🛒 분할 매수"
        else: return None, "구간 이탈"
        
        return {"spike_date": s_date.strftime("%Y-%m-%d"), "current_price": current_price, "target": int(current_price*1.1), "vol_ratio": vol_ratio, "buy_zone": f"{int(b_low):,}~{int(b_high):,}", "stop": int(s_open*0.98)}, status
    
    else: # v4.0
        df['vol20'] = df['거래량'].rolling(20).mean()
        spikes = df[(df['등락률'] >= 15) & (df['거래량'] > df['vol20'] * 2.5)]
        if spikes.empty: return None, "기준봉 미달"
        recent = spikes.tail(1)
        s_date = recent.index[0]
        if (base_date - s_date.date()).days > 45: return None, "기준봉 노후화"
        
        s_close, s_open, s_high = int(recent['종가'].iloc[0]), int(recent['시가'].iloc[0]), int(recent['고가'].iloc[0])
        s_body = s_close - s_open
        b1, b2, b3 = s_close-(s_body*0.382), s_close-(s_body*0.5), s_close-(s_body*0.618)
        
        if b1 >= current_price > b2: status = "🟡 1차 타점"
        elif b2 >= current_price > b3: status = "🟠 2차 타점"
        elif b3 >= current_price > s_open*0.98: status = "🔴 3차 타점"
        else: return None, "구간 이탈"
        
        return {"spike_date": s_date.strftime("%Y-%m-%d"), "current_price": current_price, "b1": int(b1), "b2": int(b2), "b3": int(b3), "target": int(s_high*0.98), "stop": int(s_open*0.98)}, status

# --- 4. 메인 UI ---
st.set_page_config(page_title="Shim's MSM Dual Pro", layout="wide")

if check_password():
    code_to_name, name_to_code, top_tickers = get_ticker_dict()
    
    st.sidebar.title("⚙️ 설정")
    app_mode = st.sidebar.radio("엔진 선택", ["v3.3 (수급 중심)", "v4.0 (타점 중심)"])
    
    st.sidebar.markdown("---")
    st.sidebar.subheader("🔍 종목명 → 코드")
    search_name = st.sidebar.text_input("종목명 입력")
    if search_name:
        f_code = name_to_code.get(search_name)
        if f_code: st.sidebar.success(f"코드: `{f_code}`")
        else: st.sidebar.error("없음")

    st.title(f"📊 Shim's MSM - {app_mode}")

    # [A] 개별 분석
    with st.container(border=True):
        c1, c2, c3 = st.columns([2, 2, 1.2])
        input_ticker = c1.text_input("종목코드", value="265560")
        analysis_date = c2.date_input("날짜", datetime.date.today())
        st.markdown('<div style="margin-top: 28px;"></div>', unsafe_allow_html=True)
        btn_run = c3.button("📊 분석 실행", use_container_width=True, type="primary")

    if btn_run or input_ticker:
        name = code_to_name.get(input_ticker, "Unknown")
        res, status = run_analysis(input_ticker, analysis_date, app_mode)
        if res:
            add_search_log(f"{name} ({input_ticker})")
            st.success(f"🎯 {name} - {status}")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("현재가", f"{res['current_price']:,}원")
            m2.metric("목표가", f"{res['target']:,}원")
            if "v3.3" in app_mode:
                m3.metric("거래비율", f"{res['vol_ratio']:.1%}")
                st.table(pd.DataFrame({"항목": ["기준봉일", "매수구간", "손절가"], "내용": [res['spike_date'], res['buy_zone'], f"{res['stop']:,}원"]}))
            else:
                m3.metric("1차타점", f"{res['b1']:,}원")
                st.table(pd.DataFrame({"항목": ["기준봉일", "2차타점", "3차타점", "손절가"], "내용": [res['spike_date'], f"{res['b2']:,}원", f"{res['b3']:,}원", f"{res['stop']:,}원"]}))
        else: st.info(f"결과: {status}")

    # [B] 고속 스캐너 (수정 핵심)
    st.markdown("---")
    st.subheader("📡 실시간 매수 타점 스캐너")
    st.caption("최근 20일 내 기준봉 형성 후 현재 눌림목 구간인 종목을 찾습니다. (거래대금 상위 500종목 대상)")
    
    if st.button("🚀 매수 타점 종목 스캔 시작", use_container_width=True):
        found = []
        progress_text = st.empty()
        bar = st.progress(0)
        
        for i, t in enumerate(top_tickers):
            if i % 50 == 0:
                progress_text.text(f"시장 분석 중... ({i}/{len(top_tickers)})")
                bar.progress(i / len(top_tickers))
            
            res_s, status_s = run_analysis(t, analysis_date, app_mode)
            if res_s: # '매수' 신호가 있는 종목만 found에 추가됨 (run_analysis에서 필터링됨)
                found.append({
                    "종목명": code_to_name.get(t, t),
                    "코드": t,
                    "상태": status_s,
                    "현재가": f"{res_s['current_price']:,}원",
                    "목표가": f"{res_s['target']:,}원"
                })
        
        bar.empty()
        progress_text.empty()
        
        if found:
            st.success(f"🔥 매수 타점 포착! {len(found)}개 종목 발견")
            st.dataframe(pd.DataFrame(found), use_container_width=True)
        else:
            st.warning("현재 매수 구간에 진입한 우량 종목이 없습니다. 날짜를 변경하거나 나중에 다시 시도하세요.")

    # [C] 최근 조회 기록
    st.markdown("---")
    st.subheader("🕒 최근 조회 기록")
    if "search_logs" in st.session_state and st.session_state["search_logs"]:
        l_cols = st.columns(5)
        for idx, log in enumerate(st.session_state["search_logs"]):
            l_cols[idx % 5].button(log, key=f"log_{idx}", use_container_width=True)
