import streamlit as st
import pandas as pd
import json
import logging
from core import StockScreener, StockAnalyzer, config

logging.basicConfig(level=logging.INFO)
st.set_page_config(page_title="A股选股-手动模式", layout="wide")

st.markdown("## 手动粘贴数据模式 (离线)")
st.info("""操作步骤:
1. 浏览器打开 https://quote.eastmoney.com/ 刷新行情
2. 按 F12 → Network 标签
3. 找到 clist/get 请求 → 点它 → Response
4. 复制完整 JSON 响应文本
5. 粘贴到下面文本框
""")

if "fetched_data" not in st.session_state:
    st.session_state.fetched_data = None
if "screen_results" not in st.session_state:
    st.session_state.screen_results = None
if "analysis_results" not in st.session_state:
    st.session_state.analysis_results = None

json_input = st.text_area("粘贴 JSON 数据", height=200)

if json_input:
    try:
        data = json.loads(json_input)
        diff = data.get("data",{}).get("diff",[]) or data.get("diff",[])
        if diff:
            df = pd.DataFrame(diff)
            cols = {
                "f2":"最新价","f3":"涨跌幅","f5":"成交量","f6":"成交额",
                "f8":"换手率","f10":"量比","f12":"股票代码","f14":"股票名称",
                "f15":"最高价","f16":"最低价","f17":"开盘价","f18":"昨收价",
                "f20":"总市值","f21":"流通市值"
            }
            df.rename(columns=cols, inplace=True)
            for c in list(cols.values()):
                if c in df.columns:
                    df[c] = pd.to_numeric(df[c], errors="coerce")
            st.session_state.fetched_data = df
            st.success(f"成功加载 {len(df)} 只股票")
        else:
            st.error("未找到股票数据，请确认复制的JSON格式是否正确")
    except Exception as e:
        st.error(f"解析JSON失败: {e}")

st.markdown("---")
st.markdown("### 选股条件设置")

c1, c2, c3, c4, c5 = st.columns(5)
with c1:
    pct_min = st.slider("涨幅下限(%)", 0.0, 20.0, 2.0, 0.5)
    pct_max = st.slider("涨幅上限(%)", 0.0, 20.0, 5.0, 0.5)
with c2:
    vr_min = st.slider("量比下限", 0.0, 10.0, 1.0, 0.1)
    vr_max = st.slider("量比上限", 0.0, 10.0, 5.0, 0.1)
with c3:
    tr_min = st.slider("换手率下限(%)", 0.0, 30.0, 5.0, 0.5)
    tr_max = st.slider("换手率上限(%)", 0.0, 30.0, 10.0, 0.5)
with c4:
    price_min = st.slider("股价下限(元)", 0.0, 200.0, 5.0, 1.0)
    price_max = st.slider("股价上限(元)", 0.0, 200.0, 80.0, 1.0)
with c5:
    mcap_min = st.slider("市值下限(亿)", 0, 1000, 30, 10)
    mcap_max = st.slider("市值上限(亿)", 0, 1000, 300, 10)

st.markdown("### AI 分析配置")
ak = st.text_input("API Key (可选)", type="password", placeholder="填入后启用AI分析")
bu = st.text_input("API地址", value="https://api.openai.com/v1")
mn = st.text_input("模型名称", value="gpt-4o-mini")

if st.button("执行选股", type="primary", use_container_width=True):
    df = st.session_state.get("fetched_data")
    if df is None or df.empty:
        st.warning("请先粘贴数据")
    else:
        with st.spinner("正在执行多条件筛选..."):
            cond = {
                "pct_min": pct_min, "pct_max": pct_max,
                "vr_min": vr_min, "vr_max": vr_max,
                "tr_min": tr_min, "tr_max": tr_max,
                "price_min": price_min, "price_max": price_max,
                "mcap_min": mcap_min * 1e8, "mcap_max": mcap_max * 1e8,
                "check_vol_trend": False, "check_limit_up": False,
            }
            try:
                s = StockScreener()
                mask = (
                    (df["涨跌幅"] >= cond["pct_min"]) & (df["涨跌幅"] <= cond["pct_max"]) &
                    (df["量比"] >= cond["vr_min"]) & (df["量比"] <= cond["vr_max"]) &
                    (df["换手率"] >= cond["tr_min"]) & (df["换手率"] <= cond["tr_max"]) &
                    (df["最新价"] >= cond["price_min"]) & (df["最新价"] <= cond["price_max"]) &
                    (df["总市值"] >= cond["mcap_min"]) & (df["总市值"] <= cond["mcap_max"])
                )
                result = df[mask].copy()
                st.session_state.screen_results = result
                st.session_state.analysis_results = None
                st.success(f"筛选完成! 共 {len(result)} 只股票满足条件")
            except Exception as ex:
                import traceback; st.error(f"选股失败: {ex}"); st.code(traceback.format_exc())

res = st.session_state.get("screen_results")
if res is not None and not res.empty:
    st.markdown("---")
    st.markdown(f"### 筛选结果 ({len(res)} 只)")
    st.dataframe(res, use_container_width=True)
    st.download_button("下载CSV", res.to_csv(index=False).encode("utf-8-sig"),
                       "选股结果.csv", "text/csv")

    if ak and st.button("开始AI分析", use_container_width=True):
        with st.spinner("AI正在逐一分析..."):
            config.llm.api_key = ak
            config.llm.base_url = bu
            config.llm.model = mn
            a = StockAnalyzer()
            results = a.analyze_batch(res)
            st.session_state.analysis_results = results
            st.rerun()

    ar = st.session_state.get("analysis_results")
    if ar:
        st.markdown("---")
        st.markdown("### AI分析结果 (按评分排序)")
        tbl = []
        for i, r in enumerate(ar, 1):
            cap_reason = r.reason[:80] + "..." if len(r.reason) > 80 else r.reason
            cap_risk = r.risk[:60] + "..." if len(r.risk) > 60 else r.risk
            tbl.append({"排名": i, "代码": r.code, "名称": r.name,
                        "评分": int(r.score), "理由": cap_reason, "风险": cap_risk})
        st.dataframe(pd.DataFrame(tbl), use_container_width=True)

st.markdown("---")
st.caption("本工具仅供学习研究，不构成投资建议。股市有风险，投资需谨慎。")
