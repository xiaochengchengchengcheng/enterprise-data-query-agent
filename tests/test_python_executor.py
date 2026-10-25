import os
import unittest
from unittest import mock

from python_executor import PythonExecutor, UnsafePythonCode, validate_python_code


class PythonExecutorTest(unittest.TestCase):
    def test_rejects_system_access(self):
        with self.assertRaises(UnsafePythonCode):
            validate_python_code('import os\nos.system("whoami")')

    def test_rejects_open(self):
        with self.assertRaises(UnsafePythonCode):
            validate_python_code('open("secret.txt").read()')

    def test_rejects_dataframe_file_io(self):
        with self.assertRaises(UnsafePythonCode):
            validate_python_code('import pandas as pd\ndf = pd.read_csv("secret.csv")')

    def test_local_execution_requires_explicit_opt_in(self):
        with mock.patch.dict(os.environ, {'ALLOW_LOCAL_PYTHON_EXECUTION': 'false'}):
            with self.assertRaises(PermissionError):
                PythonExecutor('local').execute('analysis_result={"ok": True}', [])

    def test_local_execution_contract(self):
        code = '''
import pandas as pd
values = df["value"].tolist()
analysis_result = {"total": int(df["value"].sum()), "count": len(values)}
charts = [{"series": [{"type": "bar", "data": values}]}]
'''
        with mock.patch.dict(os.environ, {'ALLOW_LOCAL_PYTHON_EXECUTION': 'true'}):
            result = PythonExecutor('local').execute(code, [{'value': 2}, {'value': 3}])
        self.assertEqual(result['analysis_result']['total'], 5)
        self.assertEqual(len(result['charts']), 1)


if __name__ == '__main__':
    unittest.main()
