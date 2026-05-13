import streamlit as st
import FinanceDataReader as fdr
import pandas as pd
import datetime
import time

# --- 1. 보안 설정 ---
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

# --- 2. 안정성 강화 데이터 엔진 (FDR 보정) ---
@st.cache_data(ttl=86400)
def get_ticker_dict():
    try:
        df_krx = fdr.StockListing('KRX')
        return dict(zip(df_krx['Code'].astype(str), df_krx['Name']))
    except:
        return {"005930": "삼성전자"}

@st.cache_data(ttl=600)
def get_robust_ohlcv(ticker, start, end):
    if not ticker: return pd.DataFrame()
    for _ in range(3):
        try:
            df = fdr.DataReader(ticker, start, end)
            if df is not None and not df.empty:
                # [중요] 모든 컬럼명을 대문자로 통일 후 한글 매핑
                df.columns = [c.upper() for c in df.columns]
                rename_map = {
                    'OPEN': '시가', 'HIGH': '고가', 'LOW': '저가', 
                    'CLOSE': '종가', 'VOLUME': '거래량', 'CHANGE': '등락률'
                }
                df = df.rename(columns=rename_map)
                
                # [에러방지] 등락률 컬럼이 없을 경우 수동 계산
                if '등락률' not in df.columns:
                    df['등락률'] = df['종가'].pct_change()
                
                # % 단위로 변환 및 결측치 처리
                df['등락률'] = df['등락률'].fillna(0) * 100
                return df
            time.sleep(0.2)
        except: continue
    return pd.DataFrame()

# --- 3. 분석 엔진 (v3.3 & v4.0) ---
def run_analysis(ticker, base_date, mode):
    start_date = (base_date - datetime.timedelta(days=365)).strftime("%Y-%m-%d")
    end_date = base_date.strftime("%Y-%m-%d")
    df = get_robust_ohlcv(ticker, start_date, end_date)
    
    if df.empty or len(df) < 10: return None, "데이터 부족"

    # 최신 데이터 확보 (iloc 사용)
    current_price = int(df['종가'].iloc[-1])
    
    if "v3.3" in mode:
        spikes = df[df['등락률'] >= 15]
        if spikes.empty: return None, "급등 패턴 없음"
        recent = spikes.tail(1)
        s_date = recent.index[0]
        # iloc[0]을 사용하여 명시적으로 첫 번째 행 접근
        s_close, s_open, s_vol = int(recent['종가'].iloc[0]), int(recent['시가'].iloc[0]), float(recent['거래량'].iloc[0])
        s_body = s_close - s_open
        vol_ratio = float(df['거래량'].iloc[-1]) / s_vol if s_vol != 0 else 0
        b_high, b_low = s_close - (s_body * 0.382), s_close - (s_body * 0.618)
        
        status = "🚀 강력 추천" if vol_ratio <= 0.15 and b_low <= current_price <= b_high else "🛒 분할 매수" if vol_ratio <= 0.22 else "⏳ 관망"
        return {"spike_date": s_date.strftime("%Y-%m-%d"), "current_price": current_price, "target": int(current_price*1.1), "vol_ratio": vol_ratio, "buy_zone": f"{int(b_low):,}~{int(b_high):,}", "stop": int(s_open*0.98)}, status
    
    else: # v4.0
        df['vol20'] = df['거래량'].rolling(20).mean()
        spikes = df[(df['등락률'] >= 15) & (df['거래량'] > df['vol20'] * 3)]
        if spikes.empty: return None, "기준봉 조건 미달"
        recent = spikes.tail(1)
        s_date = recent.index[0]
        s_close, s_open, s_high = int(recent['종가'].iloc[0]), int(recent['시가'].iloc[0]), int(recent['고가'].iloc[0])
        s_body = s_close - s_open
        b1, b2, b3 = s_close-(s_body*0.382), s_close-(s_body*0.5), s_close-(s_body*0.618)
        
        status = "🟡 1차" if b1 >= current_price > b2 else "🟠 2차" if b2 >= current_price > b3 else "🔴 3차" if current_price > s_open*0.98 else "⏳ 이탈"
        return {"spike_date": s_date.strftime("%Y-%m-%d"), "current_price": current_price, "b1": int(b1), "b2": int(b2), "b3": int(b3), "target": int(s_high*0.98), "stop": int(s_open*0.98)}, status

# --- 4. 메인 UI ---
st.set_page_config(page_title="Shim's MSM Dual Pro", layout="wide")

if check_password():
    ticker_dict = get_ticker_dict()
    st.sidebar.title("⚙️ 설정")
    app_mode = st.sidebar.radio("엔진", ["v3.3 (수급 중심)", "v4.0 (타점 중심)"])
    if st.sidebar.button("🔄 캐시 삭제"):
        st.cache_data.clear()
        st.rerun()

    st.title(f"📊 Shim's MSM - {app_mode}")

    # [A] 분석 섹션
    with st.container(border=True):
        c1, c2, c3 = st.columns([2, 2, 1.2])
        input_ticker = c1.text_input("종목코드", value="265560")
        analysis_date = c2.date_input("날짜", datetime.date.today())
        btn_run = c3.button("📊 분석", use_container_width=True, type="primary")

    if btn_run or input_ticker:
        name = ticker_dict.get(input_ticker, "Unknown")
        res, status = run_analysis(input_ticker, analysis_date, app_mode)
        if res:
            st.success(f"🎯 {name} - {status}")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("현재가", f"{res['current_price']:,}원")
            m2.metric("목표가", f"{res['target']:,}원")
            if "v3.3" in app_mode:
                m3.metric("거래비율", f"{res['vol_ratio']:.1%}")
                st.table(pd.DataFrame({"항목": ["기준일", "매수구간", "손절가"], "내용": [res['spike_date'], res['buy_zone'], f"{res['stop']:,}원"]}))
            else:
                m3.metric("1차타점", f"{res['b1']:,}원")
                st.table(pd.DataFrame({"항목": ["기준일", "2차타점", "3차타점", "손절가"], "내용": [res['spike_date'], f"{res['b2']:,}원", f"{res['b3']:,}원", f"{res['stop']:,}원"]}))
        else: st.info(status)

    st.markdown("---")

    # [B] 고속 스캐너 (FDR 최적화)
    if st.button("🚀 전 종목 고속 스캔", use_container_width=True):
        with st.status("스캔 중...", expanded=True) as s_box:
            df_list = fdr.StockListing('KRX')
            # FDR의 등락률 컬럼명인 'ChgPct'가 있는지 확인 후 필터링
            col_name = 'ChgPct' if 'ChgPct' in df_list.columns else 'Change'
            candidates = df_list[df_list[col_name] >= 0.1]['Code'].tolist() # 10% 이상 우선 선별
            
            found = []
            for t in candidates[:50]: # 속도를 위해 상위 50개 우선
                res_s, status_s = run_analysis(str(t), analysis_date, app_mode)
                if res_s and ("매수" in status_s or "추천" in status_s):
                    found.append({"종목명": ticker_dict.get(t, t), "코드": t, "상태": status_s, "현재가": f"{res_s['current_price']:,}", "목표가": f"{res_s['target']:,}"})
            s_box.update(label="완료!", state="complete", expanded=False)
            if found: st.dataframe(pd.DataFrame(found), use_container_width=True)
            else: st.write("조건 부합 없음")
