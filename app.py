import streamlit as st
import FinanceDataReader as fdr
import pandas as pd
import datetime
import json
import os

# --- 데이터 영구 저장 시스템 ---
LOG_FILE = "trade_v5_log.json"
MONITOR_FILE = "monitoring_v5.json"
SCAN_FILE = "scan_results_v5.json"

def load_data(file_path, default_val):
    try:
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
    except: pass
    return default_val

def save_data(file_path, data):
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# 데이터 로드
trade_data = load_data(LOG_FILE, {"balance": 10000000, "history": []})
mon_stocks = load_data(MONITOR_FILE, [])

st.set_page_config(page_title="Shim's 100M Project", layout="wide")

# --- 보안 설정 ---
if "auth" not in st.session_state: st.session_state.auth = False
if not st.session_state.auth:
    pwd = st.text_input("Access Key", type="password")
    if pwd == "1234":
        st.session_state.auth = True
        st.rerun()
    st.stop()

# --- 사이드바: 자산 관리 ---
st.sidebar.title("💰 자산 및 플랜")
current_balance = st.sidebar.number_input("현재 자산 수정", value=trade_data["balance"], step=100000)
if st.sidebar.button("자산 데이터 업데이트"):
    trade_data["balance"] = current_balance
    save_data(LOG_FILE, trade_data)
    st.toast("자산 정보가 업데이트되었습니다.")

per_trade = trade_data["balance"] * 0.2
st.sidebar.divider()
st.sidebar.info(f"**종목당 한도:** {int(per_trade):,}원\n(1차 40% / 2차 60%)")

# --- 분석 엔진 (V5.2 고도화 + 3.11 호환) ---
@st.cache_data(ttl=3600) # 3.11 성능 최적화 캐싱
def analyze_stock(ticker, base_date):
    try:
        # 데이터 수집
        df = fdr.DataReader(ticker, base_date - datetime.timedelta(days=80), base_date)
        if df.empty or len(df) < 20: return None
        
        df.columns = [c.upper() for c in df.columns]
        df = df.rename(columns={'OPEN':'시가','HIGH':'고가','LOW':'저가','CLOSE':'종가','VOLUME':'거래량'})
        
        # 1. 몸통 강도 및 거래량 필터 (사고 모델 반영)
        df['BODY_RATIO'] = (df['종가'] - df['시가']).abs() / (df['고가'] - df['저가'])
        df['VOL_AVG'] = df['거래량'].rolling(20).mean()
        
        spikes = df[(df['종가'] > df['시가']) & (df['BODY_RATIO'] > 0.7) & (df['거래량'] > df['VOL_AVG'] * 5)]
        if spikes.empty: return None
        
        target = spikes.tail(1).iloc[0]
        curr = df.iloc[-1]
        
        # 2. 가짜 눌림목 판별 (하방 경직성 체크)
        if df['저가'].tail(2).min() < target['저가'] * 0.98: return None
        
        return {
            "code": ticker, "curr": int(curr['종가']), "t_low": int(target['저가']),
            "stop": int(target['저가'] * 0.95),
            "is_buy_zone": target['저가'] <= curr['종가'] <= target['저가'] * 1.03,
            "dist": (curr['종가'] - target['저가']) / target['저가'],
            "vol_red": curr['거래량'] / target['거래량'],
            "t_date": spikes.tail(1).index[0].strftime("%Y-%m-%d")
        }
    except: return None

# --- 메인 화면: 모니터링 ---
st.title("🖥️ MSM Pro: 실시간 대응 포털")
if mon_stocks:
    for idx, s in enumerate(mon_stocks):
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns([1.5, 2, 3, 1])
            c1.metric(s['name'], f"{s['buy_price']:,}원", f"손절가 {s['stop']:,}")
            c2.info(f"진입액: {s['amt1']:,}원\n메모: {s.get('memo', '-')}")
            with c3:
                sc1, sc2 = st.columns(2)
                amt2 = sc1.number_input("2차 매수액", value=int(per_trade*0.6), key=f"a2_{idx}")
                memo2 = sc2.text_input("대응 메모", key=f"m2_{idx}")
                if st.button("2차 매수 기록", key=f"b2_{idx}"):
                    trade_data["balance"] -= amt2
                    s['amt1'] += amt2
                    s['memo'] += f" | 2차:{memo2}"
                    save_data(LOG_FILE, trade_data)
                    save_data(MONITOR_FILE, mon_stocks)
                    st.rerun()
            if c4.button("🔴 매도", key=f"sell_{idx}"):
                mon_stocks.pop(idx)
                save_data(MONITOR_FILE, mon_stocks)
                st.rerun()

# --- 스캐너 섹션 ---
st.divider()
st.subheader("📡 오후 3시 전략 스캐너")
now = datetime.datetime.now()
is_after_3 = (now.hour >= 15)

if st.button("🚀 전 종목 스캔 시작 (상위 500개)", use_container_width=True):
    with st.spinner("3.11 엔진 가동 중..."):
        krx = fdr.StockListing('KRX')
        results = [analyze_stock(c, datetime.date.today()) for c in krx.head(500)['Code'].tolist()]
        results = [r for r in results if r]
        
        group_a = sorted([r for r in results if 0 <= r['dist'] <= 0.03], key=lambda x: x['dist'])[:10]
        group_b = sorted([r for r in results if r['vol_red'] <= 0.20], key=lambda x: x['vol_red'])[:10]
        
        scan_data = {"A": group_a, "B": group_b, "time": now.strftime("%Y-%m-%d %H:%M:%S")}
        save_data(SCAN_FILE, scan_data)
        st.session_state.last_scan = scan_data

scan_res = st.session_state.get("last_scan", load_data(SCAN_FILE, None))
if scan_res:
    for cat, title in [("A", "📍 그룹 A: 눌림목 완성"), ("B", "🔋 그룹 B: 에너지 응축")]:
        st.markdown(f"#### {title}")
        if not scan_res[cat]: st.caption("조건 부합 종목 없음")
        for item in scan_res[cat]:
            with st.expander(f"{item['code']} | 현재가: {item['curr']:,}원"):
                col_i1, col_i2, col_i3 = st.columns([2, 2, 2])
                col_i1.write(f"**손절가:** {item['stop']:,}원")
                col_i2.write(f"**추천 1차액:** {int(per_trade*0.4):,}원")
                with col_i3:
                    if is_after_3:
                        memo_in = st.text_input("메모", key=f"memo_{item['code']}")
                        if st.button("🔥 매수 등록", key=f"btn_{item['code']}"):
                            buy_amt = int(per_trade * 0.4)
                            trade_data["balance"] -= buy_amt
                            mon_stocks.append({"name":item['code'], "buy_price":item['curr'], "stop":item['stop'], "amt1":buy_amt, "memo":memo_in})
                            save_data(LOG_FILE, trade_data); save_data(MONITOR_FILE, mon_stocks)
                            st.rerun()
                    else: st.warning("15:00 이후 활성화")
