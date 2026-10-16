"""Exercise SVG box assembly, geometry, motion preferences, and ownership."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

BOX_SCRIPT = Path(__file__).parents[1] / "src/omphalos/ui/box.js"

HARNESS = r"""
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const pending = new Map(), targets = [];
let now = 0, frameId = 0;
class Target {
  constructor() { this.listeners = new Map(); targets.push(this); }
  addEventListener(type, callback) { if (!this.listeners.has(type)) this.listeners.set(type, new Set()); this.listeners.get(type).add(callback); }
  removeEventListener(type, callback) { this.listeners.get(type)?.delete(callback); }
  emit(type) { for (const callback of [...(this.listeners.get(type) || [])]) callback(); }
}
class Element extends Target {
  constructor(name) { super(); this.name = name; this.attributes = {}; this.style = {}; this.children = []; this.textContent = ''; }
  setAttribute(name, value) { assert.notEqual(name, 'style', 'SVG rendering must respect the application CSP.'); this.attributes[name] = String(value); }
  getAttribute(name) { return this.attributes[name] ?? null; }
  removeAttribute(name) { delete this.attributes[name]; }
  append(...children) { for (const child of children) { child.remove(); child.parent = this; this.children.push(child); } }
  remove() { if (this.parent) this.parent.children = this.parent.children.filter((child) => child !== this); this.parent = null; }
}
const document = new Target(), window = new Target(), motion = new Target(), scene = new Element('div');
document.createElementNS = (_, name) => new Element(name);
document.hidden = false; motion.matches = false;
window.matchMedia = () => motion;
window.requestAnimationFrame = (callback) => { pending.set(++frameId, callback); return frameId; };
window.cancelAnimationFrame = (id) => pending.delete(id);
vm.runInNewContext(fs.readFileSync(process.argv[1], 'utf8'), {window, document});
const titles = ['Records', 'Sources', 'Plan', 'Findings', 'Assessment', 'Package'];
const faces = (count) => titles.map((title, index) => ({title, value: '—', complete: index < count, available: index <= count}));
const mount = (count = 0) => window.OmphalosBox.mount(scene, {faces: faces(count), selected: Math.min(count, 5)});
function all(node, name) { return [...(node.name === name ? [node] : []), ...node.children.flatMap((child) => all(child, name))]; }
function panel(index) { return all(scene, 'g').find((node) => node.getAttribute('data-face') === String(index)); }
function points(index) { return panel(index).children[0].getAttribute('points').split(' ').map((point) => point.split(',').map(Number)); }
function moving() { return [0,1,2,3,4,5].filter((index) => panel(index).getAttribute('data-fold-state') === 'folding'); }
function advance(steps = 1, interval = 50) {
  for (let step = 0; step < steps; step += 1) { now += interval; const callbacks = [...pending.values()]; pending.clear(); callbacks.forEach((callback) => callback(now)); }
}
function finish() { for (let step = 0; pending.size && step < 200; step += 1) advance(); assert.equal(pending.size, 0); }
function assertHinges() {
  const base = points(0), left = points(1), back = points(2), right = points(3), front = points(4), lid = points(5);
  assert.deepEqual(left[0], base[0]); assert.deepEqual(left[3], base[3]);
  assert.deepEqual(back[0], base[0]); assert.deepEqual(back[1], base[1]);
  assert.deepEqual(right[0], base[1]); assert.deepEqual(right[1], base[2]);
  assert.deepEqual(front[0], base[3]); assert.deepEqual(front[1], base[2]);
  assert.deepEqual(lid[0], back[3]); assert.deepEqual(lid[1], back[2]);
}
function assertReleased() {
  assert.equal(pending.size, 0); assert.equal(scene.children.length, 0);
  assert.equal(targets.reduce((count, target) => count + [...target.listeners.values()].reduce((sum, callbacks) => sum + callbacks.size, 0), 0), 0);
}
function color(value) { return value.startsWith('#') ? [1,3,5].map(offset => parseInt(value.slice(offset, offset + 2), 16)) : value.match(/[\d.]+/g).map(Number); }
function linear(color) { return color.map(channel => { const value = channel / 255; return value <= .04045 ? value / 12.92 : ((value + .055) / 1.055) ** 2.4; }); }
function luminance(color) { const value = linear(color); return value[0] * .2126 + value[1] * .7152 + value[2] * .0722; }
function contrast(left, right) { const a = luminance(left), b = luminance(right); return (Math.max(a, b) + .05) / (Math.min(a, b) + .05); }
function pigment(index) { return all(scene, 'radialGradient').find(node => node.getAttribute('id').endsWith(`-face-${index}`)).children.map(stop => color(stop.getAttribute('stop-color'))); }
function reflectedPigment(index, text) {
  const overlay = panel(index).children.find(node => node.getAttribute('class') === 'box-iridescence');
  const amount = Number(overlay.getAttribute('opacity'));
  const fields = all(scene, 'radialGradient').filter(node => /-reflection-\d+$/.test(node.getAttribute('id')));
  const x = Number(text.getAttribute('x')), y = Number(text.getAttribute('y'));
  const size = Number(text.getAttribute('font-size')), half = text.textContent.length * size * .54 / 2;
  const blend = (left, right, opacity) => left.map((channel, axis) => Math.round(channel + (right[axis] - channel) * opacity));
  return pigment(index).flatMap(base => [-half, 0, half].flatMap(dx => [-size/2, 0, size/2].flatMap(dy => {
    let result = base;
    for (const field of fields) {
      const distance = Math.hypot(x + dx - Number(field.getAttribute('cx')), y + dy - Number(field.getAttribute('cy')));
      const ratio = Math.min(1, distance / Number(field.getAttribute('r')));
      const stops = field.children;
      const end = stops.findIndex((stop, offset) => offset && Number(stop.getAttribute('offset')) >= ratio);
      const from = stops[end - 1], to = stops[end];
      const progress = (ratio - Number(from.getAttribute('offset'))) / (Number(to.getAttribute('offset')) - Number(from.getAttribute('offset')));
      const opacity = Number(from.getAttribute('stop-opacity')) + (Number(to.getAttribute('stop-opacity')) - Number(from.getAttribute('stop-opacity'))) * progress;
      result = blend(result, color(from.getAttribute('stop-color')), opacity);
    }
    result = blend(base, result, amount);
    return index === 5 ? [result, blend(result, [248,252,255], .3), blend(result, [101,119,137], .18)] : [result];
  })));
}
__SCENARIO__
"""


def run_scenario(scenario: str) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required for SVG renderer tests")
    result = subprocess.run(
        [node, "-e", HARNESS.replace("__SCENARIO__", scenario), str(BOX_SCRIPT)],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_existing_complete_case_mounts_assembled_and_lid_closes_exactly() -> None:
    run_scenario(r"""
const controller = mount(6);
assert.equal(pending.size, 0, 'Reopening a case must not replay its assembly.');
for (let index = 1; index < 6; index += 1) assert.equal(panel(index).getAttribute('data-fold-state'), 'folded');
assertHinges();
assert.deepEqual(points(5)[2], points(4)[2]);
assert.deepEqual(points(5)[3], points(4)[3]);
assert.match(all(scene, 'svg')[0].getAttribute('aria-label'), /Package: complete/);
controller.destroy(); assertReleased();
""")


def test_completion_folds_one_panel_at_a_time_in_workflow_order() -> None:
    run_scenario(r"""
const controller = mount(1), order = [];
controller.update(faces(6), 5);
for (let step = 0; pending.size && step < 100; step += 1) {
  advance(); assertHinges();
  const active = moving(); assert.ok(active.length <= 1, 'Only one hinge moves at a time.');
  if (active.length && order.at(-1) !== active[0]) order.push(active[0]);
  for (let face = 0; face < 6; face += 1) for (const [x, y] of points(face)) {
    assert.ok(Number.isFinite(x) && Number.isFinite(y));
    assert.ok(x >= 20 && x <= 580 && y >= 20 && y <= 410, 'Every folding panel stays inside the fixed viewport.');
  }
}
assert.deepEqual(order, [1, 2, 3, 4, 5]); assert.equal(pending.size, 0);
assert.equal(panel(0).getAttribute('data-fold-state'), 'flat', 'Records is the base, not a sixth artificial hinge.');
controller.destroy(); assertReleased();
""")


def test_invalidating_work_unfolds_lid_and_walls_in_reverse_order() -> None:
    run_scenario(r"""
const controller = mount(6), order = [];
controller.update(faces(1), 0);
for (let step = 0; pending.size && step < 100; step += 1) {
  advance(); assertHinges(); const active = moving();
  assert.ok(active.length <= 1);
  if (active.length && order.at(-1) !== active[0]) order.push(active[0]);
}
assert.deepEqual(order, [5, 4, 3, 2, 1]); assert.equal(pending.size, 0);
controller.destroy(); assertReleased();
""")


def test_interrupted_fold_reverses_from_its_visible_position_without_a_jump() -> None:
    run_scenario(r"""
const controller = mount(1);
controller.update(faces(2), 1); advance(5);
const visible = [0,1,2,3,4,5].map(points);
controller.update(faces(1), 0);
assert.deepEqual([0,1,2,3,4,5].map(points), visible);
finish(); assertHinges();
assert.equal(panel(1).getAttribute('data-fold-state'), 'flat');
controller.destroy(); assertReleased();
""")


def test_panel_color_follows_its_own_fold_and_step_identity_survives_completion() -> (
    None
):
    run_scenario(r"""
const controller = mount(1);
const initial = [0,1,2,3,4,5].map(pigment);
const labels = ['I Records', 'II Sources', 'III Plan', 'IV Findings', 'V Assessment', 'VI Package'];
controller.update(faces(6), 5);
for (let index = 1; index < 6; index += 1) assert.deepEqual(pigment(index), initial[index], 'Completion must not recolor every queued panel at once.');
advance(5);
assert.notDeepEqual(pigment(1), initial[1]);
for (let index = 2; index < 6; index += 1) assert.deepEqual(pigment(index), initial[index]);
const interrupted = pigment(1);
controller.update(faces(1), 0);
assert.deepEqual(pigment(1), interrupted, 'A reversed fold must keep its current color.');
finish();
assert.deepEqual(pigment(1), initial[1]);
controller.update(faces(6), 5); finish();
for (let index = 0; index < 6; index += 1) {
  const label = panel(index).children.at(-1);
  const numeral = labels[index].split(' ')[0];
  assert.ok([titles[index], ''].includes(label.textContent));
  const marker = panel(index).children.find(child => child.getAttribute('class') === 'box-panel-step');
  assert.equal(marker.children[1].textContent, numeral);
  assert.equal(marker.children[2].getAttribute('opacity'), '1');
  assert.ok(label.getAttribute('clip-path'), 'Labels stay within their own folded panels.');
  if (index > 0 && index < 5) assert.notDeepEqual(pigment(index), initial[index]);
}
assert.deepEqual(pigment(5), initial[5], 'VI remains pearl before and after completion.');
controller.destroy(); assertReleased();
""")


def test_stage_panels_keep_their_hue_until_the_verified_package_finish() -> None:
    run_scenario(r"""
const first = mount(0), unfinished = [0,1,2,3,4,5].map(pigment);
first.destroy();
const second = mount(5), completed = [0,1,2,3,4,5].map(pigment);
// Machado et al. (2009) severity-0.5 transforms are a regression model,
// not a diagnosis or a promise of individual color discrimination.
const models = [
  [[1,0,0],[0,1,0],[0,0,1]],
  [[.458064,.679578,-.137642],[.092785,.846313,.060902],[-.007494,-.016807,1.024301]],
  [[.547494,.607765,-.155259],[.181692,.781742,.036566],[-.010410,.027275,.983136]],
];
const lightness = (rgb, matrix = models[0]) => {
  const source = linear(rgb);
  const transformed = matrix.map(row => Math.max(0, Math.min(1, row.reduce((sum, coefficient, index) => sum + coefficient * source[index], 0))));
  const y = transformed[0] * .2126 + transformed[1] * .7152 + transformed[2] * .0722;
  return y > (6 / 29) ** 3 ? 116 * Math.cbrt(y) - 16 : y * (29 / 3) ** 3;
};
for (let index = 0; index < 5; index += 1) {
  const light = unfinished[index].at(-1), dark = completed[index].at(-1);
  assert.ok(lightness(light) >= 65, 'Unfinished material stays light.');
  assert.ok(lightness(dark) >= 40 && lightness(dark) <= 75, 'Complete material has medium depth, not black or pastel white.');
  for (const model of models) assert.ok(lightness(light, model) - lightness(dark, model) >= 15, 'Completion changes shade even in red-green vision simulations.');
  for (const stops of [unfinished[index], completed[index]]) {
    assert.ok(lightness(stops[0]) - lightness(stops.at(-1)) <= 6, 'The gentle reflection must not wash each panel to the same white.');
    for (const stop of stops) assert.ok(Math.max(...stop) - Math.min(...stop) >= 35, 'Surfaces keep chroma instead of becoming neutral gray.');
  }
}
assert.deepEqual(unfinished[5], completed[5], 'VI keeps its cool pearl base from the beginning.');
assert.deepEqual(unfinished[5].at(-1), [220,228,237]);
assert.equal(new Set(unfinished.map(stops => stops.at(-1).join(','))).size, 6);
assert.equal(new Set(completed.map(stops => stops.at(-1).join(','))).size, 6);
second.destroy(); assertReleased();
""")


def test_label_and_marker_contrast_survives_every_fold_and_reverse() -> None:
    run_scenario(r"""
const controller = mount(0);
function checkContrast() {
  for (let index = 0; index < 6; index += 1) {
    const group = panel(index), title = group.children.at(-1);
    const marker = group.children.find(child => child.getAttribute('class') === 'box-panel-step');
    const [ring, numeral, check] = marker.children;
    const ringFill = color(ring.getAttribute('fill')), opacity = Number(ring.getAttribute('fill-opacity'));
    for (const text of [title, numeral, check]) for (const background of reflectedPigment(index, text)) {
      const surface = text === numeral ? background.map((value, channel) => value + (ringFill[channel] - value) * opacity) : background;
      const halo = text.style.stroke;
      if (halo !== 'none') {
        assert.ok(contrast(color(text.getAttribute('fill')), color(halo)) >= 4.5, 'A fine outline must contrast with its lettering.');
        assert.ok(parseFloat(text.style.strokeWidth) <= 1.2, 'Contrast protection must stay close to the glyphs.');
      } else assert.ok(contrast(color(text.getAttribute('fill')), surface) >= 4.5, `Stage ${index} lettering must meet 4.5:1 over the actual reflected pigment.`);
    }
  }
}
checkContrast(); controller.update(faces(6), 5); checkContrast();
for (let step = 0; pending.size && step < 300; step += 1) { advance(1, 1000 / 60); checkContrast(); }
assert.equal(pending.size, 0);
controller.update(faces(0), 0);
for (let step = 0; pending.size && step < 300; step += 1) { advance(1, 1000 / 60); checkContrast(); }
assert.equal(pending.size, 0);
controller.destroy(); assertReleased();
""")


def test_package_finish_stays_on_its_plane_without_cutting_out_the_caption() -> None:
    run_scenario(r"""
const controller = mount(0);
const finishLayers = all(scene, 'g').filter(node => node.getAttribute('class') === 'box-package-finish');
assert.equal(finishLayers.length, 1, 'Only the Package lid gets the special finish.');
assert.equal(finishLayers[0].parent, panel(5));
assert.equal(finishLayers[0].getAttribute('pointer-events'), 'none');
assert.equal(finishLayers[0].getAttribute('mask'), null);
assert.equal(all(scene, 'mask').length, 0, 'The continuous material must not leave a blank spot behind the caption.');
assert.equal(all(scene, 'pattern').filter(node => node.getAttribute('id').endsWith('-package-weave')).length, 1);
assert.equal(all(scene, 'animate').length, 0);
function checkFinish() {
  const matrix = finishLayers[0].children[0].getAttribute('transform').match(/[-+\d.e]+/g).map(Number);
  const transformed = [[0,0], [260,0], [260,180], [0,180]].map(([x,y]) => [matrix[0]*x + matrix[2]*y + matrix[4], matrix[1]*x + matrix[3]*y + matrix[5]]);
  for (let corner = 0; corner < 4; corner += 1) for (let axis = 0; axis < 2; axis += 1)
    assert.ok(Math.abs(transformed[corner][axis] - points(5)[corner][axis]) < .001, 'Engraving must stay attached to the lid at every angle.');
}
checkFinish(); controller.update(faces(6), 5);
while (pending.size) { advance(); checkFinish(); }
assert.equal(pending.size, 0, 'The special finish never adds idle animation.');
controller.update(faces(0), 0);
while (pending.size) { advance(); checkFinish(); }
controller.destroy(); assertReleased();
""")


def test_verified_package_shares_one_continuous_reflection_across_the_box() -> None:
    run_scenario(r"""
const controller = mount(5);
const stagePigments = [0,1,2,3,4,5].map(pigment);
const reflection = index => panel(index).children.find(node => node.getAttribute('class') === 'box-iridescence');
const fill = reflection(5).getAttribute('fill');
const field = all(scene, 'pattern').find(node => node.getAttribute('id') === fill.slice(5, -1));
assert.equal(field.getAttribute('patternUnits'), 'userSpaceOnUse');
assert.equal(field.getAttribute('width'), '600');
assert.equal(field.getAttribute('height'), '430');
assert.equal(field.children.length, 4, 'Separated violet, cyan, rose, and amber pools form one reflection.');
for (let index = 0; index < 6; index += 1) {
  assert.equal(reflection(index).getAttribute('fill'), fill, 'Every face samples the same field instead of restarting its own rainbow.');
  assert.equal(reflection(index).getAttribute('opacity'), index === 5 ? '1' : '0');
}
controller.update(faces(5), 5);
assert.equal(pending.size, 0, 'Viewing Package must not finish the box.');
assert.deepEqual([0,1,2,3,4,5].map(pigment), stagePigments);
for (let index = 0; index < 5; index += 1) assert.equal(reflection(index).getAttribute('opacity'), '0');
controller.update(faces(6), 5); advance(5);
assert.ok(Number(reflection(0).getAttribute('opacity')) > 0 && Number(reflection(0).getAttribute('opacity')) < 1);
assert.notDeepEqual(pigment(0), stagePigments[0], 'The last fold transitions the stage pigment into pearl.');
assert.notDeepEqual(pigment(0), stagePigments[5], 'The whole-box material transitions rather than jumping to its finished base.');
finish();
for (let index = 0; index < 6; index += 1) {
  assert.equal(reflection(index).getAttribute('opacity'), '1');
  assert.deepEqual(pigment(index), stagePigments[5], 'Every finished side must have exactly the same cool pearl base, with no stage-color patches.');
  assert.equal(reflection(index).getAttribute('points'), panel(index).children[0].getAttribute('points'), 'The reflection is clipped to its panel.');
  assert.equal(reflection(index).getAttribute('transform'), null, 'The shared field remains in one coordinate system across seams.');
}
controller.update(faces(5), 4);
assert.deepEqual([0,1,2,3,4,5].map(pigment), stagePigments, 'Invalidating the export restores the stage pigments while VI stays pearl.');
for (let index = 0; index < 5; index += 1) assert.equal(reflection(index).getAttribute('opacity'), '0', 'An invalidated export must remove the whole-box finish.');
assert.equal(reflection(5).getAttribute('opacity'), '1');
finish(); controller.destroy(); assertReleased();
""")


@pytest.mark.parametrize("stop", ["reduced_motion", "hidden"])
def test_motion_preferences_settle_to_current_work_without_background_animation(
    stop: str,
) -> None:
    run_scenario(r"""
const controller = mount(1);
controller.update(faces(6), 5); advance(4);
if (STOP === 'reduced_motion') { motion.matches = true; motion.emit('change'); }
else { document.hidden = true; document.emit('visibilitychange'); }
assert.equal(pending.size, 0);
for (let index = 1; index < 6; index += 1) assert.equal(panel(index).getAttribute('data-fold-state'), 'folded');
controller.update(faces(1), 0);
assert.equal(pending.size, 0);
for (let index = 1; index < 6; index += 1) assert.equal(panel(index).getAttribute('data-fold-state'), 'flat');
controller.destroy(); assertReleased();
""".replace("STOP", repr(stop)))


def test_selecting_completed_work_does_not_unfold_it_and_future_panels_are_inert() -> (
    None
):
    run_scenario(r"""
const controller = mount(3), before = [0,1,2,3,4,5].map(points);
controller.update(faces(3), 0);
assert.deepEqual([0,1,2,3,4,5].map(points), before); assert.equal(pending.size, 0);
assert.equal(panel(0).getAttribute('data-flow'), 'cube');
assert.equal(panel(3).getAttribute('data-flow'), 'cube');
assert.equal(panel(5).getAttribute('data-flow'), null);
controller.destroy(); assertReleased();
""")


def test_remount_and_destroy_release_every_listener_and_pending_frame() -> None:
    run_scenario(r"""
const first = mount(1); first.update(faces(6), 5); advance(3);
const second = mount(1);
assert.equal(scene.children.length, 1); assert.equal(pending.size, 0);
first.destroy(); first.update(faces(6), 5);
assert.equal(scene.children.length, 1);
second.update(faces(6), 5); advance(); second.destroy(); second.destroy();
advance(); assertReleased();
""")
