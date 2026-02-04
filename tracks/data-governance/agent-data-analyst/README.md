# Khipu Enterprise

> Analytics automation powered by your data catalog

**Private repository** - GalacticaIA

## Overview

Khipu reads your OpenMetadata catalog (schemas, glossaries, lineage) and proposes automated analytics:
- Churn prediction
- Customer segmentation
- Propensity scoring
- Revenue analytics
- Anomaly detection

## Architecture

```
OpenMetadata API → Khipu Core → Analytics Dashboard
                      ↓
              SQL Generation + ML Models
```

## Tech Stack

- **API**: FastAPI + LangChain
- **Frontend**: Next.js 14
- **Data Catalog**: OpenMetadata integration
- **ML**: scikit-learn, MindsDB
- **Deploy**: Docker

## Development

```bash
# API
cd apps/api
pip install -r requirements.txt
uvicorn main:app --reload

# Web
cd apps/web
npm install
npm run dev
```

## License

Proprietary - GalacticaIA
