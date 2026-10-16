'use strict';

(() => {
  const namespace = 'http://www.w3.org/2000/svg';
  const instances = new WeakMap();
  const palette = [
    { light: '#a6c8e8', complete: '#5a84af', sheen: [0.14, 0.08] },
    { light: '#83c3b8', complete: '#42978d', sheen: [0.11, 0.06] },
    { light: '#ffd4af', complete: '#d88b49', sheen: [0.1, 0.06] },
    { light: '#fff1a8', complete: '#ccae3b', sheen: [0.08, 0.04] },
    { light: '#f5bcd3', complete: '#cc7fa1', sheen: [0.1, 0.06] },
    { light: '#dce4ed', complete: '#dce4ed', sheen: [0, 0] },
  ].map((face) => ({ ...face, light: channels(face.light), complete: channels(face.complete) }));
  const darkInk = [11, 20, 32];
  const white = [255, 255, 255];
  const black = [0, 0, 0];
  const finishedBase = channels('#293246');
  const rainbow = [
    { color: '#aaa5ff', x: 430, y: 125, radius: 205 },
    { color: '#68dfea', x: 190, y: 265, radius: 205 },
    { color: '#f3a8d3', x: 420, y: 310, radius: 185 },
    { color: '#ffda93', x: 85, y: 70, radius: 170 },
  ].map((pool) => ({ ...pool, channels: channels(pool.color) }));
  const labelFontSize = 14;
  const minimumLabelSize = 11;
  const azimuth = (25 * Math.PI) / 180;
  const elevation = (55 * Math.PI) / 180;
  const projection = {
    cosAzimuth: Math.cos(azimuth),
    sinAzimuth: Math.sin(azimuth),
    cosElevation: Math.cos(elevation),
    sinElevation: Math.sin(elevation),
  };
  let nextId = 0;

  function element(name, attributes = {}) {
    const node = document.createElementNS(namespace, name);
    Object.entries(attributes).forEach(([key, value]) => node.setAttribute(key, String(value)));
    return node;
  }

  function channels(color) {
    return [1, 3, 5].map((offset) => Number.parseInt(color.slice(offset, offset + 2), 16));
  }

  function mix(from, to, amount) {
    return from.map((value, index) => Math.round(value + (to[index] - value) * amount));
  }

  function rgb(color) {
    return `rgb(${color.join(' ')})`;
  }

  function luminance(color) {
    const linear = color.map((channel) => {
      const value = channel / 255;
      return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
    });
    return linear[0] * 0.2126 + linear[1] * 0.7152 + linear[2] * 0.0722;
  }

  function contrast(left, right) {
    const a = luminance(left),
      b = luminance(right);
    return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
  }

  function reflectionField(defs, id) {
    const field = element('pattern', {
      id: `${id}-iridescence`,
      patternUnits: 'userSpaceOnUse',
      x: 0,
      y: 0,
      width: 600,
      height: 430,
    });
    rainbow.forEach((pool, index) => {
      const gradient = element('radialGradient', {
        id: `${id}-reflection-${index}`,
        gradientUnits: 'userSpaceOnUse',
        cx: pool.x,
        cy: pool.y,
        r: pool.radius,
        'color-interpolation': 'sRGB',
      });
      gradient.append(
        element('stop', { offset: 0, 'stop-color': pool.color, 'stop-opacity': 0.6 }),
        element('stop', { offset: 0.42, 'stop-color': pool.color, 'stop-opacity': 0.34 }),
        element('stop', { offset: 1, 'stop-color': pool.color, 'stop-opacity': 0 }),
      );
      defs.append(gradient);
      field.append(
        element('rect', { width: 600, height: 430, fill: `url(#${id}-reflection-${index})` }),
      );
    });
    defs.append(field);
    return `url(#${id}-iridescence)`;
  }

  function packageFinish(defs, id) {
    const weave = element('pattern', {
      id: `${id}-package-weave`,
      width: 18,
      height: 18,
      patternUnits: 'userSpaceOnUse',
    });
    const thread = 'M-9,9 Q0,-3 9,9 T27,9 M-9,9 Q0,21 9,9 T27,9';
    const relief = element('path', {
      d: thread,
      fill: 'none',
      stroke: '#f8fcff',
      'stroke-width': 0.6,
      'stroke-opacity': 0.3,
      transform: 'translate(0 0.7)',
    });
    const engraving = element('path', {
      d: thread,
      fill: 'none',
      stroke: '#657789',
      'stroke-width': 0.55,
      'stroke-opacity': 0.18,
    });
    weave.append(relief, engraving);
    defs.append(weave);
    const group = element('g', {
      class: 'box-package-finish',
      'pointer-events': 'none',
    });
    const plane = element('g');
    plane.append(
      element('rect', { width: 260, height: 180, fill: `url(#${id}-package-weave)` }),
      element('rect', {
        x: 8,
        y: 8,
        width: 244,
        height: 164,
        rx: 2,
        fill: 'none',
        stroke: '#f8fcff',
        'stroke-width': 0.7,
        'stroke-opacity': 0.34,
      }),
    );
    group.append(plane);
    return { group, plane };
  }

  function completionEngraving(defs, id) {
    const weave = element('pattern', {
      id: `${id}-completed-weave`,
      width: 22,
      height: 22,
      patternUnits: 'userSpaceOnUse',
    });
    const thread = 'M-11,11 Q0,-5 11,11 T33,11 M-11,11 Q0,27 11,11 T33,11';
    weave.append(
      element('path', {
        d: thread,
        fill: 'none',
        stroke: '#dae4ff',
        'stroke-width': 0.8,
        'stroke-opacity': 0.24,
        transform: 'translate(0 0.65)',
      }),
      element('path', {
        d: thread,
        fill: 'none',
        stroke: '#08111f',
        'stroke-width': 0.55,
        'stroke-opacity': 0.3,
      }),
    );
    defs.append(weave);
    return `url(#${id}-completed-weave)`;
  }

  function paintMaterial(node, index, filled, finished) {
    if (node.paintedFill === filled && node.paintedFinish === finished) return;
    node.paintedFill = filled;
    node.paintedFinish = finished;
    const face = palette[index];
    const base = mix(face.light, face.complete, filled);
    let reflection = face.sheen[0] + (face.sheen[1] - face.sheen[0]) * filled;
    let highlight = mix(base, white, reflection);
    const ink =
      contrast(base, darkInk) >= 4.5 ? darkInk : contrast(base, black) >= 4.5 ? black : white;
    // Keep a stage's reflection legible while its pigment crosses midtones.
    if (ink === white && contrast(highlight, ink) < 4.5) {
      let low = 0,
        high = reflection;
      for (let iteration = 0; iteration < 12; iteration += 1) {
        const middle = (low + high) / 2;
        if (contrast(mix(base, white, middle), ink) >= 4.5) low = middle;
        else high = middle;
      }
      reflection = low;
      highlight = mix(base, white, reflection);
    }
    node.materialColors = [highlight, mix(base, highlight, 0.28), base].map((color) =>
      mix(color, finishedBase, finished),
    );
    node.materialColors.forEach((color, stop) => {
      node.stops[stop].setAttribute('stop-color', rgb(color));
    });
  }

  function paintCaption(node, amount, center, width, stacked) {
    const backgrounds = [];
    for (const dx of [-width / 2, 0, width / 2]) {
      for (const dy of [-1, 0, 1].map((value) => value * (stacked ? 22 : 14))) {
        for (const base of node.materialColors) {
          let reflected = base;
          rainbow.forEach((pool) => {
            const distance = Math.hypot(center[0] + dx - pool.x, center[1] + dy - pool.y);
            const radius = Math.min(1, distance / pool.radius);
            const opacity =
              radius < 0.42 ? 0.6 - (0.26 * radius) / 0.42 : (0.34 * (1 - radius)) / 0.58;
            reflected = mix(reflected, pool.channels, opacity);
          });
          const color = mix(base, reflected, amount);
          let samples = [color];
          if (node.finish && node.paintedFinish < 1) {
            const strength = 1 - node.paintedFinish;
            samples.push(mix(color, [248, 252, 255], 0.3 * strength));
            samples.push(mix(color, [101, 119, 137], 0.18 * strength));
          }
          if (node.paintedFinish > 0)
            samples = samples.flatMap((sample) => [
              sample,
              mix(sample, [218, 228, 255], 0.24 * node.paintedFinish),
              mix(sample, [8, 17, 31], 0.3 * node.paintedFinish),
            ]);
          backgrounds.push(...samples);
        }
      }
    }
    const candidates = [darkInk, black, white].map((ink) => ({
      ink,
      score: Math.min(...backgrounds.map((background) => contrast(ink, background))),
    }));
    const choice =
      candidates.find((candidate) => candidate.score >= 4.5) ||
      candidates.reduce((best, candidate) => (candidate.score > best.score ? candidate : best));
    const ink = choice.ink;
    [node.label, node.numeral, node.check].forEach((label) => {
      label.setAttribute('fill', rgb(ink));
      // A subpixel outline protects rare mid-fold contrast crossings without
      // removing any of the reflection underneath the caption.
      label.style.stroke = choice.score >= 4.5 ? 'none' : rgb(ink === white ? black : white);
      label.style.strokeWidth = '1.2px';
      label.style.paintOrder = 'stroke fill';
      label.style.strokeLinejoin = 'round';
    });
    node.ring.setAttribute('fill', rgb(ink === white ? black : white));
    node.ring.setAttribute('stroke', rgb(ink));
    node.score.setAttribute('stroke', rgb(ink));
  }

  function rotateX(point, angle) {
    const [x, y, z] = point;
    return [
      x,
      y * Math.cos(angle) - z * Math.sin(angle),
      y * Math.sin(angle) + z * Math.cos(angle),
    ];
  }

  function rotateY(point, angle) {
    const [x, y, z] = point;
    return [
      x * Math.cos(angle) + z * Math.sin(angle),
      y,
      -x * Math.sin(angle) + z * Math.cos(angle),
    ];
  }

  function geometry(folds) {
    const quarter = Math.PI / 2;
    const back = (x, distance) => {
      const point = rotateX([x, -distance, 0], -quarter * folds[2]);
      return [point[0], point[1] - 90, point[2]];
    };
    const left = (distance, y) => {
      const point = rotateY([-distance, y, 0], quarter * folds[1]);
      return [point[0] - 130, point[1], point[2]];
    };
    const right = (distance, y) => {
      const point = rotateY([distance, y, 0], -quarter * folds[3]);
      return [point[0] + 130, point[1], point[2]];
    };
    const front = (x, distance) => {
      const point = rotateX([x, distance, 0], quarter * folds[4]);
      return [point[0], point[1] + 90, point[2]];
    };
    const lid = (x, distance) => {
      const leaf = rotateX([x, -distance, 0], -quarter * folds[5]);
      const point = rotateX([leaf[0], leaf[1] - 65, leaf[2]], -quarter * folds[2]);
      return [point[0], point[1] - 90, point[2]];
    };
    return [
      [
        [-130, -90, 0],
        [130, -90, 0],
        [130, 90, 0],
        [-130, 90, 0],
      ],
      [left(0, -90), left(65, -90), left(65, 90), left(0, 90)],
      [back(-130, 0), back(130, 0), back(130, 65), back(-130, 65)],
      [right(0, -90), right(0, 90), right(65, 90), right(65, -90)],
      [front(-130, 0), front(130, 0), front(130, 65), front(-130, 65)],
      [lid(-130, 0), lid(130, 0), lid(130, 180), lid(-130, 180)],
    ];
  }

  function project(point) {
    const [x, y, z] = point;
    const horizontal = x * projection.cosAzimuth - y * projection.sinAzimuth;
    const along = x * projection.sinAzimuth + y * projection.cosAzimuth;
    return [
      horizontal,
      along * projection.cosElevation - z * projection.sinElevation,
      along * projection.sinElevation + z * projection.cosElevation,
    ];
  }

  function mount(scene, { faces = [], selected = 0 } = {}) {
    instances.get(scene)?.destroy();
    if (!scene) return { update() {}, destroy() {} };
    const id = `evidence-box-${++nextId}`;
    const svg = element('svg', {
      class: 'box-art',
      viewBox: '0 0 600 430',
      role: 'img',
      focusable: 'false',
      preserveAspectRatio: 'xMidYMid meet',
    });
    const defs = element('defs');
    const panels = element('g', { class: 'box-panels' });
    const shadow = element('ellipse', {
      cx: 300,
      cy: 332,
      rx: 150,
      ry: 13,
      fill: '#17212b',
      opacity: 0.025,
    });
    svg.append(defs, shadow, panels);
    const reflection = reflectionField(defs, id);
    const engravingFill = completionEngraving(defs, id);
    const nodes = palette.map((_, index) => {
      const gradient = element('radialGradient', {
        id: `${id}-face-${index}`,
        cx: `${[24, 72, 35, 62, 18, 78][index]}%`,
        cy: `${[22, 38, 72, 18, 68, 54][index]}%`,
        r: '92%',
        'color-interpolation': 'sRGB',
      });
      const stops = [0, 0.46, 1].map((offset) => element('stop', { offset }));
      gradient.append(...stops);
      const labelClip = element('clipPath', { id: `${id}-label-${index}` });
      const labelBounds = element('polygon');
      labelClip.append(labelBounds);
      defs.append(gradient, labelClip);
      const group = element('g', { class: 'box-panel', 'data-face': index, 'aria-hidden': 'true' });
      const surface = element('polygon', {
        fill: `url(#${id}-face-${index})`,
        stroke: '#475569',
        'stroke-opacity': 0.28,
        'stroke-width': 1,
        'stroke-linejoin': 'round',
      });
      const sheen = element('polygon', {
        fill: 'none',
        stroke: '#ffffff',
        'stroke-opacity': 0.48,
        'stroke-width': 0.6,
        'stroke-linejoin': 'round',
      });
      const score = element('path', {
        fill: 'none',
        stroke: '#344256',
        'stroke-width': 0.75,
        'stroke-opacity': 0.27,
        'stroke-dasharray': '3 4',
        'pointer-events': 'none',
      });
      const label = element('text', {
        class: 'box-panel-label',
        'text-anchor': 'middle',
        'dominant-baseline': 'central',
        fill: '#253244',
        'font-size': labelFontSize,
        'font-weight': 500,
        'letter-spacing': '-0.15',
        'pointer-events': 'none',
        'clip-path': `url(#${id}-label-${index})`,
      });
      const marker = element('g', {
        class: 'box-panel-step',
        'pointer-events': 'none',
        'clip-path': `url(#${id}-label-${index})`,
      });
      const ring = element('circle', {
        r: 9,
        fill: '#ffffff',
        'fill-opacity': 0.12,
        stroke: '#475569',
        'stroke-opacity': 0.23,
        'stroke-width': 0.65,
      });
      const numeral = element('text', {
        class: 'box-panel-label',
        'text-anchor': 'middle',
        'dominant-baseline': 'central',
        'font-size': 8,
        'font-weight': 400,
        fill: '#66717e',
      });
      const check = element('text', {
        class: 'box-panel-label',
        'text-anchor': 'middle',
        'dominant-baseline': 'central',
        'font-size': 8,
        fill: '#253244',
      });
      check.textContent = '✓';
      marker.append(ring, numeral, check);
      const iridescence = element('polygon', {
        class: 'box-iridescence',
        fill: reflection,
        'pointer-events': 'none',
      });
      const finish = index === 5 ? packageFinish(defs, id) : null;
      const engraving = element('polygon', {
        class: 'box-completion-engraving',
        fill: engravingFill,
        'pointer-events': 'none',
      });
      group.append(
        surface,
        iridescence,
        ...(finish ? [finish.group] : []),
        engraving,
        sheen,
        score,
        marker,
        label,
      );
      panels.append(group);
      return {
        group,
        surface,
        sheen,
        score,
        marker,
        ring,
        numeral,
        check,
        label,
        labelBounds,
        stops,
        finish,
        iridescence,
        engraving,
      };
    });
    scene.append(svg);
    let currentFaces = [];
    let currentSelected = selected;
    let targets = [0, 0, 0, 0, 0, 0];
    const folds = targets.slice();
    let active = null;
    let frame = 0;
    let destroyed = false;
    let panelOrder = '';
    const motion = window.matchMedia('(prefers-reduced-motion: reduce)');

    function readFaces(value) {
      return palette.map((_, index) => ({
        step: String(value[index]?.step || ['I', 'II', 'III', 'IV', 'V', 'VI'][index]),
        title: String(
          value[index]?.title ||
            ['Records', 'Sources', 'Plan', 'Findings', 'Assessment', 'Package'][index],
        ),
        complete: value[index]?.complete === true,
        available: value[index]?.available === true,
      }));
    }

    function setAppearance() {
      currentFaces.forEach((face, index) => {
        const node = nodes[index];
        node.group.setAttribute('data-complete', String(face.complete));
        node.group.setAttribute('data-selected', String(currentSelected === index));
        node.surface.setAttribute('stroke-width', currentSelected === index ? '1.6' : '0.9');
        node.surface.setAttribute('stroke-opacity', currentSelected === index ? '0.54' : '0.24');
        if (face.available || face.complete) {
          node.group.setAttribute('data-flow', 'cube');
          node.group.setAttribute('cursor', 'pointer');
        } else {
          node.group.removeAttribute('data-flow');
          node.group.removeAttribute('cursor');
        }
        node.numeral.textContent = face.step;
        node.check.setAttribute('opacity', face.complete ? 1 : 0);
        if (node.fullLabel !== face.title) {
          node.fullLabel = face.title;
          node.label.textContent = node.fullLabel;
          node.label.setAttribute('font-size', labelFontSize);
          node.labelWidth =
            node.label.getComputedTextLength?.() || node.fullLabel.length * labelFontSize * 0.54;
        }
      });
      svg.setAttribute(
        'aria-label',
        `Evidence box. Current step: ${currentFaces[currentSelected]?.title || 'Records'}. ${currentFaces.map((face) => `${face.step} ${face.title}: ${face.complete ? 'complete' : face.available ? 'ready' : 'not started'}`).join('. ')}.`,
      );
    }

    function render() {
      const world = geometry(folds);
      const projected = world.map((panel) => panel.map(project));
      const points = projected.flat();
      const minX = Math.min(...points.map((point) => point[0]));
      const maxX = Math.max(...points.map((point) => point[0]));
      const minY = Math.min(...points.map((point) => point[1]));
      const maxY = Math.max(...points.map((point) => point[1]));
      const scale = Math.min(1.16, 548 / (maxX - minX), 370 / (maxY - minY));
      const position = (point) => [
        300 + (point[0] - (minX + maxX) / 2) * scale,
        215 + (point[1] - (minY + maxY) / 2) * scale,
      ];
      const ordered = projected
        .map((panel, index) => ({
          index,
          depth: panel.reduce((sum, point) => sum + point[2], 0) / 4,
        }))
        .sort((left, right) => left.depth - right.depth);
      ordered.forEach(({ index }) => {
        const node = nodes[index];
        // Pigment follows the hinge, including reversals. Queued panels keep
        // their unfinished color until their own fold starts; the base has no hinge.
        const filled = index === 0 ? Number(currentFaces[index].complete) : folds[index];
        const finished = currentFaces[5].complete ? folds[5] : 0;
        const reflectionAmount = index === 5 ? 1 : finished;
        paintMaterial(node, index, filled, finished);
        const polygon = projected[index].map(position);
        const coordinates = polygon
          .map((point) => point.map((value) => value.toFixed(3)).join(','))
          .join(' ');
        node.surface.setAttribute('points', coordinates);
        node.iridescence.setAttribute('points', coordinates);
        node.engraving.setAttribute('points', coordinates);
        node.engraving.setAttribute('opacity', finished);
        node.finish?.group.setAttribute('opacity', 1 - finished);
        // VI carries the reflection before export. A verified package shares
        // that one field across every visible panel as its lid closes.
        node.iridescence.setAttribute('opacity', reflectionAmount);
        node.sheen.setAttribute('points', coordinates);
        node.labelBounds.setAttribute('points', coordinates);
        const center = polygon.reduce(
          (sum, point) => [sum[0] + point[0] / 4, sum[1] + point[1] / 4],
          [0, 0],
        );
        // Narrow folded walls show their step number. Full stage names remain
        // in the external controls, and no label can leak beyond its panel.
        const roomFor = (offsets) =>
          Math.min(
            ...offsets.map((offset) => {
              const y = center[1] + offset;
              const crossings = polygon.flatMap((point, edge) => {
                const next = polygon[(edge + 1) % 4];
                if (y < Math.min(point[1], next[1]) || y >= Math.max(point[1], next[1])) return [];
                return [point[0] + ((y - point[1]) * (next[0] - point[0])) / (next[1] - point[1])];
              });
              return crossings.length < 2
                ? 0
                : 2 *
                    Math.min(
                      center[0] - Math.min(...crossings),
                      Math.max(...crossings) - center[0],
                    );
            }),
          );
        const labelRoom = roomFor([-10, 10]);
        const inlineSize = Math.min(
          labelFontSize,
          (labelFontSize * Math.max(0, labelRoom - 32)) / node.labelWidth,
        );
        const stackedSize = Math.min(
          labelFontSize,
          (labelFontSize * Math.max(0, roomFor([-18, 18]) - 8)) / node.labelWidth,
        );
        const stacked = inlineSize < minimumLabelSize && stackedSize >= minimumLabelSize;
        const labelSize = stacked ? stackedSize : inlineSize;
        const showTitle = labelSize >= minimumLabelSize;
        const captionWidth =
          showTitle && !stacked ? 24 + (node.labelWidth * labelSize) / labelFontSize : 18;
        if (node.finish) {
          const [origin, along, , across] = polygon;
          const matrix = [
            (along[0] - origin[0]) / 260,
            (along[1] - origin[1]) / 260,
            (across[0] - origin[0]) / 180,
            (across[1] - origin[1]) / 180,
            ...origin,
          ];
          node.finish.plane.setAttribute('transform', `matrix(${matrix.join(' ')})`);
        }
        paintCaption(
          node,
          reflectionAmount,
          center,
          Math.max(captionWidth, (node.labelWidth * labelSize) / labelFontSize + 24),
          stacked,
        );
        const markerX = center[0] - captionWidth / 2 + 9;
        const markerY = center[1] - (stacked ? 9 : 0);
        node.label.textContent = showTitle ? node.fullLabel : '';
        node.label.setAttribute('font-size', showTitle ? labelSize : labelFontSize);
        node.ring.setAttribute('cx', markerX.toFixed(3));
        node.ring.setAttribute('cy', markerY.toFixed(3));
        node.numeral.setAttribute('x', markerX.toFixed(3));
        node.numeral.setAttribute('y', markerY.toFixed(3));
        node.check.setAttribute('x', (markerX + 8).toFixed(3));
        node.check.setAttribute('y', (markerY + 8).toFixed(3));
        const area =
          Math.abs(
            polygon.reduce((sum, point, offset) => {
              const next = polygon[(offset + 1) % 4];
              return sum + point[0] * next[1] - next[0] * point[1];
            }, 0),
          ) / 2;
        node.label.setAttribute('x', (center[0] + (stacked ? 0 : 12)).toFixed(3));
        node.label.setAttribute('y', (center[1] + (stacked ? 12 : 0)).toFixed(3));
        node.label.setAttribute('opacity', area > 850 ? '1' : '0');
        node.marker.setAttribute('opacity', area > 850 && labelRoom >= 22 ? '1' : '0');
        const hingeEnd = index === 1 ? 3 : 1;
        node.score.setAttribute(
          'd',
          index === 0 ? '' : `M${polygon[0].join(',')}L${polygon[hingeEnd].join(',')}`,
        );
        node.group.setAttribute(
          'data-fold-state',
          active?.index === index ? 'folding' : folds[index] > 0.999 ? 'folded' : 'flat',
        );
      });
      const nextOrder = ordered.map(({ index }) => index).join(',');
      if (nextOrder !== panelOrder) {
        ordered.forEach(({ index }) => panels.append(nodes[index].group));
        panelOrder = nextOrder;
      }
      shadow.setAttribute('cy', Math.min(411, 215 + ((maxY - minY) * scale) / 2 + 12));
      shadow.setAttribute('rx', Math.min(160, (maxX - minX) * scale * 0.31));
    }

    function nextFold() {
      for (let index = 5; index >= 1; index -= 1) {
        if (folds[index] > targets[index] + 0.0001) return index;
      }
      for (let index = 1; index <= 5; index += 1) {
        if (folds[index] < targets[index] - 0.0001) return index;
      }
      return -1;
    }

    function settle() {
      window.cancelAnimationFrame(frame);
      frame = 0;
      active = null;
      targets.forEach((target, index) => {
        folds[index] = target;
      });
      render();
    }

    function tick(now) {
      frame = 0;
      if (destroyed) return;
      if (motion.matches || document.hidden) {
        settle();
        return;
      }
      if (!active) {
        const index = nextFold();
        if (index < 0) {
          render();
          return;
        }
        active = { index, from: folds[index], to: targets[index], start: now };
      }
      const duration = 420 * Math.max(0.18, Math.abs(active.to - active.from));
      const progress = Math.min(1, (now - active.start) / duration);
      const eased = (1 - Math.cos(progress * Math.PI)) / 2;
      folds[active.index] = active.from + (active.to - active.from) * eased;
      if (progress === 1) {
        folds[active.index] = active.to;
        active = null;
      }
      render();
      if (active || nextFold() >= 0) frame = window.requestAnimationFrame(tick);
    }

    function update(nextFaces, nextSelected = currentSelected) {
      if (destroyed) return;
      const newFaces = readFaces(nextFaces);
      const newTargets = newFaces.map((face, index) => Number(index > 0 && face.complete));
      const changed = newTargets.some((target, index) => target !== targets[index]);
      currentFaces = newFaces;
      currentSelected = nextSelected;
      targets = newTargets;
      if (changed && active && (targets[active.index] !== active.to || nextFold() !== active.index))
        active = null;
      setAppearance();
      if (motion.matches || document.hidden) settle();
      else {
        render();
        if (!frame && (active || nextFold() >= 0)) frame = window.requestAnimationFrame(tick);
      }
    }

    function visibilityChanged() {
      if (document.hidden || motion.matches) settle();
    }

    function destroy() {
      if (destroyed) return;
      destroyed = true;
      window.cancelAnimationFrame(frame);
      frame = 0;
      motion.removeEventListener('change', visibilityChanged);
      document.removeEventListener('visibilitychange', visibilityChanged);
      svg.remove();
      if (instances.get(scene) === controller) instances.delete(scene);
    }

    const controller = { update, destroy };
    instances.set(scene, controller);
    currentFaces = readFaces(faces);
    targets = currentFaces.map((face, index) => Number(index > 0 && face.complete));
    targets.forEach((target, index) => {
      folds[index] = target;
    });
    setAppearance();
    render();
    motion.addEventListener('change', visibilityChanged);
    document.addEventListener('visibilitychange', visibilityChanged);
    return controller;
  }

  window.OmphalosBox = Object.freeze({ mount });
})();
