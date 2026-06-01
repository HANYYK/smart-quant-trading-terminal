"""
技术指标统一计算模块
整合所有技术指标，避免重复计算
"""
import pandas as pd
import numpy as np
from typing import Optional


def calculate_all_indicators(df: pd.DataFrame, indicators: Optional[list[str]] = None) -> pd.DataFrame:
    """
    一次性计算所有技术指标，避免多次遍历DataFrame
    
    Args:
        df: K线数据DataFrame，必须包含 high, low, close, volume 列
        indicators: 要计算的指标列表，默认计算所有
    
    Returns:
        添加了技术指标的DataFrame
    """
    if df.empty or len(df) < 2:
        return df
    
    # 默认计算所有指标
    if indicators is None:
        indicators = ['ma', 'ema', 'macd', 'rsi', 'kdj', 'bollinger', 'obv', 'dmi', 'atr', 'psy']
    
    # 一次性计算移动平均线
    if 'ma' in indicators:
        df = calculate_ma(df, periods=[5, 10, 20, 60])
    
    # 一次性计算指数移动平均线
    if 'ema' in indicators:
        df = calculate_ema(df, periods=[12, 26])
    
    # 计算MACD（内部会计算EMA）
    if 'macd' in indicators:
        df = calculate_macd(df)
    
    # 计算RSI
    if 'rsi' in indicators:
        df = calculate_rsi(df)
    
    # 计算KDJ
    if 'kdj' in indicators:
        df = calculate_kdj(df)
    
    # 计算布林带
    if 'bollinger' in indicators:
        df = calculate_bollinger_bands(df)
    
    # 计算OBV
    if 'obv' in indicators:
        df = calculate_obv(df)
    
    # 计算DMI
    if 'dmi' in indicators:
        df = calculate_dmi(df)
    
    # 计算ATR
    if 'atr' in indicators:
        df = calculate_atr(df)
    
    # 计算PSY
    if 'psy' in indicators:
        df = calculate_psy(df)
    
    return df


def calculate_ma(df: pd.DataFrame, periods: list[int] = [5, 10, 20, 60]) -> pd.DataFrame:
    """计算移动平均线"""
    for period in periods:
        df[f"ma{period}"] = df["close"].rolling(window=period, min_periods=1).mean()
    return df


def calculate_ema(df: pd.DataFrame, periods: list[int] = [12, 26]) -> pd.DataFrame:
    """计算指数移动平均线"""
    for period in periods:
        df[f"ema{period}"] = df["close"].ewm(span=period, adjust=False, min_periods=1).mean()
    return df


def calculate_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """计算MACD指标"""
    # 如果EMA12和EMA26尚未计算，先计算
    if 'ema_fast' not in df.columns:
        df["ema_fast"] = df["close"].ewm(span=fast, adjust=False, min_periods=1).mean()
    if 'ema_slow' not in df.columns:
        df["ema_slow"] = df["close"].ewm(span=slow, adjust=False, min_periods=1).mean()
    
    df["macd"] = df["ema_fast"] - df["ema_slow"]
    df["macd_signal"] = df["macd"].ewm(span=signal, adjust=False, min_periods=1).mean()
    df["macd_hist"] = df["macd"] - df["macd_signal"]
    return df


def calculate_rsi(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """计算RSI指标"""
    if 'rsi' not in df.columns:
        delta = df["close"].diff()
        gain = delta.where(delta > 0, 0).rolling(window=period, min_periods=1).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period, min_periods=1).mean()
        rs = gain / loss
        df["rsi"] = 100 - (100 / (1 + rs))
        df["rsi"] = df["rsi"].fillna(50)
    return df


def calculate_kdj(df: pd.DataFrame, n: int = 9, m1: int = 3, m2: int = 3) -> pd.DataFrame:
    """计算KDJ随机指标"""
    if 'kdj_k' not in df.columns:
        low_list = df["low"].rolling(window=n, min_periods=1).min()
        high_list = df["high"].rolling(window=n, min_periods=1).max()
        
        rsv = (df["close"] - low_list) / (high_list - low_list + 1e-9) * 100
        rsv = rsv.fillna(50)
        
        df["kdj_k"] = rsv.ewm(com=m1 - 1, adjust=False).mean()
        df["kdj_d"] = df["kdj_k"].ewm(com=m2 - 1, adjust=False).mean()
        df["kdj_j"] = 3 * df["kdj_k"] - 2 * df["kdj_d"]
    return df


def calculate_bollinger_bands(df: pd.DataFrame, period: int = 20, std_dev: int = 2) -> pd.DataFrame:
    """计算布林带指标"""
    if 'bb_middle' not in df.columns:
        rolling = df["close"].rolling(window=period, min_periods=1)
        middle = rolling.mean()
        std = rolling.std().fillna(0)
        close = df["close"]
        
        bb_upper = middle + std_dev * std
        bb_lower = middle - std_dev * std
        
        df["bb_middle"] = middle
        df["bb_std"] = std
        df["bb_upper"] = bb_upper
        df["bb_lower"] = bb_lower
        df["bb_width"] = (bb_upper - bb_lower) / (middle + 1e-9)
        df["bb_position"] = (close - bb_lower) / (bb_upper - bb_lower + 1e-9)
    return df


def calculate_obv(df: pd.DataFrame) -> pd.DataFrame:
    """计算OBV能量潮指标"""
    if 'obv' not in df.columns:
        close_diff = df["close"].diff().fillna(0)
        sign = (close_diff > 0).astype(int) - (close_diff < 0).astype(int)
        obv = (sign * df["volume"]).cumsum()
        df["obv"] = obv
        df["obv_ma"] = obv.rolling(window=20, min_periods=1).mean()
    return df


def calculate_dmi(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """计算DMI趋向指标"""
    if 'adx' not in df.columns:
        high_diff = df["high"].diff().fillna(0)
        low_diff = (-df["low"].diff()).fillna(0)
        
        pos_dm = high_diff.where((high_diff > low_diff) & (high_diff > 0), 0)
        neg_dm = low_diff.where((low_diff > high_diff) & (low_diff > 0), 0)
        
        tr1 = df["high"] - df["low"]
        tr2 = abs(df["high"] - df["close"].shift())
        tr3 = abs(df["low"] - df["close"].shift())
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        atr = tr.rolling(window=period, min_periods=1).mean()
        atr_safe = atr.replace(0, 1)
        
        pos_di = 100 * (pos_dm.rolling(window=period, min_periods=1).mean() / atr_safe)
        neg_di = 100 * (neg_dm.rolling(window=period, min_periods=1).mean() / atr_safe)
        
        dx = 100 * abs(pos_di - neg_di) / (pos_di + neg_di).replace(0, 1)
        adx = dx.rolling(window=period, min_periods=1).mean()
        
        df["dmi_plus"] = pos_di.fillna(0)
        df["dmi_minus"] = neg_di.fillna(0)
        df["adx"] = adx.fillna(0)
    return df


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """计算ATR平均真实波幅"""
    if 'atr' not in df.columns:
        high_low = df["high"] - df["low"]
        high_close = abs(df["high"] - df["close"].shift())
        low_close = abs(df["low"] - df["close"].shift())
        
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df["atr"] = tr.rolling(window=period, min_periods=1).mean()
    return df


def calculate_psy(df: pd.DataFrame, period: int = 12) -> pd.DataFrame:
    """计算PSY心理线指标"""
    if 'psy' not in df.columns:
        df["psy"] = (df["close"] > df["close"].shift(1)).rolling(window=period, min_periods=1).sum() / period * 100
    return df


def calculate_money_flow(df: pd.DataFrame) -> pd.DataFrame:
    """计算资金流向"""
    if 'money_flow' not in df.columns:
        close_diff = df["close"].diff().fillna(0)
        inflow = close_diff.apply(lambda x: x if x > 0 else 0) * df["volume"]
        outflow = (-close_diff.apply(lambda x: x if x < 0 else 0)) * df["volume"]
        
        df["money_flow"] = df["close"] * df["volume"]
        df["money_inflow"] = inflow.rolling(window=5, min_periods=1).sum()
        df["money_outflow"] = outflow.rolling(window=5, min_periods=1).sum()
        df["net_money_flow"] = df["money_inflow"] - df["money_outflow"]
    return df


def kline_to_json_list(df: pd.DataFrame) -> list[dict]:
    """
    将K线DataFrame转换为JSON列表格式
    优化版本：减少重复代码
    """
    kline_data = []
    pd_notna = pd.notna
    
    # 字段映射：DataFrame列名 -> JSON键名 -> 默认值
    scalar_fields = {
        'open': 0, 'high': 0, 'low': 0, 'close': 0, 'volume': 0, 'pctChg': 0,
        'macd': 0, 'macd_signal': 0, 'macd_hist': 0,
        'rsi': 50, 'kdj_k': 50, 'kdj_d': 50, 'kdj_j': 50,
        'obv': 0, 'dmi_plus': 0, 'dmi_minus': 0, 'adx': 0, 'atr': 0, 'psy': 50,
        'money_inflow': 0, 'money_outflow': 0, 'net_money_flow': 0,
    }
    
    nullable_fields = {
        'ma5': None, 'ma10': None, 'ma20': None, 'ma60': None,
        'ema12': None, 'ema26': None,
        'bb_upper': None, 'bb_middle': None, 'bb_lower': None, 'bb_width': None,
        'obv_ma': None,
    }
    
    for row in df.itertuples(index=False):
        item = {"date": str(row.date)}
        
        # 标量字段
        for field, default in scalar_fields.items():
            val = getattr(row, field, None)
            item[field] = float(val) if pd_notna(val) else default
        
        # 可空字段
        for field, default in nullable_fields.items():
            val = getattr(row, field, None)
            item[field] = float(val) if pd_notna(val) else default
        
        kline_data.append(item)
    
    return kline_data
