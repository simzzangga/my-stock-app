import streamlit as st
import FinanceDataReader as fdr
import pandas as pd
import datetime
import json
import os
import plotly.graph_objects as go

# --- 데이터 영구 저장 시스템 ---
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

# [안전장치] KRX 종목 리스트 로드
@st.cache_data(ttl=86400)
def get_krx_list():
    try:
        df = fdr.StockListing('KRX')
        return df[['Code', 'Name']]
    except:
        return pd.DataFrame(columns=['Code', 'Name'])

# 데이터 초기화
trade_data = load_data(LOG_FILE, {"balance": 10000000, "history": []})
mon_stocks = load_data(MONITOR_FILE, [])
search_history = load_data(SEARCH_HISTORY_FILE, [])
krx_df = get_krx_list()

st.set_page_config(page_title="Shim's 100M Project", layout="wide")

# 세션 상태 초기화
if "auto_code" not in st.session_state: st.session_state.auto_code = ""
if "auth" not in st.session_state: st.session_state.auth = False

# --- [1단계] 보안 설정 ---
if not st.session_state.auth:
    st.title("💰 Shim's MSM Portal v5.2")
    st.info("1억 프로젝트 From 202605")
    pwd = st.text_input("Access Key (4 digits)", type="password", max_chars=4, key="entry_pwd")
    if len(pwd) == 4:
        if pwd == "1234":
            st.session_state.auth = True
            st.rerun()
        else: st.error("비밀번호가 올바르지 않습니다.")
    st.stop()

# --- [2단계] 사이드바: 자산 관리 및 목표 달성 게이지 ---
st.sidebar.title("🏁 1억 만들기")
target_goal = 100000000
current_balance = trade_data["balance"]
progress = min(current_balance / target_goal, 1.0)

st.sidebar.metric("현재 자산", f"{current_balance:,}원")
st.sidebar.progress(progress)
st.sidebar.write(f"목표 달성률: {progress:.1%}")

new_balance = st.sidebar.number_input("가용 자산 수정", value=current_balance, step=100000)
if st.sidebar.button("자산 업데이트"):
    trade_data["balance"] = new_balance
    save_data(LOG_FILE, trade_data)
    st.rerun()

st.sidebar.divider()
st.sidebar.subheader("🔍 종목명/종목코드 검색")

if krx_df.empty:
    # KRX 서버 응답이 없을 때 표시
    st.sidebar.warning("⚠️ KRX 서버 연결 실패 (종목명 검색 불가)")
    st.sidebar.info("하단의 '최근 기록'을 이용하거나 메인창에 코드를 직접 입력하세요.")
else:
    # 정상 작동 시 기존 검색창 표시
    stock_names = krx_df['Name'].tolist()
    selected_name = st.sidebar.selectbox("검색할 종목 선택", stock_names, index=None, placeholder="종목명을 입력하세요")
    if selected_name:
        target_code = krx_df[krx_df['Name'] == selected_name]['Code'].values[0]
        st.sidebar.success(f"✅ **{selected_name}** | `{target_code}`")
        if not any(h['code'] == target_code for h in search_history):
            search_history.insert(0, {"name": selected_name, "code": target_code})
            save_data(SEARCH_HISTORY_FILE, search_history[:20])

st.sidebar.divider()
st.sidebar.caption("🕒 최근 검색 기록 (클릭 시 자동 입력)")
for h in search_history[:15]:
    if st.sidebar.button(f" {h['name']} ({h['code']})", key=f"side_{h['code']}", use_container_width=True):
        st.session_state.auto_code = h['code']
        st.rerun()

# --- [3단계] 메인 상단: 골든타임 알림 바 ---
now = datetime.datetime.now()
is_golden_time = (now.hour == 15 and 0 <= now.minute <= 30)

if is_golden_time:
    st.markdown("""
        <div style="background-color: #FFD700; padding: 15px; border-radius: 10px; text-align: center; border: 2px solid #DAA520;">
            <h3 style="color: black; margin: 0;">🔥 실전 매수 골든타임 (3:00 PM)</h3>
            <p style="color: black; margin: 0; font-weight: bold;">캔들이 완성되는 시점입니다. 최종 타점을 확정하세요!</p>
        </div>
    """, unsafe_allow_html=True)
    st.write("")

# --- [4단계] 분석 엔진 (V5.2 고도화) ---
def analyze_v5(ticker, base_date):
    try:
        df = fdr.DataReader(ticker, base_date - datetime.timedelta(days=100), base_date)
        if df.empty or len(df) < 20: return None, None
        df.columns = [c.upper() for c in df.columns]
        df = df.rename(columns={'OPEN':'시가','HIGH':'고가','LOW':'저가','CLOSE':'종가','VOLUME':'거래량'})
        
        df['BODY_RATIO'] = (df['종가'] - df['시가']).abs() / (df['고가'] - df['저가'])
        df['VOL_AVG'] = df['거래량'].rolling(20).mean()
        
        spikes = df[(df['종가'] > df['시가']) & (df['BODY_RATIO'] > 0.7) & (df['거래량'] > df['VOL_AVG'] * 5)]
        if spikes.empty: return None, df
        
        target = spikes.tail(1).iloc[0]
        curr = df.iloc[-1]
        if df['저가'].tail(2).min() < target['저가'] * 0.98: return None, df
        
        vol_force = (1 - (curr['거래량'] / target['거래량'])) * 100
        dist = (curr['종가'] - target['저가']) / target['저가']
        
        res = {
            "code": ticker, "curr": int(curr['종가']), "t_low": int(target['저가']),
            "stop": int(target['저가'] * 0.95), "t_date": spikes.tail(1).index[0],
            "vol_red": curr['거래량'] / target['거래량'], "vol_force": vol_force,
            "dist": dist, "is_buy_zone": target['저가'] <= curr['종가'] <= target['저가'] * 1.03
        }
        return res, df
    except: return None, None

# --- [5단계] 메인 화면: 실시간 모니터링 ---
st.title("🖥️ 살까 말까, 팔까 말까")
if mon_stocks:
    for idx, s in enumerate(mon_stocks):
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns([1.5, 2, 3, 1])
            c1.metric(s['name'], f"{s['buy_price']:,}원", f"손절 {s['stop']:,}")
            c2.info(f"진입액: {s['amt1']:,}원\n메모: {s.get('memo', '-')}")
            with c3:
                sc1, sc2 = st.columns(2)
                amt2 = sc1.number_input("2차 매수액", value=int(current_balance*0.12), key=f"a2_{idx}")
                memo2 = sc2.text_input("추가 메모", key=f"m2_{idx}")
                if st.button("2차 매수 기록", key=f"b2_{idx}"):
                    trade_data["balance"] -= amt2; s['amt1'] += amt2; s['memo'] += f" | 2차:{memo2}"
                    save_data(LOG_FILE, trade_data); save_data(MONITOR_FILE, mon_stocks); st.rerun()
            if c4.button("🔴 매도", key=f"sell_{idx}", use_container_width=True):
                mon_stocks.pop(idx); save_data(MONITOR_FILE, mon_stocks); st.rerun()
else:
    st.caption("현재 모니터링 중인 종목이 없습니다.")

# --- [6단계] 종목 정밀 분석 및 차트 ---
st.divider()
st.subheader("🔍 종목 정밀 분석 및 차트")
with st.container(border=True):
    col_s1, col_s2, col_s3 = st.columns([2, 2, 1])
    input_ticker = col_s1.text_input("종목코드 입력", value=st.session_state.auto_code, placeholder="예: 005930")
    analysis_date = col_s2.date_input("분석 기준일", datetime.date.today())
    btn_analysis = col_s3.button("📊 분석", use_container_width=True, type="primary")

if btn_analysis and input_ticker:
    res, df = analyze_v5(input_ticker, analysis_date)
    if res:
        st.success(f"🎯 분석 결과: {'🚀 매수 적기' if res['is_buy_zone'] else '🟡 관망 요망'}")
        
        # 차트 시각화
        fig = go.Figure(data=[go.Candlestick(x=df.index, open=df['시가'], high=df['고가'], low=df['저가'], close=df['종가'], name='주가')])
        fig.add_hline(y=res['t_low'], line_dash="dash", line_color="yellow", annotation_text="기준봉 저가")
        fig.add_hline(y=res['stop'], line_color="red", annotation_text="손절선(-5%)")
        fig.update_layout(height=450, xaxis_rangeslider_visible=False, template="plotly_dark", margin=dict(l=10, r=10, t=30, b=10))
        st.plotly_chart(fig, use_container_width=True)

        m1, m2, m3 = st.columns(3)
        m1.metric("현재가", f"{res['curr']:,}원")
        m2.metric("기준봉 저가", f"{res['t_low']:,}원")
        m3.metric("전략 손절가", f"{res['stop']:,}원")
        
        with st.expander("세부 전략 리포트"):
            st.write(f"- 세력 잔존 신뢰도: {res['vol_force']:.1f}% | 거래량 감소율: {res['vol_red']:.1%}")
            memo_in = st.text_input("매매 특이사항 메모", key="single_memo")
            if now.hour >= 15:
                if st.button("🔥 모니터링 등록"):
                    buy_amt = int(current_balance * 0.08)
                    trade_data["balance"] -= buy_amt
                    mon_stocks.append({"name": input_ticker, "buy_price": res['curr'], "stop": res['stop'], "amt1": buy_amt, "memo": memo_in})
                    save_data(LOG_FILE, trade_data); save_data(MONITOR_FILE, mon_stocks); st.rerun()
            else: st.warning("매수 등록은 15:00 이후 가능합니다.")
    else: st.warning("기준에 적합한 패턴을 찾을 수 없습니다.")

# --- [7단계] 시장 스캐너 (진행 상황 바 포함) ---
st.divider()
st.subheader("📡 오후 3시 전략 스캐너")
if st.button("🚀 전 종목 스캔 시작 (상위 500개)", use_container_width=True):
    if krx_df.empty: 
        st.error("KRX 서버 장애로 스캔이 불가능합니다.")
    else:
        # 진행 상황 표시창 생성
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        krx_codes = krx_df.head(500)['Code'].tolist()
        total_count = len(krx_codes)
        all_res = []
        
        for i, c in enumerate(krx_codes):
            # 진행률 업데이트
            progress = (i + 1) / total_count
            progress_bar.progress(progress)
            status_text.text(f"⏳ 전체 500개 종목 중 {i + 1}개 분석 중... ({int(progress * 100)}%)")
            
            r, _ = analyze_v5(c, datetime.date.today())
            if r: all_res.append(r)
        
        # 완료 후 진행창 제거
        progress_bar.empty()
        status_text.empty()
        
        g_a = sorted([r for r in all_res if 0 <= r['dist'] <= 0.03], key=lambda x: x['dist'])[:10]
        g_b = sorted([r for r in all_res if r['vol_red'] <= 0.20], key=lambda x: x['vol_red'])[:10]
        scan_results = {"A": g_a, "B": g_b, "time": now.strftime("%Y-%m-%d %H:%M:%S")}
        save_data(SCAN_FILE, scan_results); st.session_state.last_scan = scan_results

s_data = st.session_state.get("last_scan", load_data(SCAN_FILE, None))
if s_data:
    st.caption(f"최근 스캔 시점: {s_data['time']}")
    ca, cb = st.columns(2)
    for cat, title, col in [("A", "📍 눌림목 완성형", ca), ("B", "🔋 에너지 응축형", cb)]:
        with col:
            st.markdown(f"**{title}**")
            if not s_data[cat]: st.write("추천 종목 없음")
            for item in s_data[cat]:
                with st.expander(f"{item['code']} ({item['curr']:,}원)"):
                    st.write(f"손절: {item['stop']:,}원 | 1차: {int(current_balance*0.08):,}원")
                    if now.hour >= 15:
                        m_in = st.text_input("기록 메모", key=f"m_{item['code']}")
                        if st.button("🔥 매수 등록", key=f"b_{item['code']}"):
                            b_amt = int(current_balance * 0.08); trade_data["balance"] -= b_amt
                            mon_stocks.append({"name":item['code'], "buy_price":item['curr'], "stop":item['stop'], "amt1":b_amt, "memo":m_in})
                            save_data(LOG_FILE, trade_data); save_data(MONITOR_FILE, mon_stocks); st.rerun()
