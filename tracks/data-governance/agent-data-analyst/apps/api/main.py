"""
Khipu Enterprise API
Analytics automation powered by your data catalog
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="Khipu Enterprise",
    description="Analytics automation powered by OpenMetadata",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure properly in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {
        "name": "Khipu Enterprise",
        "version": "0.1.0",
        "status": "running",
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}


# TODO: Add routes
# - POST /api/chat - Natural language to analytics
# - GET /api/catalog - List available tables from OpenMetadata
# - GET /api/glossary - Get business glossary
# - POST /api/analyze - Run analysis (churn, segmentation, etc.)
