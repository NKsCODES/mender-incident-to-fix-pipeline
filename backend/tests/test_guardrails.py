from mender import guardrails
from mender.config import ServiceConfig
from mender.sandbox import Change

SVC = ServiceConfig(name="s", repo=".")
OK = {"repro": "reproduced"}


def rules(diff="", changes=(), verification=OK, svc=SVC):
    return {v["rule"] for v in guardrails.check(diff, list(changes), svc, verification)}


def diff_adding(path, *lines):
    return f"--- a/{path}\n+++ b/{path}\n@@ -1 +1 @@\n" + "\n".join("+" + line for line in lines)


def test_clean_patch_passes():
    assert rules(diff_adding("app/x.py", "    if q == 0:", "        return 0"), [Change("app/x.py", "M", 2, 0)]) == set()


def test_broad_except_variants_blocked():
    for line in ["except:", "    except Exception:", "except Exception as exc:", "except (Exception):", "except BaseException:"]:
        assert "broad_except" in rules(diff_adding("a.py", line)), line


def test_specific_except_allowed():
    for line in ["except ValueError:", "except (KeyError, TypeError) as e:", "except ExceptionGroup:"]:
        assert "broad_except" not in rules(diff_adding("a.py", line)), line


def test_removed_lines_are_not_scanned():
    assert "broad_except" not in rules("--- a/a.py\n+++ b/a.py\n@@ -1 +0,0 @@\n-except Exception:")


def test_existing_test_modified_or_deleted_is_tampering():
    assert "test_tampering" in rules(changes=[Change("tests/test_a.py", "M", 1, 1)])
    assert "test_tampering" in rules(changes=[Change("tests/test_a.py", "D", 0, 9)])
    assert "test_tampering" not in rules(changes=[Change("tests/test_new.py", "A", 5, 0)])


def test_skip_marker_blocked():
    assert "skip_marker" in rules(diff_adding("tests/test_new.py", "@pytest.mark.skip(reason='flaky')"))
    assert "skip_marker" in rules(diff_adding("tests/test_new.py", "@pytest.mark.xfail"))


def test_forbidden_and_dependency_paths():
    assert "forbidden_path" in rules(changes=[Change(".github/workflows/ci.yml", "M", 1, 0)])
    assert "forbidden_path" in rules(changes=[Change("app/migrations/0002.py", "A", 3, 0)])
    assert "dependency_change" in rules(changes=[Change("requirements.txt", "M", 1, 0)])
    assert "dependency_change" in rules(changes=[Change("web/package.json", "M", 1, 0)])


def test_size_limits():
    assert "max_lines" in rules(changes=[Change("a.py", "M", 200, 0)])
    assert "max_files" in rules(changes=[Change(f"a{i}.py", "M", 1, 0) for i in range(7)])


def test_secret_detected():
    assert "secret" in rules(diff_adding("a.py", 'API_KEY = "abcd1234abcd1234abcd"'))
    assert "secret" not in rules(diff_adding("a.py", 'api_key = os.environ["KEY"]'))


def test_repro_states():
    assert "missing_regression_test" in rules(verification={"repro": "missing"})
    assert "test_does_not_reproduce" in rules(verification={"repro": "not_reproduced"})
    blocks = guardrails.blocking(guardrails.check("", [], SVC, {"repro": "missing"}))
    assert blocks == []  # a missing test warns, it does not block
