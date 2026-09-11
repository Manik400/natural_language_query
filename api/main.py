from fastapi import FastAPI

from api.handlers import register_exception_handlers
from api.routers import artifacts, debug, health, pipeline, sync
from logger import setup_logging

# Setup logging
setup_logging()

app = FastAPI(
    title="NLI Pipeline API",
    description="Natural Language Intelligence Query Pipeline with Error Handling",
    version="1.0.0",
)

# Register routers
app.include_router(health.router)
app.include_router(sync.router)
app.include_router(pipeline.router)
app.include_router(debug.router)
app.include_router(artifacts.router)
# Register exception handlers
register_exception_handlers(app)
