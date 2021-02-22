"""Code for pytest-rts plugin logic"""
import logging

import pytest
from sqlalchemy_utils import database_exists

from pytest_rts.connection import DB_FILE_NAME, MappingConn
from pytest_rts.pytest.init_phase_plugin import InitPhasePlugin
from pytest_rts.pytest.normal_phase_plugin import NormalPhasePlugin
from pytest_rts.pytest.update_phase_plugin import UpdatePhasePlugin
from pytest_rts.utils.git import (
    get_current_head_hash,
    is_git_repo,
    repo_has_commits,
)
from pytest_rts.utils.selection import (
    get_tests_and_data_committed,
    get_tests_and_data_current,
)
from pytest_rts.utils.mappinghelper import MappingHelper
from pytest_rts.utils.testgetter import TestGetter


def pytest_addoption(parser):
    """Register pytest flags"""
    group = parser.getgroup("pytest-rts")
    group.addoption("--rts", action="store_true", default=False, help="run rts")
    group.addoption(
        "--rts-db-conn",
        action="store",
        default="",
        help="database connection string",
    )


def pytest_configure(config):
    """Register RTS plugins based on state"""
    logger = logging.getLogger()
    logging.basicConfig(format="%(message)s", level=logging.INFO)

    if not config.option.rts:
        return

    if not is_git_repo():
        logger.info(
            "Not a git repository! pytest-rts is disabled. Run git init before using pytest-rts."
        )
        return

    if not repo_has_commits():
        logger.info(
            "No commits yet! pytest-rts is disabled. Create a git commit before using pytest-rts."
        )
        return

    config.option.rts_db_conn = (
        f"sqlite:///{DB_FILE_NAME}"
        if not config.option.rts_db_conn
        else config.option.rts_db_conn
    )

    init_required = not database_exists(config.option.rts_db_conn)

    mapping_helper = MappingHelper(MappingConn.engine(config.option.rts_db_conn))
    test_getter = TestGetter(MappingConn.engine(config.option.rts_db_conn))

    if init_required:
        logger.info("No mapping database detected, starting initialization...")
        config.pluginmanager.register(
            InitPhasePlugin(mapping_helper), "rts-init-plugin"
        )
        return

    workdir_data = get_tests_and_data_current(mapping_helper, test_getter)

    logger.info("WORKING DIRECTORY CHANGES")
    logger.info("Found %s changed test files", workdir_data.changed_testfiles_amount)
    logger.info("Found %s changed src files", workdir_data.changed_srcfiles_amount)
    logger.info("Found %s tests to execute\n", len(workdir_data.test_set))

    if workdir_data.test_set:
        logger.info(
            "Running WORKING DIRECTORY test set and exiting without updating..."
        )
        config.pluginmanager.register(
            NormalPhasePlugin(workdir_data.test_set, test_getter)
        )
        return

    logger.info("No WORKING DIRECTORY tests to run, checking COMMITTED changes...")

    current_hash = get_current_head_hash()
    previous_hash = mapping_helper.last_update_hash
    if current_hash == previous_hash:
        pytest.exit("Database is updated to the current commit state", 0)

    logger.info("Comparison: %s\n", " => ".join([current_hash, previous_hash]))

    committed_data = get_tests_and_data_committed(mapping_helper, test_getter)

    logger.info("COMMITTED CHANGES")
    logger.info("Found %s changed test files", committed_data.changed_testfiles_amount)
    logger.info("Found %s changed src files", committed_data.changed_srcfiles_amount)
    logger.info(
        "Found %s newly added tests",
        committed_data.new_tests_amount,
    )
    logger.info("Found %s tests to execute\n", len(committed_data.test_set))

    if committed_data.warning_needed:
        logger.info(
            "WARNING: New lines were added to the following files but no new tests discovered:"
        )
        logger.info("\n".join(committed_data.files_to_warn))

    logger.info("=> Executing tests (if any) and updating database")
    mapping_helper.set_last_update_hash(current_hash)

    mapping_helper.update_mapping(committed_data.update_data)

    if committed_data.test_set:
        config.pluginmanager.register(
            UpdatePhasePlugin(committed_data.test_set, mapping_helper, test_getter)
        )
        return

    pytest.exit("No tests to run", 0)


def pytest_unconfigure(config):
    """Cleanup after pytest run"""
    if config.option.rts:
        MappingConn.engine(config.option.rts_db_conn).dispose()
