from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from app import __version__
from app.api.routes import router
from app.config import get_settings
from app.contracts.effectiveness import PolicyEffectivenessReport
from app.contracts.evaluation import EvaluationReport
from app.contracts.mirofish import MiroFishPack
from app.contracts.policy import PolicyDocument, PolicyIR
from app.contracts.run import AudienceSegment, RunRecord, SeedSpec
from app.contracts.scenario import ScenarioSuite


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Policy rehearsal engine",
        version=__version__,
        description=(
            "Policy PDF → PolicyIR → Person 3 fuzz (≤50 agents) + optional MiroFish swarm "
            "→ EvaluationReport + PolicyEffectivenessReport (0–100)."
        ),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router, prefix="/v1")

    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "service": "policy-engine",
            "version": __version__,
            "llm": settings.use_llm,
            "mirofish": bool(settings.mirofish_base_url),
            "max_swarm_agents": settings.max_swarm_agents,
        }

    @app.get("/v1/contracts")
    def contracts():
        """JSON Schema handoff for the frontend and other roles."""
        return {
            "PolicyDocument": PolicyDocument.model_json_schema(),
            "PolicyIR": PolicyIR.model_json_schema(),
            "SeedSpec": SeedSpec.model_json_schema(),
            "AudienceSegment": AudienceSegment.model_json_schema(),
            "ScenarioSuite": ScenarioSuite.model_json_schema(),
            "RunRecord": RunRecord.model_json_schema(),
            "EvaluationReport": EvaluationReport.model_json_schema(),
            "PolicyEffectivenessReport": PolicyEffectivenessReport.model_json_schema(),
            "MiroFishPack": MiroFishPack.model_json_schema(),
        }

    @app.get("/download/api-docs.zip")
    def download_api_docs():
        """Zip of engine/docs — send this file to the frontend developer."""
        import io
        import zipfile
        from pathlib import Path

        docs_dir = Path(__file__).resolve().parent.parent / "docs"
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(docs_dir.iterdir()):
                if path.is_file() and path.suffix != ".zip" and path.name != ".DS_Store":
                    archive.write(path, arcname=path.name)
        buffer.seek(0)
        return StreamingResponse(
            buffer,
            media_type="application/zip",
            headers={
                "Content-Disposition": 'attachment; filename="policy-engine-api-docs.zip"'
            },
        )

    return app


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
