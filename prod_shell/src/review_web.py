"""Local-only C pilot. Do not expose this development server to a network."""
from __future__ import annotations

import asyncio
import json
import os
import secrets
import threading
from pathlib import Path
from flask import Flask, jsonify, render_template, request, session

from .document_review import review_document


def create_app(router=None, output_dir=None):
    app = Flask(__name__)
    app.secret_key = secrets.token_hex(32)
    app.config.update(MAX_CONTENT_LENGTH=100000, TRUSTED_HOSTS=['127.0.0.1', 'localhost'],
                      SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Strict')
    lock = threading.Lock()
    destination = Path(output_dir or os.environ.get('MACIE_C_OUTPUT_DIR', 'logs/macie-c'))

    @app.before_request
    def local_only():
        if request.remote_addr not in ('127.0.0.1', '::1'):
            return jsonify(error='This pilot permits local access only.'), 403
        if request.method == 'POST':
            supplied = request.headers.get('X-CSRF-Token', '')
            expected = session.get('csrf', '')
            if not expected or not secrets.compare_digest(supplied, expected):
                return jsonify(error='Reload the page before submitting.'), 403
            if request.headers.get('Origin') != request.host_url.rstrip('/'):
                return jsonify(error='Cross-origin requests are denied.'), 403

    @app.after_request
    def private_response(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        return response

    @app.get('/macie-c')
    def home():
        session.setdefault('csrf', secrets.token_hex(32))
        return render_template('review.html', csrf=session['csrf'])

    @app.post('/macie-c/review')
    def review():
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or set(data) != {'document'}:
            return jsonify(error='Only a document field is accepted.'), 400
        if not lock.acquire(blocking=False):
            return jsonify(error='A review is already running.'), 409
        try:
            receipt = asyncio.run(review_document(data['document'], router))
            destination.mkdir(parents=True, exist_ok=True)
            with (destination / (receipt['review_id'] + '.json')).open('x', encoding='utf-8') as f:
                json.dump(receipt, f, ensure_ascii=False, indent=2)
            return jsonify(receipt)
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        finally:
            lock.release()

    return app


if __name__ == '__main__':
    create_app().run(host='127.0.0.1', port=5073, debug=False, use_reloader=False)
