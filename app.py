import streamlit as st
import pandas as pd

from core import (
    CUSTOM_CONDITION_FIELDS,
    EastMoneyFetcher,
    StockAnalyzer,
    StockScreener,
    config,
)
from core.chrome_fallback import load_cached_data


CACHE_FILE = "stock_data.json"
NETWORK_HINT = (
    "所有在线行情源当前均不可用。股票行情数据不需要 API Key；API Key 只用于后面的 AI 分析。"
)


st.set_page_config(page_title="A股量化选股工具", layout="wide", page_icon=":material/finance:")


def init_state() -> None:
    for key in ["fetched_data", "screen_results", "analysis_results", "data_source", "last_error"]:
        st.session_state.setdefault(key, None)
    st.session_state.setdefault("custom_condition_ids", [])
    st.session_state.setdefault("custom_condition_seq", 0)


def load_local_stock_data() -> pd.DataFrame | None:
    return load_cached_data(CACHE_FILE)


def fetch_stock_data() -> tuple[pd.DataFrame | None, str, str | None]:
    cached = load_local_stock_data()
    if cached is not None and not cached.empty:
        return cached, f"本地缓存 {CACHE_FILE}", None

    try:
        fetcher = EastMoneyFetcher()
        df = fetcher.fetch_realtime()
        if df is not None and not df.empty:
            return df, fetcher.last_source or "在线行情接口", None
        return None, "", "在线接口返回为空，未获取到股票数据。"
    except Exception as exc:
        return None, "", f"{NETWORK_HINT} 当前也没有找到可用的 {CACHE_FILE}。底层错误：{exc.__class__.__name__}"


def reset_results() -> None:
    st.session_state.screen_results = None
    st.session_state.analysis_results = None


def stock_data_for_display(df: pd.DataFrame) -> pd.DataFrame:
    display_df = df.copy()
    for source_column, display_column in [
        ("总市值", "总市值(亿)"),
        ("流通市值", "流通市值(亿)"),
    ]:
        if source_column not in display_df.columns:
            continue
        market_cap = pd.to_numeric(display_df[source_column], errors="coerce") / 1e8
        column_index = display_df.columns.get_loc(source_column)
        display_df = display_df.drop(columns=[source_column])
        display_df.insert(column_index, display_column, market_cap.round(2))
    return display_df


def add_custom_condition() -> None:
    condition_id = st.session_state.custom_condition_seq
    st.session_state.custom_condition_seq += 1
    st.session_state.custom_condition_ids.append(condition_id)


def remove_custom_condition(condition_id: int) -> None:
    st.session_state.custom_condition_ids = [
        item for item in st.session_state.custom_condition_ids if item != condition_id
    ]
    for suffix in ["field", "min", "max"]:
        st.session_state.pop(f"custom_{condition_id}_{suffix}", None)


def range_condition_input(
    label: str,
    key: str,
    default_min: int | float,
    default_max: int | float,
    *,
    allowed_min: int | float | None = None,
    allowed_max: int | float | None = None,
    step: int | float = 0.1,
) -> tuple[int | float, int | float]:
    label_col, min_col, max_col = st.columns(
        [1.45, 1, 1], vertical_alignment="center", gap="small"
    )
    label_col.markdown(f"**{label}**")
    minimum = min_col.number_input(
        f"{label}最小值",
        min_value=allowed_min,
        max_value=allowed_max,
        value=default_min,
        step=step,
        key=f"{key}_min",
        label_visibility="collapsed",
        placeholder="最小",
    )
    maximum = max_col.number_input(
        f"{label}最大值",
        min_value=allowed_min,
        max_value=allowed_max,
        value=default_max,
        step=step,
        key=f"{key}_max",
        label_visibility="collapsed",
        placeholder="最大",
    )
    return minimum, maximum


init_state()

with st.sidebar:
    st.markdown("## 条件设置")
    st.markdown("---")

    header_label, header_min, header_max = st.columns([1.45, 1, 1], gap="small")
    header_label.caption("条件")
    header_min.caption("最小值")
    header_max.caption("最大值")

    pct_min, pct_max = range_condition_input(
        "涨幅 (%)", "pct", 2.0, 5.0,
        allowed_min=-100.0, allowed_max=100.0, step=0.1,
    )
    vr_min, vr_max = range_condition_input(
        "量比", "vr", 1.0, 5.0, allowed_min=0.0, step=0.1,
    )
    tr_min, tr_max = range_condition_input(
        "换手率 (%)", "tr", 5.0, 10.0,
        allowed_min=0.0, allowed_max=100.0, step=0.1,
    )
    price_min, price_max = range_condition_input(
        "股价 (元)", "price", 5.0, 80.0, allowed_min=0.0, step=0.1,
    )
    mcap_min, mcap_max = range_condition_input(
        "总市值 (亿)", "mcap", 30.0, 300.0, allowed_min=0.0, step=1.0,
    )

    include_chinext = st.toggle("包含创业板", True)
    include_star_market = st.toggle("包含科创板", True)
    check_vol_trend = st.toggle("成交量 3 日逐渐增加", True)
    check_macd = st.toggle("MACD 金叉", False)

    limit_label, limit_min_col, limit_max_col = st.columns(
        [1.45, 1, 1], vertical_alignment="center", gap="small"
    )
    check_limit_up = limit_label.toggle("近一月涨停", True)
    limit_up_min = limit_min_col.number_input(
        "最近一个月涨停次数最小值",
        min_value=0,
        max_value=31,
        value=2,
        step=1,
        disabled=not check_limit_up,
        label_visibility="collapsed",
    )
    limit_up_max = limit_max_col.number_input(
        "最近一个月涨停次数最大值",
        min_value=0,
        max_value=31,
        value=31,
        step=1,
        disabled=not check_limit_up,
        label_visibility="collapsed",
    )

    st.markdown("---")
    custom_title, custom_add = st.columns([2, 1], vertical_alignment="center")
    custom_title.markdown("#### 自定义条件")
    custom_add.button(
        "增加",
        icon=":material/add:",
        on_click=add_custom_condition,
        width="stretch",
    )

    custom_conditions = []
    condition_errors = []
    field_options = list(CUSTOM_CONDITION_FIELDS)
    for condition_id in st.session_state.custom_condition_ids:
        field_col, min_col, max_col, delete_col = st.columns(
            [1.65, 1, 1, 0.45], vertical_alignment="center", gap="small"
        )
        field_label = field_col.selectbox(
            f"自定义条件 {condition_id + 1} 字段",
            field_options,
            key=f"custom_{condition_id}_field",
            label_visibility="collapsed",
        )
        custom_min = min_col.number_input(
            f"{field_label}最小值",
            value=None,
            step=0.1,
            key=f"custom_{condition_id}_min",
            label_visibility="collapsed",
            placeholder="最小",
        )
        custom_max = max_col.number_input(
            f"{field_label}最大值",
            value=None,
            step=0.1,
            key=f"custom_{condition_id}_max",
            label_visibility="collapsed",
            placeholder="最大",
        )
        delete_col.button(
            ":material/delete:",
            key=f"delete_custom_{condition_id}",
            help="删除条件",
            on_click=remove_custom_condition,
            args=(condition_id,),
        )

        definition = CUSTOM_CONDITION_FIELDS[field_label]
        scale = definition["scale"]
        custom_conditions.append({
            "label": field_label,
            "column": definition["column"],
            "min": None if custom_min is None else float(custom_min) * scale,
            "max": None if custom_max is None else float(custom_max) * scale,
        })
        if custom_min is None or custom_max is None:
            condition_errors.append(f"请填写“{field_label}”的最小值和最大值")
        elif custom_min > custom_max:
            condition_errors.append(f"“{field_label}”的最小值不能大于最大值")

    for label, minimum, maximum in [
        ("涨幅", pct_min, pct_max),
        ("量比", vr_min, vr_max),
        ("换手率", tr_min, tr_max),
        ("股价", price_min, price_max),
        ("市值", mcap_min, mcap_max),
        ("最近一个月涨停次数", limit_up_min, limit_up_max),
    ]:
        if minimum > maximum:
            condition_errors.append(f"“{label}”的最小值不能大于最大值")

    if condition_errors:
        st.error(condition_errors[0])

    st.markdown("---")
    api_key = st.text_input("API Key", type="password", placeholder="sk-")
    base_url = st.text_input(
        "API 地址",
        value=config.llm.base_url,
    )
    model_name = st.text_input(
        "模型名称",
        value=config.llm.model_display_name,
    )

    st.markdown("---")
    fetch_clicked = st.button(":material/download: 获取数据", type="primary", width="stretch")
    screen_clicked = st.button(
        ":material/search: 执行选股",
        width="stretch",
        disabled=bool(condition_errors),
    )


if api_key:
    config.llm.api_key = api_key
    config.llm.base_url = base_url
    config.llm.model = model_name


conditions = {
    "pct_min": pct_min,
    "pct_max": pct_max,
    "vr_min": vr_min,
    "vr_max": vr_max,
    "tr_min": tr_min,
    "tr_max": tr_max,
    "price_min": price_min,
    "price_max": price_max,
    "mcap_min": mcap_min * 1e8,
    "mcap_max": mcap_max * 1e8,
    "include_chinext": include_chinext,
    "include_star_market": include_star_market,
    "check_vol_trend": check_vol_trend,
    "check_macd": check_macd,
    "check_limit_up": check_limit_up,
    "limit_up_min": limit_up_min,
    "limit_up_max": limit_up_max,
    "custom_conditions": custom_conditions,
}


if fetch_clicked:
    with st.spinner("正在获取 A 股行情数据..."):
        df, source, error = fetch_stock_data()
        if df is not None and not df.empty:
            st.session_state.fetched_data = df
            st.session_state.data_source = source
            st.session_state.last_error = None
            reset_results()
            st.success(f"成功加载 {len(df)} 只股票数据，来源：{source}")
            st.rerun()
        else:
            st.session_state.last_error = error


if screen_clicked:
    if st.session_state.fetched_data is None or st.session_state.fetched_data.empty:
        st.warning("请先获取数据。")
    else:
        with st.spinner("正在执行多条件筛选..."):
            try:
                screener = StockScreener()
                result = screener.screen_stream(st.session_state.fetched_data, conditions)
                st.session_state.screen_results = result
                st.session_state.analysis_results = None
                st.rerun()
            except Exception as exc:
                st.error(f"选股出错：{exc}")


st.title("A股多条件量化选股 + AI 分析")
st.caption("基于多源在线行情数据，多条件筛选，并支持大模型按 T+1 策略打分排序。")

if st.session_state.last_error:
    st.warning(st.session_state.last_error)


tab_data, tab_screen, tab_ai = st.tabs(["数据浏览", "选股结果", "AI 分析"])

with tab_data:
    df = st.session_state.fetched_data
    if df is not None and not df.empty:
        st.success(f"已加载 {len(df)} 只股票数据，来源：{st.session_state.data_source}")
        display_df = stock_data_for_display(df)
        visible_cols = [
            col
            for col in [
                "股票代码", "股票名称", "最新价", "涨跌幅", "量比", "换手率",
                "总市值(亿)", "流通市值(亿)",
            ]
            if col in display_df.columns
        ]
        st.dataframe(
            display_df[visible_cols] if visible_cols else display_df,
            width="stretch",
            height=500,
        )
    else:
        st.info("点击侧边栏的“获取数据”开始。")

with tab_screen:
    result = st.session_state.screen_results
    if result is not None and not result.empty:
        st.success(f"筛选结果：{len(result)} 只股票满足条件")
        display_result = stock_data_for_display(result)
        st.dataframe(display_result, width="stretch", height=420)
        st.download_button(
            ":material/download: 下载 CSV",
            display_result.to_csv(index=False).encode("utf-8-sig"),
            "选股结果.csv",
            "text/csv",
            width="stretch",
        )
    else:
        st.info("设置条件后点击“执行选股”。")

with tab_ai:
    results = st.session_state.analysis_results
    if results:
        st.success(f"AI 分析完成，共 {len(results)} 只股票")
        rows = []
        for rank, item in enumerate(results, 1):
            reason = item.reason[:100] + "..." if len(item.reason) > 100 else item.reason
            risk = item.risk[:60] + "..." if len(item.risk) > 60 else item.risk
            target_display = "-"
            if item.target_price > 0:
                target_display = f"{item.target_price:.2f}"
                if item.target_gain_pct is not None:
                    target_display += f"（涨幅 {item.target_gain_pct:.2f}%）"
            stop_loss_display = "-"
            if item.stop_loss > 0:
                stop_loss_display = f"{item.stop_loss:.2f}"
                if item.stop_loss_pct is not None:
                    stop_loss_display += f"（跌幅 {item.stop_loss_pct:.2f}%）"
            rows.append(
                {
                    "排名": rank,
                    "代码": item.code,
                    "名称": item.name,
                    "评分": int(item.score),
                    "当前价": round(item.current_price, 2),
                    "目标价（涨幅）": target_display,
                    "止损价（跌幅）": stop_loss_display,
                    "理由": reason,
                    "风险": risk,
                }
            )
        st.dataframe(pd.DataFrame(rows), width="stretch")

        with st.expander("查看完整分析详情"):
            for rank, item in enumerate(results, 1):
                st.markdown(f"### {rank}. {item.name}({item.code}) 评分：{int(item.score)}")
                st.markdown(f"**当前价**：{item.current_price:.2f} 元")
                st.markdown(f"**理由**：{item.reason}")
                st.markdown(f"**风险**：{item.risk}")
                if item.target_price:
                    target_gain = (
                        f"（涨幅 {item.target_gain_pct:.2f}%）"
                        if item.target_gain_pct is not None else ""
                    )
                    st.markdown(f"**目标价**：{item.target_price:.2f} 元{target_gain}")
                if item.stop_loss:
                    stop_loss_drop = (
                        f"（跌幅 {item.stop_loss_pct:.2f}%）"
                        if item.stop_loss_pct is not None else ""
                    )
                    st.markdown(f"**止损价**：{item.stop_loss:.2f} 元{stop_loss_drop}")
                st.divider()
    elif not api_key:
        st.info("请在侧边栏配置 API Key 后再进行 AI 分析。")
    else:
        st.info("选股完成后点击下方按钮进行 AI 分析。")


if st.session_state.screen_results is not None and not st.session_state.screen_results.empty:
    if api_key and st.button(":material/psychology: 开始 AI 分析", type="primary", width="stretch"):
        with st.spinner("AI 正在逐一分析..."):
            analyzer = StockAnalyzer(api_key, base_url, model_name)
            st.session_state.analysis_results = analyzer.analyze_batch(st.session_state.screen_results)
        st.rerun()


st.markdown("---")
st.caption("本工具仅供学习研究，不构成投资建议。股市有风险，投资需谨慎。")
