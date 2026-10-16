"""Exercise folding-box integration without substituting for visual browser QA."""

from test_guided_frontend import run_guided


def test_box_renderer_survives_workflow_renders_so_folds_are_not_restarted() -> None:
    run_guided(r"""
  let attachedScene = null, mounts = 0, updates = 0, destroys = 0;
  const originalMarkup = Object.getOwnPropertyDescriptor(Element.prototype, 'innerHTML');
  Object.defineProperty(main, 'innerHTML', {
    get() {return originalMarkup.get.call(this);},
    set(value) {
      originalMarkup.set.call(this, value);
      attachedScene = new Element('.box-scene');
      attachedScene.replaceWith = (retained) => {attachedScene = retained;};
    },
  });
  main.querySelector = (selector) => selector === '.box-scene' ? attachedScene : null;
  window.OmphalosBox = {mount(scene, options) {
    assert.equal(scene, attachedScene);
    assert.equal(options.faces.length, 6);
    mounts += 1;
    return {update(faces, selected) {
      updates += 1;
      assert.equal(faces.length, 6);
      assert.ok(Number.isInteger(selected));
    }, destroy() {destroys += 1;}};
  }};
  run('renderGuided()');
  const retained = attachedScene;
  run('model.flow.busyStep = "Preparing checks"; renderGuided();');
  run('model.flow.busyStep = ""; model.flow.cubeFace = 2; renderGuided();');
  assert.equal(mounts, 1, 'Workflow updates must not recreate the folding object.');
  assert.equal(updates, 2);
  assert.equal(attachedScene, retained, 'The animated geometry is reattached in the same render.');
  assert.equal(destroys, 0);
  navigate('overview');
  assert.equal(destroys, 1, 'Leaving the investigation releases the renderer.');
""")


def test_new_box_exposes_only_records_and_cannot_be_freely_rotated() -> None:
    run_guided(r"""
  run('model.flow = newFlow(); model.run = null; model.selectedRun = ""; renderGuided();');
  const markup = run('flowCube()');
  assert.ok(markup.includes('Investigation box'));
  assert.ok(!markup.includes('Drag to rotate'));
  const steps = [...markup.matchAll(/<button\b[^>]*aria-label="Open [^"]+"[^>]*>/g)].map(match => match[0]);
  assert.equal(steps.length, 6);
  assert.ok(!steps[0].includes('disabled'));
  assert.ok(steps.slice(1).every(step => step.includes('disabled')));
  const before = run('model.navigationVersion');
  click(flowButton('cube', {face: '5'}));
  assert.equal(run('model.flow.cubeFace'), 0);
  assert.equal(run('model.navigationVersion'), before);
  assert.equal(main.listeners.get('pointermove'), undefined, 'Free cube gestures are no longer part of the box workflow.');
""")
