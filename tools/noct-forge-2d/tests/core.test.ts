import assert from 'node:assert/strict';
import {
  Point,
  Shape,
  Polygon,
  Path,
  Group,
  StrokeStyle,
  ShapeStyle,
  defineBrush,
  listBrushes,
  describeBrush,
  definePrimitive,
  listPrimitives,
  describePrimitive,
  loft,
  sweep,
  morph,
  extrude2D,
  mirror,
  revolve,
  attach,
  align,
  distribute,
  scatterAlong,
  type Transformable,
} from '../core/brush/index.js';

console.log('🧪 Starting NoctBrush Core & Ergonomics Test Suite...\n');

// ----------------------------------------------------
// 1. Defending Against Point Aliasing (Bug B1)
// ----------------------------------------------------
{
  const p1 = { x: 10, y: 10 };
  const p2 = { x: 50, y: 50 };
  const line = Path.line(p1, p2);
  line.translate(10, 10);
  assert.equal(p1.x, 10, 'Path.line must not mutate caller start point');
  assert.equal(p2.x, 50, 'Path.line must not mutate caller end point');
  assert.equal(line.points[0].x, 20, 'Path points must be properly translated');

  const pts = [{ x: 0, y: 0 }, { x: 20, y: 0 }, { x: 10, y: 20 }];
  const poly = Polygon.fromPoints(pts);
  poly.translate(5, 5);
  assert.equal(pts[0].x, 0, 'Polygon.fromPoints must not mutate input array');
  assert.equal(poly.toPoints()[0].x, 5, 'Polygon points must be translated');

  // toPoints immutability check
  const polyPts = poly.toPoints();
  polyPts[0].x = 999;
  assert.notEqual(poly.toPoints()[0].x, 999, 'Mutating toPoints() array must not alter Shape state');
  console.log('✔ Bug B1 (Aliasing Prevention) passed.');
}

// ----------------------------------------------------
// 2. Path Measurements & Slicing
// ----------------------------------------------------
{
  const p = Path.line({ x: 0, y: 0 }, { x: 100, y: 0 });
  assert.equal(p.length, 100, 'Path length must equal distance');

  const mid = p.pointAt(0.5);
  assert.equal(mid.x, 50, 'pointAt(0.5) must be midpoint');
  assert.equal(mid.y, 0);

  const tan = p.tangentAt(0.5);
  assert.equal(tan.x, 1);
  assert.equal(tan.y, 0);

  const norm = p.normalAt(0.5);
  assert.equal(norm.x, 0);
  assert.equal(norm.y, 1);

  const sliced = p.slice(0.2, 0.8);
  assert.equal(sliced.length, 60);
  assert.equal(sliced.points[0].x, 20);

  const resampled = p.resample(5);
  assert.equal(resampled.points.length, 5);
  assert.equal(resampled.points[2].x, 50);

  console.log('✔ Path measurements & slicing passed.');
}

// ----------------------------------------------------
// 3. Path -> Shape (toShape) & Shape -> Path (contours, outline)
// ----------------------------------------------------
{
  const line = Path.line({ x: 0, y: 10 }, { x: 100, y: 10 });
  const ribbon = line.toShape({ width: 10, cap: 'butt' });
  const bounds = ribbon.bounds;
  assert.equal(bounds.minX, 0);
  assert.equal(bounds.maxX, 100);
  assert.equal(bounds.height, 10);

  const rect = Polygon.rect(40, 20, { cx: 50, cy: 50 });
  const contours = rect.contours();
  assert.equal(contours.length, 1);
  assert.equal(contours[0].closed, true);

  const outlineShape = rect.outline({ width: 4, position: 'outside' });
  assert.ok(outlineShape.bounds.width > 40, 'Outline shape must expand outside');

  console.log('✔ Path toShape and Shape outline passed.');
}

// ----------------------------------------------------
// 4. Extensible Brushes (defineBrush, inheritance, params)
// ----------------------------------------------------
{
  const baseCalls: number[] = [];
  const myCustom = defineBrush({
    name: 'testBaseBrush',
    defaults: { width: 4, opacity: 0.8 },
    draw(line, params, base) {
      baseCalls.push(1);
    },
  });

  const myDerived = defineBrush({
    name: 'testDerivedBrush',
    extends: 'testBaseBrush',
    defaults: { width: 6, extraFactor: 2 },
    draw(line, params, base) {
      base();
      baseCalls.push(2);
    },
  });

  assert.ok(listBrushes().includes('testBaseBrush'));
  assert.ok(listBrushes().includes('testDerivedBrush'));

  const stroke = myDerived({ color: '#ff0000' });
  assert.equal(stroke.renderer, 'testDerivedBrush');

  // Deep merge test
  const modified = stroke.with({ width: 10 });
  assert.equal(modified.renderer, 'testDerivedBrush');
  assert.equal(modified.attrs.width, 10);
  assert.equal(modified.attrs.color, '#ff0000');

  // Test rendering simulation
  const dummyCtx = {} as CanvasRenderingContext2D;
  stroke.render(dummyCtx, [{ x: 0, y: 0 }, { x: 10, y: 10 }]);
  assert.deepEqual(baseCalls, [1, 2], 'Inherited brush must invoke parent base()');

  // ShapeStyle deep merge test (Bug B6)
  const baseShapeStyle = new ShapeStyle({
    fill: '#111111',
    stroke: new StrokeStyle({ width: 4, color: '#222222', renderer: 'clean' }),
    shadow: { color: '#000000', x: 2, y: 2 },
  });

  const derivedShapeStyle = baseShapeStyle.with({
    stroke: { width: 8 },
  });

  const derivedStrokeOpts = derivedShapeStyle.stroke instanceof StrokeStyle
    ? derivedShapeStyle.stroke.attrs
    : derivedShapeStyle.stroke!;
  assert.equal(derivedStrokeOpts.width, 8);
  assert.equal(derivedStrokeOpts.color, '#222222', 'ShapeStyle.with must preserve base stroke color');
  assert.equal(derivedStrokeOpts.renderer, 'clean', 'ShapeStyle.with must preserve base stroke renderer');

  console.log('✔ Extensible Brush system and deep merge passed.');
}

// ----------------------------------------------------
// 5. Parametric Primitives (definePrimitive)
// ----------------------------------------------------
{
  const cross = definePrimitive('cross', (p: { size: number; thickness: number }) => {
    const s = p.size / 2;
    const t = p.thickness / 2;
    return [
      { x: -t, y: -s }, { x: t, y: -s }, { x: t, y: -t },
      { x: s, y: -t }, { x: s, y: t }, { x: t, y: t },
      { x: t, y: s }, { x: -t, y: s }, { x: -t, y: t },
      { x: -s, y: t }, { x: -s, y: -t }, { x: -t, y: -t },
    ];
  });

  const shape = cross({ size: 40, thickness: 10 }, { cx: 100, cy: 100, rotation: 45 });
  assert.equal(shape.center.x, 100);
  assert.equal(shape.center.y, 100);
  console.log('✔ definePrimitive passed.');
}

// ----------------------------------------------------
// 6. Modeling Operations (loft, morph, place)
// ----------------------------------------------------
{
  const c1 = Path.line({ x: 0, y: 0 }, { x: 50, y: 0 });
  const c2 = Path.line({ x: 0, y: 20 }, { x: 50, y: 20 });
  const surface = loft(c1, c2, { steps: 10 });
  assert.equal(surface.bounds.height, 20);

  const polyA = Polygon.rect(20, 20, { cx: 0, cy: 0 });
  const polyB = Polygon.circle(10, { cx: 0, cy: 0 });
  const blended = morph(polyA, polyB, 0.5);
  assert.ok(blended.toPoints().length > 10);

  // Attachment and alignment
  const b1 = Polygon.rect(40, 40, { cx: 50, cy: 50 });
  const b2 = Polygon.circle(10, { cx: 0, cy: 0 });
  attach(b2, b1, { from: 'bottom', at: 'top' });
  assert.equal(b2.bounds.maxY, b1.bounds.minY);

  const row = [Polygon.rect(10, 10), Polygon.rect(10, 20), Polygon.rect(10, 30)];
  align(row, 'centerY');
  assert.equal(row[0].center.y, row[1].center.y);
  assert.equal(row[1].center.y, row[2].center.y);

  distribute(row, 'x', { gap: 5 });
  assert.equal(row[1].bounds.minX, row[0].bounds.maxX + 5);
  assert.equal(row[2].bounds.minX, row[1].bounds.maxX + 5);

  console.log('✔ Modeling (loft, morph, place, align) passed.');
}

// ----------------------------------------------------
// 7. Group Hierarchy and Operations
// ----------------------------------------------------
{
  const s1 = Polygon.rect(20, 20, { cx: 10, cy: 10 });
  const p1 = Path.line({ x: 30, y: 10 }, { x: 50, y: 10 });
  const grp = new Group([s1, p1]);

  assert.equal(grp.bounds.minX, 0);
  assert.equal(grp.bounds.maxX, 50);

  grp.translate(10, 5);
  assert.equal(grp.bounds.minX, 10);
  assert.equal(grp.bounds.maxX, 60);

  const flattened = grp.flatten();
  assert.equal(flattened.length, 2);

  console.log('✔ Group hierarchy passed.');
}

// ----------------------------------------------------
// 8. Bidirectional Line ↔ Shape CSG (unionLine & cutLine)
// ----------------------------------------------------
{
  const base = Polygon.rect(60, 60, { cx: 50, cy: 50 });
  const cutPath = Path.line({ x: 20, y: 50 }, { x: 80, y: 50 });

  // Cut base shape with line
  const sliced = base.cutLine(cutPath, 6);
  assert.ok(sliced.regions.length >= 2 || sliced.bounds.height < 60, 'cutLine must split or reduce shape');

  // Unite an ear/spike line with base shape
  const hornPath = Path.line({ x: 50, y: 20 }, { x: 50, y: 0 });
  const withHorn = base.unionLine(hornPath, 8);
  assert.equal(withHorn.bounds.minY, 0, 'unionLine must expand the shape boundary to the tip of the line');

  console.log('✔ Bidirectional Line ↔ Shape CSG (unionLine & cutLine) passed.');
}

// ----------------------------------------------------
// 9. Boolean CSG with Direct Path Inputs
// ----------------------------------------------------
{
  const square = Polygon.rect(40, 40, { cx: 50, cy: 50 });
  const crossLine = Path.line({ x: 30, y: 50 }, { x: 70, y: 50 });

  const cutResult = square.subtract(crossLine, 4);
  assert.ok(cutResult.bounds.width >= 40);

  const united = square.union(crossLine, 10);
  assert.ok(united.bounds.width >= 40);

  console.log('✔ Boolean CSG with direct Path inputs passed.');
}

// ----------------------------------------------------
// 10. 2.5D Pseudo-3D Extrusion (extrude2D)
// ----------------------------------------------------
{
  const plate = Polygon.rect(40, 20, { cx: 50, cy: 50 });
  const extrusion = extrude2D(plate, { depth: 10, angle: 90 });

  assert.ok(extrusion.front, 'Must have front face');
  assert.ok(extrusion.sides, 'Must have sides');
  assert.ok(extrusion.all, 'Must have united silhouette');
  assert.equal(extrusion.all.bounds.maxY, plate.bounds.maxY + 10, 'Extrusion must extend downward by depth');
  assert.ok(typeof extrusion.draw === 'function', 'Must have draw helper');

  // Test bevel option
  const beveled = extrude2D(plate, { depth: 6, angle: 45, bevel: 2 });
  assert.ok(beveled.front.bounds.width < plate.bounds.width, 'Front face must be inset by bevel');

  console.log('✔ 2.5D Pseudo-3D Extrusion (extrude2D) passed.');
}

// ----------------------------------------------------
// 11. StrokeStyle<P> Generic Typed Custom Parameters
// ----------------------------------------------------
{
  interface NeonParams {
    glowIntensity: number;
    flicker: boolean;
  }

  const neonBrush = defineBrush<NeonParams>({
    name: 'neonGlow',
    extends: 'ribbon',
    defaults: { width: 3, glowIntensity: 5, flicker: false },
    draw({ ctx, points }, params, base) {
      base();
    },
  });

  const baseNeon = neonBrush({ glowIntensity: 10, color: '#00ffcc' });
  assert.equal(baseNeon.attrs.glowIntensity, 10);
  assert.equal(baseNeon.attrs.flicker, false);

  // Deriving with .with() preserves custom params and allows typed overrides
  const updatedNeon = baseNeon.with({ glowIntensity: 20 });
  assert.equal(updatedNeon.attrs.glowIntensity, 20);
  assert.equal(updatedNeon.attrs.flicker, false);
  assert.equal(updatedNeon.attrs.color, '#00ffcc');

  console.log('✔ StrokeStyle<P> typed custom parameters & derivation passed.');
}

// ----------------------------------------------------
// 12. BoundingBox Aliases & Path.toRibbon
// ----------------------------------------------------
{
  const rect = Polygon.rect(100, 50, { cx: 50, cy: 50 });
  const b = rect.bounds;
  assert.equal(b.left, b.minX);
  assert.equal(b.right, b.maxX);
  assert.equal(b.top, b.minY);
  assert.equal(b.bottom, b.maxY);

  const curve = Path.curve({ x: 0, y: 0 }, { x: 100, y: 0 }, 20);
  const ribbon1 = curve.toShape({ width: 10 });
  const ribbon2 = curve.toRibbon({ width: 10 });
  assert.equal(Math.round(ribbon1.bounds.width), Math.round(ribbon2.bounds.width));
  assert.equal(Math.round(ribbon1.bounds.height), Math.round(ribbon2.bounds.height));
  console.log('✔ BoundingBox aliases (left/right/top/bottom) & Path.toRibbon passed.');
}

// ----------------------------------------------------
// 13. Custom Named Anchors on Shape, Path and Group
// ----------------------------------------------------
{
  const sword = Polygon.rect(20, 100, { cx: 50, cy: 50 });
  sword.setAnchor('hilt', { x: 50, y: 90 });
  sword.setAnchor('tip', { x: 50, y: 0 });
  assert.deepEqual(sword.anchor('hilt'), { x: 50, y: 90 });
  assert.deepEqual(sword.anchor('tip'), { x: 50, y: 0 });

  // Custom anchors translate with the shape
  sword.translate(10, 20);
  assert.deepEqual(sword.anchor('hilt'), { x: 60, y: 110 });

  // Custom anchors work with moveTo
  const pommel = Polygon.circle(10, { cx: 0, cy: 0 });
  attach(pommel, sword, { from: 'center', at: 'hilt' });
  assert.deepEqual(pommel.center, { x: 60, y: 110 });

  // Path custom anchors (including arc-length fraction t)
  const arc = Path.curve({ x: 0, y: 0 }, { x: 100, y: 0 }, 30);
  arc.setAnchor('peak', 0.5);
  const peakPt = arc.anchor('peak');
  assert.equal(Math.round(peakPt.x), 50);

  // Group custom anchors
  const grp = new Group([sword, pommel]);
  grp.setAnchor('mount', { x: 100, y: 100 });
  grp.translate(5, 5);
  assert.deepEqual(grp.anchor('mount'), { x: 105, y: 105 });

  console.log('✔ Custom named anchors & placeable integration passed.');
}

// ----------------------------------------------------
// 14. Mirror & Flip (Shape & Path)
// ----------------------------------------------------
{
  const leftBladeHalf = Polygon.fromPoints([
    { x: 50, y: 10 },
    { x: 30, y: 60 },
    { x: 50, y: 90 },
  ]);
  const fullBlade = mirror(leftBladeHalf, { axis: 'x', side: 'max' });
  assert.equal(Math.round(fullBlade.bounds.center.x), 50);
  assert.ok(fullBlade.bounds.width >= 39, 'Full blade must be doubled across center');

  // Path mirror & close
  const halfContour = Path.line({ x: 50, y: 10 }, { x: 20, y: 50 });
  const fullContour = mirror(halfContour, { axis: 'x', side: 'max', close: true });
  assert.equal(fullContour.closed, true);
  assert.equal(fullContour.points.length, 3, 'Closing a mirrored line creates a 3-vertex triangle without duplicate endpoints');

  // In-place / pure flip
  const flipped = leftBladeHalf.flip('x', 50);
  assert.equal(Math.round(flipped.bounds.minX), 50);
  console.log('✔ Symmetry (mirror, flip) on Shape & Path passed.');
}

// ----------------------------------------------------
// 15. 2D Lathe / Revolve
// ----------------------------------------------------
{
  const vaseProfile = Path.builder({ x: 60, y: 20 })
    .curveTo({ x: 80, y: 60 }, 15)
    .curveTo({ x: 65, y: 100 }, -10)
    .build();

  const vase = revolve(vaseProfile, { axis: 'x', at: 50 });
  assert.ok(vase.bounds.width >= 58);
  assert.equal(Math.round(vase.bounds.center.x), 50);
  console.log('✔ 2D Lathe / Revolve passed.');
}

// ----------------------------------------------------
// 16. Multi-section Loft
// ----------------------------------------------------
{
  const rim = Path.line({ x: 40, y: 20 }, { x: 80, y: 20 });
  const belly = Path.line({ x: 20, y: 60 }, { x: 100, y: 60 });
  const base = Path.line({ x: 45, y: 100 }, { x: 75, y: 100 });

  const vase = loft([rim, belly, base], { smooth: true, steps: 16 });
  assert.ok(vase instanceof Polygon);
  assert.equal(Math.round(vase.bounds.minY), 20);
  assert.equal(Math.round(vase.bounds.maxY), 100);
  assert.ok(vase.bounds.width >= 55);
  console.log('✔ Multi-section Loft (N sections + smooth) passed.');
}

// ----------------------------------------------------
// 17. ScatterAlong
// ----------------------------------------------------
{
  const spine = Path.curve({ x: 10, y: 50 }, { x: 110, y: 50 }, 30);
  const thorn = Polygon.triangle(8, 16);

  const thorns = scatterAlong(spine, thorn, {
    count: 5,
    align: true,
    offset: 4,
    scale: (t) => 0.5 + 0.5 * Math.sin(t * Math.PI),
  });

  assert.equal(thorns.length, 5);
  for (const t of thorns) {
    assert.ok(t instanceof Polygon);
  }
  console.log('✔ scatterAlong (procedural placement along path) passed.');
}

// ----------------------------------------------------
// 18. Non-Destructive Deformations (warp, twist, inflate)
// ----------------------------------------------------
{
  const block = Polygon.rect(60, 60, { cx: 50, cy: 50 });

  // Warp
  const warped = block.warp((p, uv) => ({ x: p.x + uv.y * 10, y: p.y }));
  assert.notEqual(warped.bounds.maxX, block.bounds.maxX);

  // Twist
  const twisted = block.twist({ angle: 45, axis: 'y' });
  assert.ok(twisted.toPoints().length > block.toPoints().length, 'Twist should densify vertices');

  // Inflate (swell / pinch)
  const swollen = block.inflate({ amount: 12, center: { x: 50, y: 50 }, radius: 40 });
  assert.ok(swollen.bounds.width > block.bounds.width, 'Inflate should expand perimeter');

  console.log('✔ Deformations (warp, twist, inflate) passed.');
}

// ----------------------------------------------------
// 19. Dashed Brush & Geometry Hook
// ----------------------------------------------------
{
  assert.ok(listBrushes().includes('dashed'));
  const desc = describeBrush('dashed');
  assert.equal(desc.reshapesLine, true);
  assert.ok(desc.params.some(p => p.name === 'dash'));
  assert.ok(desc.params.some(p => p.name === 'gap'));
  console.log('✔ Dashed brush & geometry hook passed.');
}

// ----------------------------------------------------
// 20. Declarative Primitives & Introspection
// ----------------------------------------------------
{
  const diamond = definePrimitive({
    name: 'testGem',
    doc: 'Parametric faceted gem crystal with bevel facets',
    params: {
      width: { default: 40, doc: 'Gem width in pixels' },
      height: { default: 60, doc: 'Gem height in pixels' },
    },
    generate: (p) => [
      { x: 0, y: -p.height / 2 },
      { x: p.width / 2, y: 0 },
      { x: 0, y: p.height / 2 },
      { x: -p.width / 2, y: 0 },
    ],
  });

  const gem = diamond({ width: 50, height: 80 }, { cx: 100, cy: 100 });
  assert.equal(gem.bounds.width, 50);
  assert.equal(gem.bounds.height, 80);
  assert.equal(gem.bounds.center.x, 100);
  assert.equal(gem.bounds.center.y, 100);

  assert.ok(listPrimitives().includes('testGem'));
  const desc = describePrimitive('testGem');
  assert.equal(desc.doc, 'Parametric faceted gem crystal with bevel facets');
  assert.ok(desc.params.some(p => p.name === 'width'));
  console.log('✔ Declarative Primitives, specs & describePrimitive passed.');
}

// ----------------------------------------------------
// 21. Ergonomics: Array Booleans, PathBuilder toShape & StrokeStyle in unionLine
// ----------------------------------------------------
{
  // PathBuilder.toShape directly
  const ribbonShape = Path.builder({ x: 0, y: 10 })
    .curveTo({ x: 100, y: 10 }, 20)
    .toShape({ width: 12 });
  assert.ok(ribbonShape instanceof Shape);
  assert.ok(ribbonShape.bounds.width >= 99);

  // path.toShape with scalar width and StrokeStyle
  const line = Path.line({ x: 0, y: 0 }, { x: 50, y: 0 });
  const scalarShape = line.toShape(6);
  assert.equal(Math.round(scalarShape.bounds.height), 6);

  const stroke = new StrokeStyle({ width: 8 });
  const strokeShape = line.toShape(stroke);
  assert.equal(Math.round(strokeShape.bounds.height), 8);

  // Array union on a shape: shape.union([s2, s3])
  const s1 = Polygon.rect(20, 20, { cx: 10, cy: 10 });
  const s2 = Polygon.rect(20, 20, { cx: 25, cy: 10 });
  const s3 = Polygon.rect(20, 20, { cx: 40, cy: 10 });
  const chained = s1.union([s2, s3]);
  assert.ok(chained.bounds.width >= 49);

  // Array subtract: shape.subtract([cut1, cut2])
  const baseBox = Polygon.rect(60, 60, { cx: 50, cy: 50 });
  const cut1 = Polygon.rect(10, 10, { cx: 30, cy: 50 });
  const cut2 = Polygon.rect(10, 10, { cx: 70, cy: 50 });
  const punched = baseBox.subtract([cut1, cut2]);
  assert.ok(punched.regions.length >= 1);

  // unionLine & cutLine with StrokeStyle
  const seamPath = Path.line({ x: 50, y: 10 }, { x: 50, y: 90 });
  const welded = baseBox.unionLine(seamPath, stroke);
  assert.ok(welded instanceof Shape);

  const sliced = baseBox.cutLine(seamPath, stroke);
  assert.ok(sliced instanceof Shape);

  console.log('✔ Array Booleans, PathBuilder toShape & StrokeStyle in unionLine passed.');
}

// ----------------------------------------------------
// 22. Side convention: a positive bow (and a positive offset) moves along normalAt,
// which is the right-hand side of the direction of travel on screen (y grows downward).
{
  const curve = Path.curve({ x: 0, y: 0 }, { x: 100, y: 0 }, 10);
  const apex = curve.pointAt(0.5);
  assert.ok(Math.abs(apex.x - 50) < 0.5, `apex x must be 50, got ${apex.x}`);
  assert.ok(Math.abs(apex.y - 10) < 0.5, `positive bow must bulge to y=+10, got ${apex.y}`);

  const chord = Path.line({ x: 0, y: 0 }, { x: 100, y: 0 });
  const normal = chord.normalAt(0.5);
  assert.ok(Math.abs(normal.x) < 1e-9 && Math.abs(normal.y - 1) < 1e-9, 'normalAt on a rightward line must be (0, 1)');

  console.log('✔ Path side convention (bow and normalAt) passed.');
}

// ----------------------------------------------------
// 23. Transformable: one generic helper moves Shape, Path and Group alike.
{
  const nudge = <T extends Transformable>(item: T): T => item.translate(10, 0);

  const shape = nudge(Polygon.rect(10, 10, { cx: 0, cy: 0 }));
  const path = nudge(Path.line({ x: 0, y: 0 }, { x: 10, y: 0 }));
  const group = nudge(new Group([Polygon.rect(4, 4, { cx: 0, cy: 0 })]));

  assert.ok(Math.abs(shape.center.x - 10) < 1e-6, 'Shape must accept Transformable helpers');
  assert.ok(Math.abs(path.center.x - 15) < 1e-6, 'Path must accept Transformable helpers');
  assert.ok(Math.abs(group.center.x - 10) < 1e-6, 'Group must accept Transformable helpers');

  console.log('✔ Transformable surface (Shape, Path, Group) passed.');
}

// ----------------------------------------------------
// 24. Pivots: the rotation option turns free points around the origin; rotate(deg, pivot) turns a part in place.
{
  const base = { x: 100, y: 200 };

  const byOption = Polygon.stem(base, 40, { rotation: 180 });
  assert.ok(byOption.bounds.y < 0, 'rotation option must pivot on the origin (the stem leaves the canvas)');

  const inPlace = Polygon.stem(base, 40).rotate(180, base);
  assert.ok(Math.abs(inPlace.bounds.y - 200) < 1e-6, `rotate(180, base) must keep the stem at its base, got y=${inPlace.bounds.y}`);
  assert.ok(Math.abs(inPlace.bounds.y + inPlace.bounds.height - 240) < 1e-6, 'the turned stem must hang down from the base');

  console.log('✔ Pivot semantics (rotation option vs rotate with pivot) passed.');
}

console.log('\n🎉 ALL CORE & ERGONOMICS TESTS PASSED SUCCESSFULLY!\n');
