import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import PatternFill

from modules.excel_reconcile import (
    _date_sort_key,
    extract_date_from_name,
    merge_and_reconcile_excel,
)
from modules.settings_store import FilenameMappingRule


def create_inspect(path: Path, quantities):
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["A", "B", "C", "D", "E", "Packed quantity", "Double"])
    sheet.column_dimensions["A"].width = 24
    for index, quantity in enumerate(quantities, 1):
        row = sheet.max_row + 1
        sheet.append([f"row-{index}", "merged", "", "", "", quantity, f"=F{row}*2"])
        sheet.merge_cells(start_row=row, start_column=2, end_row=row, end_column=3)
        sheet.row_dimensions[row].height = 28
        sheet.cell(row, 1).fill = PatternFill("solid", fgColor="DDEBF7")
    workbook.save(path)


def create_droplist(path: Path, quantities):
    workbook = Workbook()
    first = workbook.active
    first.title = "Cover"
    data = workbook.create_sheet("Data")
    workbook.create_sheet("Summary")
    data.append([])
    data.append([])
    data.append(["S/O", "B", "C", "D", "E", "QTY"])
    for index, quantity in enumerate(quantities, 1):
        data.append([f"row-{index}", "", "", "", "", quantity])
    data.append(["Total", "", "", "", "", sum(quantities)])
    workbook.save(path)


def create_droplist_with_ignored_sheet1(path: Path, quantities, ignored_quantities):
    workbook = Workbook()
    workbook.active.title = "9.10"
    data = workbook.create_sheet("无类型和日期")
    ignored = workbook.create_sheet("Sheet1")
    workbook.create_sheet("Address")
    for sheet, values in ((data, quantities), (ignored, ignored_quantities)):
        sheet.append([])
        sheet.append([])
        sheet.append(["S/O", "B", "C", "D", "E", "QTY"])
        for index, quantity in enumerate(values, 1):
            sheet.append([f"row-{index}", "", "", "", "", quantity])
        sheet.append(["Total", "", "", "", "", sum(values)])
    workbook.save(path)


def create_droplist_with_business_end_gap(path: Path):
    workbook = Workbook()
    workbook.active.title = "Cover"
    data = workbook.create_sheet("Data")
    headers = ["S/O", "Line", "P/N", "Company", "Country", "QTY", "Amount", "Currency",
               "Gross Weight", "Box", "By", "AWB", "Delivery", "Shipment", "Freight", "BOX", "Note"]
    data.append([])
    data.append([])
    data.append(headers)
    data.append(["SO-1", "10", "P1", "A", "US", 5, 1, "USD", 10, "B1", "UPS"])
    # A-D still contain values, but I-K are blank: this is the business end marker.
    data.append(["footer", "x", "x", "x", "", 999, "", "", "", "", ""])
    data.append(["SO-2", "20", "P2", "B", "US", 7, 1, "USD", 11, "B2", "UPS"])
    workbook.save(path)


class ExcelReconcileTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.inspect = self.root / "inspect"
        self.droplist = self.root / "droplist"
        self.inspect.mkdir()
        self.droplist.mkdir()
        self.rules = [
            FilenameMappingRule("澳车", "光联", note="光联业务", display_type="澳车"),
            FilenameMappingRule("814S", "MPO", display_type="814S"),
            FilenameMappingRule("光联", "光联", display_type="光联"),
            FilenameMappingRule("MPO", "MPO", display_type="MPO"),
        ]

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_date_parser_supports_year_and_month_day(self):
        self.assertEqual(((2026, 9, 10), "2026/9/10"), extract_date_from_name("9.10光联.xlsx"))
        self.assertEqual(
            ((2026, 9, 10), "2026/9/10"),
            extract_date_from_name("2026-09-10 MPO.xlsx"),
        )
        self.assertEqual(((0, 0, 0), ""), extract_date_from_name("unknown.xlsx"))
        self.assertEqual(((2026, 9, 10), "2026/9/10"), extract_date_from_name("9.10"))
        self.assertLess(_date_sort_key("2026/9/17"), _date_sort_key("2026/9/18"))

    def test_merge_and_reconcile_outputs_traceable_sheets(self):
        create_inspect(self.inspect / "9.10 澳车.xlsx", [10, 20])
        create_inspect(self.inspect / "9.10 814S.xlsx", [5])
        day = self.droplist / "9.10"
        day.mkdir()
        create_droplist(day / "Drop shipment list9.10光联.xlsx", [30])
        create_droplist(day / "Drop shipment list9.10MPO.xlsx", [4])
        output = self.root / "output"
        progress = []

        result = merge_and_reconcile_excel(
            self.inspect,
            self.droplist,
            output,
            self.rules,
            progress.append,
        )

        self.assertEqual(2, result.inspect_files)
        self.assertEqual(2, result.droplist_files)
        self.assertEqual(3, result.inspect_rows)
        self.assertEqual(2, result.droplist_rows)
        by_type = {row.target_type: row for row in result.rows}
        self.assertEqual("一致", by_type["光联"].result)
        self.assertEqual(0, by_type["光联"].difference)
        self.assertEqual("不一致", by_type["MPO"].result)
        self.assertEqual(1, by_type["MPO"].difference)
        self.assertEqual([45, 80, 100], progress)

        self.assertEqual(output / "合并检验表.xlsx", result.inspect_output_file)
        self.assertEqual(output / "合并Droplist.xlsx", result.droplist_output_file)
        self.assertTrue(result.droplist_output_file.is_file())
        workbook = load_workbook(result.inspect_output_file, data_only=False)
        self.assertEqual(
            ["合并检验表", "类型箱数", "核对汇总", "异常文件"],
            workbook.sheetnames,
        )
        self.assertEqual("类型", workbook["合并检验表"][1][7].value)
        self.assertEqual("归总类别", workbook["合并检验表"][1][8].value)
        inspect_rows = list(workbook["合并检验表"].iter_rows(min_row=2, values_only=True))
        guanglian = next(row for row in inspect_rows if row[7] == "澳车")
        self.assertEqual("光联", guanglian[8])
        self.assertEqual("光联业务", guanglian[11])
        self.assertFalse(workbook["核对汇总"].sheet_view.showGridLines)
        self.assertGreaterEqual(workbook["核对汇总"].column_dimensions["F"].width, 12)
        self.assertEqual("#,##0", workbook["核对汇总"].cell(2, 3).number_format)
        type_rows = list(
            workbook["类型箱数"].iter_rows(min_row=2, values_only=True)
        )
        self.assertIn(("2026/9/10", "澳车", 30, "光联"), type_rows)
        self.assertIn(("2026/9/10", "814S", 5, "MPO"), type_rows)
        self.assertFalse(workbook["类型箱数"].sheet_view.showGridLines)

        merged_sheet = workbook["合并检验表"]
        self.assertEqual(24, merged_sheet.column_dimensions["A"].width)
        self.assertEqual(28, merged_sheet.row_dimensions[2].height)
        self.assertEqual("00DDEBF7", merged_sheet["A2"].fill.fgColor.rgb)
        self.assertIn("B2:C2", {str(item) for item in merged_sheet.merged_cells.ranges})
        # 第二个文件的数据被追加到后续行，公式引用必须同步平移。
        self.assertEqual("=F3*2", merged_sheet["G3"].value)

    def test_unmatched_files_are_kept_and_reported(self):
        unknown = self.inspect / "9.11 未知客户.xlsx"
        create_inspect(unknown, [7])
        unknown_book = load_workbook(unknown)
        unknown_book.active["A2"] = "UNKNOWN-ONLY"
        unknown_book.save(unknown)
        create_droplist(
            self.droplist / "Drop shipment list9.11MPO.xlsx",
            [7],
        )
        output = self.inspect
        result = merge_and_reconcile_excel(
            self.inspect,
            self.droplist,
            output,
            self.rules,
        )
        self.assertTrue(any(issue[0] == "检验表" for issue in result.issues))
        self.assertFalse(any(row.target_type == "未识别" for row in result.rows))
        self.assertEqual((self.inspect / "9.11 未知客户.xlsx",), result.unrecognized_files)
        summary = load_workbook(result.inspect_output_file)["核对汇总"]
        self.assertGreaterEqual(summary.column_dimensions["F"].width, 12)

        # 第二次运行时不得把第一次输出再次当成输入。
        second = merge_and_reconcile_excel(
            self.inspect,
            self.droplist,
            output,
            self.rules,
        )
        self.assertEqual(1, second.inspect_files)

    def test_overseas_numbered_truck_defaults_to_guanglian(self):
        source = self.inspect / "9.12 国外出货第6车.xlsx"
        create_inspect(source, [8])
        workbook = load_workbook(source)
        workbook.active.cell(20, 1).fill = PatternFill("solid", fgColor="FFFFFF")
        workbook.save(source)
        create_droplist(
            self.droplist / "Drop shipment list9.12光联.xlsx",
            [8],
        )

        result = merge_and_reconcile_excel(
            self.inspect,
            self.droplist,
            self.root / "output",
            self.rules,
        )

        row = next(item for item in result.rows if item.target_type == "光联")
        self.assertEqual("一致", row.result)
        self.assertFalse(any(issue[1] == source.name for issue in result.issues))
        merged = load_workbook(result.inspect_output_file)["合并检验表"]
        self.assertEqual("光联", merged.cell(2, 8).value)
        self.assertEqual("光联", merged.cell(2, 9).value)
        self.assertEqual(2, merged.max_row)

    def test_droplist_uses_headers_and_ignores_sheet1_and_empty_files(self):
        create_inspect(self.inspect / "9.10 MPO国外EI自提.xlsx", [12])
        day = self.droplist / "9.10"
        day.mkdir()
        create_droplist_with_ignored_sheet1(
            day / "Drop shipment list without date MPO.xlsx",
            [12],
            [999],
        )
        Workbook().save(day / "Drop shipment list empty MPO.xlsx")

        result = merge_and_reconcile_excel(
            self.inspect,
            self.droplist,
            self.root / "output",
            self.rules,
        )

        self.assertEqual(1, result.droplist_files)
        self.assertEqual(1, result.droplist_rows)
        mpo = next(
            row for row in result.rows
            if row.target_type == "MPO" and row.date == "2026/9/10"
        )
        self.assertEqual("2026/9/10", mpo.date)
        self.assertEqual(12, mpo.droplist_quantity)
        self.assertEqual("一致", mpo.result)
        self.assertTrue(any("empty" in issue[1] for issue in result.issues))
        self.assertTrue(any(
            "2026-9-10" in issue[1] for issue in result.issues if "empty" in issue[1]
        ))

    def test_droplist_infers_date_and_category_from_ancestor_folder(self):
        day = self.droplist / "2026.9.22 MPO"
        day.mkdir()
        create_droplist(day / "Drop shipment list.xlsx", [9])
        result = merge_and_reconcile_excel(
            None, self.droplist, self.root / "output", self.rules
        )
        row = result.rows[0]
        self.assertEqual("2026/9/22", row.date)
        self.assertEqual("MPO", row.target_type)
        merged = load_workbook(result.droplist_output_file)["合并Droplist"]
        headers = {cell.value: cell.column for cell in merged[1]}
        source_values = [
            merged.cell(row_index, headers["来源文件"]).value
            for row_index in range(2, merged.max_row + 1)
        ]
        self.assertTrue(any("2026-9-22-MPO" in str(value) for value in source_values))

    def test_ambiguous_droplist_is_unrecognized_and_not_counted(self):
        day = self.droplist / "9.23"
        day.mkdir()
        create_droplist(day / "Drop shipment list.xlsx", [4])
        result = merge_and_reconcile_excel(
            None, self.droplist, self.root / "output", self.rules
        )
        self.assertEqual((), result.rows)
        self.assertEqual((day / "Drop shipment list.xlsx",), result.unrecognized_files)
        self.assertTrue(any("未计入光联或 MPO" in issue[2] for issue in result.issues))

    def test_droplist_stops_when_columns_i_to_k_are_empty(self):
        day = self.droplist / "9.24 MPO"
        day.mkdir()
        create_droplist_with_business_end_gap(day / "Drop shipment list.xlsx")
        result = merge_and_reconcile_excel(
            None, self.droplist, self.root / "output", self.rules
        )
        self.assertEqual(1, result.droplist_rows)
        self.assertEqual(5, result.rows[0].droplist_quantity)

    def test_inspect_and_droplist_can_run_independently(self):
        create_inspect(self.inspect / "9.10 澳车.xlsx", [10])
        inspect_result = merge_and_reconcile_excel(
            self.inspect,
            None,
            self.root / "inspect-output",
            self.rules,
        )
        self.assertTrue(inspect_result.inspect_output_file.is_file())
        self.assertIsNone(inspect_result.droplist_output_file)
        self.assertEqual(10, inspect_result.rows[0].inspect_quantity)
        self.assertIsNone(inspect_result.rows[0].droplist_quantity)
        self.assertIsNone(inspect_result.rows[0].difference)
        self.assertEqual("仅检验表统计", inspect_result.rows[0].result)

        create_droplist(
            self.droplist / "Drop shipment list9.10MPO.xlsx",
            [6],
        )
        droplist_result = merge_and_reconcile_excel(
            None,
            self.droplist,
            self.root / "droplist-output",
            self.rules,
        )
        self.assertIsNone(droplist_result.inspect_output_file)
        self.assertTrue(droplist_result.droplist_output_file.is_file())
        self.assertIsNone(droplist_result.rows[0].inspect_quantity)
        self.assertEqual(6, droplist_result.rows[0].droplist_quantity)
        self.assertEqual("仅 Droplist 统计", droplist_result.rows[0].result)
        workbook = load_workbook(droplist_result.droplist_output_file)
        self.assertEqual(["合并Droplist", "核对汇总", "异常文件"], workbook.sheetnames)

    def test_merge_requires_at_least_one_input_folder(self):
        with self.assertRaisesRegex(ValueError, "至少选择一个"):
            merge_and_reconcile_excel(None, None, self.root / "output", self.rules)

    def test_later_inspection_file_extra_column_is_preserved_before_metadata(self):
        create_inspect(self.inspect / "9.17 国外第一车.xlsx", [2])
        wider = self.inspect / "9.17 国外第三车.xlsx"
        create_inspect(wider, [3])
        source = load_workbook(wider)
        source.active.cell(1, 8, "COO")
        source.active.cell(2, 8, "CN")
        source.active.cell(2, 8).fill = PatternFill("solid", fgColor="FFF2CC")
        source.save(wider)
        result = merge_and_reconcile_excel(
            self.inspect, None, self.root / "output", self.rules
        )
        merged = load_workbook(result.inspect_output_file)["合并检验表"]
        self.assertEqual("COO", merged.cell(1, 8).value)
        self.assertEqual("类型", merged.cell(1, 9).value)
        self.assertEqual("CN", merged.cell(3, 8).value)
        self.assertEqual("00FFF2CC", merged.cell(3, 8).fill.fgColor.rgb)
        self.assertTrue(any("已保留全部原始列" in issue[2] for issue in result.issues))

    def test_samples_prevent_bondex_substring_misclassification(self):
        inspect_file = self.inspect / "9.25 Bondex深圳自提.xlsx"
        create_inspect(inspect_file, [1])
        inspect_book = load_workbook(inspect_file)
        inspect_book.active["A2"] = "MPO-AWB-777"
        inspect_book.save(inspect_file)

        day = self.droplist / "9.25 MPO"
        day.mkdir()
        droplist_file = day / "Drop shipment list.xlsx"
        create_droplist(droplist_file, [1])
        droplist_book = load_workbook(droplist_file)
        droplist_book["Data"]["A4"] = "MPO-AWB-777"
        droplist_book.save(droplist_file)

        conflicting_rules = self.rules + [
            FilenameMappingRule("Bondex深圳自提", "光联", display_type="Bondex"),
            FilenameMappingRule("MPO Bondex深圳自提", "MPO", display_type="Bondex"),
        ]
        result = merge_and_reconcile_excel(
            self.inspect, self.droplist, self.root / "output", conflicting_rules
        )

        # The content sample says MPO while the shorter filename rule says 光联.
        # Conflict protection sends the file to review instead of forcing either.
        self.assertEqual((inspect_file,), result.unrecognized_files)
        self.assertTrue(any("冲突" in issue[2] for issue in result.issues))


if __name__ == "__main__":
    unittest.main()
