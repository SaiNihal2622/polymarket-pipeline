"""
ML price prediction module — uses historical price patterns + market features
to predict price direction. Lightweight online learning approach.

Uses feature engineering from existing pipeline signals:
- Price momentum (1h, 4h, 24h changes)
- Volume patterns
- Orderbook imbalance
- Sentiment scores
- Time-to-resolution

Industry standard: ensemble of simple models beats single complex model.
"""
from __future__ import annotations

import json
import logging
import math
import time
from dataclasses import dataclass
from pathlib import Path

import config

log = logging.getLogger(__name__)


@dataclass
class MarketFeatures:
    """Feature vector for ML prediction."""
    # Price features
    price_1h_change: float = 0.0
    price_4h_change: float = 0.0
    price_24h_change: float = 0.0
    volatility_1h: float = 0.0
    volatility_24h: float = 0.0
    # Orderbook features
    bid_ask_imbalance: float = 0.0  # (bid_vol - ask_vol) / (bid_vol + ask_vol)
    spread: float = 0.0
    # Market features
    current_price: float = 0.5
    volume_24h: float = 0.0
    liquidity: float = 0.0
    hours_to_resolution: float = 168.0
    # Signal features
    sentiment_score: float = 0.0
    ai_confidence: float = 0.0
    materiality: float = 0.0
    news_count: int = 0
    # Meta
    category_encoded: int = 0  # Hash of category
    day_of_week: int = 0
    hour_of_day: int = 0


@dataclass
class Prediction:
    """ML prediction output."""
    direction: str  # "YES", "NO", "NEUTRAL"
    confidence: float  # 0.0 to 1.0
    predicted_price: float  # Where we think price is heading
    edge_estimate: float  # Estimated edge over market price
    features_used: int
    model_version: str = "v1.0"


class OnlinePredictor:
    """
    Lightweight online predictor using logistic regression-style scoring.
    Learns from resolved trades to adjust feature weights.
    
    No heavy ML dependencies — uses simple weighted scoring with 
    sigmoid calibration. Runs on the pipeline thread.
    """

    def __init__(self, model_path: str | None = None):
        self.model_path = model_path or str(config.PROJECT_ROOT / "ml_model.json")
        # Feature weights (initialized with domain knowledge)
        self.weights: dict[str, float] = {
            "price_1h_change": 0.15,
            "price_4h_change": 0.10,
            "price_24h_change": 0.08,
            "volatility_1h": -0.05,
            "volatility_24h": -0.03,
            "bid_ask_imbalance": 0.12,
            "spread": -0.08,
            "volume_log": 0.05,
            "liquidity_log": 0.04,
            "time_decay": 0.10,
            "sentiment_score": 0.12,
            "ai_confidence": 0.20,
            "materiality": 0.15,
            "news_count_log": 0.06,
        }
        self.bias: float = 0.0
        self.accuracy_history: list[float] = []
        self.total_predictions: int = 0
        self.correct_predictions: int = 0
        self._load_model()

    def _sigmoid(self, x: float) -> float:
        """Sigmoid activation."""
        return 1.0 / (1.0 + math.exp(-max(-10, min(10, x))))

    def _load_model(self):
        """Load model weights from disk."""
        try:
            path = Path(self.model_path)
            if path.exists():
                with open(path) as f:
                    data = json.load(f)
                self.weights.update(data.get("weights", {}))
                self.bias = data.get("bias", 0.0)
                self.total_predictions = data.get("total_predictions", 0)
                self.correct_predictions = data.get("correct_predictions", 0)
                log.info(f"[ml] Loaded model: {self.total_predictions} predictions, "
                         f"{self.correct_predictions/self.total_predictions*100:.1f}% accuracy"
                         if self.total_predictions > 0 else "[ml] Loaded fresh model")
        except Exception as e:
            log.debug(f"[ml] Model load failed: {e}")

    def save_model(self):
        """Save model weights to disk."""
        try:
            data = {
                "weights": self.weights,
                "bias": self.bias,
                "total_predictions": self.total_predictions,
                "correct_predictions": self.correct_predictions,
                "accuracy": self.correct_predictions / self.total_predictions if self.total_predictions > 0 else 0,
                "saved_at": time.time(),
            }
            with open(self.model_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            log.debug(f"[ml] Model save failed: {e}")

    def extract_features(
        self,
        current_price: float,
        sentiment_score: float = 0.0,
        ai_confidence: float = 0.0,
        materiality: float = 0.0,
        news_count: int = 0,
        volatility_1h: float = 0.0,
        volatility_24h: float = 0.0,
        price_1h_change: float = 0.0,
        price_4h_change: float = 0.0,
        price_24h_change: float = 0.0,
        bid_ask_imbalance: float = 0.0,
        spread: float = 0.0,
        volume_24h: float = 0.0,
        liquidity: float = 0.0,
        hours_to_resolution: float = 168.0,
    ) -> dict[str, float]:
        """Extract normalized feature vector."""
        return {
            "price_1h_change": max(-1, min(1, price_1h_change)),
            "price_4h_change": max(-1, min(1, price_4h_change)),
            "price_24h_change": max(-1, min(1, price_24h_change)),
            "volatility_1h": min(1, volatility_1h),
            "volatility_24h": min(1, volatility_24h),
            "bid_ask_imbalance": max(-1, min(1, bid_ask_imbalance)),
            "spread": min(1, spread),
            "volume_log": min(1, math.log1p(volume_24h) / 15),
            "liquidity_log": min(1, math.log1p(liquidity) / 12),
            "time_decay": max(0, 1 - hours_to_resolution / 168),  # Closer = more urgent
            "sentiment_score": max(-1, min(1, sentiment_score)),
            "ai_confidence": max(0, min(1, ai_confidence)),
            "materiality": max(0, min(1, materiality)),
            "news_count_log": min(1, math.log1p(news_count) / 5),
        }

    def predict(self, features: dict[str, float]) -> Prediction:
        """Make a prediction from features."""
        # Weighted sum
        z = self.bias
        for name, value in features.items():
            weight = self.weights.get(name, 0)
            z += weight * value

        # Sigmoid to get probability
        prob_yes = self._sigmoid(z)

        # Direction
        if prob_yes > 0.6:
            direction = "YES"
        elif prob_yes < 0.4:
            direction = "NO"
        else:
            direction = "NEUTRAL"

        # Confidence: distance from 0.5
        confidence = abs(prob_yes - 0.5) * 2  # 0 to 1

        # Edge estimate: how much we think market is mispriced
        edge_estimate = abs(prob_yes - 0.5) - 0.08  # Min 8% edge to be meaningful

        self.total_predictions += 1

        return Prediction(
            direction=direction,
            confidence=confidence,
            predicted_price=prob_yes,
            edge_estimate=max(0, edge_estimate),
            features_used=len(features),
        )

    def update_from_outcome(self, features: dict[str, float], predicted_direction: str, actual_outcome: str, learning_rate: float = 0.01):
        """
        Online learning update from trade outcome.
        Adjusts weights based on prediction error.
        """
        correct = predicted_direction == actual_outcome
        if correct:
            self.correct_predictions += 1

        # Gradient update
        actual_prob = 1.0 if actual_outcome == "YES" else 0.0
        z = self.bias + sum(self.weights.get(name, 0) * value for name, value in features.items())
        predicted_prob = self._sigmoid(z)
        error = actual_prob - predicted_prob

        # Update weights
        for name, value in features.items():
            if name in self.weights:
                self.weights[name] += learning_rate * error * value
        self.bias += learning_rate * error

        # Save periodically
        if self.total_predictions % 10 == 0:
            self.save_model()

        log.debug(f"[ml] Updated weights. {'CORRECT' if correct else 'WRONG'}. "
                  f"Accuracy: {self.correct_predictions/max(1,self.total_predictions)*100:.1f}%")

    def get_accuracy(self) -> float:
        """Get current prediction accuracy."""
        if self.total_predictions == 0:
            return 0.0
        return self.correct_predictions / self.total_predictions


# Singleton
_predictor = OnlinePredictor()


def predict(
    current_price: float,
    sentiment_score: float = 0.0,
    ai_confidence: float = 0.0,
    materiality: float = 0.0,
    news_count: int = 0,
    volatility_1h: float = 0.0,
    volatility_24h: float = 0.0,
    price_1h_change: float = 0.0,
    price_4h_change: float = 0.0,
    price_24h_change: float = 0.0,
    bid_ask_imbalance: float = 0.0,
    spread: float = 0.0,
    volume_24h: float = 0.0,
    liquidity: float = 0.0,
    hours_to_resolution: float = 168.0,
) -> Prediction:
    """Module-level: make ML prediction."""
    features = _predictor.extract_features(
        current_price=current_price,
        sentiment_score=sentiment_score,
        ai_confidence=ai_confidence,
        materiality=materiality,
        news_count=news_count,
        volatility_1h=volatility_1h,
        volatility_24h=volatility_24h,
        price_1h_change=price_1h_change,
        price_4h_change=price_4h_change,
        price_24h_change=price_24h_change,
        bid_ask_imbalance=bid_ask_imbalance,
        spread=spread,
        volume_24h=volume_24h,
        liquidity=liquidity,
        hours_to_resolution=hours_to_resolution,
    )
    return _predictor.predict(features)


def update_from_outcome(features: dict[str, float], predicted_direction: str, actual_outcome: str):
    """Module-level: update model from trade outcome."""
    _predictor.update_from_outcome(features, predicted_direction, actual_outcome)


def get_accuracy() -> float:
    """Module-level: get current model accuracy."""
    return _predictor.get_accuracy()


def get_ml_boost(prediction: Prediction) -> float:
    """
    Return a score boost (0.0 to 0.10) based on ML prediction confidence.
    """
    if prediction.direction == "NEUTRAL":
        return 0.0
    if prediction.edge_estimate < 0.02:
        return 0.0
    return min(0.10, prediction.confidence * 0.10)