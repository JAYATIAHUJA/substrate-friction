import pytest

from friction import baselines as B
from friction.swebench import Instance


PATCH = """diff --git a/a.py b/a.py
--- a/a.py
+++ b/a.py
@@ -1,3 +1,4 @@
 x = 1
+y = 2
@@ -20,2 +21,2 @@
-z = 3
+z = 4
diff --git a/b.py b/b.py
--- a/b.py
+++ b/b.py
@@ -1,1 +1,2 @@
+q = 9
"""


def inst(patch=PATCH, statement="boom", f2p=("t1", "t2")):
    return Instance("i1", "django/django", "abc", statement, patch, "", list(f2p), [])


def test_counts_files_and_hunks():
    f = B.extract(inst())
    assert f.patch_files == 2
    assert f.patch_hunks == 3


def test_counts_changed_lines_not_context():
    assert B.extract(inst()).patch_lines == 4


def test_counts_fail_to_pass():
    assert B.extract(inst()).f2p_count == 2


def test_statement_length_and_traceback_flag():
    f = B.extract(inst(statement="Traceback (most recent call last):\n  File x"))
    assert f.statement_chars > 0
    assert f.statement_has_traceback is True


def test_no_traceback_flag_when_absent():
    assert B.extract(inst(statement="please fix")).statement_has_traceback is False


def test_table_reports_one_auc_per_feature():
    xs = [inst(statement="x" * i, f2p=tuple(f"t{j}" for j in range(i))) for i in range(1, 11)]
    xs = [Instance(f"i{i}", "r", "c", s.problem_statement, s.patch, "", s.fail_to_pass, [])
          for i, s in enumerate(xs)]
    failed = {x.instance_id: (i > 4) for i, x in enumerate(xs)}
    t = B.table(xs, failed)
    assert {"patch_lines", "patch_files", "patch_hunks", "f2p_count",
            "statement_chars"} <= set(t)
    assert all(0.0 <= v <= 1.0 or v != v for v in t.values())
