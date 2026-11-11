"""Guest request API. Possession of a per-analysis bearer token grants read access."""

import hashlib
import secrets
from collections.abc import Callable
from uuid import UUID

from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis import Redis
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from .collection import CollectionError, validate_public_url
from .config import Settings, configure_logging, get_settings
from .database import make_engine, session_factory
from .repository import accept_supplement, create_analysis, get_analysis
from .schemas import AnalysisAccepted, AnalysisInput, AnalysisResult, SupplementalInput


def dispatch_analysis(analysis_id: str) -> None:
    from .tasks import process_analysis

    process_analysis.delay(analysis_id)


def create_app(
    settings: Settings | None = None,
    *,
    engine: Engine | None = None,
    dispatch: Callable[[str], None] | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging()
    application = FastAPI(title="건강기능식품 수집 보고서", version="0.1.0")
    sessions = session_factory(engine or make_engine(settings.database_url))
    publish = dispatch or dispatch_analysis
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Analysis-Token"],
    )

    @application.middleware("http")
    async def private_response(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @application.exception_handler(RequestValidationError)
    async def invalid_input(request: Request, exc: RequestValidationError):
        # Pydantic errors include the original input; do not echo URL queries.
        return JSONResponse(
            status_code=422, content={"detail": "입력 URL과 제품명을 확인해 주세요."}
        )

    @application.exception_handler(SQLAlchemyError)
    async def unavailable_database(request: Request, exc: SQLAlchemyError):
        return JSONResponse(status_code=503, content={"detail": "저장소에 연결할 수 없습니다."})

    @application.get("/api/health")
    def health():
        return {"status": "ok", "scope": "collection_only"}

    @application.get("/api/ready")
    def ready(response: Response):
        database_ok = broker_ok = False
        try:
            with sessions() as session:
                session.execute(text("SELECT 1 FROM analyses LIMIT 1"))
            database_ok = True
        except SQLAlchemyError:
            pass
        try:
            with Redis.from_url(
                settings.redis_url, socket_connect_timeout=2, socket_timeout=2
            ) as broker:
                broker_ok = bool(broker.ping())
        except Exception:
            pass
        if not (database_ok and broker_ok):
            response.status_code = 503
        return {"database": database_ok, "broker": broker_ok}

    @application.get("/api/capabilities")
    def capabilities():
        return {
            "scope": "collection_only",
            "openai": "configured_unverified" if settings.openai_api_key else "not_configured",
            "food_safety": (
                "configured_unverified" if settings.food_safety_api_key else "not_configured"
            ),
            "tavily": "configured_unverified" if settings.tavily_api_key else "not_configured",
            "research": "configured_unverified" if settings.openai_api_key and settings.tavily_api_key else "not_configured",
            "clerk": "deferred_m3",
            "langsmith": "deferred_m4",
            "personal_suitability": "not_evaluated",
        }

    @application.post("/api/analyses", response_model=AnalysisAccepted, status_code=202)
    async def submit(payload: AnalysisInput):
        try:
            await validate_public_url(payload.url)
        except CollectionError as exc:
            raise HTTPException(status_code=422, detail=exc.message) from None
        access_token = secrets.token_urlsafe(32)
        def save_request() -> str:
            with sessions() as session:
                analysis = create_analysis(
                    session,
                    url=payload.url,
                    product_name=payload.product_name or None,
                    token_hash=hashlib.sha256(access_token.encode()).hexdigest(),
                    mode=payload.mode,
                )
                session.commit()
                return analysis.id

        analysis_id = await run_in_threadpool(save_request)
        try:
            await run_in_threadpool(publish, analysis_id)
        except Exception:
            # The committed queued row is the recovery source. Beat retries it.
            pass
        return {"id": analysis_id, "access_token": access_token, "status": "queued", "mode": payload.mode}

    @application.get("/api/analyses/{analysis_id}", response_model=AnalysisResult)
    def read(analysis_id: str, x_analysis_token: str | None = Header(default=None)):
        if x_analysis_token is not None and len(x_analysis_token) > 256:
            raise HTTPException(status_code=404, detail="결과를 찾을 수 없습니다.")
        try:
            UUID(analysis_id)
        except ValueError:
            raise HTTPException(status_code=404, detail="결과를 찾을 수 없습니다.") from None
        digest = hashlib.sha256((x_analysis_token or "").encode()).hexdigest()
        with sessions() as session:
            analysis = get_analysis(session, analysis_id)
            if analysis is None or not secrets.compare_digest(analysis.token_hash, digest):
                raise HTTPException(status_code=404, detail="결과를 찾을 수 없습니다.")
            report = analysis.report
            return AnalysisResult(
                id=analysis.id,
                status=analysis.status,
                mode=analysis.mode,
                product_name=analysis.product_name,
                report=report,
                error_code=analysis.error_code,
                message=analysis.message,
                missing_fields=report.get("missing_fields", []) if report else [],
                supplemental_input_used=analysis.supplemental_input is not None,
                can_supplement=(
                    analysis.status == "needs_input" and analysis.supplemental_input is None
                ),
                created_at=analysis.created_at,
                updated_at=analysis.updated_at,
            )

    @application.post("/api/analyses/{analysis_id}/supplement", status_code=202)
    def supplement(
        analysis_id: str,
        payload: SupplementalInput,
        x_analysis_token: str | None = Header(default=None),
    ):
        if x_analysis_token is not None and len(x_analysis_token) > 256:
            raise HTTPException(status_code=404, detail="결과를 찾을 수 없습니다.")
        try:
            UUID(analysis_id)
        except ValueError:
            raise HTTPException(status_code=404, detail="결과를 찾을 수 없습니다.") from None
        digest = hashlib.sha256((x_analysis_token or "").encode()).hexdigest()
        accepted_payload = payload.model_dump()
        with sessions() as session:
            accepted = accept_supplement(session, analysis_id, digest, accepted_payload)
            if accepted:
                session.commit()
            else:
                analysis = get_analysis(session, analysis_id)
                if analysis is None or not secrets.compare_digest(analysis.token_hash, digest):
                    raise HTTPException(status_code=404, detail="결과를 찾을 수 없습니다.")
                raise HTTPException(status_code=409, detail="추가 정보를 받을 수 없는 상태입니다.")
        try:
            publish(analysis_id)
        except Exception:
            # The committed queued row is recovered by the existing beat scan.
            pass
        return {"id": analysis_id, "status": "queued"}

    return application


app = create_app()
