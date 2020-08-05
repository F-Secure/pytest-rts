import os
import sqlite3
import subprocess
import sys
import random

from tests_selector.helper import (
    get_test_lines_and_update_lines,
    start_test_init,
    get_testfiles_and_srcfiles,
    run_tests_and_update_db,
    get_git_repo,
    tests_from_changes_between_commits,
    read_newly_added_tests
)

PIPE = subprocess.PIPE

PROJECT_FOLDER = sys.argv[1]


def iterate_commits():
    # builds database by going through commits and running specific tests
    # problem: different dependencies
    repo = get_git_repo(PROJECT_FOLDER)
    git_commits = list(repo.get_list_commits())

    print(f"repo has {len(git_commits)} commits")
    start = int(input("start commit?"))
    end = int(input("end commit?"))

    hash_1 = git_commits[start].hash
    repo.checkout(hash_1)
    start_test_init(PROJECT_FOLDER)

    for commit in git_commits[start + 1 : end]:
        hash_2 = commit.hash
        repo.checkout(hash_2)
        change_test_set, update_tuple = tests_from_changes_between_commits(hash_1, hash_2,PROJECT_FOLDER)
        new_tests = read_newly_added_tests(PROJECT_FOLDER)
        final_test_set = change_test_set.union(new_tests)
        run_tests_and_update_db(final_test_set, update_tuple,PROJECT_FOLDER)
        hash_1 = commit.hash

    repo._delete_tmp_branch()


def random_remove_test(iterations):
    # Delete random line, run tests, store exit codes of pytest if possible
    repo = get_git_repo(PROJECT_FOLDER)
    git_helper = repo.repo.git

    ans = input("init db? [y/n]: ")
    if ans == "y":
        start_test_init(PROJECT_FOLDER)

    test_files, src_files = get_testfiles_and_srcfiles()
    conn = sqlite3.connect("results.db")
    c = conn.cursor()
    c.execute(
        "CREATE TABLE IF NOT EXISTS data (specific_exit INTEGER, all_exit INTEGER)"
    )

    for i in range(iterations):
        while True:
            random_src = random.choice(src_files)
            src_name = random_src[1]
            src_id = random_src[0]
            if "tests-selector" not in src_name: #for now some tests-selector runners get mapped to source files by accident
                break
        try:
            with open(os.getcwd() + "/" + PROJECT_FOLDER + "/" + src_name, "r") as f:
                data = f.readlines()
                rand_line = random.randint(0, len(data) - 1)
                data[rand_line] = "\n" # replace random line with newline.
        except FileNotFoundError:
            continue
        with open(os.getcwd() + "/" + PROJECT_FOLDER + "/" + src_name, "w") as f:
            for line in data:
                f.write(line)

        git_diff_data = git_helper.diff("-U0","--",src_name)
        test_lines, updates_to_lines = get_test_lines_and_update_lines(git_diff_data)
        tests = query_tests_sourcefile(test_lines, src_id)

        # run specific tests and capture exit code
        try:
            specific_exit_code = int(
                str(
                    subprocess.run(
                        ["tests_selector_specific_without_remap", PROJECT_FOLDER]
                        + tests,
                        capture_output=True,
                        timeout=60,
                    ).stdout,
                    "utf-8",
                ).strip()
            )
        except (subprocess.TimeoutExpired,ValueError) as e:
            specific_exit_code = -1

        #run all tests and capture exit code
        try:
            all_exit_code = int(
                str(
                    subprocess.run(
                        ["tests_selector_all_without_remap", PROJECT_FOLDER],
                        capture_output=True,
                        timeout=60,
                    ).stdout,
                    "utf-8",
                ).strip()
            )
        except (subprocess.TimeoutExpired,ValueError) as e:
            all_exit_code = -1

        data_tuple = (specific_exit_code, all_exit_code)
        c.execute("INSERT INTO data VALUES (?,?)", data_tuple)
        conn.commit()
        print("result:", "specific_exit_code:", data_tuple[0],"all_exit_code:",data_tuple[1],"iteration:", i + 1)
        git_helper.restore(src_name)
    
    conn.close()

def main():
    
    ans = input("Iterate commits [1] or remove random lines and run tests [2] ?")
    if ans == "1":
        iterate_commits()
    elif ans == "2":
        print("This will randomly remove a src file line and run specific tests and compare it to all of the tests")
        print("Exit codes of test runs will be stored to database")
        ans = input("how many iterations? ")
        iters = int(ans)
        random_remove_test(iters)
    

if __name__ == "__main__":
    main()