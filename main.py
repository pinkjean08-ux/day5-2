import time
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st

st.set_page_config(page_title="청년인구와 스타벅스", page_icon="☕", layout="wide")

DATA_FILE = Path(__file__).with_name("analysis_data.xlsx")
STORE_API_URL = "https://www.starbucks.co.kr/store/getStore.do"
STORE_MAP_URL = "https://www.starbucks.co.kr/store/store_map.do"

SIDO_CODES = {
    "서울특별시": "01", "광주광역시": "02", "대구광역시": "03",
    "대전광역시": "04", "부산광역시": "05", "울산광역시": "06",
    "인천광역시": "07", "경기도": "08", "강원특별자치도": "09",
    "경상남도": "10", "경상북도": "11", "전라남도": "12",
    "전북특별자치도": "13", "충청남도": "14", "충청북도": "15",
    "제주특별자치도": "16", "세종특별자치시": "17",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36",
    "Referer": STORE_MAP_URL,
    "Origin": "https://www.starbucks.co.kr",
    "X-Requested-With": "XMLHttpRequest",
}

AGE_GROUPS = ["20–24세", "25–29세", "30–34세", "35–39세"]


def clean_text(v):
    if v is None:
        return ""
    return " ".join(str(v).strip().split())


def to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def extract_sigungu(address):
    parts = clean_text(address).split()
    if not parts:
        return ""
    if "세종" in parts[0]:
        return "세종시"
    cands = [p for p in parts[1:4] if p.endswith(("시", "군", "구"))]
    if len(cands) >= 2 and cands[0].endswith("시") and cands[1].endswith("구"):
        return f"{cands[0]} {cands[1]}"
    return cands[0] if cands else ""


def analysis_sigungu(store_sigungu):
    """일반구 매장을 분석자료의 시 단위로 합친다."""
    if " " in store_sigungu:
        first, second = store_sigungu.split(" ", 1)
        if first.endswith("시") and second.endswith("구"):
            return first
    return store_sigungu


def extract_store_list(obj):
    if isinstance(obj, list):
        return obj
    if not isinstance(obj, dict):
        return []
    for key in ["list", "storeList", "stores", "result", "data"]:
        val = obj.get(key)
        if isinstance(val, list):
            return val
        if isinstance(val, dict):
            for key2 in ["list", "storeList", "stores", "result", "data"]:
                val2 = val.get(key2)
                if isinstance(val2, list):
                    return val2
    return []


@st.cache_data(ttl=3600, show_spinner=False)
def collect_stores(sido_name):
    code = SIDO_CODES[sido_name]
    payload = {
        "ins_lat": "37.56682", "ins_lng": "126.97865", "p_sido_cd": code,
        "p_gugun_cd": "", "in_biz_cd": "", "set_date": "", "iend": "5000",
        "search_text": "", "all_store": "0", "T03": "0", "T01": "0",
        "T12": "0", "T09": "0", "T30": "0", "T05": "0", "T22": "0",
        "T21": "0", "T10": "0", "T36": "0", "P10": "0", "P50": "0",
        "P20": "0", "P60": "0", "P30": "0", "P70": "0", "P40": "0",
        "P80": "0", "whcroad_yn": "0", "P90": "0", "new_bool": "0",
    }
    with requests.Session() as session:
        try:
            session.get(STORE_MAP_URL, headers=HEADERS, timeout=15)
        except requests.RequestException:
            pass
        response = session.post(STORE_API_URL, data=payload, headers=HEADERS, timeout=30)
        response.raise_for_status()
        rows = []
        for s in extract_store_list(response.json()):
            addr = clean_text(s.get("addr") or s.get("addr2") or s.get("new_address"))
            sigungu = extract_sigungu(addr)
            rows.append({
                "매장명": clean_text(s.get("s_name") or s.get("store_nm") or s.get("name")),
                "시도": sido_name,
                "매장 시군구": sigungu,
                "분석 시군구": analysis_sigungu(sigungu),
                "주소": addr,
                "전화번호": clean_text(s.get("tel") or s.get("store_tel")),
                "위도": to_float(s.get("lat") or s.get("latitude")),
                "경도": to_float(s.get("lot") or s.get("lng") or s.get("longitude")),
            })
        time.sleep(0.1)
        return pd.DataFrame(rows)


@st.cache_data
def load_analysis():
    if not DATA_FILE.exists():
        raise FileNotFoundError("analysis_data.xlsx 파일이 없습니다.")
    corr = pd.read_excel(DATA_FILE, sheet_name="상관분석")
    regional = pd.read_excel(DATA_FILE, sheet_name="시군구별 분석자료")
    return corr, regional


def p_text(p):
    if p < 0.001:
        return "< .001"
    return f"{p:.3f}"


corr_df, data = load_analysis()

st.title("시군구 청년인구·전출률과 스타벅스 매장")
st.caption("청년인구는 2026년 4~5월 평균, 전출률은 같은 기간 월평균 총전출자 수를 평균 주민등록인구로 나눈 값입니다.")

with st.sidebar:
    st.header("지역 선택")
    sido = st.selectbox("시도", sorted(data["시도"].unique()))
    sigungu = st.selectbox("시군구", sorted(data.loc[data["시도"] == sido, "시군구"].unique()))
    age = st.radio("산점도 연령대", AGE_GROUPS, index=0)

selected = data[(data["시도"] == sido) & (data["시군구"] == sigungu)].iloc[0]

try:
    with st.spinner("선택한 시도의 스타벅스 위치를 불러오는 중입니다."):
        sido_stores = collect_stores(sido)
    selected_stores = sido_stores[sido_stores["분석 시군구"] == sigungu].copy()
except Exception as e:
    selected_stores = pd.DataFrame()
    st.warning(f"스타벅스 위치를 불러오지 못했습니다. 분석자료의 매장 수는 계속 표시합니다. ({e})")

st.subheader(f"{sido} {sigungu}")
metric_cols = st.columns(5)
metric_cols[0].metric("스타벅스 매장", f"{int(selected['스타벅스 매장 수']):,}개")
for i, ag in enumerate(AGE_GROUPS, start=1):
    metric_cols[i].metric(ag, f"{int(round(selected[f'{ag} 평균 주민등록인구'])):,}명")

left, right = st.columns([1, 1.25])

with left:
    pop_long = pd.DataFrame({
        "연령대": AGE_GROUPS,
        "평균 청년인구": [selected[f"{ag} 평균 주민등록인구"] for ag in AGE_GROUPS],
        "전출률(%)": [selected[f"{ag} 전출률(%)"] for ag in AGE_GROUPS],
    })
    fig_pop = px.bar(pop_long, x="연령대", y="평균 청년인구", text_auto=",.0f", title="5세 급간별 평균 청년인구")
    fig_pop.update_traces(marker_color="#4C78A8")
    fig_pop.update_layout(yaxis_title="명", xaxis_title=None)
    st.plotly_chart(fig_pop, use_container_width=True)

    st.dataframe(
        pop_long.style.format({"평균 청년인구": "{:,.0f}", "전출률(%)": "{:.2f}"}),
        use_container_width=True,
        hide_index=True,
    )

with right:
    st.markdown("#### 스타벅스 매장 위치")
    if selected_stores.empty:
        st.info("표시할 매장 좌표가 없습니다.")
    else:
        map_df = selected_stores.dropna(subset=["위도", "경도"]).copy()
        fig_map = px.scatter_map(
            map_df, lat="위도", lon="경도", hover_name="매장명",
            hover_data={"주소": True, "전화번호": True, "위도": False, "경도": False},
            zoom=10, height=500,
        )
        fig_map.update_traces(marker={"size": 13, "color": "#00704A"})
        fig_map.update_layout(map_style="open-street-map", margin={"r":0,"t":0,"l":0,"b":0})
        st.plotly_chart(fig_map, use_container_width=True)
        st.dataframe(selected_stores[["매장명", "주소", "전화번호"]], use_container_width=True, hide_index=True)

st.divider()
st.header("스타벅스 매장 수와 청년 전출률의 상관관계")

show_corr = corr_df.copy()
show_corr["Pearson p"] = show_corr["Pearson p"].map(p_text)
show_corr["Spearman p"] = show_corr["Spearman p"].map(p_text)
st.dataframe(
    show_corr.style.format({"Pearson r": "{:.3f}", "Spearman rho": "{:.3f}", "평균 전출률(%)": "{:.2f}"}),
    use_container_width=True,
    hide_index=True,
)

scatter_col, detail_col = st.columns([1.5, 1])
with scatter_col:
    x = data["스타벅스 매장 수"]
    ycol = f"{age} 전출률(%)"
    y = data[ycol]

    fig = px.scatter(
        data, x="스타벅스 매장 수", y=ycol, hover_name="지역",
        trendline="ols", opacity=0.55,
        title=f"스타벅스 매장 수와 {age} 전출률",
    )
    fig.update_traces(marker={"color": "#9E9E9E", "size": 8}, selector=dict(mode="markers"))
    fig.add_trace(go.Scatter(
        x=[selected["스타벅스 매장 수"]], y=[selected[ycol]],
        mode="markers+text", name=f"선택: {sigungu}",
        text=[sigungu], textposition="top center",
        marker={"color": "red", "size": 15, "line": {"color": "darkred", "width": 1.5}},
        hovertemplate=(f"{sido} {sigungu}<br>매장 수: {int(selected['스타벅스 매장 수'])}개"
                       f"<br>{age} 전출률: {selected[ycol]:.2f}%<extra></extra>"),
    ))
    fig.update_layout(xaxis_title="스타벅스 매장 수", yaxis_title=f"{age} 전출률(%)")
    st.plotly_chart(fig, use_container_width=True)

with detail_col:
    row = corr_df[corr_df["연령대"] == age].iloc[0]
    st.markdown(f"#### {age} 결과")
    st.metric("Pearson r", f"{row['Pearson r']:.3f}")
    st.metric("Spearman ρ", f"{row['Spearman rho']:.3f}")
    st.write(f"Pearson p: **{p_text(row['Pearson p'])}**")
    st.write(f"선택 지역 전출률: **{selected[ycol]:.2f}%**")
    st.write(f"전체 평균 전출률: **{row['평균 전출률(%)']:.2f}%**")

st.caption("상관관계는 인과관계를 의미하지 않습니다. 전출률은 전입을 고려하지 않으므로 청년 순유출을 직접 나타내는 지표는 아닙니다.")
