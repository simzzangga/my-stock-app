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
        # 종목코드:종목명, 종목명:종목코드 양방향 맵핑 준비
        code_to_name = dict(zip(df_krx['Code'].astype(str), df_krx['Name']))
        name_to_code = dict(zip(df_krx['Name'], df_krx['Code'].astype(str)))
        return code_to_name, name_to_code
    except:
        return {"005930": "삼성전자"}, {"삼성전자": "005930"}

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
            time.sleep(0.1)
        except: continue
    return pd.DataFrame()

# 최근 조회 로그 관리 함수
def add_search_log(log_text):
    if "search_logs" not in st.session_state:
        st.session_state["search_logs"] = []
    if log_text in st.session_state["search_logs"]:
        st.session_state["search_logs"].remove(log_text)
    st.session_state["search_logs"].insert(0, log_text)
    st.session_state["search_logs"] = st.session_state["search_logs"][:10]

# --- 3. 분석 엔진 ---
def run_analysis(ticker, base_date, mode):
    start_date = (base_date - datetime.timedelta(days=365)).strftime("%Y-%m-%d")
    end_date = base_date.strftime("%Y-%m-%d")
    df = get_robust_ohlcv(ticker, start_date, end_date)
    if df.empty or len(df) < 10: return None, "데이터 부족"
    current_price = int(df['종가'].iloc[-1])
    
    if "v3.3" in mode:
        spikes = df[df['등락률'] >= 15]
        if spikes.empty: return None, "패턴 없음"
        recent = spikes.tail(1)
        s_date = recent.index[0]
        s_close, s_open, s_vol = int(recent['종가'].iloc[0]), int(recent['시가'].iloc[0]), float(recent['거래량'].iloc[0])
        s_body = s_close - s_open
        vol_ratio = float(df['거래량'].iloc[-1]) / s_vol if s_vol != 0 else 0
        b_high, b_low = s_close - (s_body * 0.382), s_close - (s_body * 0.618)
        status = "🚀 강력 추천" if vol_ratio <= 0.15 and b_low <= current_price <= b_high else "🛒 분할 매수" if vol_ratio <= 0.22 else "⏳ 관망"
        return {"spike_date": s_date.strftime("%Y-%m-%d"), "current_price": current_price, "target": int(current_price*1.1), "vol_ratio": vol_ratio, "buy_zone": f"{int(b_low):,}~{int(b_high):,}", "stop": int(s_open*0.98)}, status
    else:
        df['vol20'] = df['거래량'].rolling(20).mean()
        spikes = df[(df['등락률'] >= 15) & (df['거래량'] > df['vol20'] * 3)]
        if spikes.empty: return None, "기준봉 미달"
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
    code_to_name, name_to_code = get_ticker_dict()
    
    st.sidebar.title("⚙️ 설정 및 검색")
    app_mode = st.sidebar.radio("엔진 선택", ["v3.3 (수급 중심)", "v4.0 (타점 중심)"])
    
    # [기능 추가] 종목명으로 코드 찾기
    st.sidebar.markdown("---")
    st.sidebar.subheader("🔍 종목명 → 코드 변환")
    search_name = st.sidebar.text_input("종목명을 입력하세요(ex: 삼성전자)")
    if search_name:
        found_code = name_to_code.get(search_name)
        if found_code: st.sidebar.success(f"코드: `{found_code}`")
        else: st.sidebar.error("종목을 찾을 수 없습니다.")

    st.title(f"📊 Shim's MSM - {app_mode}")

    # [A] 분석 섹션 (정렬 보정)
    with st.container(border=True):
        c1, c2, c3 = st.columns([2, 2, 1.2])
        with c1:
            input_ticker = st.text_input("종목코드", value="265560")
        with c2:
            analysis_date = st.date_input("날짜", datetime.date.today())
        with c3:
            # 수직 정렬을 위한 마진 추가
            st.markdown('<div style="margin-top: 28px;"></div>', unsafe_allow_html=True)
            btn_run = st.button("📊 분석 실행", use_container_width=True, type="primary")

    if btn_run:
        name = code_to_name.get(input_ticker, "Unknown")
        res, status = run_analysis(input_ticker, analysis_date, app_mode)
        if res:
            # 로그 기록 추가
            add_search_log(f"{name} ({input_ticker})")
            st.success(f"🎯 {name} ({input_ticker}) - {status}")
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

    # [B] 최근 조회 기록 로그 (하단 배치)
    st.markdown("---")
    st.subheader("🕒 최근 조회 기록 (최근 10개)")
    if "search_logs" in st.session_state and st.session_state["search_logs"]:
        cols = st.columns(5) # 5개씩 2줄로 표시
        for idx, log in enumerate(st.session_state["search_logs"]):
            cols[idx % 5].button(log, key=f"log_{idx}", use_container_width=True)
    else:
        st.write("조회 기록이 없습니다.")

   # [C] 스캐너 (KeyError 보정 버전)
    st.markdown("---")
    if st.button("🚀 전 종목 고속 스캔 (급등주 대상)", use_container_width=True):
        with st.status("시장 데이터를 분석 중입니다...") as s_box:
            try:
                # 1. 전체 종목 리스팅
                df_list = fdr.StockListing('KRX')
                
                # 2. 등락률 컬럼명 유연한 감지 (ChgPct, Change, 등락률 등)
                col_candidates = ['ChgPct', 'Change', '등락률', 'Rate']
                target_col = None
                for col in col_candidates:
                    if col in df_list.columns:
                        target_col = col
                        break
                
                if target_col:
                    # 등락률이 10% (0.1) 이상인 종목 필터링
                    # FDR 버전에 따라 소수점(0.1)일 수도, 퍼센트(10)일 수도 있으므로 보정
                    if df_list[target_col].max() > 1.0: # 퍼센트 단위인 경우
                        candidates = df_list[df_list[target_col] >= 10]['Code'].tolist()
                    else: # 소수점 단위인 경우
                        candidates = df_list[df_list[target_col] >= 0.1]['Code'].tolist()
                else:
                    # 컬럼명을 못 찾을 경우 안전하게 전체 리스트의 상위 일부만 시도
                    candidates = df_list['Code'].head(100).tolist()
                    st.warning("등락률 컬럼을 찾을 수 없어 상위 100개 종목만 정밀 분석합니다.")

                found = []
                # 분석 부하를 줄이기 위해 최대 100개까지만 정밀 분석 진행
                for t in candidates[:100]:
                    res_s, status_s = run_analysis(str(t), analysis_date, app_mode)
                    if res_s and ("매수" in status_s or "추천" in status_s):
                        found.append({
                            "종목명": code_to_name.get(t, t), 
                            "코드": t, 
                            "상태": status_s, 
                            "현재가": f"{res_s['current_price']:,}원", 
                            "목표가": f"{res_s['target']:,}원"
                        })
                
                s_box.update(label="스캔 완료!", state="complete", expanded=False)
                
                if found: 
                    st.success(f"조건에 맞는 종목 {len(found)}개를 찾았습니다.")
                    st.dataframe(pd.DataFrame(found), use_container_width=True)
                else: 
                    st.write("현재 조건(급등 후 눌림)에 부합하는 종목이 없습니다.")
                    
            except Exception as e:
                st.error(f"스캐너 구동 중 예상치 못한 오류가 발생했습니다: {e}")
