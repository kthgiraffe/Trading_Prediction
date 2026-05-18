import warnings
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from xgboost import XGBRegressor

# [개선] Prophet/Stan/cmdstanpy 관련 경고만 선택적으로 억제
#        그 외 경고(데이터 부족, 수렴 실패 등)는 정상 출력됨
warnings.filterwarnings("ignore", category=FutureWarning, module="prophet")
warnings.filterwarnings("ignore", category=FutureWarning, module="pystan")
warnings.filterwarnings("ignore", category=UserWarning, module="prophet")
warnings.filterwarnings("ignore", message=".*cmdstanpy.*")
warnings.filterwarnings("ignore", message=".*Stan.*")
warnings.filterwarnings("ignore", message=".*Importing plotly failed.*")


# ── 공통 유틸 ──────────────────────────────────────────────

def _rsi(series, period=14):
    delta = series.diff(1)
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def _build_features(df):
    """기술적 지표 기반 특성 행렬을 만든다."""
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


# ── 단기 예측 (1개월) : XGBoost + 기술적 지표 ───────────────

def _predict_short_term(df, target_days=21):
    """
    XGBoost로 target_days 이후 수익률을 예측한다.
    - 중앙값(50%), 하한(10%), 상한(90%) 세 모델로 80% 예측 구간을 구성
    - 선형회귀와 달리 지표 간 조합 패턴(RSI 고점 + MA 하락 등)을 학습
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

    # 공통 하이퍼파라미터 (과적합 방지 설정)
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

    # 중앙값 예측 (50th percentile)
    model_mid = XGBRegressor(objective="reg:quantileerror", quantile_alpha=0.5, **base_params)
    model_mid.fit(X_scaled, y)

    # 하한 예측 (10th percentile → 80% 구간 하단)
    model_low = XGBRegressor(objective="reg:quantileerror", quantile_alpha=0.1, **base_params)
    model_low.fit(X_scaled, y)

    # 상한 예측 (90th percentile → 80% 구간 상단)
    model_high = XGBRegressor(objective="reg:quantileerror", quantile_alpha=0.9, **base_params)
    model_high.fit(X_scaled, y)

    X_pred = scaler.transform(feat_df[feature_cols].iloc[[-1]].values)
    pred_return = float(model_mid.predict(X_pred)[0])
    lower_return = float(model_low.predict(X_pred)[0])
    upper_return = float(model_high.predict(X_pred)[0])

    # [수정] 단조성 보정 — 세 모델을 독립 학습하면 역전이 발생할 수 있으므로 강제 정렬
    # 예측가(중앙값)가 반드시 lower ~ upper 범위 내에 있도록 보장
    lower_return = min(lower_return, pred_return)
    upper_return = max(upper_return, pred_return)
    if lower_return > upper_return:
        lower_return, upper_return = upper_return, lower_return

    current_price = float(df["Close"].iloc[-1])

    return {
        "period": "1개월",
        "days": target_days,
        "predicted_price": current_price * (1 + pred_return),
        "predicted_return": pred_return,
        "lower": current_price * (1 + lower_return),
        "upper": current_price * (1 + upper_return),
        "method": "XGBoost + 기술적 지표",
    }


# ── 중·장기 예측 (3 / 6 / 12개월) : Prophet ─────────────────

def _predict_prophet(df, periods_days, label):
    """
    Prophet으로 periods_days 이후 가격을 예측한다.
    - weekly_seasonality : 주 5일 장세 패턴 반영
    - yearly_seasonality : 연간 계절성 반영
    - changepoint_prior_scale=0.05 : 안정형 포트폴리오에 적합한 보수적 변화점
    - interval_width=0.80 : 80% 신뢰 구간
    """
    from prophet import Prophet

    prophet_df = df[["Close"]].reset_index()
    prophet_df.columns = ["ds", "y"]
    # tz-naive 변환 (Prophet 요구사항)
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

    future = model.make_future_dataframe(periods=periods_days)
    forecast = model.predict(future)
    last = forecast.iloc[-1]

    current_price = float(df["Close"].iloc[-1])
    pred_price = float(last["yhat"])
    pred_return = (pred_price - current_price) / current_price

    return {
        "period": label,
        "days": periods_days,
        "predicted_price": pred_price,
        "predicted_return": pred_return,
        "lower": float(last["yhat_lower"]),
        "upper": float(last["yhat_upper"]),
        "method": "Prophet (트렌드 + 계절성)",
    }


# ── 배당 포함 총수익률 추정 ────────────────────────────────────

def _estimate_total_return(pred_return, div_yield, years):
    """예측 가격 상승분 + 배당 수익률 합산으로 총수익률 추정."""
    dividend_contribution = div_yield * years
    return pred_return + dividend_contribution


# ── 퍼블릭 API ────────────────────────────────────────────────

def predict_ticker(ticker, df, div_yield=0.0):
    """
    종목의 단기/중기/장기 가격을 예측하고 결과 딕셔너리를 반환한다.

    Parameters
    ----------
    ticker   : 종목 티커 (로깅용)
    df       : OHLCV DataFrame (최소 1년 이상 권장, 3년 이상 최적)
    div_yield: 연간 배당률 (소수, 예: 0.03 = 3%)

    Returns
    -------
    dict : 1개월~12개월 예측 결과
    """
    results = {}

    # 1개월 — XGBoost
    try:
        results["1m"] = _predict_short_term(df, target_days=21)
    except Exception as e:
        results["1m"] = {"error": str(e), "period": "1개월"}

    # 3개월 — Prophet
    try:
        results["3m"] = _predict_prophet(df, 90, "3개월")
    except Exception as e:
        results["3m"] = {"error": str(e), "period": "3개월"}

    # 6개월 — Prophet
    try:
        results["6m"] = _predict_prophet(df, 180, "6개월")
    except Exception as e:
        results["6m"] = {"error": str(e), "period": "6개월"}

    # 12개월 — Prophet + 배당 포함 총수익률
    try:
        pred_12m = _predict_prophet(df, 365, "12개월")
        pred_12m["total_return"] = _estimate_total_return(
            pred_12m["predicted_return"], div_yield, years=1.0
        )
        results["12m"] = pred_12m
    except Exception as e:
        results["12m"] = {"error": str(e), "period": "12개월"}

    return results
