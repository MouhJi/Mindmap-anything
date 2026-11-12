"""Small dependency-free WSGI read API; mount behind project authorization.

No backend framework existed in the repository. This adapter can be mounted in
an existing WSGI/ASGI stack later without coupling the domain logic to one.
"""

from __future__ import annotations

import argparse
import json
import re
from urllib.parse import parse_qs, unquote
from wsgiref.simple_server import make_server

from pydantic import ValidationError

from .expansion import ExpansionService, InvalidCursor, NodeNotFound, StaleCursor
from .neo4j import Neo4jRepository
from .repository import RepositoryUnavailable


class GraphAPI:
    def __init__(self, service: ExpansionService):
        self.service = service

    def __call__(self, environ, start_response):
        try:
            if environ.get("REQUEST_METHOD") != "GET":
                return self._respond(start_response, "405 Method Not Allowed", {"error": "GET required"})
            path = environ.get("PATH_INFO", "")
            if path == "/api/graph/config":
                return self._respond(start_response, "200 OK", self.service.policy.model_dump())
            expansion = re.fullmatch(r"/api/graph/nodes/([^/]+)/expand", path)
            evidence = re.fullmatch(r"/api/graph/edges/([^/]+)/evidence", path)
            if not expansion and not evidence:
                raise NodeNotFound("Endpoint not found")
            parsed = parse_qs(environ.get("QUERY_STRING", ""), keep_blank_values=True, max_num_fields=20)
            if any(len(values) != 1 for values in parsed.values()):
                raise ValueError("Repeated query parameters are not allowed")
            params = {key: values[0] for key, values in parsed.items()}
            allowed = {"project_id", "limit", "cursor"}
            if expansion:
                allowed.update({"min_importance", "min_confidence", "context"})
            if set(params) - allowed:
                raise ValueError("Unknown query parameter")
            project_id = params.pop("project_id", "").strip()
            if not project_id or len(project_id) > 200:
                raise ValueError("A project_id is required")
            if "limit" in params:
                params["limit"] = int(params["limit"])
            for key in ("min_importance", "min_confidence"):
                if key in params:
                    params[key] = float(params[key])
            if expansion:
                result = self.service.expand(project_id, unquote(expansion[1]), **params).model_dump(mode="json")
            else:
                result = self.service.evidence(project_id, unquote(evidence[1]), **params)
            return self._respond(start_response, "200 OK", result)
        except NodeNotFound as error:
            return self._respond(start_response, "404 Not Found", {"error": str(error)})
        except StaleCursor as error:
            return self._respond(start_response, "409 Conflict", {"error": str(error)})
        except (ValidationError, ValueError) as error:
            message = "Invalid query parameters" if isinstance(error, ValidationError) else str(error)
            return self._respond(start_response, "422 Unprocessable Entity", {"error": message})
        except RepositoryUnavailable:
            return self._respond(start_response, "503 Service Unavailable", {"error": "Graph database unavailable"})

    @staticmethod
    def _respond(start_response, status, body):
        encoded = json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8")
        start_response(status, [("Content-Type", "application/json; charset=utf-8"),
                                ("Content-Length", str(len(encoded))), ("Cache-Control", "no-store")])
        return [encoded]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--init-schema", action="store_true")
    args = parser.parse_args()
    repository = Neo4jRepository.from_env()
    try:
        if args.init_schema:
            repository.ensure_schema()
        app = GraphAPI(ExpansionService(repository))
        with make_server("127.0.0.1", args.port, app) as server:
            print(f"Graph API listening on http://127.0.0.1:{args.port}")
            server.serve_forever()
    finally:
        repository.close()


if __name__ == "__main__":
    main()
