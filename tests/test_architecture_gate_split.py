"""Do not let missing private inputs hide genuine synthetic regressions.

These tests assert two *independent* claims: the public gate can pass with the
four exactly identified external pilots skipped, but private certification
cannot pass without their actual successful execution.
"""
import xml.etree.ElementTree as ET

import pytest

from scripts import architecture_validation as gate


def xml_report(path, statuses, ordinary="pass"):
    root = ET.Element("testsuites")
    suite = ET.SubElement(root, "testsuite")
    for classname, name in sorted(gate.EXTERNAL_TEST_IDS):
        status = statuses.get((classname, name))
        if status is None:
            continue
        case = ET.SubElement(suite, "testcase", classname=classname, name=name)
        if status != "pass":
            ET.SubElement(case, status, message="synthetic diagnostic only")
    if ordinary:
        case = ET.SubElement(suite, "testcase", classname="tests.synthetic", name="ordinary_case")
        if ordinary != "pass":
            ET.SubElement(case, ordinary, message="synthetic diagnostic only")
    ET.ElementTree(root).write(path, encoding="utf-8")


def observe(path, *, private=False, code=0):
    public = gate.test_status(code, path, allow_external_skips=not private)
    pilot = gate.external_pilot_acceptance(path)
    sections = {"full_pytest": public, "focused": {"status": "PASS"}, "external_pilots": pilot}
    return public, pilot, gate.development_gate_status(sections, private_fixtures=private)


def test_public_gate_approves_exact_disclosed_skips_not_private_certification(tmp_path):
    path = tmp_path / "results.xml"
    xml_report(path, {key: "skipped" for key in gate.EXTERNAL_TEST_IDS})
    public, pilot, acceptance = observe(path)
    assert public["status"] == acceptance == "PASS"
    assert len(public["skips"]) == 4 and public["unexpected_skips"] == []
    assert pilot["status"] == "BLOCKED" and set(pilot["outcomes"].values()) == {"SKIP"}
    _, _, private_gate = observe(path, private=True)
    assert private_gate == "FAIL"


def test_private_source_certification_requires_real_four_passing_cases(tmp_path):
    path = tmp_path / "results.xml"
    xml_report(path, {key: "pass" for key in gate.EXTERNAL_TEST_IDS})
    public, pilot, private_gate = observe(path, private=True)
    assert public["status"] == pilot["status"] == private_gate == "PASS"


@pytest.mark.parametrize("problem", ["unexpected_skip", "private_failure", "ordinary_failure", "missing_pilot", "duplicate_pilot", "pytest_nonzero", "missing_junit"])
def test_synthetic_gate_fails_closed_on_other_problems(tmp_path, problem):
    path = tmp_path / "results.xml"
    statuses = {key: "skipped" for key in gate.EXTERNAL_TEST_IDS}
    ordinary = "pass"
    code = 0
    if problem == "private_failure":
        statuses[next(iter(statuses))] = "failure"
    if problem == "missing_pilot":
        del statuses[next(iter(statuses))]
    if problem == "unexpected_skip":
        ordinary = "skipped"
    if problem == "ordinary_failure":
        ordinary = "failure"
    if problem == "pytest_nonzero":
        code = 1
    if problem != "missing_junit":
        xml_report(path, statuses, ordinary)
    if problem == "duplicate_pilot":
        tree = ET.parse(path)
        classname, name = next(iter(gate.EXTERNAL_TEST_IDS))
        ET.SubElement(tree.getroot()[0], "testcase", classname=classname, name=name)
        tree.write(path)
    public, pilot, acceptance = observe(path, code=code)
    assert acceptance == "FAIL"
    if problem == "unexpected_skip":
        assert len(public["unexpected_skips"]) == 1
    if problem == "missing_pilot":
        assert "NOT_RUN" in pilot["outcomes"].values()
    if problem == "duplicate_pilot":
        assert "DUPLICATE" in pilot["outcomes"].values()


def test_any_other_runnable_category_failure_blocks_a_public_merge(tmp_path):
    path = tmp_path / "results.xml"
    xml_report(path, {key: "skipped" for key in gate.EXTERNAL_TEST_IDS})
    full = gate.test_status(0, path, allow_external_skips=True)
    pilots = gate.external_pilot_acceptance(path)
    assert gate.development_gate_status({
        "full_pytest": full, "focused": {"status": "FAIL"}, "external_pilots": pilots,
    }) == "FAIL"


def test_public_success_never_requires_environment_or_private_zip_files(tmp_path, monkeypatch):
    for item in gate.FIXTURES.values():
        monkeypatch.delenv(item["environment"], raising=False)
    path = tmp_path / "results.xml"
    xml_report(path, {key: "skipped" for key in gate.EXTERNAL_TEST_IDS})
    assert observe(path)[2] == "PASS"
