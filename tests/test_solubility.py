import sys
import types
import unittest
from unittest import mock

from pip_planner import solubility


class SolubilityTests(unittest.TestCase):
    def tearDown(self) -> None:
        solubility.predict_solubility.cache_clear()
        solubility._load_admet_ai_model.cache_clear()

    def test_reports_admet_ai_and_soltrannet_values(self) -> None:
        fake_admet_ai = types.ModuleType("admet_ai")
        fake_soltrannet = types.ModuleType("soltrannet")
        test_case = self

        class FakeADMETModel:
            def predict(self, smiles: str) -> dict[str, float]:
                test_case.assertTrue(smiles)
                return {"Solubility_AqSolDB": -1.25}

        def fake_predict(smiles: list[str], num_workers: int = 1):
            self.assertEqual(smiles, ["CCO"])
            self.assertEqual(num_workers, 0)
            return iter([(-0.75, "CCO", "")])

        fake_admet_ai.ADMETModel = FakeADMETModel
        fake_soltrannet.predict = fake_predict

        with mock.patch.dict(sys.modules, {"admet_ai": fake_admet_ai, "soltrannet": fake_soltrannet}):
            solubility.predict_solubility.cache_clear()
            solubility._load_admet_ai_model.cache_clear()
            results = list(solubility.predict_solubility("CCO"))

        by_method = {result["method"]: result for result in results}
        self.assertEqual(by_method["ADMET-AI v2"]["status"], "ok")
        self.assertEqual(by_method["ADMET-AI v2"]["value"], -1.25)
        self.assertEqual(by_method["ADMET-AI v2"]["property_name"], "Solubility_AqSolDB")
        self.assertEqual(by_method["SolTranNet"]["status"], "ok")
        self.assertEqual(by_method["SolTranNet"]["value"], -0.75)
        self.assertEqual(by_method["SolTranNet"]["property_name"], "SolTranNet")


if __name__ == "__main__":
    unittest.main()
