import warnings
import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Optional
from sklearn.preprocessing import StandardScaler
from xgboost import XGBRegressor
from src.logger import get_logger

logger = get_logger(__name__)

# Prophet/Stan 관련 불필요한 경고를 억제한다
warnings.filterwarnings("ignore", category=FutureWarning, module="prophet")
warnings.filterwarnings("ignore", category=FutureWarning, module="pystan")
warnings.filterwarnings("ignore", category=UserWarning, module="prophet")
warnings.filterwarnings("ignore", message=".*cmdstanpy.*")
warnings.filterwarnings("ignore", message=".*Stan.*")
warnings.filterwarnings("ignore", message=".*Importing plotly failed.*")


# -- 예측 결과 dataclass ------------------------------------------------------

@dataclass
class PredictionResult:
    period: str
    method: str
    predicted_price: float = 0.0
    predicted_return: float = 0.0
    lower: float = 0.0
    upper: float = 0.0
    total_return: Optional[float] = None
    error: Optional[str] = None

    def ok(self) -> bool:
        """예측이 성공적으로 완료됐는지 반환한다."""
        return self.error is None


# -- 공통 유틸 -----------------------------------------------------------------

def _rsi(series, period=14):
    delta = series.diff(1)
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def _build_features(df):
    """종가 기반 기술적 지표 특성 행렬을 구성한다."""
    d = df[["Close"]].copy()
    d["rsi"] = _rsi(d["Close"])
    d["ma20"] = d["Close"].rolling(20).mean()
    d["ma60"] = d["Close"].rolling(60).mean()
    d["ma200"] = d["Close"].rolling(200).mean()
    d["ma_ratio_20_60"] = d["ma20"] / d["ma60"]
    d["ma_ratio_close_200"] = d["Close"] / d["ma200"]
    d["return_5d"] = d["Close"].pct_change(5)
    d["return_20d"] = d["Close"].pct_change(20)
    d["vol_20d"] = d["Close"].pct_change().rolling(20).std()
    return d.dropna()


# -- 단기 예측 (1개월): XGBoost -----------------------------------------------

def _predict_short_term(df, target_days=21) -> PredictionResult:
    """
    XGBoost Quantile Regression으로 target_days 후 수익률을 예측한다.

    10th / 50th / 90th percentile 세 모델을 독립 학습해 80% 예측 구간을 구성한다.
    각 모델이 독립적이므로 역전이 발생할 수 있어, 단조성 보정(lower <= mid <= upper)을
    예측 후 강제 적용한다.
    """
    feat_df = _build_features(df)
    feature_cols = [
        "rsi", "ma_ratio_20_60", "ma_ratio_close_200",
        "return_5d", "return_20d", "vol_20d",
    ]

    feat_df["target"] = feat_df["Close"].shift(-target_days) / feat_df["Close"] - 1
    train = feat_df.dropna(subset=["target"])

    X = train[feature_cols].values
    y = train["target"].values

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    base_params = dict(
        n_estimators=300,
        max_depth=4,
        learning_rate=0.03,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=5,
        random_state=42,
        verbosity=0,
    )

    model_mid  = XGBRegressor(objective="reg:quantileerror", quantile_alpha=0.5, **base_params)
    model_low  = XGBRegressor(objective="reg:quantileerror", quantile_alpha=0.1, **base_params)
    model_high = XGBRegressor(objective="reg:quantileerror", quantile_alpha=0.9, **base_params)
    model_mid.fit(X_scaled, y)
    model_low.fit(X_scaled, y)
    model_high.fit(X_scaled, y)

    X_pred = scaler.transform(feat_df[feature_cols].iloc[[-1]].values)
    pred_return  = float(model_mid.predict(X_pred)[0])
    lower_return = float(model_low.predict(X_pred)[0])
    upper_return = float(model_high.predict(X_pred)[0])

    # 독립 학습된 세 모델의 예측값이 역전되는 경우를 단조성 보정으로 수정한다
    lower_return = min(lower_return, pred_return)
    upper_return = max(upper_return, pred_return)
    if lower_return > upper_return:
        lower_return, upper_return = upper_return, lower_return

    current_price = float(df["Close"].iloc[-1])

    return PredictionResult(
        period="1개월",
        method="XGBoost + 기술적 지표",
        predicted_price=current_price * (1 + pred_return),
        predicted_return=pred_return,
        lower=current_price * (1 + lower_return),
        upper=current_price * (1 + upper_return),
    )


# -- 중장기 예측 (3 / 6 / 12개월): Prophet -----------------------------------

def _predict_prophet(df, periods_days, label) -> PredictionResult:
    """
    Prophet으로 periods_days 후 가격을 예측한다.

    weekly_seasonality와 yearly_seasonality를 활성화해 주간/연간 주기를 반영하고,
    changepoint_prior_scale=0.05로 보수적인 추세 변화를 가정한다.
    interval_width=0.80으로 80% 신뢰 구간을 제공한다.
    """
    from prophet import Prophet

    prophet_df = df[["Close"]].reset_index()
    prophet_df.columns = ["ds", "y"]
    # Prophet은 tz-naive DatetimeIndex를 요구한다
    prophet_df["ds"] = pd.to_datetime(prophet_df["ds"]).dt.tz_localize(None)

    model = Prophet(
        daily_seasonality=False,
        weekly_seasonality=True,
        yearly_seasonality=True,
        changepoint_prior_scale=0.05,
        seasonality_prior_scale=10.0,
        interval_width=0.80,
    )
    model.fit(prophet_df, iter=300)

    future   = model.make_future_dataframe(periods=periods_days)
    forecast = model.predict(future)
    last     = forecast.iloc[-1]

    current_price = float(df["Close"].iloc[-1])
    pred_price    = float(last["yhat"])
    pred_return   = (pred_price - current_price) / current_price

    return PredictionResult(
        period=label,
        method="Prophet (트렌드 + 계절성)",
        predicted_price=pred_price,
        predicted_return=pred_return,
        lower=float(last["yhat_lower"]),
        upper=float(last["yhat_upper"]),
    )


# -- 배당 포함 총수익률 추정 --------------------------------------------------

def _estimate_total_return(pred_return, div_yield, years):
    """예측 가격 수익률에 배당 수익률 기여분을 합산해 총수익률을 추정한다."""
    return pred_return + div_yield * years


# -- 퍼블릭 API ---------------------------------------------------------------

def predict_ticker(ticker, df, div_yield=0.0) -> dict:
    """
    종목의 단기/중기/장기 가격을 예측하고 dict[str, PredictionResult]를 반환한다.

    Parameters
    ----------
    ticker   : 종목 티커 (로깅용)
    df       : OHLCV DataFrame (최소 1년, 3년 이상 권장)
    div_yield: 연간 배당률 소수 형태 (예: 0.03 = 3%)
    """
    results = {}

    try:
        results["1m"] = _predict_short_term(df, target_days=21)
    except Exception as e:
        logger.error(f"[{ticker}] 1개월 예측 실패: {e}")
        results["1m"] = PredictionResult(period="1개월", method="XGBoost + 기술적 지표", error=str(e))

    try:
        results["3m"] = _predict_prophet(df, 90, "3개월")
    except Exception as e:
        logger.error(f"[{ticker}] 3개월 예측 실패: {e}")
        results["3m"] = PredictionResult(period="3개월", method="Prophet (트렌드 + 계절성)", error=str(e))

    try:
        results["6m"] = _predict_prophet(df, 180, "6개월")
    except Exception as e:
        logger.error(f"[{ticker}] 6개월 예측 실패: {e}")
        results["6m"] = PredictionResult(period="6개월", method="Prophet (트렌드 + 계절성)", error=str(e))

    try:
        pred_12m = _predict_prophet(df, 365, "12개월")
        pred_12m.total_return = _estimate_total_return(
            pred_12m.predicted_return, div_yield, years=1.0
        )
        results["12m"] = pred_12m
    except Exception as e:
        logger.error(f"[{ticker}] 12개월 예측 실패: {e}")
        results["12m"] = PredictionResult(period="12개월", method="Prophet (트렌드 + 계절성)", error=str(e))

    return results
