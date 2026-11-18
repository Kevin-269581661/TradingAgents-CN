"""AKShare 接口改名兼容层。

AKShare 1.20.45 起重命名/移除了一批接口（如 stock_zh_a_hist -> stock_zh_a_hist_em）。
业务代码中仍有旧名称调用，直接执行会抛 AttributeError。这里在进程内把旧名映射到
新实现，使调用点无需改动；若当前 AKShare 版本仍提供旧接口，则不覆盖原生实现。
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

try:
    import akshare as ak
except Exception as exc:  # pragma: no cover - akshare 为必需依赖，仅防御导入期异常
    ak = None
    logger.warning("AKShare 导入失败，跳过接口兼容映射: %s", exc)

# 新旧接口签名一致，可直接别名映射
_ALIASES = {
    "stock_zh_a_hist": "stock_zh_a_hist_em",
    "stock_zh_a_spot": "stock_zh_a_spot_sina",
    "tool_trade_date_hist_sina": "calendar_trade_date_hist_sina",
    "stock_zh_index_daily": "index_zh_daily_sina",
    "stock_zh_index_spot": "index_zh_spot_sina",
    "stock_hk_daily": "stock_hk_hist_sina",
    "stock_hk_spot": "stock_hk_spot_sina",
    "news_cctv": "alternative_news_cctv",
    "stock_dividents_cninfo": "stock_dividend_cninfo",
    "stock_financial_abstract_ths": "stock_financial_abstract",
    # 新浪日线接口已移除，腾讯接口参数（带市场前缀的 symbol + start/end/adjust）一致
    "stock_zh_a_daily": "stock_zh_a_hist_tx",
}

_applied = False


def _empty_frame():
    try:
        import pandas as pd

        return pd.DataFrame()
    except Exception:
        return None


def _stock_zh_a_minute(symbol: str = "", period: str = "5", adjust: str = "", **kwargs):
    """旧接口签名 (symbol, period, adjust)，新接口需要时间区间。"""
    window_days = 5 if str(period) == "1" else 30
    end = datetime.now()
    start = end - timedelta(days=window_days)
    return ak.stock_zh_a_hist_min_em(
        symbol=str(symbol),
        period=str(period),
        start_date=start.strftime("%Y-%m-%d %H:%M:%S"),
        end_date=end.strftime("%Y-%m-%d %H:%M:%S"),
        adjust=adjust or "",
    )


def _stock_announcement_em(symbol: str = "", **kwargs):
    """个股公告接口迁移到 stock_individual_notice_report，并对齐列名。"""
    df = ak.stock_individual_notice_report(symbol=str(symbol).zfill(6), indicator="全部")
    if df is None or getattr(df, "empty", True):
        return df
    return df.rename(columns={"公告日期": "公告时间", "网址": "公告链接"})


def _bond_zh_us_rate(start_date: str | None = None, **kwargs):
    """中美收益率曲线接口迁移到 bond_zh_us_yield_em，返回列保持一致。"""
    if start_date is None:
        start_date = (datetime.now() - timedelta(days=3 * 365)).strftime("%Y%m%d")
    return ak.bond_zh_us_yield_em(start_date=start_date)


def _fund_etf_fund_daily_em():
    """ETF 净值接口已下线，退化为 ETF 实时快照；字段缺失由调用方按空值处理。"""
    try:
        return ak.fund_etf_spot_em()
    except Exception as exc:
        logger.warning("AKShare fund_etf_spot_em 获取失败（原 fund_etf_fund_daily_em）: %s", exc)
        return _empty_frame()


def _fund_etf_fund_info_em(fund: str = "", **kwargs):
    """ETF 历史净值接口已下线，无等价替代，返回空表由调用方降级处理。"""
    logger.debug("AKShare fund_etf_fund_info_em 已移除，返回空数据: fund=%s", fund)
    return _empty_frame()


# 签名或返回结构发生变化，需要适配
_WRAPPERS = {
    "stock_zh_a_minute": _stock_zh_a_minute,
    "stock_announcement_em": _stock_announcement_em,
    "bond_zh_us_rate": _bond_zh_us_rate,
    "fund_etf_fund_daily_em": _fund_etf_fund_daily_em,
    "fund_etf_fund_info_em": _fund_etf_fund_info_em,
}


def ensure_akshare_compat() -> None:
    """注册兼容映射，幂等。"""
    global _applied
    if _applied or ak is None:
        return
    _applied = True

    for old_name, new_name in _ALIASES.items():
        if hasattr(ak, old_name):
            continue
        new_func = getattr(ak, new_name, None)
        if new_func is None:
            logger.warning("AKShare 兼容映射缺少目标接口: %s -> %s", old_name, new_name)
            continue
        setattr(ak, old_name, new_func)
        logger.info("AKShare 兼容映射: %s -> %s", old_name, new_name)

    for old_name, wrapper in _WRAPPERS.items():
        if hasattr(ak, old_name):
            continue
        setattr(ak, old_name, wrapper)
        logger.info("AKShare 兼容适配: %s", old_name)


ensure_akshare_compat()