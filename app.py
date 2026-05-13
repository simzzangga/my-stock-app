import streamlit as st
import FinanceDataReader as fdr
import pandas as pd
import datetime
import json
import os

# --- 파일 데이터 관리 시스템 ---
LOG_FILE = "trade_v5_log.json"
MONITOR_FILE = "monitoring_v5.json"
SCAN_FILE = "scan_results_v5.json"
SEARCH_HISTORY_FILE = "search_history_v5.json"

def load_data(file_path, default_val):
    try:
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f: return json.load(f)
    except: pass
    return default_val

def save_data(file_path, data):
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# 데이터 초기화
trade_data = load_data(LOG_FILE, {"balance": 10000000, "history": []})
mon_stocks = load_data(MONITOR_FILE, [])
search_history = load_data(SEARCH_HISTORY_FILE, [])

st.set_page_config(page_title="Shim's 100M Project", layout="wide")

# --- [수정] 보안 설정: 4자리 입력 시 즉시 반응 ---
if "auth" not in st.session_state:
    st.session_state.auth = False

if not st.session_state.auth:
    st.title("💰 Shim's 100M Project Portal")
    st.info("비밀번호 4자리를 입력하면 자동으로 입장합니다.")
    
    # on_change 대신 입력값 실시간 체크를 위해 key 활용
    pwd = st.text_input("Access Key (4 digits)", type="password", max_chars=4, key="pwd_input")
    
    # 4자리가 완성되면 즉시 검증
    if len(pwd) == 4:
        if pwd == "1234":
            st.session_state.auth = True
            st.rerun() # 즉시 메인 페이지로 이동
        else:
            st.error("비밀번호가 올바르지 않습니다.")
    st.stop()

# --- 사이드바: 자산 및 로그 관리 ---
st.sidebar.title("💰 자산 및 플랜")
c_balance = st.sidebar.number_input("현재 자산 수정", value=trade_data["balance"], step=100000)
if st.sidebar.button("자산 업데이트"):
    trade_data["balance"] = c_balance
    save_data(LOG_FILE, trade_data)
    st.toast("자산 정보가 수정되었습니다.")

per_trade = trade_data["balance"] * 0.2
st.sidebar.info(f"**종목당 한도:** {int(per_trade):,}원\n(1차 40% / 2차 60%)")

# --- 분석 엔진 (V5.2 고도화 버전) ---
def analyze_v5(ticker, base_date):
    try:
        df = fdr.DataReader(ticker, base_date - datetime.timedelta(days=100), base_date)
        if df.empty or len(df) < 20: return None
        df.columns = [c.upper() for c in df.columns]
        df = df.rename(columns={'OPEN':'시가','HIGH':'고가','LOW':'저가','CLOSE':'종가','VOLUME':'거래량'})
        
        # 몸통 강도 및 거래량 필터
        df['BODY_RATIO'] = (df['종가'] - df['시가']).abs() / (df['고가'] - df['저가'])
        df['VOL_AVG'] = df['거래량'].rolling(20).mean()
        
        spikes = df[(df['종가'] > df['시가']) & (df['BODY_RATIO'] > 0.7) & (df['거래량'] > df['VOL_AVG'] * 5)]
        if spikes.empty: return None
        
        target = spikes.tail(1).iloc[0]
        curr = df.iloc[-1]
        
        # 가짜 눌림목 판별 (하방 경직성)
        if df['저가'].tail(2).min() < target['저가'] * 0.98: return None
        
        return {
            "code": ticker, "curr": int(curr['종가']), "t_low": int(target['저가']),
            "stop": int(target['저가'] * 0.95), "t_date": spikes.tail(1).index[0].strftime("%Y-%m-%d"),
            "dist": (curr['종가'] - target['저가']) / target['저가'],
            "vol_red": curr['거래량'] / target['거래량'],
            "is_buy_zone": target['저가'] <= curr['종가'] <= target['저가'] * 1.03
        }
    except: return None

# --- 메인 화면: 1. 모니터링 섹션 ---
st.title("🖥️ MSM Pro: 실시간 모니터링")
if mon_stocks:
    for idx, s in enumerate(mon_stocks):
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns([1.5, 2, 3, 1])
            c1.metric(s['name'], f"{s['buy_price']:,}원", f"손절 {s['stop']:,}")
            c2.info(f"진입액: {s['amt1']:,}원\n메모: {s.get('memo', '-')}")
            with c3:
                sc1, sc2 = st.columns(2)
                amt2 = sc1.number_input("2차 매수액", value=int(per_trade*0.6), key=f"a2_{idx}")
                memo2 = sc2.text_input("추가 메모", key=f"m2_{idx}")
                if st.button("2차 매수 기록", key=f"b2_{idx}"):
                    trade_data["balance"] -= amt2
                    s['amt1'] += amt2
                    s['memo'] += f" | 2차:{memo2}"
                    save_data(LOG_FILE, trade_data); save_data(MONITOR_FILE, mon_stocks)
                    st.rerun()
            if c4.button("🔴 매도", key=f"sell_{idx}"):
                mon_stocks.pop(idx); save_data(MONITOR_FILE, mon_stocks); st.rerun()

# --- 2. 개별 종목 분석 (v3.3 스타일 + v5 로직) ---
st.divider()
st.subheader("🔍 종목 정밀 분석 (v3.3 리포트)")
with st.container(border=True):
    col_s1, col_s2, col_s3 = st.columns([2, 2, 1])
    input_ticker = col_s1.text_input("종목코드", placeholder="6자리 입력")
    analysis_date = col_s2.date_input("기준 날짜", datetime.date.today())
    btn_analysis = col_s3.button("📊 분석 실행", use_container_width=True)

if btn_analysis and input_ticker:
    res = analyze_v5(input_ticker, analysis_date)
    if res:
        # 검색 기록 저장 (최대 20개, 중복 제거)
        log_entry = f"{input_ticker} ({datetime.date.today()})"
        if log_entry in search_history: search_history.remove(log_entry)
        search_history.insert(0, log_entry)
        save_data(SEARCH_HISTORY_FILE, search_history[:20])
        
        st.success(f"🎯 분석 결과: {'🚀 매수 추천' if res['is_buy_zone'] else '🟡 관망'}")
        m1, m2, m3 = st.columns(3)
        m1.metric("현재가", f"{res['curr']:,}원")
        m2.metric("기준봉 저가", f"{res['t_low']:,}원")
        m3.metric("전략 손절가", f"{res['stop']:,}원")
        
        with st.expander("세부 리포트 확인"):
            st.write(f"- 기준봉 발생일: {res['t_date']}")
            st.write(f"- 거래량 감소율: {res['vol_red']:.1%}")
            memo_in = st.text_input("매매 기록용 메모", key="single_memo")
            if datetime.datetime.now().hour >= 15:
                if st.button("🔥 이 종목 모니터링 등록"):
                    buy_amt = int(per_trade * 0.4)
                    trade_data["balance"] -= buy_amt
                    mon_stocks.append({"name": input_ticker, "buy_price": res['curr'], "stop": res['stop'], "amt1": buy_amt, "memo": memo_in})
                    save_data(LOG_FILE, trade_data); save_data(MONITOR_FILE, mon_stocks); st.rerun()
    else: st.warning("분석 기준에 부합하는 패턴이 없습니다.")

# --- 3. 최근 검색 기록 섹션 ---
st.markdown("##### 🕒 최근 검색 기록 (최대 20개)")
if search_history:
    h_cols = st.columns(5)
    for i, h in enumerate(search_history):
        h_cols[i % 5].caption(f"• {h}")

# --- 4. 시장 스캐너 섹션 ---
st.divider()
st.subheader("📡 오후 3시 전략 스캐너")
if st.button("🚀 전 종목 스캔 (상위 500개)", use_container_width=True):
    with st.spinner("시장 데이터 스캔 중..."):
        krx = fdr.StockListing('KRX')
        all_res = [analyze_v5(c, datetime.date.today()) for c in krx.head(500)['Code'].tolist()]
        all_res = [r for r in all_res if r]
        g_a = sorted([r for r in all_res if 0 <= r['dist'] <= 0.03], key=lambda x: x['dist'])[:10]
        g_b = sorted([r for r in all_res if r['vol_red'] <= 0.20], key=lambda x: x['vol_red'])[:10]
        scan_results = {"A": g_a, "B": g_b, "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        save_data(SCAN_FILE, scan_results); st.session_state.last_scan = scan_results

s_data = st.session_state.get("last_scan", load_data(SCAN_FILE, None))
if s_data:
    st.caption(f"마지막 스캔: {s_data['time']}")
    ca, cb = st.columns(2)
    for cat, title, col in [("A", "📍 눌림목 완성형", ca), ("B", "🔋 에너지 응축형", cb)]:
        with col:
            st.markdown(f"**{title}**")
            if not s_data[cat]: st.write("종목 없음")
            for item in s_data[cat]:
                with st.expander(f"{item['code']} ({item['curr']:,}원)"):
                    st.write(f"손절: {item['stop']:,}원 / 1차추천: {int(per_trade*0.4):,}원")
                    if datetime.datetime.now().hour >= 15:
                        m_in = st.text_input("메모", key=f"m_{item['code']}")
                        if st.button("🔥 매수 등록", key=f"b_{item['code']}"):
                            b_amt = int(per_trade * 0.4); trade_data["balance"] -= b_amt
                            mon_stocks.append({"name":item['code'], "buy_price":item['curr'], "stop":item['stop'], "amt1":b_amt, "memo":m_in})
                            save_data(LOG_FILE, trade_data); save_data(MONITOR_FILE, mon_stocks); st.rerun()
