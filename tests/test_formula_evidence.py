import json
from unittest.mock import Mock

import pytest
import pymupdf

from biokb.formula_evidence import equation_candidates, validate_crops, preview_warnings
from biokb.paper_review import Limits, ReviewError, run_review, complete_text_preview, write_json
from test_paper_review import fixture, response


@pytest.mark.parametrize("value", [None, {}, [dict(page=1, bbox=[0,0,1,1])],
    [dict(page=True, bbox=[0,0,1,1], reason="missing")],
    [dict(page=1, bbox=[0,0,1,1], reason="")],
    [dict(page=1, bbox=[0,0,float('nan'),1], reason="missing")],
    [dict(page=1, bbox=[0,0,float('inf'),1], reason="missing")],
    [dict(page=1, bbox=[0,0,False,1], reason="missing")],
    [dict(page=1, bbox=[0,0,2,1], reason="missing")],
    [dict(page=1, bbox=[.5,0,.1,1], reason="missing")],
    [dict(page=1, bbox=[0,0,0,1], reason="missing")]])
def test_invalid_crop_contract(value):
    with pytest.raises(ValueError):validate_crops(value, 2)


def crops(page=1):
    return [dict(page=page, bbox=[0,0,.9,.8], reason="Missing critical loss denominator")]


def test_duplicate_and_budget():
    with pytest.raises(ValueError):validate_crops(crops()*2, 2)
    with pytest.raises(ValueError):validate_crops(crops(), 0)


def test_preview_provenance_warnings_are_not_scientific_approval():
    note = 'Equation (11): L = MSE + MAE'
    warnings = preview_warnings('Eq. 5 视觉转写为 xM W', [note])
    assert {w['kind'] for w in warnings} == {'missing_digest_frontmatter','visual_formula_attribution_needs_review'}
    assert warnings[1]['equation_ids'] == ['5']
    assert preview_warnings('---\ntitle: null\n---\nEq. 11 视觉转写未人工审核', [note]) == []


def test_native_equation_candidates_keep_source_and_geometry():
    with pymupdf.open() as d:
        p = d.new_page()
        p.insert_text((50,100), "L = MSE + MAE (11)")
        p.insert_text((50,160), "L is the training loss.")
        rows = equation_candidates(p, 3)
        assert len(rows) == 1
        c = rows[0]
        assert c["equation_number_candidates"] == ["11"] and c["pdf_page"] == 3
        assert c["native_expression_block"].strip() == "L = MSE + MAE (11)"
        assert c["expression_latex"] is None and c["manual_review_status"] == "not_reviewed"
        assert "L is the training loss" in ''.join(c["adjacent_native_context"])
        for rotation in (0,90,180,270):
            p.set_rotation(rotation)
            box = equation_candidates(p,3)[0]["bbox_normalized"]
            assert all(0 <= v <= 1 for v in box)
            assert box[0] < box[2] and box[1] < box[3]


def test_crop_default_dryrun_and_cached_apply(fixture):
    cfg,pdf,out = fixture
    post = Mock(return_value=response("Equation transcription; definitions unclear."))
    s = run_review(cfg,pdf,out,'v1',formula_crops=crops(),transport=post)
    assert s['plan']['calls'] == 2 and not post.called
    assert s['pages'][0]['visual_scope'] == 'formula_crop'
    with pymupdf.open(pdf) as d:
        img = pymupdf.Pixmap(str(out/'pages/page_001.jpg'))
        assert img.width <= 2201 and img.height <= 2201
    s = run_review(cfg,pdf,out,'v1',formula_crops=crops(),transport=post,apply=True)
    assert post.call_count == 2
    vp = post.call_args_list[0].kwargs['json']['messages'][0]['content'][0]['text']
    assert 'LaTeX' in vp and '<=350' not in vp and 'not a whole-page' in vp
    dp = post.call_args_list[1].kwargs['json']['messages'][1]['content']
    assert 'Formula-crop-only pages: [1]' in dp and 'formula crop only' in dp
    run_review(cfg,pdf,out,'v1',formula_crops=crops(),transport=post,apply=True)
    assert post.call_count == 2


def test_crop_contract_edits_refuse_resume(fixture):
    cfg,pdf,out = fixture
    run_review(cfg,pdf,out,'v1',formula_crops=crops())
    other = crops(); other[0]['bbox'][2] = .8
    with pytest.raises(ReviewError,match='changed'):
        run_review(cfg,pdf,out,'v1',formula_crops=other)
    (out/'formula_crops.json').write_text('{}')
    with pytest.raises(ReviewError,match='changed'):
        run_review(cfg,pdf,out,'v1',formula_crops=crops())


@pytest.mark.parametrize('selection,page', [('1',1),('auto',1),('none',3)])
def test_mixed_or_out_of_range_crops_no_api(fixture,selection,page):
    cfg,pdf,out = fixture; post = Mock()
    with pytest.raises(ReviewError):
        run_review(cfg,pdf,out,'v1',selection=selection,formula_crops=crops(page),apply=True,transport=post)
    post.assert_not_called()
    assert not out.exists()


def test_crop_not_ocr_for_sparse_page(fixture):
    cfg,pdf,out = fixture
    with pymupdf.open() as d:
        d.new_page(); d.save(pdf)
    post = Mock()
    with pytest.raises(ReviewError,match='cannot cover'):
        run_review(cfg,pdf,out,'v1',formula_crops=crops(),apply=True,transport=post)
    post.assert_not_called()


def test_unresolved_crop_is_saved_not_retried(fixture):
    cfg,pdf,out = fixture; post = Mock(return_value=response('UNRESOLVED_FORMULA: denominator unclear.'))
    s = run_review(cfg,pdf,out,'v1',formula_crops=crops(),apply=True,transport=post)
    assert s['unresolved_formula_pages'] == [1]
    assert 'UNRESOLVED_FORMULA' in post.call_args_list[1].kwargs['json']['messages'][1]['content']
    run_review(cfg,pdf,out,'v1',formula_crops=crops(),apply=True,transport=post)
    assert post.call_count == 2


def test_crop_budget_shared_with_vision(fixture):
    cfg,pdf,out = fixture; post = Mock()
    with pytest.raises(ReviewError,match='exceeds budget'):
        run_review(cfg,pdf,out,'v1',formula_crops=crops(),apply=True,transport=post,
                   limits=Limits(max_vision_usd=.000001))
    post.assert_not_called()


def test_prose_reference_cannot_hide_missing_equation(fixture, monkeypatch):
    cfg,pdf,out = fixture
    import pymupdf4llm
    with pymupdf.open() as d:
        p = d.new_page()
        p.insert_textbox((50,50,500,500), 'We optimize equation (11). ' + 'Scientific prose here. '*30)
        p.insert_text((50,600), 'L = 0.37 * MSE + MAE (11)')
        d.save(pdf)
    monkeypatch.setattr(pymupdf4llm,'to_markdown',lambda d,**kw:[{'text':p.get_text().replace('L = 0.37 * MSE + MAE (11)','')} for p in d])
    post = Mock(return_value=response())
    s = run_review(cfg,pdf,out,'v1',apply=True,transport=post)
    assert 'native_formula_candidate_blocks_retained' in s['pages'][0]['warning']
    assert '0.37 * MSE' in post.call_args.kwargs['json']['messages'][1]['content']
    assert post.call_count == 1


def truncated_crop(fixture):
    cfg,pdf,out = fixture
    post = Mock(side_effect=[response('L = MSE + MAE. UNRESOLVED_FORMULA: index unclear.'),response(finish='length')])
    with pytest.raises(ReviewError):
        run_review(cfg,pdf,out,'v1',formula_crops=crops(),apply=True,transport=post)
    return cfg,out


def test_completion_reuses_crop_notes_without_images(fixture):
    cfg,out = truncated_crop(fixture)
    post = Mock(return_value=response())
    s = complete_text_preview(cfg,out,True,post)
    assert s['plan']['visual_notes_used'] and not s['plan']['images_resent']
    messages = post.call_args.kwargs['json']['messages']
    assert all(isinstance(m['content'],str) for m in messages)
    assert 'UNRESOLVED_FORMULA' in messages[1]['content'] and 'L = MSE + MAE' in messages[1]['content']
    assert 'rest of page not visually inspected' in messages[1]['content']
    complete_text_preview(cfg,out,True,post)
    assert post.call_count == 1


def test_completion_old_pipeline_blocked_before_api(fixture):
    cfg,out = truncated_crop(fixture)
    state = json.loads((out/'review.json').read_text())
    state['contract']['pipeline_version'] = 'bounded-review-4'
    write_json(out/'review.json',state)
    post = Mock()
    with pytest.raises(ReviewError,match='Pipeline version'):
        complete_text_preview(cfg,out,True,post)
    post.assert_not_called()


def test_completion_changed_visual_note_blocked(fixture):
    cfg,out = truncated_crop(fixture)
    (out/'visual_page_001.md').write_text('silently corrected formula')
    post = Mock()
    with pytest.raises(ReviewError,match='Cached visual'):
        complete_text_preview(cfg,out,True,post)
    post.assert_not_called()
