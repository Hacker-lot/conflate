import io
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from conflate.compiler import ConflateError, Runner, parse_program


class ContractParserTests(unittest.TestCase):
    def test_parses_typed_inputs_and_outputs(self):
        blocks = parse_program(
            "@python(in: seed: int, scale: float; out: answer: int)\n"
            "answer = seed\n"
        )
        self.assertEqual(blocks[0].inputs, {"seed": "int", "scale": "float"})
        self.assertEqual(blocks[0].outputs, {"answer": "int"})

    def test_bare_and_empty_markers_are_distinct(self):
        blocks = parse_program("@python\nx = 1\n@python()\ny = 2\n")
        self.assertIsNone(blocks[0].inputs)
        self.assertIsNone(blocks[0].outputs)
        self.assertEqual(blocks[1].inputs, {})
        self.assertEqual(blocks[1].outputs, {})

    def test_rejects_unknown_contract_type_with_location(self):
        with self.assertRaisesRegex(ConflateError, r"program\.cfl:1: unsupported contract type"):
            parse_program("@python(in: seed: number)\n", "program.cfl")


class PythonContractTests(unittest.TestCase):
    def run_source(self, source):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "program.cfl"
            path.write_text(source, encoding="utf-8")
            runner = Runner(path)
            runner.run()
            return runner.state

    def test_imports_only_declared_values_and_preserves_previous_state(self):
        state = self.run_source(
            "@python\n"
            "seed = 40\n"
            "hidden = 99\n"
            "@python(in: seed: int; out: answer: int)\n"
            "answer = seed + 2\n"
            "@python\n"
            "assert answer == 42\n"
            "assert hidden == 99\n"
        )
        self.assertEqual(state["answer"], 42)
        self.assertEqual(state["hidden"], 99)

    def test_contract_cannot_read_undeclared_shared_value(self):
        with self.assertRaisesRegex(ConflateError, r"Python block failed: name 'hidden' is not defined"):
            self.run_source(
                "@python\nhidden = 99\n"
                "@python(out: answer: int)\n"
                "answer = hidden\n"
            )

    def test_rejects_bool_for_int_and_invalid_output(self):
        with self.assertRaisesRegex(ConflateError, r"input `seed` expected int, got bool"):
            self.run_source(
                "@python\nseed = True\n"
                "@python(in: seed: int; out: answer: int)\nanswer = seed\n"
            )
        with self.assertRaisesRegex(ConflateError, r"missing required output `answer`"):
            self.run_source(
                "@python\nseed = 1\n"
                "@python(in: seed: int; out: answer: int)\nseed += 1\n"
            )

    def test_same_name_can_be_input_and_output(self):
        state = self.run_source(
            "@python\ntotal = 40\n"
            "@python(in: total: int; out: total: int)\n"
            "total += 2\n"
        )
        self.assertEqual(state["total"], 42)

    def test_undeclared_mutation_does_not_change_preserved_state(self):
        state = self.run_source(
            "@python\nvalues = {'items': [1]}\n"
            "@python(in: values: dict; out: answer: int)\n"
            "values['items'].append(2)\nanswer = 42\n"
        )
        self.assertEqual(state["values"], {"items": [1]})
        self.assertEqual(state["answer"], 42)

    def test_tuple_does_not_satisfy_list_output(self):
        with self.assertRaisesRegex(ConflateError, r"output `answer` expected list, got tuple"):
            self.run_source(
                "@python(out: answer: list)\nanswer = (1, 2)\n"
            )

    def test_cyclic_output_has_boundary_diagnostic(self):
        with self.assertRaisesRegex(ConflateError, r"output `answer` is not a finite portable value"):
            self.run_source(
                "@python(out: answer: any)\nanswer = []\nanswer.append(answer)\n"
            )

    def test_undeclared_cyclic_local_does_not_block_valid_output(self):
        state = self.run_source(
            "@python(out: answer: int)\n"
            "temporary = []\n"
            "temporary.append(temporary)\n"
            "answer = 42\n"
        )
        self.assertEqual(state, {"answer": 42})


@unittest.skipUnless(shutil.which("g++"), "g++ is required")
class NativeContractTests(unittest.TestCase):
    def test_cpp_imports_and_exports_only_declared_values(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "program.cfl"
            path.write_text(
                "@python\nseed = 40\nhidden = 99\n"
                "@cpp(in: seed: int; out: answer: int)\n"
                "int answer = seed.as<int>() + 2;\n"
                "auto scratch = []() { return 7; };\n"
                "@python\nassert answer == 42\nassert hidden == 99\n"
                "try:\n    scratch\nexcept NameError:\n    pass\nelse:\n    raise AssertionError('scratch leaked')\n",
                encoding="utf-8",
            )
            runner = Runner(path)
            runner.run()
            self.assertEqual(runner.state, {"seed": 40, "hidden": 99, "answer": 42})


if __name__ == "__main__":
    unittest.main()
