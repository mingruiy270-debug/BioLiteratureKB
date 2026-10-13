import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from biokb.config import Config
from biokb.paper_review import (BudgetClient, Limits, ReviewError, choose_pages,
                                complete_text_preview, input_upper_estimate, run_review, write_json)


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    root = tmp_path / "kb"; root.mkdir()
    (root / "prompts").mkdir()
    (root / "prompts/paper_digest_v1.md").write_text("Read the full supplied evidence. No invented facts.")
    cfg = Config(root)
    monkeypatch.setenv(cfg.llm_api_key_env, "test-not-a-real-key")
    monkeypatch.setenv(cfg.llm_base_url_env, "https://example.invalid")
    monkeypatch.setenv(cfg.llm_model_env, "fake-model")
    import pymupdf
    doc = pymupdf.open()
    for i in range(2):
        page = doc.new_page()
        page.insert_textbox((50, 70, 500, 700), f"Methods page {i+1}. " + "Controlled synthetic fixture. " * 20)
    pdf = tmp_path / "paper.pdf"; doc.save(pdf); doc.close()
    # Synthetic converter avoids OCR/model initialization in unit tests.
    import pymupdf4llm
    monkeypatch.setattr(pymupdf4llm, "to_markdown", lambda d, **k: [{"text": p.get_text()} for p in d])
    return cfg, pdf, tmp_path / "review"


def response(text="Extracted evidence, not a scientific result.", finish="stop", usage=True):
    r = Mock()
    data = dict(model="fake-model", choices=[dict(message={"content": text}, finish_reason=finish)])
    if usage:
        data["usage"] = dict(prompt_tokens=100, completion_tokens=60, total_tokens=160)
    r.json.return_value = data
    return r


def test_dry_run_no_api_and_coverage(fixture):
    cfg, pdf, out = fixture; transport = Mock()
    state = run_review(cfg, pdf, out, "v1", limits=Limits(), transport=transport)
    assert state["status"] == "prepared_no_api" and state["calls"] == []
    assert len(state["pages"]) == 2
    assert "PDF page 2" in (out / "source.md").read_text()
    assert not transport.called


def test_apply_then_resume_without_charge(fixture):
    cfg, pdf, out = fixture; post = Mock(return_value=response())
    state = run_review(cfg, pdf, out, "v1", selection="1", apply=True, transport=post)
    assert post.call_count == 2
    assert state["actual_usage"]["prompt_tokens"] == 200
    vision = post.call_args_list[0].kwargs["json"]
    assert vision["messages"][0]["content"][1]["type"] == "image_url"
    assert vision["thinking"]["type"] == "disabled"
    assert vision["max_tokens"] == Limits().vision_output_tokens
    assert "Visual supplements only for pages [1]" in post.call_args_list[1].kwargs["json"]["messages"][1]["content"]
    run_review(cfg, pdf, out, "v1", selection="1", apply=True, transport=post)
    assert post.call_count == 2
    assert "test-not-a-real-key" not in (out / "review.json").read_text()
    assert "base64" not in (out / "review.json").read_text()


@pytest.mark.parametrize("limits", [Limits(max_calls=1), Limits(max_usd=.0000001), Limits(max_reserved_tokens=1)])
def test_whole_plan_rejected_before_billing(fixture, limits):
    cfg, pdf, out = fixture; post = Mock()
    with pytest.raises(ReviewError, match="exceeds budget"):
        run_review(cfg, pdf, out, "v1", selection="1", limits=limits, apply=True, transport=post)
    post.assert_not_called()


@pytest.mark.parametrize("bad", [response(finish="length"), response(usage=False)])
def test_partial_or_unknown_usage_cannot_be_ready_or_retried(fixture, bad):
    cfg, pdf, out = fixture; post = Mock(return_value=bad)
    with pytest.raises(ReviewError):
        run_review(cfg, pdf, out, "v1", selection="none", apply=True, transport=post)
    with pytest.raises(ReviewError, match="no automatic retry"):
        run_review(cfg, pdf, out, "v1", selection="none", apply=True, transport=post)
    assert post.call_count == 1 and not (out / "digest.preview.md").exists()
    assert (out / "digest.preview.partial.md").exists()


def test_timeout_reserved_not_retried(fixture):
    import requests
    cfg, pdf, out = fixture; post = Mock(side_effect=requests.Timeout("sensitive response"))
    with pytest.raises(ReviewError):
        run_review(cfg, pdf, out, "v1", selection="none", apply=True, transport=post)
    assert post.call_count == 1
    text = (out / "review.json").read_text()
    assert "reserved_cost_usd" in text and "sensitive response" not in text


def test_prepared_material_edit_blocks_resume(fixture):
    cfg, pdf, out = fixture
    run_review(cfg, pdf, out, "v1")
    (out / "source.md").write_text("changed")
    with pytest.raises(ReviewError, match="material changed"):
        run_review(cfg, pdf, out, "v1")


def test_budget_edit_blocks_resume(fixture):
    cfg, pdf, out = fixture
    run_review(cfg, pdf, out, "v1")
    with pytest.raises(ReviewError, match="budget changed"):
        run_review(cfg, pdf, out, "v1", limits=Limits(max_usd=1))


def test_lock_not_removed_by_second_process(fixture):
    cfg, pdf, out = fixture
    lock = out.with_name(out.name + ".running"); lock.write_text("other")
    with pytest.raises(ReviewError, match="already running"):
        run_review(cfg, pdf, out, "v1")
    assert lock.read_text() == "other"


def test_page_selection_and_limits():
    rows = [dict(page=1, visual_candidate=True, priority=2), dict(page=2, visual_candidate=True, priority=3)]
    assert choose_pages(rows, "auto", 1) == [2]
    assert choose_pages(rows, "none", 0) == []
    for pages in ("0", "3", "1,1", "x", "1,2"):
        with pytest.raises(ReviewError):
            choose_pages(rows, pages, 1)
    for kwargs in ({"max_usd": float("nan")}, {"max_calls": 0}, {"max_vision_pages": -1}):
        with pytest.raises(ValueError):
            Limits(**kwargs)


def test_image_not_billed_as_base64_text():
    messages = [{"content": [{"type": "text", "text": "abc"}, {"type": "image_url", "image_url": {"url": "data:" + "A" * 999999}}]}]
    assert input_upper_estimate(messages) == 1024 + 3 + 2048


def test_provider_usage_overrun_stops(fixture):
    cfg, pdf, out = fixture; r = response()
    data = r.json.return_value; data["usage"]["prompt_tokens"] = 9999999
    with pytest.raises(ReviewError):
        run_review(cfg, pdf, out, "v1", selection="none", apply=True, transport=Mock(return_value=r))
    assert not (out / "digest.preview.md").exists()


def test_no_source_discovery_for_standalone(tmp_path, monkeypatch):
    import biokb.config as module
    a, b = Mock(side_effect=AssertionError("Unexpected scan")), Mock(side_effect=AssertionError("Unexpected scan"))
    monkeypatch.setattr(module, "detect_json_dir", a)
    monkeypatch.setattr(module, "detect_zotero_storage", b)
    Config(tmp_path, discover_sources=False)
    a.assert_not_called(); b.assert_not_called()


def test_failed_local_preparation_can_be_repeated(fixture, monkeypatch):
    cfg, pdf, out = fixture
    import biokb.paper_review as module
    original = module.extract_pdf
    def fail(pdf, output, limits, selection):
        (output / "source.md").write_text("partial local extraction")
        raise RuntimeError("render failure")
    monkeypatch.setattr(module, "extract_pdf", fail)
    with pytest.raises(RuntimeError):run_review(cfg, pdf, out, "v1")
    assert not out.exists()
    monkeypatch.setattr(module, "extract_pdf", original)
    assert run_review(cfg, pdf, out, "v1")["status"] == "prepared_no_api"


def test_visual_bytes_are_bounded_before_digest(fixture):
    cfg, pdf, out = fixture; post = Mock(return_value=response("x" * 13000))
    with pytest.raises(ReviewError):
        run_review(cfg, pdf, out, "v1", selection="1", apply=True, transport=post)
    assert post.call_count == 1 and (out / "visual_page_001.partial.md").exists()


def test_sparse_page_transcription_not_just_caption(fixture):
    cfg, pdf, out = fixture
    import pymupdf
    d = pymupdf.open(); d.new_page(); d.save(pdf); d.close()
    post = Mock(return_value=response("Full page transcription."))
    state = run_review(cfg, pdf, out, "v1", selection="1", apply=True, transport=post)
    prompt = post.call_args_list[0].kwargs["json"]["messages"][0]["content"][0]["text"]
    assert "Transcribe its scientific prose" in prompt and "do not repeat paragraphs" not in prompt
    assert state["status"] == "preview_ready_with_coverage_restrictions"


def test_unread_sparse_page_blocks_before_api(fixture):
    cfg, pdf, out = fixture
    import pymupdf
    d = pymupdf.open(); d.new_page(); d.save(pdf); d.close()
    post = Mock()
    with pytest.raises(ReviewError, match="Sparse/image-only"):
        run_review(cfg, pdf, out, "v1", selection="none", apply=True, transport=post)
    post.assert_not_called()


def test_incomplete_scanned_transcription_stops_digest(fixture):
    cfg, pdf, out = fixture
    import pymupdf
    d = pymupdf.open(); d.new_page(); d.save(pdf); d.close()
    post = Mock(return_value=response("INCOMPLETE_TRANSCRIPTION"))
    with pytest.raises(ReviewError, match="transcription incomplete"):
        run_review(cfg, pdf, out, "v1", selection="1", apply=True, transport=post)
    assert post.call_count == 1


def test_explicit_completion_preserves_spend_and_no_images(fixture):
    cfg, pdf, out = fixture
    bad = Mock(return_value=response(finish="length"))
    with pytest.raises(ReviewError):run_review(cfg, pdf, out, "v1", apply=True, transport=bad)
    plan = complete_text_preview(cfg, out)
    assert plan['prior_calls'] == 1 and plan['visual_notes_used'] is False
    good = Mock(return_value=response())
    result = complete_text_preview(cfg, out, True, good)
    assert result['actual_usage']['prompt_tokens'] == 200
    assert good.call_count == 1
    payload = good.call_args.kwargs['json']
    assert payload['thinking']['type'] == 'disabled'
    assert isinstance(payload['messages'][1]['content'], str)
    complete_text_preview(cfg, out, True, good)
    assert good.call_count == 1


def test_unknown_usage_cannot_trigger_completion(fixture):
    cfg, pdf, out = fixture
    with pytest.raises(ReviewError):run_review(cfg, pdf, out, "v1", apply=True, transport=Mock(return_value=response(finish="length", usage=False)))
    with pytest.raises(ReviewError, match='known-usage'):complete_text_preview(cfg, out, True, Mock())


def test_auto_vision_cannot_apply_without_selection(fixture):
    cfg, pdf, out = fixture
    import pymupdf
    d = pymupdf.open(); d.new_page(); d.save(pdf); d.close()
    post = Mock()
    with pytest.raises(ReviewError, match='Auto finds candidates'):
        run_review(cfg, pdf, out, "v1", selection="auto", apply=True, transport=post)
    post.assert_not_called()


def test_default_is_one_text_only_request(fixture):
    cfg, pdf, out = fixture; post = Mock(return_value=response())
    s = run_review(cfg, pdf, out, 'v1', apply=True, transport=post)
    assert post.call_count == 1 and s['selected_pages'] == []
    assert post.call_args.kwargs['json']['thinking']['type'] == 'disabled'
    assert post.call_args.kwargs['json']['max_tokens'] == 393216


def test_visual_cost_bound_independent_of_text_cap(fixture):
    cfg, pdf, out = fixture; post = Mock()
    with pytest.raises(ReviewError, match='exceeds budget'):
        run_review(cfg, pdf, out, 'v1', selection='1', limits=Limits(max_usd=0, max_vision_usd=.000001), apply=True, transport=post)
    post.assert_not_called()


def test_dropped_equation_retains_native_alternative(fixture, monkeypatch):
    cfg, pdf, out = fixture
    import pymupdf, pymupdf4llm
    d = pymupdf.open(); p = d.new_page()
    p.insert_textbox((50, 70, 500, 700), 'Methods. ' + 'Scientific prose here. ' * 20 + '\nLoss = MSE + MAE (11)')
    d.save(pdf); d.close()
    monkeypatch.setattr(pymupdf4llm, 'to_markdown', lambda d, **k: [{'text': p.get_text().replace('Loss = MSE + MAE (11)', '')} for p in d])
    s = run_review(cfg, pdf, out, 'v1')
    assert 'math_or_numbered_equation_loss' in s['pages'][0]['warning']
    assert 'Loss = MSE + MAE (11)' in (out / 'source.md').read_text()


@pytest.mark.parametrize('usage', [None, {'prompt_tokens': True, 'completion_tokens': False}, {'total_tokens': 10}])
def test_malformed_usage_retains_output_and_refuses_recovery(fixture, usage):
    cfg, pdf, out = fixture; r = response(finish='length')
    r.json.return_value['usage'] = usage
    with pytest.raises(ReviewError):run_review(cfg, pdf, out, 'v1', apply=True, transport=Mock(return_value=r))
    assert (out / 'digest.preview.partial.md').read_text()
    with pytest.raises(ReviewError):complete_text_preview(cfg, out, True, Mock())


def test_manifest_failure_does_not_publish_half_prepared_directory(fixture, monkeypatch):
    cfg, pdf, out = fixture
    import biokb.paper_review as module
    save = module.write_json
    monkeypatch.setattr(module, 'write_json', Mock(side_effect=OSError('disk full')))
    with pytest.raises(OSError):run_review(cfg, pdf, out, 'v1')
    assert not out.exists()
    monkeypatch.setattr(module, 'write_json', save)
    assert run_review(cfg, pdf, out, 'v1')['status'] == 'prepared_no_api'
