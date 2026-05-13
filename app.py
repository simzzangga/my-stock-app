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

# [수정] KRX 종목 리스트 로드 - 서버 장애 대응 로직 추가
@st.cache_data(ttl=86400)
def get_krx_list():
    try:
        df = fdr.StockListing('KRX')
        return df[['Code', 'Name']]
    except Exception as e:
        # 서버 장애 시 사용자에게 알리고 빈 데이터 반환하여 앱 중단 방지
        return pd.DataFrame(columns=['Code', 'Name'])

# 데이터 초기화
trade_data = load_data(LOG_FILE, {"balance": 10000000, "history": []})
mon_stocks = load_data(MONITOR_FILE, [])
search_history = load_data(SEARCH_HISTORY_FILE, [])
krx_df = get_krx_list()

st.set_page_config(page_title="Shim's 100M Project", layout="wide")

# --- 보안 설정 (4자리 즉시 반응) ---
if "auth" not in st.session_state: st.session_state.auth = False
if not st.session_state.auth:
    st.title("💰 Shim's 100M Project Portal")
    pwd = st.text_input("Access Key (4 digits)", type="password", max_chars=4, key="entry_pwd")
    if len(pwd) == 4:
        if pwd == "1234":
            st.session_state.auth = True
            st.rerun()
        else: st.error("비밀번호가 올바르지 않습니다.")
    st.stop()

# --- 사이드바: 자산 관리 및 검색 ---
st.sidebar.title("🏁 1억 만들기 플랜")
current_balance = trade_data["balance"]
progress = min(current_balance / 100000000, 1.0)
st.sidebar.metric("현재 자산", f"{current_balance:,}원")
st.sidebar.progress(progress)

if st.sidebar.button("자산 데이터 업데이트"):
    save_data(LOG_FILE, trade_data)
    st.toast("자산 정보 업데이트 완료")

st.sidebar.divider()
st.sidebar.subheader("🔍 종목명/코드 검색")

# KRX 데이터 로드 실패 시 안내
if krx_df.empty:
    st.sidebar.warning("⚠️ KRX 서버 일시 장애로 검색이 제한됩니다. 잠시 후 시도하세요.")
    selected_name = None
else:
    stock_names = krx_df['Name'].tolist()
    selected_name = st.sidebar.selectbox("검색", stock_names, index=None, placeholder="종목명 입력")

if selected_name:
    target_code = krx_df[krx_df['Name'] == selected_name]['Code'].values[0]
    st.sidebar.success(f"✅ {selected_name} | `{target_code}`")
    st.session_state.auto_code = target_code

st.sidebar.caption("🕒 최근 기록")
for h in search_history[:10]:
    if st.sidebar.button(f"{h['name']} ({h['code']})", key=f"side_{h['code']}", use_container_width=True):
        st.session_state.auto_code = h['code']
        st.rerun()

# --- 분석 엔진 및 메인 UI (기존 로직 유지) ---
def analyze_v5(ticker, base_date):
    try:
        df = fdr.DataReader(ticker, base_date - datetime.timedelta(days=100), base_date)
        if df.empty: return None
        df.columns = [c.upper() for c in df.columns]
        df = df.rename(columns={'OPEN':'시가','HIGH':'고가','LOW':'저가','CLOSE':'종가','VOLUME':'거래량'})
        
        # 3.11 최적화된 몸통 강도 및 지지력 분석
        df['BODY'] = (df['종가'] - df['시가']).abs() / (df['고가'] - df['저가'])
        df['VOL_MA'] = df['거래량'].rolling(20).mean()
        spikes = df[(df['종가'] > df['시가']) & (df['BODY'] > 0.7) & (df['거래량'] > df['VOL_MA'] * 5)]
        
        if spikes.empty: return None
        target = spikes.tail(1).iloc[0]
        curr = df.iloc[-1]
        
        return {
            "code": ticker, "curr": int(curr['종가']), "t_low": int(target['저가']),
            "stop": int(target['저가'] * 0.95), "is_buy": target['저가'] <= curr['종가'] <= target['저가'] * 1.03
        }
    except: return None

st.title("🖥️ MSM Pro: 실시간 대응 포털")
# (이후 모니터링 및 스캐너 로직 생략 - v5.5와 동일하게 구성 가능)
# ... (생략된 부분은 v5.5의 모니터링/스캐너 섹션을 그대로 붙여넣으시면 됩니다)
