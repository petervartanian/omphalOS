"""Package completion means a verified artifact for the exact latest review."""

from pathlib import Path

from test_case_review import case_review
from test_workflow import workspace as workspace

from omphalos.runner import Workspace
from omphalos.util import read_json, write_json


def test_package_completion_requires_current_review_and_survives_reopen(workspace):
    run_id = workspace.run_case("case-1")["run_id"]
    run = workspace.get_run(run_id)
    assert run["latest_export"] is None
    first = workspace.save_review(run_id, case_review(run))
    assert workspace.get_run(run_id)["latest_export"] is None
    exported = workspace.export_run(run_id)
    retained = Workspace(workspace.root).get_run(run_id)["latest_export"]
    assert retained == {
        "name": exported["name"],
        "download_url": "/api/exports/" + exported["name"],
    }
    workspace.save_review(run_id, case_review(run, "escalate"))
    assert workspace.get_run(run_id)["latest_export"] is None
    workspace.export_run(run_id, review_id=first["review_id"])
    assert workspace.get_run(run_id)["latest_export"] is None
    current = workspace.export_run(run_id)
    assert workspace.get_run(run_id)["latest_export"]["name"] == current["name"]
    Path(current["path"]).write_bytes(b"damaged package")
    assert workspace.get_run(run_id)["latest_export"] is None


def test_package_completion_rejects_pointer_to_another_review(workspace):
    run_id = workspace.run_case("case-1")["run_id"]
    run = workspace.get_run(run_id)
    workspace.save_review(run_id, case_review(run))
    old_export = workspace.export_run(run_id)
    pointer_path = workspace.root / "exports" / f"{run_id}-latest.json"
    old_pointer = read_json(pointer_path)
    latest = workspace.save_review(run_id, case_review(run, "escalate"))
    # Updating a pointer cannot turn a prior decision's valid ZIP into a package
    # for the current decision, even when its hash still verifies.
    write_json(pointer_path, {**old_pointer, "review_id": latest["review_id"]})
    assert Path(old_export["path"]).exists()
    assert workspace.get_run(run_id)["latest_export"] is None
