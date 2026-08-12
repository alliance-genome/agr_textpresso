#!/usr/bin/env python3
"""Minimal stdlib HTTP server exposing CAS2 annotation and ontology-category data.

Lets off-server clients get the same (sentences, annotations, sections) data
that previously required direct filesystem access to this container's CAS2
files under /data/textpresso/tpcas-2, and look up the exact stored ontology
category strings --category requires -- see
sorghumbase_textpresso_implementation/bin/tpc_search_internal.py and
bin/tpc_search.py, which call these endpoints instead of reading local files
or guessing at category strings.

Runs as a separate process alongside textpressoapi, proxied by lighttpd at
/v1/textpresso/annotate and /v1/textpresso/category_search (see
lighttpd.conf). Both paths are deliberately disjoint from the existing
/v1/textpresso/api proxy rule (share only the "/v1/textpresso/" prefix, not
the "api" segment) so the new routes can't match or interact with it.

Binds to 127.0.0.1 only -- reachable exclusively through the lighttpd proxy,
never directly.

Endpoints:
  GET /v1/textpresso/annotate
      ?identifier=<doc identifier, e.g. "MaizeTest100//10.1038_srep35479/10.1038_srep35479.tpcas">
      &ontology=GO&ontology=PO           (repeatable; default: all except *_RELATED)
      &related_synonyms=1                (include *_RELATED annotations; ignored if ontology given)

    200 -> {"sentences": [...], "annotations": [...], "sections": [...]}
    400 -> {"error": "..."}  (missing identifier)
    404 -> {"error": "..."}  (no CAS2 file for that identifier)
    500 -> {"error": "..."}  (parse failure)

  GET /v1/textpresso/category_search
      ?q=<free-text query, e.g. "seed">
      &ontology=PO                       (repeatable; default: all)
      &limit=20                          (default 20, capped at 100)

    200 -> {"query": "...", "matches": [{"id","name","category","ontology","matched_on"}, ...]}
    400 -> {"error": "..."}  (missing q)
"""

import json
import os
import socketserver
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

import casannot
import category_index

HOST = "127.0.0.1"
PORT = int(os.environ.get("CAS_ANNOTATE_PORT", "8082"))
ANNOTATE_SUFFIX = "/v1/textpresso/annotate"
CATEGORY_SEARCH_SUFFIX = "/v1/textpresso/category_search"

_CATEGORY_INDEX = None  # built once at startup, see main()


def _load_annotation(identifier, ontology_filter, include_related):
    """Return {sentences, annotations, sections} for identifier, or None if no CAS2 file."""
    path = casannot.identifier_to_cas_path(identifier)
    if not os.path.exists(path):
        return None
    sentences, annotations, sections = casannot.parse_cas_file(path)
    if ontology_filter:
        annotations = [a for a in annotations if a["ontology"] in ontology_filter]
    elif not include_related:
        annotations = [a for a in annotations if not a["ontology"].endswith("_RELATED")]
    return {"sentences": sentences, "annotations": annotations, "sections": sections}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stderr.write("cas_annotate_server: " + (fmt % args) + "\n")

    def _send_json(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        qs = parse_qs(parsed.query)

        if path.endswith(ANNOTATE_SUFFIX):
            self._handle_annotate(qs)
        elif path.endswith(CATEGORY_SEARCH_SUFFIX):
            self._handle_category_search(qs)
        else:
            self._send_json(404, {"error": "not found"})

    def _handle_annotate(self, qs):
        identifier = (qs.get("identifier") or [None])[0]
        if not identifier:
            self._send_json(400, {"error": "missing identifier"})
            return

        ontology_filter = set(qs.get("ontology") or ()) or None
        include_related = (qs.get("related_synonyms") or ["0"])[0] == "1"

        try:
            result = _load_annotation(identifier, ontology_filter, include_related)
        except Exception as e:
            self._send_json(500, {"error": str(e)})
            return

        if result is None:
            self._send_json(404, {"error": "CAS2 file not found for identifier"})
            return

        self._send_json(200, result)

    def _handle_category_search(self, qs):
        query = (qs.get("q") or [None])[0]
        if not query:
            self._send_json(400, {"error": "missing q"})
            return

        ontology_filter = set(qs.get("ontology") or ()) or None
        try:
            limit = min(int((qs.get("limit") or ["20"])[0]), 100)
        except ValueError:
            limit = 20

        matches = category_index.search(_CATEGORY_INDEX, query, ontology_filter, limit)
        self._send_json(200, {"query": query, "matches": matches})


class ThreadingHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads = True


def main():
    global _CATEGORY_INDEX
    print("cas_annotate_server: building category index from OBO files...", file=sys.stderr)
    _CATEGORY_INDEX = category_index.build_index(casannot._ontology_of)
    print(f"cas_annotate_server: indexed {len(_CATEGORY_INDEX['categories'])} categories, "
          f"{len(_CATEGORY_INDEX['synonyms'])} distinct synonyms", file=sys.stderr)

    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"cas_annotate_server listening on {HOST}:{PORT}", file=sys.stderr)
    server.serve_forever()


if __name__ == "__main__":
    main()
