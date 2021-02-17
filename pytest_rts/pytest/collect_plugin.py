"""This module contains code for collecting newly added tests"""
# pylint: disable=too-few-public-methods
from pytest_rts.connection import MappingConn
from pytest_rts.utils.testgetter import TestGetter


class CollectPlugin:
    """Plugin class for pytest to collect newly added tests"""

    def __init__(self):
        """Query existing test functions from database before collection"""
        self.collected = set()
        self.testgetter = TestGetter(MappingConn.session())
        self.existing_tests = self.testgetter.existing_tests
        self.testgetter.delete_newly_added_tests()

    def pytest_collection_modifyitems(self, session, config, items):
        """Select tests that have not been previously seen"""
        del session, config
        for item in items:
            if item.nodeid not in self.existing_tests:
                self.collected.add(item.nodeid)
        self.testgetter.set_newly_added_tests(self.collected)
        MappingConn.session().commit()
        MappingConn.session().close()
