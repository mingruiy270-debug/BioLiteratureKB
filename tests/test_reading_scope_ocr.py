from unittest.mock import Mock
import json

import pytest
import pymupdf

from biokb.reading_scope import parse_text_pages
from biokb.local_ocr import OCRSettings
from biokb.paper_review import run_review, ReviewError, complete_text_preview
from test_paper_review import fixture, response


@pytest.mark.parametrize('bad',['0','3','2-1','1-99','1,1','1-2,2','x',''])
def test_invalid_scope(bad):
    with pytest.raises(ValueError):parse_text_pages(bad,2)


def test_scope_ranges():
    assert parse_text_pages('all',3)==[1,2,3]
    assert parse_text_pages('1-2,4',4)==[1,2,4]


def test_excluded_sparse_pages_not_sent_or_ocr(fixture,monkeypatch):
    cfg,pdf,out=fixture
    import biokb.paper_review as module
    with pymupdf.open() as d:
        p=d.new_page();p.insert_textbox((50,60,500,700),'Main Methods. '+'Relevant body. '*40)
        d.new_page();d.save(pdf)
    ocr=Mock(side_effect=AssertionError('Unexpected OCR'));monkeypatch.setattr(module,'recognize_sparse_page',ocr)
    post=Mock(return_value=response())
    s=run_review(cfg,pdf,out,'v1',text_pages='1',apply=True,transport=post)
    assert post.call_count==1 and s['plan']['excluded_text_pages']==[2]
    assert s['pages'][1]['text_status']=='excluded_by_scope'
    assert '## PDF page 2' not in (out/'source.md').read_text()
    assert '1 of 2 PDF pages' in post.call_args.kwargs['json']['messages'][1]['content']
    ocr.assert_not_called()


def test_cannot_select_visuals_outside_scope(fixture):
    cfg,pdf,out=fixture;post=Mock()
    with pytest.raises(ReviewError,match='outside explicit reading scope'):
        run_review(cfg,pdf,out,'v1',text_pages='1',selection='2',apply=True,transport=post)
    post.assert_not_called()


def ocr_config(tmp_path):
    folder=tmp_path/'tessdata';folder.mkdir();(folder/'eng.traineddata').write_bytes(b'synthetic, not an OCR model')
    return OCRSettings(str(folder))


def test_ocr_validation(tmp_path):
    with pytest.raises(ValueError,match='Missing local'):OCRSettings(str(tmp_path)).contract()
    with pytest.raises(ValueError):OCRSettings(str(tmp_path),'../eng').contract()
    with pytest.raises(ValueError):OCRSettings(str(tmp_path),dpi=999).contract()


def test_local_ocr_is_labeled_cached_and_not_vision(fixture,tmp_path,monkeypatch):
    cfg,pdf,out=fixture
    with pymupdf.open() as d:
        d.new_page();d.save(pdf)
    import biokb.paper_review as module
    recognize=Mock(return_value=dict(text='OCR Methods. '+'Unverified scanned prose. '*20,language='eng',effective_dpi=300))
    monkeypatch.setattr(module,'recognize_sparse_page',recognize)
    settings=ocr_config(tmp_path);post=Mock(return_value=response())
    s=run_review(cfg,pdf,out,'v1',ocr=settings,apply=True,transport=post)
    assert recognize.call_count==1 and post.call_count==1
    assert s['pages'][0]['text_status']=='ocr_extracted_unverified'
    assert s['plan']['local_ocr_pages']==[1]
    assert (out/'ocr_pages.json').exists()
    message=post.call_args.kwargs['json']['messages'][1]['content']
    assert 'Do not infer checked form choices' in message and 'Local OCR pages: [1]' in message
    run_review(cfg,pdf,out,'v1',ocr=settings,apply=True,transport=post)
    assert recognize.call_count==1 and post.call_count==1
    (tmp_path/'tessdata/eng.traineddata').write_bytes(b'changed')
    with pytest.raises(ReviewError,match='changed'):
        run_review(cfg,pdf,out,'v1',ocr=settings,apply=True,transport=post)


def test_empty_ocr_still_blocks(fixture,tmp_path,monkeypatch):
    cfg,pdf,out=fixture
    with pymupdf.open() as d:
        d.new_page();d.save(pdf)
    import biokb.paper_review as module
    monkeypatch.setattr(module,'recognize_sparse_page',lambda *a:dict(text='',language='eng'))
    post=Mock()
    with pytest.raises(ReviewError,match='Sparse/image-only'):
        run_review(cfg,pdf,out,'v1',ocr=ocr_config(tmp_path),apply=True,transport=post)
    post.assert_not_called()


def test_scope_change_cannot_reuse_paid_output(fixture):
    cfg,pdf,out=fixture;post=Mock(return_value=response())
    run_review(cfg,pdf,out,'v1',text_pages='1',apply=True,transport=post)
    with pytest.raises(ReviewError,match='changed'):
        run_review(cfg,pdf,out,'v1',text_pages='all',apply=True,transport=post)
    assert post.call_count==1


def test_symlinked_ocr_model_completion(fixture,tmp_path,monkeypatch):
    cfg,pdf,out=fixture
    model=tmp_path/'model.data';model.write_bytes(b'synthetic model')
    folder=tmp_path/'linked-tessdata';folder.mkdir();(folder/'eng.traineddata').symlink_to(model)
    settings=OCRSettings(str(folder))
    assert settings.contract()['language_files'][0]['path']==str(model.resolve())
    with pytest.raises(ReviewError):
        run_review(cfg,pdf,out,'v1',ocr=settings,apply=True,transport=Mock(return_value=response(finish='length')))
    good=Mock(return_value=response())
    result=complete_text_preview(cfg,out,True,good)
    assert good.call_count==1 and result['plan']['images_resent'] is False
