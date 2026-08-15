import time
import logging

logger = logging.getLogger('pipeline.timing')


class PipelineTimingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if '/api/proxy/' in request.path:
            start = time.perf_counter()
            response = self.get_response(request)
            elapsed = (time.perf_counter() - start) * 1000
            logger.info(f"[PIPELINE] {request.method} {request.path} → {response.status_code} | {elapsed:.2f}ms")
            return response

        return self.get_response(request)
