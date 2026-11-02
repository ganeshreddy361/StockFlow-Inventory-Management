from datetime import datetime, timezone

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

app = FastAPI(
    title="Inventory and Order Management API Gateway",
    description="Central entry point for the inventory and order microservices.",
    version="1.0.0",
)

SERVICES = {
    "auth": "http://127.0.0.1:8101",
    "products": "http://127.0.0.1:8102",
    "inventory": "http://127.0.0.1:8103",
    "cart": "http://127.0.0.1:8104",
    "orders": "http://127.0.0.1:8105",
    "payments": "http://127.0.0.1:8106",
    "notifications": "http://127.0.0.1:8107",
}


@app.get("/")
def root():
    return {
        "application": "Inventory and Order Management System",
        "gateway": "running",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/health")
def health():
    return {
        "gateway": "healthy",
        "status": "running",
    }


@app.api_route(
    "/{service}/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
)
async def route_request(
    service: str,
    path: str,
    request: Request,
):
    if service not in SERVICES:
        return JSONResponse(
            status_code=404,
            content={"detail": f"Unknown service: {service}"},
        )

    target_url = f"{SERVICES[service]}/{path}"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            upstream = await client.request(
                method=request.method,
                url=target_url,
                params=request.query_params,
                content=await request.body(),
                headers={
                    key: value
                    for key, value in request.headers.items()
                    if key.lower() not in {
                        "host",
                        "content-length",
                        "connection",
                    }
                },
            )

        excluded_headers = {
            "content-encoding",
            "content-length",
            "transfer-encoding",
            "connection",
        }

        response_headers = {
            key: value
            for key, value in upstream.headers.items()
            if key.lower() not in excluded_headers
        }

        return Response(
            content=upstream.content,
            status_code=upstream.status_code,
            headers=response_headers,
            media_type=upstream.headers.get("content-type"),
        )

    except httpx.RequestError:
        return JSONResponse(
            status_code=503,
            content={
                "detail": (
                    f"The {service} service is unavailable. "
                    "Check that its server is running."
                )
            },
        )



