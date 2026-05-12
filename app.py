import streamlit as st
from pykrx import stock
import pandas as pd
import datetime
import time

# =========================================================
# 1. 보안 설정
# =========================================================
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False

    if st.session_state["password_correct"]:
        return True

    password = st.text_input("💰 Shim's MSM NetWork v4.0", type="password")

    if st.button("로그인"):
        if password == st.secrets.get("password", "1234"):
            st.session_state["password_correct"] = True
            st.rerun()
        else:
            st.error("비밀번호가 틀렸습니다.")

    return False


# =========================================================
# 2. 데이터 수집 엔진
# =========================================================
@st.cache_data(ttl=600)
def get_robust_ohlcv(ticker, start, end):

    for _ in range(3):
        try:
            df = stock.get_market_ohlcv_by_date(start, end, ticker)

            if df is not None and not df.empty:
                return df

            time.sleep(0.1)

        except:
            continue

    return pd.DataFrame()


@st.cache_data(ttl=86400)
def get_verified_ticker_list():

    try:
        ksp = stock.get_market_ticker_list(market="KOSPI")
        time.sleep(0.1)

        ksq = stock.get_market_ticker_list(market="KOSDAQ")

        combined = list(set(ksp + ksq))

        return combined if combined else []

    except:
        return []


# =========================================================
# 3. 핵심 분석 로직
# =========================================================
def run_antigravity_analysis(ticker, base_date):

    if not ticker or len(ticker) != 6:
        return None, "종목코드 오류"

    start_date = (base_date - datetime.timedelta(days=365)).strftime("%Y%m%d")
    end_date = base_date.strftime("%Y%m%d")

    df = get_robust_ohlcv(ticker, start_date, end_date)

    try:
        raw_name = stock.get_market_ticker_name(ticker)
    except:
        raw_name = "Unknown"

    if df.empty:
        return None, "데이터 없음"

    if len(df) < 120:
        return None, "상장 기간 부족"

    # -----------------------------------------------------
    # 이동평균선
    # -----------------------------------------------------
    df['ma5'] = df['종가'].rolling(5).mean()
    df['ma20'] = df['종가'].rolling(20).mean()
    df['ma60'] = df['종가'].rolling(60).mean()

    df['vol20'] = df['거래량'].rolling(20).mean()

    # -----------------------------------------------------
    # 의미있는 급등봉 탐색
    # -----------------------------------------------------
    spikes = df[
        (df['등락률'] >= 15) &
        (df['종가'] > df['시가']) &
        (df['거래량'] > df['vol20'] * 3)
    ]

    if spikes.empty:
        return None, "의미있는 급등봉 없음"

    recent_spike = spikes.tail(1)

    spike_date = recent_spike.index[0]

    spike_close = recent_spike['종가'].values[0]
    spike_open = recent_spike['시가'].values[0]
    spike_high = recent_spike['고가'].values[0]
    spike_vol = recent_spike['거래량'].values[0]

    spike_body = spike_close - spike_open

    # -----------------------------------------------------
    # 급등 이후 데이터
    # -----------------------------------------------------
    after_spike = df.loc[spike_date:].iloc[1:]

    if len(after_spike) < 5:
        return None, "눌림목 형성 부족"

    current_price = df['종가'].iloc[-1]
    current_vol = df['거래량'].iloc[-1]

    # -----------------------------------------------------
    # 이미 시세 분출 여부
    # -----------------------------------------------------
    max_high_after = after_spike['고가'].max()

    hit_10_percent = max_high_after >= spike_close * 1.10

    if hit_10_percent:
        return None, "이미 10% 이상 상승 완료"

    # -----------------------------------------------------
    # 거래량 감소 체크
    # -----------------------------------------------------
    recent_vol_avg = after_spike['거래량'].tail(5).mean()

    vol_ratio = recent_vol_avg / spike_vol if spike_vol != 0 else 999

    dry_volume = (
        current_vol <
        df['vol20'].iloc[-1] * 0.6
    )

    if not dry_volume:
        return None, "거래량 감소 부족"

    # -----------------------------------------------------
    # 눌림목 구간 계산
    # -----------------------------------------------------
    buy1 = spike_close - (spike_body * 0.382)
    buy2 = spike_close - (spike_body * 0.5)
    buy3 = spike_close - (spike_body * 0.618)

    stop_loss_price = spike_open * 0.98

    # -----------------------------------------------------
    # 이평선 조건
    # -----------------------------------------------------
    ma_condition = (
        df['ma5'].iloc[-1] > df['ma20'].iloc[-1] and
        current_price > df['ma20'].iloc[-1]
    )

    if not ma_condition:
        return None, "이평선 조건 미충족"

    # -----------------------------------------------------
    # 분할 매수 단계 판단
    # -----------------------------------------------------
    buy_signal = None

    if buy1 >= current_price > buy2:
        buy_signal = "🟡 1차 매수"

    elif buy2 >= current_price > buy3:
        buy_signal = "🟠 2차 매수"

    elif current_price <= buy3:
        buy_signal = "🔴 3차 매수"

    else:
        return None, "매수 구간 아님"

    # -----------------------------------------------------
    # 목표가 계산
    # -----------------------------------------------------
    target_sell_price = max(
        int(spike_high * 0.98),
        int(current_price * 1.10)
    )

    potential_yield = (
        (target_sell_price / current_price) - 1
    ) * 100

    # -----------------------------------------------------
    # 신뢰도 계산
    # -----------------------------------------------------
    reliability = 100

    if vol_ratio > 0.30:
        reliability -= 15

    if len(after_spike) < 10:
        reliability -= 10

    if current_price < df['ma20'].iloc[-1]:
        reliability -= 20

    if current_price < buy3:
        reliability -= 15

    reliability = max(0, reliability)

    # -----------------------------------------------------
    # 결과 정리
    # -----------------------------------------------------
    result = {

        "full_name": f"{raw_name} ({ticker})",

        "spike_date": spike_date.strftime("%Y-%m-%d"),

        "current_price": current_price,

        "buy1": int(buy1),
        "buy2": int(buy2),
        "buy3": int(buy3),

        "stop_loss": int(stop_loss_price),

        "target_10": int(target_sell_price),

        "vol_ratio": vol_ratio,

        "reliability": reliability,

        "potential_yield": potential_yield,

        "buy_signal": buy_signal
    }

    return result, buy_signal


# =========================================================
# 4. 시장 스캔 함수
# =========================================================
def scan_market_full(base_date):

    tickers = get_verified_ticker_list()

    if not tickers:
        st.error("종목 리스트 로딩 실패")
        return [], [], []

    buy1_list = []
    buy2_list = []
    buy3_list = []

    msg = st.empty()
    bar = st.progress(0)

    total = len(tickers)

    for i, t in enumerate(tickers):

        if i % 100 == 0:
            msg.info(
                f"📡 {base_date.strftime('%Y-%m-%d')} "
                f"전수 조사 중: {i}/{total}"
            )

            bar.progress(i / total)

        res, status = run_antigravity_analysis(t, base_date)

        if res:

            item = {

                "종목": res['full_name'],

                "현재가": f"{res['current_price']:,}원",

                "목표가": f"{res['target_10']:,}원",

                "기대수익": f"+{res['potential_yield']:.1f}%",

                "신뢰도": f"{res['reliability']}%",

                "거래량비율": f"{res['vol_ratio']:.1%}"
            }

            if status == "🟡 1차 매수":
                buy1_list.append(item)

            elif status == "🟠 2차 매수":
                buy2_list.append(item)

            elif status == "🔴 3차 매수":
                buy3_list.append(item)

    bar.empty()
    msg.empty()

    return buy1_list, buy2_list, buy3_list


# =========================================================
# 5. 웹 UI
# =========================================================
st.set_page_config(
    page_title="Shim's MSM v4.0",
    layout="wide"
)

if check_password():

    st.title("💰 Shim's MSM v4.0")

    st.markdown("### 🔍 분석 제어 센터")

    c1, c2, c3 = st.columns([2, 2, 1.2])

    with c1:
        input_ticker = st.text_input(
            "종목코드 6자리",
            value="265560"
        )

    with c2:
        analysis_date = st.date_input(
            "기준 날짜 선택",
            datetime.date.today()
        )

    with c3:
        st.markdown(
            '<div style="margin-top: 28px;"></div>',
            unsafe_allow_html=True
        )

        if st.button(
            "🔄 데이터 다시 분석",
            use_container_width=True
        ):
            st.cache_data.clear()
            st.rerun()

    # -----------------------------------------------------
    # 개별 분석
    # -----------------------------------------------------
    res, status = run_antigravity_analysis(
        input_ticker,
        analysis_date
    )

    if res:

        st.markdown(
            f"#### 🎯 {res['full_name']} 분석 결과"
        )

        m1, m2, m3, m4 = st.columns(4)

        m1.metric("매수 시그널", status)

        m2.metric(
            "목표가",
            f"{res['target_10']:,}원"
        )

        m3.metric(
            "기대수익",
            f"+{res['potential_yield']:.1f}%"
        )

        m4.metric(
            "신뢰도",
            f"{res['reliability']}%"
        )

        st.table(pd.DataFrame({

            "항목": [
                "최근 급등일",
                "현재가",
                "1차 매수",
                "2차 매수",
                "3차 매수",
                "손절가",
                "목표가"
            ],

            "내용": [

                res['spike_date'],

                f"{res['current_price']:,}원",

                f"{res['buy1']:,}원",

                f"{res['buy2']:,}원",

                f"{res['buy3']:,}원",

                f"{res['stop_loss']:,}원",

                f"{res['target_10']:,}원"
            ]

        }))

    else:
        st.info(f"💡 분석 결과: {status}")

    st.markdown("---")

    # -----------------------------------------------------
    # 시장 스캐너
    # -----------------------------------------------------
    st.markdown("### 📡 시장 전수 스캐너")

    sc_col1, sc_col2 = st.columns(2)

    with sc_col1:

        btn_backtest = st.button(
            f"📅 {analysis_date.strftime('%m/%d')} 기준 스캔",
            use_container_width=True
        )

    with sc_col2:

        btn_today_scan = st.button(
            "☀️ 오늘 기준 실시간 스캔",
            use_container_width=True
        )

    target_date = None

    if btn_backtest:
        target_date = analysis_date

    elif btn_today_scan:
        target_date = datetime.date.today()

    if target_date:

        st.subheader(
            f"📊 {target_date.strftime('%Y-%m-%d')} 추천 리스트"
        )

        buy1_res, buy2_res, buy3_res = scan_market_full(target_date)

        r1, r2, r3 = st.columns(3)

        with r1:
            st.success(f"🟡 1차 매수 ({len(buy1_res)}개)")

            if buy1_res:
                st.table(pd.DataFrame(buy1_res))
            else:
                st.write("조건 부합 없음")

        with r2:
            st.warning(f"🟠 2차 매수 ({len(buy2_res)}개)")

            if buy2_res:
                st.table(pd.DataFrame(buy2_res))
            else:
                st.write("조건 부합 없음")

        with r3:
            st.error(f"🔴 3차 매수 ({len(buy3_res)}개)")

            if buy3_res:
                st.table(pd.DataFrame(buy3_res))
            else:
                st.write("조건 부합 없음")
