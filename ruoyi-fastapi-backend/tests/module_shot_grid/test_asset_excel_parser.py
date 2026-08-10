import io
from pathlib import Path

import pytest
from openpyxl import Workbook

from module_shot_grid.config import ShotGridImportConfig
from module_shot_grid.entity.vo.asset_import_vo import AssetImportCommitRequestModel
from module_shot_grid.exceptions import ShotGridDomainException
from module_shot_grid.service.asset_excel_parser import AssetExcelParser

REPO_ROOT = Path(__file__).resolve().parents[3]
ASSET_SAMPLE = REPO_ROOT / 'shot-grid-frontend' / 'docs' / '资产-样表.xlsx'
HEADERS = ['类型', '名称', '描述', '制作分项', '备注', '状态', '制作人']
EXCEL_LAST_ROW = 1_048_576
COMPOSITE_ASSIGNEE_ROW = 16
DUPLICATE_ROW_COUNT = 2


def _save_workbook(workbook: Workbook) -> bytes:
    stream = io.BytesIO()
    workbook.save(stream)
    workbook.close()
    return stream.getvalue()


def _minimal_workbook() -> Workbook:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'Sheet1'
    sheet.append(HEADERS)
    sheet.append(['场景', '控制室', '控制室描述', '恐怖气氛主视角', '重点', None, 'maker'])
    return workbook


def test_real_asset_sample_has_frozen_counts_and_warnings() -> None:
    result = AssetExcelParser().parse(ASSET_SAMPLE.read_bytes())

    assert result.summary.model_dump(by_alias=True) == {
        'totalRows': 20,
        'validRows': 19,
        'warningRows': 3,
        'errorRows': 1,
        'distinctAssets': 12,
        'distinctAssetItems': 20,
        'byType': {
            'Character': {'assets': 6, 'items': 12, 'validRows': 11, 'warningRows': 0, 'errorRows': 1},
            'Environment': {'assets': 2, 'items': 4, 'validRows': 4, 'warningRows': 0, 'errorRows': 0},
            'Prop': {'assets': 4, 'items': 4, 'validRows': 4, 'warningRows': 3, 'errorRows': 0},
        },
        'estimatedAutoMatches': 0,
    }
    assert [warning.error_key for warning in result.workbook_warnings] == ['SG_IMPORT_READONLY_COLUMNS_IGNORED']
    warning_rows = [row.row_number for row in result.rows if row.warnings]
    assert warning_rows == [6, 7, 8]
    error_row = next(row for row in result.rows if row.errors)
    assert error_row.row_number == COMPOSITE_ASSIGNEE_ROW
    assert [issue.error_key for issue in error_row.errors] == ['SG_TASK_ASSIGNEE_AMBIGUOUS']


def test_merged_parent_cells_are_inherited_without_blind_forward_fill() -> None:
    result = AssetExcelParser().parse(ASSET_SAMPLE.read_bytes())
    by_row = {row.row_number: row for row in result.rows}

    assert by_row[2].normalized.asset_name == by_row[3].normalized.asset_name
    assert by_row[2].normalized.item_description == by_row[3].normalized.item_description
    assert by_row[18].normalized.asset_name == by_row[19].normalized.asset_name
    assert by_row[18].normalized.item_description != by_row[19].normalized.item_description

    workbook = _minimal_workbook()
    workbook.active.append([None, None, None, '第二分项'])
    parsed = AssetExcelParser().parse(_save_workbook(workbook))
    assert parsed.rows[1].normalized.asset_name is None
    assert {'SG_ASSET_TYPE_INVALID', 'SG_ASSET_NAME_REQUIRED'} <= {issue.error_key for issue in parsed.rows[1].errors}


def test_status_formula_and_columns_after_first_blank_header_are_ignored() -> None:
    workbook = _minimal_workbook()
    sheet = workbook.active
    sheet['F2'] = '=1+1'
    sheet['I1'] = '辅助列'
    sheet['I2'] = '=1+1'

    result = AssetExcelParser().parse(_save_workbook(workbook))

    assert result.summary.total_rows == 1
    assert result.rows[0].errors == []
    assert [warning.error_key for warning in result.workbook_warnings] == ['SG_IMPORT_READONLY_COLUMNS_IGNORED']


def test_hidden_sheets_add_one_workbook_warning() -> None:
    workbook = _minimal_workbook()
    workbook.create_sheet('隐藏1').sheet_state = 'hidden'
    workbook.create_sheet('隐藏2').sheet_state = 'hidden'

    result = AssetExcelParser().parse(_save_workbook(workbook))

    assert [warning.error_key for warning in result.workbook_warnings] == [
        'SG_IMPORT_HIDDEN_SHEETS_IGNORED',
        'SG_IMPORT_READONLY_COLUMNS_IGNORED',
    ]


def test_duplicate_production_item_is_rejected_across_sheets() -> None:
    workbook = _minimal_workbook()
    second = workbook.create_sheet('Sheet2')
    second.append(HEADERS)
    second.append(['Environment', '控制室', '另一描述', '恐怖气氛主视角'])

    result = AssetExcelParser().parse(_save_workbook(workbook))

    assert result.summary.error_rows == DUPLICATE_ROW_COUNT
    assert all(
        any(issue.error_key == 'SG_ASSET_PRODUCTION_ITEM_CONFLICT' for issue in row.errors) for row in result.rows
    )


def test_only_parent_columns_allow_single_column_vertical_merges() -> None:
    workbook = _minimal_workbook()
    sheet = workbook.active
    sheet.append(['场景', '第二资产', '描述', '分项'])
    sheet.merge_cells('B2:C2')

    with pytest.raises(ShotGridDomainException) as exc_info:
        AssetExcelParser().parse(_save_workbook(workbook))

    assert exc_info.value.error_key == 'SG_IMPORT_TEMPLATE_INVALID'


def test_row_limit_rejects_sparse_malicious_tail_before_full_scan() -> None:
    workbook = _minimal_workbook()
    workbook.active.cell(row=EXCEL_LAST_ROW, column=1, value='恶意尾行')

    with pytest.raises(ShotGridDomainException) as exc_info:
        AssetExcelParser(ShotGridImportConfig(max_rows_per_workbook=10)).parse(_save_workbook(workbook))

    assert exc_info.value.error_key == 'SG_IMPORT_ROW_LIMIT_EXCEEDED'


@pytest.mark.parametrize(
    ('column', 'value', 'field_name'),
    [
        ('B', 'İ' * 200, 'assetName'),
        ('D', 'İ' * 240, 'productionItem'),
        ('E', '备' * 501, 'remark'),
        ('G', '制' * 31, 'assigneeUserName'),
    ],
)
def test_values_and_casefold_keys_fit_database_lengths(column: str, value: str, field_name: str) -> None:
    workbook = _minimal_workbook()
    workbook.active[f'{column}2'] = value

    result = AssetExcelParser().parse(_save_workbook(workbook))

    assert any(
        issue.error_key == 'SG_IMPORT_FIELD_TOO_LONG' and issue.field_name == field_name
        for issue in result.rows[0].errors
    )


def test_commit_selection_is_composite_and_allows_partial_parent_group() -> None:
    request = AssetImportCommitRequestModel(
        importToken='token',
        selectedRows=[{'sheetName': 'Sheet1', 'rowNumber': 2}],
    )
    assert [row.key() for row in request.selected_rows] == [('Sheet1', 2)]

    with pytest.raises(ValueError):
        AssetImportCommitRequestModel(
            importToken='token',
            selectedRows=[
                {'sheetName': 'Sheet1', 'rowNumber': 2},
                {'sheetName': 'Sheet1', 'rowNumber': 2},
            ],
        )
