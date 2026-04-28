from __future__ import annotations

import unittest
from pathlib import Path

from core.api.app.services.parsers import parse_csv_file
from tests.helpers import workspace_tempdir


class ParserTests(unittest.TestCase):
    def test_parse_rchb_file_creates_budget_facts(self) -> None:
        content = "\n".join(
            [
                "министерство финансов Амурской области;;;;;;;;;;;;;;;;;;;;;",
                ";;;;",
                "на 01.09.2025 г.;;;;",
                "Бюджет;Дата проводки;КФСР;Наименование КФСР;КЦСР;Наименование КЦСР;КВР;Наименование КВР;КВСР;Наименование КВСР;КОСГУ;Наименование КОСГУ;Код цели;Наименование Код цели;КВФО;Наименование КВФО;Источник средств;Лимиты ПБС 2025 год;Подтв. лимитов по БО 2025 год;Подтв. лимитов без БО 2025 год;Остаток лимитов 2025 год;Всего выбытий (бух.уч.)",
                "Бюджет города Благовещенска;19.06.2025;05.02;Коммунальное хозяйство;03.2.01.61058;Мероприятие;8.1.2;Субсидии;002;Администрация города Благовещенска;0.0.0;НЕ УКАЗАНО;ОБ-136-3;Код цели;1;Бюджетная деятельность;Региональные средства;1 600 000,00;840 000,00;100 000,00;760 000,00;620 000,00",
            ]
        )

        with workspace_tempdir() as directory:
            path = Path(directory) / "август2025.csv"
            path.write_text(content, encoding="utf-8-sig")

            parsed = parse_csv_file(path, "1. РЧБ/август2025.csv", "rchb")

        self.assertEqual(len(parsed.raw_rows), 1)
        self.assertEqual({fact["metric"] for fact in parsed.budget_facts}, {
            "limits",
            "obligations",
            "obligations_without_bo",
            "remaining_limits",
            "cash_payments",
        })
        self.assertEqual(parsed.budget_facts[0]["budget_name"], "Бюджет города Благовещенска")

    def test_parse_agreements_file_creates_agreements_and_facts(self) -> None:
        content = (
            "period_of_date,documentclass_id,budget_id,caption,document_id,close_date,reg_number,"
            "main_close_date,main_reg_number,amount_1year,dd_estimate_caption,dd_recipient_caption,"
            "kadmr_code,kfsr_code,kcsr_code,kvr_code,dd_purposefulgrant_code,kesr_code,kdr_code,kde_code,kdf_code,dd_grantinvestment_code\n"
            "2025-01-01 - 2026-04-01,273,1,Областной бюджет,121,2025-03-07 00:00:00.000,01-39-4662,"
            "2025-03-07 00:00:00.000,01-39-4662,10000000.00,,Получатель,911,0502,0520197002,540,ОБ-1,000,000,000,000,\n"
        )

        with workspace_tempdir() as directory:
            path = Path(directory) / "01012025-01042026.csv"
            path.write_text(content, encoding="utf-8-sig")

            parsed = parse_csv_file(path, "2. Соглашения/01012025-01042026.csv", "agreements")

        self.assertEqual(len(parsed.agreements), 1)
        self.assertEqual(len(parsed.budget_facts), 1)
        self.assertEqual(parsed.budget_facts[0]["metric"], "agreement_amount")
        self.assertEqual(parsed.agreements[0]["reg_number"], "01-39-4662")

    def test_parse_gz_files(self) -> None:
        with workspace_tempdir() as directory:
            root = Path(directory)

            contracts_path = root / "Контракты и договора.csv"
            contracts_path.write_text(
                "con_document_id,con_number,con_date,con_amount,zakazchik_key\n"
                "9598856,Ф.2025.0003,2025-10-17 00:00:00.000,1821173.90,1401000010706\n",
                encoding="utf-8-sig",
            )
            contracts = parse_csv_file(contracts_path, "3. ГЗ/Контракты и договора.csv", "gz")

            lines_path = root / "Бюджетные строки.csv"
            lines_path.write_text(
                "con_document_id,kfsr_code,kcsr_code,kvr_code,kesr_code,kvsr_code,kdf_code,kde_code,kdr_code,kif_code,purposefulgrant\n"
                "9598856,0502,101016105Б,414,000,007,000,000,000,1,ОБ-136-4\n",
                encoding="utf-8-sig",
            )
            lines = parse_csv_file(lines_path, "3. ГЗ/Бюджетные строки.csv", "gz")

            payments_path = root / "Платежки.csv"
            payments_path.write_text(
                "con_document_id,platezhka_paydate,platezhka_key,platezhka_num,platezhka_amount\n"
                "9598856,2025-05-15 00:00:00.000,1401053980155,1158,2682663.14\n",
                encoding="utf-8-sig",
            )
            payments = parse_csv_file(payments_path, "3. ГЗ/Платежки.csv", "gz")

        self.assertEqual(len(contracts.contracts), 1)
        self.assertEqual(contracts.budget_facts[0]["metric"], "contract_amount")
        self.assertEqual(len(lines.contract_budget_lines), 1)
        self.assertEqual(len(payments.payments), 1)
        self.assertEqual(payments.budget_facts[0]["metric"], "contract_payment")

    def test_parse_buau_file_creates_institution_payments_and_facts(self) -> None:
        content = (
            "Бюджет;Дата проводки;КФСР;КЦСР;КВР;КОСГУ;Код субсидии;Отраслевой код;КВФО;Организация;Орган, предоставляющий субсидии;Выплаты с учетом возврата;Выплаты - Исполнение;Выплаты - Восстановление выплат - год\n"
            "Бюджет г. Тынды;20.08.2025;0409;0220197003;243;225;2222097003;000;5;МБУ;АДМИНИСТРАЦИЯ;44 622 636,12;44 622 636,12;0,00\n"
        )

        with workspace_tempdir() as directory:
            path = Path(directory) / "хакатон БУАУ август 2025.csv"
            path.write_text(content, encoding="utf-8-sig")

            parsed = parse_csv_file(path, "4. Выгрузка БУАУ/хакатон БУАУ август 2025.csv", "buau")

        self.assertEqual(len(parsed.institution_payments), 1)
        self.assertEqual(len(parsed.budget_facts), 2)
        self.assertEqual(
            {fact["metric"] for fact in parsed.budget_facts},
            {"institution_payments_with_refund", "institution_payments_execution"},
        )


if __name__ == "__main__":
    unittest.main()
