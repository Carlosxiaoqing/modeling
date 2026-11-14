import json
from types import SimpleNamespace
import httpx
import pytest
import app.providers as providers
from app.providers import VisionProvider, ImageProvider, ProviderFailure, configured, configured_price, FLASH_MODEL

class FakeSDK:
    def __init__(self, result=None, error=None):
        self.result, self.error, self.sent = result, error, {}
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.request))
        self.images = SimpleNamespace(generate=self.request)
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def request(self, **kwargs):
        self.sent.update(kwargs)
        if self.error: raise self.error
        return SimpleNamespace(model_dump=lambda: self.result)

def test_vision_contract_and_no_thinking(monkeypatch):
    monkeypatch.setenv('DASHSCOPE_API_KEY', 'synthetic-test-token')
    client = FakeSDK({'id': 'request-test', 'choices': [{'message': {'content': json.dumps({'observations': [], 'unknown_fields': [], 'photo_issues': [], 'blocking_issues': []})}}]})
    options = {}
    def factory(**kwargs):
        options.update(kwargs); return client
    monkeypatch.setattr(providers, 'OpenAI', factory)
    result, meta = VisionProvider().analyze([b'synthetic'])
    assert client.sent['extra_body']['enable_thinking'] is False
    assert client.sent['response_format'] == {'type': 'json_object'}
    assert options['max_retries'] == 0
    assert meta['usage'] is None and meta['cost_status'] == 'unreconciled'

def test_image_single_output_parameters_and_unknown_timeout(monkeypatch):
    monkeypatch.setenv('ARK_API_KEY', 'synthetic-test-token')
    monkeypatch.delenv('IMAGE_MODEL', raising=False)
    client = FakeSDK(error=providers.ArkTimeoutError(request=httpx.Request('POST', 'https://ark.cn-beijing.volces.com'), request_id='synthetic-timeout'))
    monkeypatch.setattr(providers, 'Ark', lambda **kw: client)
    with pytest.raises(ProviderFailure) as e: ImageProvider().generate([b'synthetic'], {}, {})
    assert e.value.code == 'PROVIDER_RESULT_UNKNOWN'
    assert client.sent['response_format'] == 'b64_json' and client.sent['watermark'] is True
    assert client.sent['model'] == FLASH_MODEL
    assert 'stream' not in client.sent and 'sequential_image_generation' not in client.sent

def test_untrusted_endpoint_rejected_without_request(monkeypatch):
    monkeypatch.setenv('VISION_ENDPOINT', 'http://127.0.0.1/secrets')
    with pytest.raises(ProviderFailure) as e: VisionProvider().analyze([])
    assert e.value.code == 'MODEL_NOT_CONFIGURED'

def test_keys_suffice_without_money_configuration(monkeypatch):
    for k in ['DASHSCOPE_API_KEY','ARK_API_KEY']: monkeypatch.setenv(k, 'synthetic')
    for k in ['IMAGE_ATTEMPT_PRICE_CNY','VISION_CALL_RESERVE_CNY','CONSULTATION_BUDGET_CNY']: monkeypatch.delenv(k, raising=False)
    assert configured()
    assert configured_price('IMAGE_ATTEMPT_PRICE_CNY') is None
    monkeypatch.setenv('IMAGE_ATTEMPT_PRICE_CNY', '-1')
    with pytest.raises(ProviderFailure): configured_price('IMAGE_ATTEMPT_PRICE_CNY')

def test_dedicated_qwen_endpoint_accepted_and_sdk_base(monkeypatch):
    monkeypatch.setenv('DASHSCOPE_API_KEY', 'synthetic-test-token')
    url = 'https://llm-test.cn-beijing.maas.aliyuncs.com/compatible-mode/v1/chat/completions'
    monkeypatch.setenv('VISION_ENDPOINT', url)
    client = FakeSDK({'choices': [{'message': {'content': '{}'}}]})
    options = {}
    def factory(**kwargs):
        options.update(kwargs); return client
    monkeypatch.setattr(providers, 'OpenAI', factory)
    VisionProvider().call('JSON')
    assert options['base_url'] == url.removesuffix('/chat/completions')
