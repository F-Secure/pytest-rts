"""This module contains code for initializing the mapping database"""
from timeit import default_timer as timer

import coverage
import pytest
from _pytest.python import Function

from pytest_rts.utils.mappinghelper import TestrunData


class MapperPlugin:
    """Class to handle mapping database initialization"""

    def __init__(self, mappinghelper):
        """"Constructor calls database and Coverage.py initialization"""
        self.cov = coverage.Coverage(data_file=None)
        self.cov._warn_unimported_source = False
        self.mappinghelper = mappinghelper
        self.testfiles = {testfile[1] for testfile in self.mappinghelper.testfiles}
        self.test_func_lines = None

    def pytest_sessionstart(self, session):
        """Start SQLalchemy transaction before test loop"""
        del session
        self.mappinghelper.start_transaction()

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_protocol(self, item, nextitem):
        """Start coverage collection for each test function run and save data"""
        del nextitem
        if isinstance(item, Function):
            start = timer()
            self.cov.erase()
            self.cov.start()
            yield
            self.cov.stop()
            end = timer()
            elapsed = round(end - start, 4)

            testrun_data = TestrunData(
                pytest_item=item,
                elapsed_time=elapsed,
                coverage_data=self.cov.get_data(),
                found_testfiles=self.testfiles,
                test_function_lines=self.test_func_lines,
            )
            self.mappinghelper.save_testrun_data(testrun_data)
        else:
            yield

    def pytest_sessionfinish(self, session):
        """End SQLalchemy transaction after test loop"""
        del session
        self.mappinghelper.end_transaction()