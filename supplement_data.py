# -*- coding: utf-8 -*-
"""
补充数据脚本：连板梯队 + 概念板块热度
数据源：akshare（免费，东方财富公开数据）
用途：补充 daily_stock_analysis 项目生成的"大盘复盘"报告里缺失的两块内容：
      1. 连板梯队（几连板各多少只，对应Coze样本里的"连板梯队分层表"）
      2. 概念板块热度排行（涨跌幅+领涨股，对应Coze样本里的"板块主线"）

运行前需要先安装依赖：
    pip install akshare pandas
"""
import akshare as ak
import time
from datetime import datetime


def retry_call(func, *args, max_retries=3, delay=5, **kwargs):
    """带重试的函数调用，专门应对akshare偶发的连接断开问题"""
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            last_error = e
            print(f"  第{attempt}次尝试失败：{e}，{delay}秒后重试...")
            if attempt < max_retries:
                time.sleep(delay)
    raise last_error


def get_trading_date():
    """今天日期，格式 YYYYMMDD（akshare涨停股池接口要求这个格式）"""
    return datetime.now().strftime("%Y%m%d")


def get_lianban_ladder(date_str):
    """连板梯队：按连续涨停天数分层统计"""
    try:
        df = retry_call(ak.stock_zt_pool_em, date=date_str, max_retries=3, delay=5)
    except Exception as e:
        return f"⚠️ 涨停股池数据获取失败（已重试3次）：{e}\n（可能是非交易日，或接口临时限流）\n"

    if df is None or df.empty:
        return "今日无涨停股票池数据（可能是非交易日）\n"

    # 按连板数从高到低分层
    ladder = df.groupby('连板数').size().sort_index(ascending=False)

    lines = ["## 连板梯队\n"]
    for days, count in ladder.items():
        names = df[df['连板数'] == days]['名称'].tolist()
        sample = "、".join(names[:5])
        more = f" 等{len(names)}只" if len(names) > 5 else ""
        lines.append(f"- **{days}连板**（{count}只）：{sample}{more}")

    lines.append(f"\n涨停总数：{len(df)}只")
    return "\n".join(lines)


def find_col(df, keywords, fallback_index=None):
    """在df的列名里模糊查找包含指定关键词的列，避免因不同数据源字段名不同而报错"""
    for col in df.columns:
        for kw in keywords:
            if kw in str(col):
                return col
    if fallback_index is not None and fallback_index < len(df.columns):
        return df.columns[fallback_index]
    return None


def get_concept_heat(top_n=10):
    """概念板块热度排行（按涨跌幅排序），依次尝试多个数据源，用第一个成功且带涨跌幅数据的"""

    candidates = [
        ("东方财富-概念行情", lambda: ak.stock_board_concept_name_em()),
        ("东方财富-概念资金流", lambda: ak.stock_fund_flow_concept(symbol="即时")),
        ("同花顺-概念汇总", lambda: ak.stock_board_concept_summary_ths()),
        ("新浪-板块行情", lambda: ak.stock_sector_spot(indicator="概念")),
    ]

    df_rank, source = None, None
    errors = []

    for name, fetch_func in candidates:
        try:
            df_try = retry_call(fetch_func, max_retries=1, delay=3)
            cols = df_try.columns.tolist()
            print(f"  [调试信息] {name} 实际返回列名：{cols}")
            pct_col = find_col(df_try, ['涨跌幅', '涨幅'])
            if df_try is not None and not df_try.empty and pct_col:
                df_rank, source = df_try, name
                break
            else:
                errors.append(f"{name}：连上了但没找到涨跌幅列，列名={cols}")
        except Exception as e:
            errors.append(f"{name}：{e}")
            print(f"  {name} 失败：{e}，尝试下一个数据源...")

    if df_rank is None:
        detail = "\n  ".join(errors)
        return f"⚠️ 概念板块数据获取失败，所有数据源均尝试过：\n  {detail}\n"

    col_name = find_col(df_rank, ['名称', '板块'], fallback_index=1)
    col_pct = find_col(df_rank, ['涨跌幅', '涨幅'])
    col_leader = find_col(df_rank, ['领涨'])
    col_turnover = find_col(df_rank, ['换手'])

    if col_pct is None:
        return f"⚠️ 未能在{source}返回结果中找到涨跌幅相关列，实际列名：{df_rank.columns.tolist()}\n请把这行发给我，我调整关键词匹配规则\n"

    df_rank = df_rank.sort_values(col_pct, ascending=False).head(top_n)

    lines = [f"## 概念板块热度 Top{top_n}（数据源：{source}）\n"]
    lines.append("| 排名 | 板块名称 | 涨跌幅 | 领涨股 | 换手率 |")
    lines.append("|---|---|---|---|---|")
    for i, (_, row) in enumerate(df_rank.iterrows(), 1):
        name = row[col_name] if col_name else '-'
        pct = row[col_pct]
        leader = row[col_leader] if col_leader else '-'
        turnover = row[col_turnover] if col_turnover else '-'
        lines.append(f"| {i} | {name} | {pct}% | {leader} | {turnover}% |")

    return "\n".join(lines)


def main():
    date_str = get_trading_date()
    print(f"补充数据生成日期：{date_str}\n")

    lianban_section = get_lianban_ladder(date_str)
    concept_section = get_concept_heat(top_n=10)

    output = f"""## 补充数据（连板梯队 + 概念板块）

{lianban_section}

{concept_section}

---
数据来源：akshare（东方财富公开数据），仅供参考，不构成投资建议。
"""

    with open("supplement.md", "w", encoding="utf-8") as f:
        f.write(output)

    print(output)


if __name__ == "__main__":
    main()
