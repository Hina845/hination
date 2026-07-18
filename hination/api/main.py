from __future__ import annotations

import os
import uuid
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from api.forecast_service import ForecastDataError, ForecastStore


ROOT = Path(__file__).resolve().parents[1]
PREDICTIONS = Path(os.getenv("HINATION_PREDICTIONS_DIR", ROOT / "data" / "predictions"))
store = ForecastStore(PREDICTIONS / "hourly_forecast.json", PREDICTIONS / "disaster_forecast.json")
app = FastAPI(title="HINATION Forecast API", version="1.0.0")


@app.exception_handler(ForecastDataError)
async def forecast_error_handler(request: Request, exc: ForecastDataError) -> JSONResponse:
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    return JSONResponse(
        status_code=503,
        content={"error": {"code": exc.code, "message": exc.message, "details": exc.details, "requestId": request_id}},
        headers={"Cache-Control": "no-store", "X-Request-Id": request_id},
    )


@app.middleware("http")
async def request_context(request: Request, call_next):
    request.state.request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
    response = await call_next(request)
    response.headers["X-Request-Id"] = request.state.request_id
    return response


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/forecasts/latest")
def latest_forecast(request: Request) -> Response:
    snapshot = store.latest()
    headers = {
        "ETag": snapshot.etag,
        "Cache-Control": "private, max-age=60, stale-while-revalidate=300",
        "Vary": "If-None-Match",
    }
    if request.headers.get("If-None-Match") == snapshot.etag:
        return Response(status_code=304, headers=headers)
    return JSONResponse(snapshot.payload, headers=headers)
