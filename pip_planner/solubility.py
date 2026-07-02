from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from functools import lru_cache
from importlib import import_module, metadata
import io
from math import isfinite
from typing import Any


LOGS_UNIT = "predicted logS"


@dataclass(frozen=True)
class SolubilityPrediction:
    method: str
    package: str
    status: str
    value: float | None = None
    unit: str = LOGS_UNIT
    property_name: str | None = None
    version: str | None = None
    message: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "method": self.method,
            "package": self.package,
            "status": self.status,
            "value": self.value,
            "unit": self.unit,
            "property_name": self.property_name,
            "version": self.version,
            "message": self.message,
        }


@lru_cache(maxsize=256)
def predict_solubility(smiles: str) -> tuple[dict[str, object], ...]:
    """Predict aqueous solubility with each configured local package."""
    cleaned = smiles.strip()
    return tuple(
        prediction.to_dict()
        for prediction in (
            _predict_admet_ai(cleaned),
            _predict_soltrannet(cleaned),
        )
    )


def _predict_admet_ai(smiles: str) -> SolubilityPrediction:
    method = "ADMET-AI v2"
    package = "admet-ai"
    if not smiles:
        return _error(method, package, "SMILES is required.")

    try:
        return _quiet_call(lambda: _predict_admet_ai_raw(smiles))
    except ModuleNotFoundError as exc:
        if exc.name == "admet_ai":
            return _unavailable(method, package, "Install with `pip install admet-ai`.")
        return _error(method, package, f"Import failed for dependency `{exc.name}`.")
    except ImportError as exc:
        return _error(method, package, f"Import failed: {exc}.")
    except Exception as exc:
        return _error(method, package, str(exc) or exc.__class__.__name__)


def _predict_admet_ai_raw(smiles: str) -> SolubilityPrediction:
    module = import_module("admet_ai")
    model = _load_admet_ai_model()
    prediction = model.predict(smiles=smiles)
    property_name, value = _find_solubility_value(prediction)
    if value is None:
        available = ", ".join(_prediction_keys(prediction)[:8]) or "none"
        raise ValueError(f"No solubility-like numeric output found. Available properties: {available}.")

    return SolubilityPrediction(
        method="ADMET-AI v2",
        package="admet-ai",
        status="ok",
        value=value,
        property_name=property_name,
        version=_package_version("admet-ai", fallback_module=module),
    )


@lru_cache(maxsize=1)
def _load_admet_ai_model() -> Any:
    module = import_module("admet_ai")
    return module.ADMETModel()


def _predict_soltrannet(smiles: str) -> SolubilityPrediction:
    method = "SolTranNet"
    package = "soltrannet"
    if not smiles:
        return _error(method, package, "SMILES is required.")

    try:
        return _quiet_call(lambda: _predict_soltrannet_raw(smiles))
    except ModuleNotFoundError as exc:
        if exc.name == "soltrannet":
            return _unavailable(method, package, "Install with `pip install soltrannet`.")
        return _error(method, package, f"Import failed for dependency `{exc.name}`.")
    except ImportError as exc:
        return _error(method, package, f"Import failed: {exc}.")
    except Exception as exc:
        return _error(method, package, str(exc) or exc.__class__.__name__)


def _predict_soltrannet_raw(smiles: str) -> SolubilityPrediction:
    module = import_module("soltrannet")
    predictions = list(module.predict([smiles]))
    if not predictions:
        raise ValueError("SolTranNet did not return a prediction.")

    property_name, value = _find_solubility_value(predictions[0])
    if value is None:
        raise ValueError("SolTranNet returned a non-numeric prediction.")

    return SolubilityPrediction(
        method="SolTranNet",
        package="soltrannet",
        status="ok",
        value=value,
        property_name=property_name or "SolTranNet",
        version=_package_version("soltrannet", fallback_module=module),
    )


def _find_solubility_value(prediction: Any) -> tuple[str | None, float | None]:
    items = list(_prediction_items(prediction))
    if not items:
        return None, _coerce_float(prediction)

    preferred_keys = {"solubilityaqsoldb", "solubilityaqsoldatabase", "aqsoldb"}
    for key, value in items:
        if _normalized_key(key) in preferred_keys:
            number = _coerce_float(value)
            if number is not None:
                return str(key), number

    for key, value in items:
        normalized = _normalized_key(key)
        if "solub" in normalized or "aqsol" in normalized:
            number = _coerce_float(value)
            if number is not None:
                return str(key), number

    if len(items) == 1:
        key, value = items[0]
        return str(key), _coerce_float(value)

    return None, None


def _prediction_items(prediction: Any) -> list[tuple[Any, Any]]:
    if hasattr(prediction, "to_dict"):
        prediction = prediction.to_dict()

    if hasattr(prediction, "items"):
        return list(prediction.items())

    if isinstance(prediction, (list, tuple)):
        return list(enumerate(prediction))

    return []


def _prediction_keys(prediction: Any) -> list[str]:
    return [str(key) for key, _value in _prediction_items(prediction)]


def _coerce_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def _normalized_key(value: Any) -> str:
    return "".join(character for character in str(value).lower() if character.isalnum())


def _quiet_call(callback: Any) -> Any:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        return callback()


def _package_version(distribution_name: str, fallback_module: Any | None = None) -> str | None:
    try:
        return metadata.version(distribution_name)
    except metadata.PackageNotFoundError:
        return getattr(fallback_module, "__version__", None)


def _unavailable(method: str, package: str, message: str) -> SolubilityPrediction:
    return SolubilityPrediction(method=method, package=package, status="unavailable", message=message)


def _error(method: str, package: str, message: str) -> SolubilityPrediction:
    return SolubilityPrediction(method=method, package=package, status="error", message=message)
