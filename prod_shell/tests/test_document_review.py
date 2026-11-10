"""Contract tests use explicit test doubles; they are not live review evidence."""
import asyncio
import hashlib
import json
import subprocess
import sys

import pytest
from prod_shell.src.document_review import review_document
from prod_shell.src.review_web import create_app
from sfc_ai_router import RouterResult, RouterError


class TestRouter:
    __test__ = False

    def __init__(self, failed=None, synthesis=None, same_model=False):
        self.requests = []
        self.failed = failed
        self.synthesis = synthesis
        self.same_model = same_model

    async def run(self, req):
        self.requests.append(req)
        failed = req.lane == self.failed
        value = self.synthesis if self.synthesis is not None else {
            'improved_document': 'Test revision', 'weaknesses': ['Test weakness'],
            'change_log': ['Test change'], 'agreements': ['Test agreement'],
            'unresolved_disagreements': []}
        return RouterResult(ok=not failed, provider='test-only',
            model='same' if self.same_model else req.lane + '-test',
            text=json.dumps(value) if req.require_json else 'Test review',
            latency_ms=1, request_id='test-only',
            error=RouterError('test failure', False) if failed else None)


def test_preserves_original_and_independent_inputs():
    router = TestRouter()
    original = '  Original\nDo not strip or execute this.  '
    result = asyncio.run(review_document(original, router))
    assert result['original_document'] == original
    assert result['original_sha256'] == hashlib.sha256(original.encode()).hexdigest()
    assert result['status'] == 'REVIEWED' and result['approved'] is False
    assert len(router.requests) == 3
    assert router.requests[0].user_prompt == router.requests[1].user_prompt
    assert json.loads(router.requests[2].user_prompt)['original_document'] == original


def test_model_failure_does_not_claim_consensus():
    router = TestRouter(failed='claude')
    result = asyncio.run(review_document('Original', router))
    assert result['status'] == 'INCOMPLETE' and result['result'] is None
    assert len(router.requests) == 2


def test_same_model_cannot_count_as_two_reviewers():
    result = asyncio.run(review_document('Original', TestRouter(same_model=True)))
    assert result['status'] == 'INCOMPLETE'


@pytest.mark.parametrize('bad', [[], {'improved_document': 'only'}, 'bad'])
def test_invalid_synthesis_is_incomplete(bad):
    result = asyncio.run(review_document('Original', TestRouter(synthesis=bad)))
    assert result['status'] == 'INCOMPLETE'


def test_unresolved_disagreement_is_explicit():
    value = {'improved_document':'Draft', 'weaknesses':[], 'change_log':[],
             'agreements':[], 'unresolved_disagreements':['Test disagreement']}
    result = asyncio.run(review_document('Original', TestRouter(synthesis=value)))
    assert result['status'] == 'NON-CONSENSUS'


@pytest.mark.parametrize('bad', ['', '  ', None, 'a' * 24001])
def test_invalid_documents_do_not_call_models(bad):
    router = TestRouter()
    with pytest.raises(ValueError):
        asyncio.run(review_document(bad, router))
    assert not router.requests


def test_web_guards_and_receipt(tmp_path):
    router = TestRouter()
    app = create_app(router, tmp_path)
    client = app.test_client()
    assert client.get('/macie-c', base_url='http://evil.example').status_code == 400
    assert client.get('/macie-c', environ_overrides={'REMOTE_ADDR':'192.0.2.1'}).status_code == 403
    assert client.post('/macie-c/review', json={'document':'text'}).status_code == 403
    page = client.get('/macie-c')
    assert page.status_code == 200 and page.headers['Cache-Control'] == 'no-store'
    with client.session_transaction() as session:
        csrf = session['csrf']
    headers = {'X-CSRF-Token':csrf, 'Origin':'http://evil.example'}
    assert client.post('/macie-c/review', json={'document':'text'}, headers=headers).status_code == 403
    headers['Origin'] = 'http://localhost'
    assert client.post('/macie-c/review', json={'document':'text','context':'private'}, headers=headers).status_code == 400
    result = client.post('/macie-c/review', json={'document':'text'}, headers=headers)
    assert result.status_code == 200
    saved = json.loads(next(tmp_path.glob('*.json')).read_text())
    assert saved == result.json
    assert client.get('/macie').status_code == 404
    assert client.get('/macie/agents').status_code == 404


def test_import_has_no_private_shell_or_config():
    code = "import prod_shell.src.review_web,sys; assert not ({'core_shell','macie_config','registry','audit_log'} & set(sys.modules))"
    subprocess.run([sys.executable, '-c', code], check=True)
