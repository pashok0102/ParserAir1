from django.http import HttpResponse


DEFAULT_ALLOWED_ORIGINS = {
    "http://localhost:19006",
    "http://127.0.0.1:19006",
    "http://localhost:8081",
    "http://127.0.0.1:8081",
    "http://localhost:8082",
    "http://127.0.0.1:8082",
    "http://localhost:8083",
    "http://127.0.0.1:8083",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
}


def is_local_origin_allowed(origin: str) -> bool:
    if origin in DEFAULT_ALLOWED_ORIGINS:
        return True
    return origin.startswith("http://localhost:") or origin.startswith("http://127.0.0.1:")


class ApiCorsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        origin = request.headers.get("Origin", "")
        is_api_request = request.path.startswith("/api/")
        origin_allowed = is_local_origin_allowed(origin)
        requested_headers = request.headers.get("Access-Control-Request-Headers", "Content-Type, X-Requested-With")
        requested_method = request.headers.get("Access-Control-Request-Method", "")

        if is_api_request and request.method == "OPTIONS":
            response = HttpResponse(status=204)
        else:
            response = self.get_response(request)

        if is_api_request and origin_allowed:
            response["Access-Control-Allow-Origin"] = origin
            response["Access-Control-Allow-Credentials"] = "true"
            response["Access-Control-Allow-Headers"] = requested_headers or "Content-Type, X-Requested-With"
            response["Access-Control-Allow-Methods"] = requested_method or "GET, POST, OPTIONS"
            response["Access-Control-Max-Age"] = "86400"
            response["Vary"] = "Origin, Access-Control-Request-Headers, Access-Control-Request-Method"

        return response
