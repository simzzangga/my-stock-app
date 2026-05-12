import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from pykrx import stock
import matplotlib.pyplot as plt

# 1. 페이지 설정 (웹 브라우저 탭 이름과 아이콘)
st.set_page_config(page_title="Make Some Money 분석기", page_icon="📈", layout="wide")

# 2. 제목 및 소개
st.title("🚀 승현이의 'Make Some Money' 분석기")
st.markdown("장대 양봉 이후 **거래량 급감(15~20%)** 구간을 포착하여 승률 높은 눌림목 타점을 찾아냅니다.")

# 3. 사이드바: 설정창
with st.sidebar:
    st.header("⚙️ 분석 설정")
    ticker = st.text_input("종목 코드 (6자리)", value="005930")
    base_date = st.date_input("분석 기준일 선택", datetime.now())
    
    st.divider()
    st.subheader("알고리즘 필터")
    min_gain = st.slider("장대양봉 기준 (최소 %)", 3, 15, 6)
    vol_range = st.slider("눌림목 거래량 범위 (%)", 5, 40, (15, 20))

# 4. 메인 분석 로직
if st.button("실시간 분석 시작"):
    with st.spinner('데이터를 분석 중입니다...'):
        try:
            # 날짜 설정
            end_date = base_date.strftime("%Y%m%d")
            start_date = (base_date - timedelta(days=90)).strftime("%Y%m%d")
            
            # 주가 데이터 가져오기
            df = stock.get_market_ohlcv_by_date(start_date, end_date, ticker)
            
            if df.empty:
                st.error("❌ 해당 종목의 데이터를 찾을 수 없습니다. 종목 코드를 확인하세요.")
            else:
                # 시그널 탐색 로직
                df['등락률'] = df['종가'].pct_change() * 100
                signals = df[(df['등락률'] >= min_gain) & (df['거래량'] > df['거래량'].shift(1) * 2)]
                
                if signals.empty:
                    st.warning("⚠️ 최근 2개월 내 조건에 맞는 장대 양봉 시그널이 없습니다. [관망]")
                else:
                    # 최신 시그널 분석
                    latest_s = signals.iloc[-1]
                    s_date = latest_s.name
                    s_vol = latest_s['거래량']
                    s_mid = (latest_s['고가'] + latest_s['저가']) / 2
                    
                    # 현재 상태 (기준일)
                    curr = df.iloc[-1]
                    curr_p = curr['종가']
                    v_ratio = (curr['거래량'] / s_vol) * 100
                    
                    # 판정 및 UI 출력
                    st.divider()
                    
                    # 결과 카드 레이아웃
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.subheader("📊 시장 상황")
                        st.metric("현재가", f"{int(curr_p):,}원", f"{curr['등락률']:.2f}%")
                        st.metric("시그널 대비 거래량", f"{v_ratio:.1f}%")
                        
                        # 판정 결과
                        if vol_range[0] <= v_ratio <= vol_range[1]:
                            if curr_p >= s_mid:
                                st.error("🔥 매수 적기 (강력 추천)")
                            else:
                                st.info("⚖️ 분할 매수 구간 (진입)")
                        else:
                            st.warning("⏳ 관망 (타점 대기 중)")

                    with col2:
                        st.subheader("🎯 전략 가이드")
                        st.write(f"✅ **1차 매수:** {int(curr_p):,}원")
                        st.write(f"✅ **2차 매수:** {int(curr_p*0.96):,}원 (-4%)")
                        st.write(f"✅ **3차 매수:** {int(curr_p*0.92):,}원 (-8%)")
                        st.success(f"🎯 **목표가:** {int(curr_p*1.09):,}원 (+9%)")

                    # 5. 차트 시각화
                    st.subheader("📈 주가 흐름 확인")
                    fig, ax = plt.subplots(figsize=(12, 5))
                    ax.plot(df.index, df['종가'], label="Price")
                    ax.axvline(s_date, color='red', linestyle='--', label="Signal Date")
                    ax.fill_between(df.index, latest_s['저가'], latest_s['고가'], color='red', alpha=0.1)
                    plt.legend()
                    st.pyplot(fig)
                    
        except Exception as e:
            st.error(f"오류가 발생했습니다: {e}")
